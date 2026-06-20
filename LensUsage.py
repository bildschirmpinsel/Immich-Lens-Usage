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

LOG_LEVEL_ENVIRONMENT_VARIABLE = "LENS_USAGE_LOG_LEVEL"

IMMICH_LIBRARIES_DELIMITER = ";"
LIBRARY_FEATURES = ["name", "id"]

IMMICH_ALBUMS_DELIMITER = ";"
ALBUM_FEATURES = ["albumName", "id"]

ASSET_METADATA_KEY = "exifInfo"
ASSET_METADATA_FOCAL_LENGTH_KEY = "focalLength"
ASSET_METADATA_FNUMBER_KEY = "fNumber"
ASSET_METADATA_LENS_MODEL_KEY = "lensModel"
ASSET_METADATA_CAMERA_MAKE_KEY = "make"

SEARCH_RESPONSE_SIZE=100

from enum import Enum

class ImageSource(Enum):
    LIBRARIES = 1
    ALBUMS = 2

def get_lens_usage_metadata():
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

    log_level_environment = extract_environment_variable(LOG_LEVEL_ENVIRONMENT_VARIABLE, "log level (INFO, DEBUG, CRITICAL)", optional=True)
    if log_level_environment is None:
        log_level = logging.INFO
    else:
        if log_level_environment.lower() == "info":
            log_level = logging.INFO
        elif log_level_environment.lower() == "debug":
            log_level = logging.DEBUG
        elif log_level_environment.lower() == "critical":
            log_level = logging.CRITICAL()
        else:
            raise ValueError(f'Invalid log level found in environment variable {LOG_LEVEL_ENVIRONMENT_VARIABLE}: {log_level_environment}')

    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_level_environment is None:
        logger.info("Default log level INFO.")
    else:
        logger.info(f'Set log level to user supplied {log_level_environment}.')

    logger.info("Start reading environment variales...")

    immich_server_address = extract_environment_variable(IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE, "address of Immich server.").strip("/")
    logger.debug(f'Extracted values of environment variable {IMMICH_SERVER_ADDRESS_ENVIRONMENT_VARIABLE} as {immich_server_address}.')
    immich_api_key = extract_environment_variable(IMMICH_API_KEY_ENVIRONMENT_VARIABLE, "API key")
    
    immich_libraries = extract_environment_variable(IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE, f'\"{IMMICH_LIBRARIES_DELIMITER}\" separated names of libraries', optional=True)
    if immich_libraries:
        immich_libraries = immich_libraries.split(sep=IMMICH_LIBRARIES_DELIMITER)
        immich_libraries = [library_name.strip() for library_name in immich_libraries]
        logger.debug(f'Extracted values of environment variable {IMMICH_LIBRARIES_NAMES_ENVIRONMENT_VARIABLE} as {immich_libraries}.')
        immich_libraries_owner_key = extract_environment_variable(IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE, "API key of owner of given libraries")
        logger.debug(f'Extracted values of environment variable {IMMICH_LIBRARIES_OWNER_ENVIRONMENT_VARIABLE}.')

    immich_albums = extract_environment_variable(IMMICH_ALBUMS_ENVIRONMENT_VARIABLE, f'\"{IMMICH_ALBUMS_DELIMITER}\" separated names of albums', optional=True)
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

    def get_assets_for_ids(json_key, search_ids):
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
                # selection for asset ids of only images, which have metadata
                asset_ids = asset_ids + [asset["id"] for asset in asset_response["items"] if asset["hasMetadata"] and asset["type"] == "IMAGE"]
                next_page = asset_response["nextPage"]
                if next_page is None:
                    iterate_over_pages = False
                else:
                    # get next page of assets
                    payload["page"] = next_page
                    search_response = requests.post(url=f'{immich_server_address}/api/search/metadata', json=payload, headers=asset_search_header)
                    asset_response = search_response.json()["assets"]

        return set(asset_ids)

    if IMAGE_SOURCE == ImageSource.ALBUMS:
        logger.info("Getting all assets for album ids...")
        asset_ids = get_assets_for_ids(json_key="albumIds", search_ids=album_ids)
        asset_headers = HEADERS
    elif IMAGE_SOURCE == ImageSource.LIBRARIES:
        logger.info("Getting all assets for library ids...")
        asset_ids = get_assets_for_ids(json_key="libraryId", search_ids=library_ids)
        asset_headers = {"X-API-Key": immich_libraries_owner_key, "Content-Type": "application/json"}

    ##############################
    # Get metadata for asset ids #
    ##############################

    metadata = {}
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
            f_number = asset_response[ASSET_METADATA_KEY][ASSET_METADATA_FNUMBER_KEY]
            if not lens_model or not focal_length or focal_length == 0:
                # ignore entries with no lens mdoel or focal length (i.e. adapted lenses)
                logger.debug(f'Dropped asset {asset_id} with lens model {lens_model}, focal length {focal_length}, and fNumber {f_number}.')
                continue
            else:
                # retreive dictionary structure
                lenses_for_camera = metadata.get(camera_make, {})
                lens_metadata = lenses_for_camera.get(lens_model, {})
                focal_lengths = lens_metadata.get(ASSET_METADATA_FOCAL_LENGTH_KEY, [])
                f_numbers = lens_metadata.get(ASSET_METADATA_FNUMBER_KEY, [])

                # add new values
                focal_lengths.append(focal_length)
                f_numbers.append(f_number)

                # update values in dictionaries
                lens_metadata[ASSET_METADATA_FOCAL_LENGTH_KEY] = focal_lengths
                lens_metadata[ASSET_METADATA_FNUMBER_KEY] = f_numbers
                lenses_for_camera[lens_model] = lens_metadata
                metadata[camera_make] = lenses_for_camera
                logger.debug(f'Added focal length {focal_length} and fNumber{f_number} for lens {lens_model} and camera {camera_make}.')

    
    return metadata

