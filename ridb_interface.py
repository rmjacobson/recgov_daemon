"""
RIDB Interface

Coordinates talking with the recreation.gov database API (RIDB) with requests, parses response
as json to extract campsite names and facility IDs. See below links for details:

https://www.recreation.gov/use-our-data
https://ridb.recreation.gov/docs#/
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

# set in ~/.virtualenvs/recgov_daemon/bin/postactivate
API_KEY = os.environ.get("ridb_api_key")
RIDB_BASE_URL = "https://ridb.recreation.gov/api/v1/facilities"
RECDATA_ELEM = "RECDATA"
FACILITY_TYPE_FIELD = "FacilityTypeDescription"
FACILITY_ID_FIELD = "FacilityID"
FACILITY_NAME_FIELD = "FacilityName"

def get_facilities_from_ridb(latitude: float, longitude: float, radius: int):
    """
    Calls RIDB API with a location and search radius, and returns campground names and RDIB
    facility ID strings.

    :param latitude: Latitude of coordinate to center the search around
    :param longitude: Longitude of coordinate to center the search around
    :param radius: Radius to search around
    :raises ValueError: if request to RIDB does not return 200 OK
    :raises KeyError: if can't find expected facility type/recdata element fields in resp json
    :returns: set of (name, facility_id) tuples
    """
    headers = {
        "accept": "application/json",
        "apikey": API_KEY
    }
    facilities_query = {
        "latitude": str(latitude),
        "longitude": str(longitude),
        "radius": str(radius),
        "FacilityTypeDescription": "Campground",
        # "Reservable": "True",
        # "lastupdated": "01-01-2021",
        "limit": 20
    }

    logger.debug("\tUse requests library to retrieve facilities from RIDB API")
    resp = requests.get(RIDB_BASE_URL, headers=headers, params=facilities_query)
    if not resp.ok:
        raise ValueError("Unable to access RIDB API. Check connection and API key.")
    try:
        res = [x for x in resp.json()[RECDATA_ELEM] if x[FACILITY_TYPE_FIELD] == "Campground"]
    except KeyError as err:
        err_msg  = "No %s field in %s element. Check RIDB API specs."
        raise KeyError(err_msg.format(FACILITY_TYPE_FIELD, RECDATA_ELEM)) from err
    logger.info("Received %d results from RIDB, parsing campground info...", len(res))

    # Construct list of campground names/facility IDs from ridb response
    facilities = []
    for idx,campsite in enumerate(res):
        try:
            facility_id = str(campsite[FACILITY_ID_FIELD])
            name = " ".join(w.capitalize() for w in res[idx][FACILITY_NAME_FIELD].split())
            facilities.append((name, facility_id))
        except KeyError as err:
            err_msg = "No %s or %s field in campground dict. Check RIDB API specs."
            raise KeyError(err_msg.format(FACILITY_ID_FIELD, FACILITY_NAME_FIELD)) from err
    logger.info("Parsed %d facilities from %d RIDB results", len(facilities), len(res))

    return facilities

def run():
    """
    Runs the RIDB interface module for specific values, should be used for debugging only.
    """
    lat = 35.994431     # these are the coordinates for Ponderosa Campground
    lon = -121.394325
    radius = 20
    campgrounds = get_facilities_from_ridb(lat, lon, radius)
    for camp in campgrounds:
        camp.print()

if __name__ == "__main__":
    run()
