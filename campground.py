"""
campground.py

Class declarations for Campground and CampgroundList. Also contains misc functions for creating
and keeping track of campground data.
"""

RECGOV_BASE_URL = "https://www.recreation.gov/camping/campgrounds"

class Campground():
    """
    Taken from https://github.com/CCInCharge/campsite-checker, has been useful for debug.
    """
    def __init__(self, name="N/A", facility_id=None):
        self.name = name                                            # name of campground
        self.id = facility_id                                       # facility ID of campground
        self.url = f"{RECGOV_BASE_URL}/{facility_id}/availability"  # recreation.gov URL for campground
        self.available = False                                      # initialize to unavailable
        # self.campsites = {}     # #TODO: develop way of storing available specific campsites

    def print(self):
        """
        Pretty print Campground information.
        """
        print("Campground")
        print(f"\t{self.name}")
        print(f"\t{self.id}")
        print(f"\t{self.url}")
        print(f"\t{self.available}")
        # print(f"\t{self.campsites}")
    def jsonify(self):
        """
        Returns JSON representation of this object, as a dict
        """
        json = {
            "name": self.name,
            "facilityID": self.id,
            "url": self.url,
            "available": self.available
            # "campsites": []
        }
        return json

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
            return []

        result = []
        for campground in self:
            result.append(campground.jsonify())
        return result
