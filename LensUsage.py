from datetime import datetime, timedelta
from os import environ, path

import requests
import json

import logging
from logging.handlers import RotatingFileHandler

IMMICH_API_KEY_ENVIRONMENT_VARIABLE = "LENS_USAGE_IMMICH_API_KEY"
IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE = "LENS_USAGE_IMMICH_SERVER"
IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE = "LENS_USAGE_IMMICH_LIBRARIES_NAMES"
IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE = "LENS_USAGE_IMMICH_LIBRARIES_OWNER"
IMMICH_ALBUMS_ENVIRONMENT_VARIABLE = "LENS_USAGE_IMMICH_ALBUMS"

LOG_FILE_ENVIRONMENT_VARIABLE = "LENS_USAGE_LOG_FILE"
LOG_LEVEL_ENVIRONMENT_VARIABLE = "LENS_USAGE_LOG_LEVEL"

IMMICH_LIBRARIES_DELIMITER = ";"
LIBRARY_FEATURES = ["name", "id"]

IMMICH_ALBUMS_DELIMITER = ";"
ALBUM_FEATURES = ["albumName", "id"]

if __name__ == "__main__":
    def extract_environment_variable(variable, variable_descriptor, optional=False):
        extracted_value = environ.get(key=variable, default=None)
        if not extracted_value and not optional:
            raise ValueError(
                f"No {variable_descriptor} found in environment variable {variable}"
            )
        return extracted_value

    immich_server_address = extract_environment_variable(IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE, "address of Immich server.") + "/api/"
    immich_api_key = extract_environment_variable(IMMICH_API_KEY_ENVIRONMENT_VARIABLE, "API key.")
    
    immich_libraries = extract_environment_variable(IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE, f'\"{IMMICH_LIBRARIES_DELIMITER}\" separated names of libraries.', optional=True)
    if immich_libraries:
        immich_libraries = immich_libraries.split(sep=IMMICH_LIBRARIES_DELIMITER)
        immich_libraries = [library_name.strip() for library_name in immich_libraries]
        immich_libraries_owner_key = extract_environment_variable(IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE, f'\"{IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE}\" API key of owner of given libraries.')

    immich_albums = extract_environment_variable(IMMICH_ALBUMS_ENVIRONMENT_VARIABLE, f'\"{IMMICH_ALBUMS_DELIMITER}\" separated names of albums.', optional=True)
    if immich_albums:
        immich_albums = immich_albums.split(sep=IMMICH_ALBUMS_DELIMITER)
        immich_albums = [album_name.strip() for album_name in immich_albums]

    ###############################################
    # Define header with API key and json replies #
    ###############################################
    HEADERS = {"X-API-Key": immich_api_key, "Content-Type": "application/json"}

    ###################################################
    # Query Immich server for libraries and/or albums #
    ###################################################

    def immich_get_all_objects(endpoint, feature_list, feature_filter, name_key):
        # get all objects at endpoint
        response = requests.get(url=(immich_server_address + endpoint), headers=HEADERS)
        response.raise_for_status()

        # extract json and filter
        response = response.json()
        # filter response for relevant features
        response = [{feature: obj.get(feature, None) for feature in feature_list} for obj in response]
        # filter response for relevant objects, if any
        if not feature_filter == "":
            response = [obj for obj in response if obj[name_key] in feature_filter]
        return [obj["id"] for obj in response]
    
    library_ids = []
    if immich_libraries is not None:
        library_ids = immich_get_all_objects(endpoint="libraries", feature_list=LIBRARY_FEATURES, feature_filter=immich_libraries, name_key="name")
    
    album_ids = []
    if immich_albums is not None:
        album_ids = immich_get_all_objects(endpoint="albums", feature_list=ALBUM_FEATURES, feature_filter=immich_albums, name_key="albumName")

    #####################################################
    # Search assets for retreived album and library IDs #
    #####################################################

    def getAssetsForIDs(json_key, search_ids, response_size=100):
        asset_ids = []
        asset_search_header = dict(HEADERS)
        for search_id in search_ids:
            if json_key == "albumIds":
                # albumIds only work as single value lists
                payload = { json_key: [search_id], "size": response_size}
            else:
                payload = { json_key: search_id, "size": response_size }
                asset_search_header["X-API-Key"] = immich_libraries_owner_key
            search_response = requests.post(url=(immich_server_address + "search/metadata"), json=payload, headers=asset_search_header)
            asset_response = search_response.json()["assets"]
            iterate_over_pages = True
            while iterate_over_pages:
                asset_ids = asset_ids + [asset["id"] for asset in asset_response["items"]]
                next_page = asset_response["nextPage"]
                if next_page is None:
                    iterate_over_pages = False
                else:
                    # get next page of assets
                    payload["page"] = next_page # maybe just "page"
                    search_response = requests.post(url=(immich_server_address + "search/metadata"), json=payload, headers=HEADERS)
                    asset_response = search_response.json()["assets"]


        return set(asset_ids)
