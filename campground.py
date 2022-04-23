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
        self.name = name                                # name of campground
        self.id = facility_id                           # facility ID of campground
        self.url = f"{RECGOV_BASE_URL}/{facility_id}"   # recreation.gov URL for campground
        self.available = False                          # initialize to unavailable
        self.error_count = 0                            # initialize parsing error count to 0
        # self.campsites = {}     # TODO: develop way of storing available specific campsites

    def pretty(self):
        """
        Create string to pretty print Campground information.
        """
        # TODO: add self.campsites when available
        return f"Campground:\n\t{self.name}\n\t{self.id}\n\t{self.url}\n\t{self.available}\n\t{self.error_count}"

    def jsonify(self):
        """
        Returns JSON representation of this object, as a dict
        """
        json = {
            "name": self.name,
            "facilityID": self.id,
            "url": self.url,
            "available": self.available,
            "error_count": self.error_count
            # TODO: "campsites": []
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
