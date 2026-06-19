from datetime import datetime, timedelta
from os import environ, path

import requests
import json

import logging

from tqdm import tqdm

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

ASSET_METADATA_KEY = "exifInfo"
ASSET_METADATA_FOCAL_LENGTH_KEY = "focalLength"
ASSET_METADATA_LENS_MODEL_KEY = "lensModel"
ASSET_METADATA_CAMERA_MAKE_KEY = "make"

SEARCH_RESPONSE_SIZE=100
LOG_LEVEL = logging.INFO

from enum import Enum

class ImageSource(Enum):
    LIBRARIES = 1
    ALBUMS = 2

if __name__ == "__main__":
    def extract_environment_variable(variable, variable_descriptor, optional=False):
        extracted_value = environ.get(key=variable, default=None)
        if not extracted_value and not optional:
            raise ValueError(
                f"No {variable_descriptor} found in environment variable {variable}"
            )
        return extracted_value

    #################
    # Set up logger #
    #################
    logger = logging.getLogger(__name__)
    logger.setLevel(LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setLevel(LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("Start reading environment variales...")

    immich_server_address = extract_environment_variable(IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE, "address of Immich server.").strip("/")
    logger.debug(f'Extracted values of environment variable {IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE} as {immich_server_address}.')
    immich_api_key = extract_environment_variable(IMMICH_API_KEY_ENVIRONMENT_VARIABLE, "API key.")
    
    immich_libraries = extract_environment_variable(IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE, f'\"{IMMICH_LIBRARIES_DELIMITER}\" separated names of libraries.', optional=True)
    if immich_libraries:
        immich_libraries = immich_libraries.split(sep=IMMICH_LIBRARIES_DELIMITER)
        immich_libraries = [library_name.strip() for library_name in immich_libraries]
        logger.debug(f'Extracted values of environment variable {IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE} as {immich_libraries}.')
        immich_libraries_owner_key = extract_environment_variable(IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE, f'\"{IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE}\" API key of owner of given libraries.')
        logger.debug(f'Extracted values of environment variable {IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE}.')

    immich_albums = extract_environment_variable(IMMICH_ALBUMS_ENVIRONMENT_VARIABLE, f'\"{IMMICH_ALBUMS_DELIMITER}\" separated names of albums.', optional=True)
    if immich_albums:
        immich_albums = immich_albums.split(sep=IMMICH_ALBUMS_DELIMITER)
        immich_albums = [album_name.strip() for album_name in immich_albums]
        logger.debug(f'Extracted values of environment variable {IMMICH_ALBUMS_ENVIRONMENT_VARIABLE} as {immich_albums}.')
    
    if not ((immich_albums is not None) ^ (immich_libraries is not None)):
        raise ValueError(f'Either both or none of the following variables have been set: {IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE}, {IMMICH_ALBUMS_ENVIRONMENT_VARIABLE}')

    if immich_albums is not None:
        IMAGE_SOURCE = ImageSource.ALBUMS
    elif immich_libraries is not None:
        IMAGE_SOURCE = ImageSource.LIBRARIES
    
    logger.debug(f'IMAGE_SOURCE set to {IMAGE_SOURCE.name}')

    logger.info("Done reading environment variales!")

    ###############################################
    # Define header with API key and json replies #
    ###############################################
    HEADERS = {"X-API-Key": immich_api_key, "Content-Type": "application/json"}

    ###################################################
    # Query Immich server for libraries and/or albums #
    ###################################################

    def immich_get_all_objects(endpoint, feature_list, feature_filter, name_key):
        # get all objects at endpoint
        response = requests.get(url=f'{immich_server_address}/api/{endpoint}', headers=HEADERS)
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
    if IMAGE_SOURCE == ImageSource.LIBRARIES:
        logger.info("Getting all library ids for libraries...")
        library_ids = immich_get_all_objects(endpoint="libraries", feature_list=LIBRARY_FEATURES, feature_filter=immich_libraries, name_key="name")
        logger.debug(f'Got library ids: {library_ids}.')
    
    album_ids = []
    if IMAGE_SOURCE == ImageSource.ALBUMS:
        logger.info("Getting all album ids for albums...")
        album_ids = immich_get_all_objects(endpoint="albums", feature_list=ALBUM_FEATURES, feature_filter=immich_albums, name_key="albumName")
        logger.debug(f'Got album ids: {album_ids}.')

    #####################################################
    # Search assets for retreived album and library IDs #
    #####################################################

    def getAssetsForIDs(json_key, search_ids):
        asset_ids = []
        asset_search_header = dict(HEADERS)
        for search_id in search_ids:
            logger.debug(f'Getting assets for id {search_id}...')
            if IMAGE_SOURCE == ImageSource.ALBUMS:
                # albumIds only work as single value lists
                payload = { json_key: [search_id], "size": SEARCH_RESPONSE_SIZE }
            elif IMAGE_SOURCE == ImageSource.LIBRARIES:
                payload = { json_key: search_id, "size": SEARCH_RESPONSE_SIZE }
                asset_search_header["X-API-Key"] = immich_libraries_owner_key
            else:
                raise ValueError("Unexpected IMAGE_SOURCE!")
            search_response = requests.post(url=f'{immich_server_address}/api/search/metadata', json=payload, headers=asset_search_header)
            search_response.raise_for_status()
            asset_response = search_response.json()["assets"]
            logger.debug(f'Got a total of {asset_response["total"]} assets.')
            iterate_over_pages = True
            while iterate_over_pages:
                logger.debug(f'This request contained {asset_response["count"]} assets.')
                asset_ids = asset_ids + [asset["id"] for asset in asset_response["items"] if asset["hasMetadata"] and asset["type"] == "IMAGE"]
                next_page = asset_response["nextPage"]
                if next_page is None:
                    iterate_over_pages = False
                else:
                    # get next page of assets
                    payload["page"] = next_page # maybe just "page"
                    search_response = requests.post(url=f'{immich_server_address}/api/search/metadata', json=payload, headers=asset_search_header)
                    asset_response = search_response.json()["assets"]

        return set(asset_ids)

    if IMAGE_SOURCE == ImageSource.ALBUMS:
        logger.info("Getting all assets for album ids...")
        asset_ids = getAssetsForIDs(json_key="albumIds", search_ids=album_ids)
        asset_headers = HEADERS
    elif IMAGE_SOURCE == ImageSource.LIBRARIES:
        logger.info("Getting all assets for library ids...")
        asset_ids = getAssetsForIDs(json_key="libraryId", search_ids=library_ids)
        asset_headers = {"X-API-Key": immich_libraries_owner_key, "Content-Type": "application/json"}

    ##############################
    # Get metadata for asset ids #
    ##############################

    lens_metadata = {}
    for i, asset_id in tqdm(enumerate(asset_ids), desc="Processing assets", total=len(asset_ids)):
        asset_response = requests.get(url=f'{immich_server_address}/api/assets/{asset_id}', headers=asset_headers)
        asset_response.raise_for_status()
        asset_response = asset_response.json()
        if asset_response["stack"] and asset_id != asset_response["stack"]["primaryAssetId"]:
            # skip stacked non-primary images to avoid counting multiple times
            logger.debug(f'Dropped asset {asset_id} because it is not the primary asset in stack.')
            continue
        else:
            camera_make = asset_response[ASSET_METADATA_KEY][ASSET_METADATA_CAMERA_MAKE_KEY]
            lens_model = asset_response[ASSET_METADATA_KEY][ASSET_METADATA_LENS_MODEL_KEY]
            focal_length = asset_response[ASSET_METADATA_KEY][ASSET_METADATA_FOCAL_LENGTH_KEY]
            if not lens_model or not focal_length or focal_length == 0:
                # ignore entries with no lens mdoel or focal length (i.e. adapted lenses)
                logger.debug(f'Dropped asset {asset_id} with lens model {lens_model} and focal length {focal_length}.')
                continue
            else:
                lenses_for_camera = lens_metadata.get(camera_make, {})
                focal_lengths = lenses_for_camera.get(lens_model, [])
                focal_lengths.append(focal_length)
                lenses_for_camera[lens_model] = focal_lengths
                lens_metadata[camera_make] = lenses_for_camera
                logger.debug(f'Added focal length {focal_length} for lens {lens_model} and camera {camera_make}.')

    
    print(lens_metadata)

    # TODO plot metadata

