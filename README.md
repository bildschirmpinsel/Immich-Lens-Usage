# Immich-Lens-Usage
This projects aims to provide a statistical overview of used focal lengths. Useful to figure out what focal length one shoots the most in general, or for a specific lens. All this without having the actual files present, but conveniently through an Immich instance.

## Permissions
The API key needs the following permissions: `assets.read`, `stack.read`.

The following optional permissions have to be granted based on filter criteria the user wants to apply:
- Album related filters: `albums.read`.
- Library related filters: `library.read`, __admin__ authenticated API key (key created by admin user).

## Configuration
The script is configured entirely by environment variables:
- `LENS_USAGE_IMMICH_SERVER`: Address of the immich server to query. E.g. http://immich.local.
- `LENS_USAGE_IMMICH_API_KEY`: Immich API key. On how to obtain it, see [here](https://docs.immich.app/features/command-line-interface/#obtain-the-api-key).
- `LENS_USAGE_LOG_LEVEL`: Specifies the log level (INFO, DEBUG, CRITICAL) for logging.

One of the following variables needs to be set, otherwise, no data can be queried from server.
- `LENS_USAGE_IMMICH_LIBRARIES_NAMES`: Set to empty string to include all libraries. To ignore this filter, do not set. If set, needs __admin__ authenticated API key.
- `LENS_USAGE_IMMICH_LIBRARIES_OWNER`: Set to API key of owner of libraries if one or more libraries have been specified.
- `LENS_USAGE_IMMICH_ALBUMS`: Set to only include a list of albums. If not set, all albums associated with the API key are taken into account.

## Usage
Running the script `Visualization.py` yields an interactive browser app for visualizing the metadata and computed statistics. The server runs by default under `http://127.0.0.1:8050`.