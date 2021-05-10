"""
#TODO add module description
"""
import sys
import logging
import os
import requests

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
)
l = logging.getLogger(__name__)

API_KEY = os.environ.get("ridb_api_key")
RIDB_BASE_URL = "https://ridb.recreation.gov/api/v1/facilities"
RECGOV_BASE_URL = "https://www.recreation.gov/camping/campgrounds"

LAT = 35.994431     # these are the coordinates for Ponderosa Campground
LON = -121.394325
RADIUS = 20

class Campground():
    """
    Taken from https://github.com/CCInCharge/campsite-checker, has been useful for debug.
    """
    def __init__(self, name, url):
        self.campsites = {}     # #TODO: develop way of storing available specific campsites
        self.name = name        # name of campground
        self.url = url          # recreation.gov URL for campground
    def print(self):
        """
        Pretty print Campground information.
        """
        print("Campground")
        print(self.name)
        print(self.campsites)
        print(self.url)
    def jsonify(self):
        """
        Returns JSON representation of this object, as a dict
        """
        campground = {
            "name": self.name,
            "url": self.url,
            "campsites": []
        }
        return campground

class CampgroundList(list):
    """
    Taken from https://github.com/CCInCharge/campsite-checker, has been useful for debug.
    Inherits from list, contains several Campground objects.
    Has a method to return a JSON string representation of its Campgrounds.
    """
    def serialize(self):
        """
        Make JSON string from Campgrounds list.
        """
        if len(self) == 0:
            return {"campgrounds": []}

        result = {"campgrounds": [None] * len(self)}
        for idx,campground in enumerate(self):
            result["campgrounds"][idx] = campground.jsonify()
        return result

def get_facilities_from_ridb(latitude, longitude, radius):
    """
    Calls RIDB API with a location and search radius, and returns URLs and campground names
    #TODO: add more description

    :param latitude: Latitude of coordinate to center the search around
    :param longitude: Longitude of coordinate to center the search around
    :param radius: Radius to search around
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

    # Gets campgrounds from RIDB API
    resp = requests.get(RIDB_BASE_URL, headers=headers, params=facilities_query)
    if not resp.ok:
        l.debug("Unable to access RIDB API. Check connection and API key.")
        sys.exit()

    try:
        res = [x for x in resp.json()["RECDATA"] if x["FacilityTypeDescription"] == "Campground"]
    except KeyError:
        l.error("No FacilityTypeDescription field in RECDATA element. Check RIDB API specs.")
        sys.exit()

    # Constructs list of Campgrounds
    facilities = CampgroundList()
    # print(json.dumps(res, indent=4))

    for idx,campsite in enumerate(res):
        facility_id_field = "FacilityID"
        facility_name_field = "FacilityName"
        try:
            facility_id = str(campsite[facility_id_field])
            campground_url = f"{RECGOV_BASE_URL}/{facility_id}/availability"
            name = " ".join(w.capitalize() for w in res[idx][facility_name_field].split())
            facilities.append(Campground(name, campground_url))
        except KeyError:
            l.error("No %s or %s field in campground dict. Check RIDB API specs.",
                facility_id_field, facility_name_field)
    return facilities

if __name__ == "__main__":
    campgrounds = get_facilities_from_ridb(LAT, LON, RADIUS)
    # print(len(campgrounds))
    for r in campgrounds:
        r.print()
