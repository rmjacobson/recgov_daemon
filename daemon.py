"""
#TODO add module description
"""
import json
import logging
import argparse
from datetime import datetime
from typing import List
from selenium.webdriver.chrome.webdriver import WebDriver
from scrape_availability import create_selenium_driver, scrape_campground
from ridb_interface import get_facilities_from_ridb
from campground import Campground, CampgroundList

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(filename)s:%(lineno)d [%(name)s] %(levelname)s - %(message)s",
)
l = logging.getLogger(__name__)

RETRY_WAIT = 300

def get_all_campgrounds_by_id(user_facs: List[str]=None, ridb_facs: List[str]=None) -> CampgroundList:
    """
    We take both campground facility IDs passed in by the user as well as the list of facility IDs
    taken from the radius search in the RIDB interface. This function ensures there is no overlap
    between those sets of facility IDs and creates a list of Campground objects to pass to the
    recreation.gov scraper.

    :param user_facs: list of str representing facility IDs passed in as args by the user
    :param ridb_facs: list of str representing facility IDs received from RIDB search
    :returns: CampgroundList object
    """
    campgrounds_from_facilities = CampgroundList()

    if ridb_facs is not None and user_facs is not None:
        # check if the user has passed in any duplicate campgrounds to those found in ridb before concatenating lists
        ridb_facs_ids = [id[1] for id in ridb_facs]
        for u_fac in user_facs:
            if u_fac[1] in ridb_facs_ids:
                logging.debug("Removing facility ID %s from user_facs because \
                    it is already present in ridb_facs list", u_fac[1])
                user_facs.remove(u_fac)
        facilities = user_facs + ridb_facs
    elif ridb_facs is None and user_facs is not None:
        facilities = user_facs
    elif user_facs is None and ridb_facs is not None:
        facilities = ridb_facs
    else:
        raise ValueError("Both ridb_facs and user_facs are None; check input or ridb output.")

    # combine facilities lists and create campground objects for each facility in the list
    for facility in facilities:
        logging.debug("Creating Campground obect for facility id: %s", facility[1])
        camp = Campground(name=facility[0], facility_id=facility[1])
        campgrounds_from_facilities.append(camp)

    return campgrounds_from_facilities

def compare_availability(selenium_driver: WebDriver, campground_list: CampgroundList, start_date, num_days):
    """
    Given a list of Campground objects, find out if any campgrounds' availability has changed
    since the last time we looked.

    :param campgrounds: list of Campground objects we want to check against
    :returns: #TODO
    """
    for campground in campground_list:
        if campground.available:
            logging.info("Skipping %s because an available site was already found", campground.name)
        elif not campground.available and scrape_campground(selenium_driver, campground.url, start_date, num_days):
            campground.available = True
            logging.info("%s is now available! Sending notification email.", campground.name)
        else:
            logging.info("%s is not available, trying again in %s seconds", campground.name, RETRY_WAIT)

def parse_start_day(arg: str) -> datetime:
    """
    Parse user input start date as Month/Day/Year (e.g. 05/19/2021).

    :param arg: date represented as a string
    :returns: datetime object representing the user-provided day
    """
    return datetime.strptime(arg, "%m/%d/%Y")

def parse_id_args(arg: str) -> List[str]:
    """
    Give user ability to input comma-separated list of campground IDs to search.

    :param arg: string of comma-separated campground GUIDs
    :returns: list of str
    """
    if arg is not None:
        user_facilities_list = arg.strip().split(",")
        user_facilities = list(zip(["Name Unknown (User Provided)"]*len(user_facilities_list), user_facilities_list))
        return user_facilities
    return None

if __name__ == "__main__":
    # kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    # mcgill = "https://www.recreation.gov/camping/campgrounds/231962/availability"
    # kirk_start_date_str = "09/17/2021"
    # mcgill_start_date_str = "05/31/2021"
    # num_days = 2
    # do_stuff(mcgill, mcgill_start_date_str, num_days)

    # LAT = 35.994431     # these are the coordinates for Ponderosa Campground
    # LON = -121.394325
    # RADIUS = 20

    parser = argparse.ArgumentParser(description="#TODO")
    parser.add_argument("-s", "--start_date", type=parse_start_day, required=True,
        help="First day you want to reserve a site, represented as Month/Day/Year (e.g. 05/19/2021).")
    parser.add_argument("-n", "--num_days", type=int, required=True,
        help="Number of days you want to camp (e.g. 2).")
    parser.add_argument("--lat", type=float,
        help="Latitude of location you want to search for (e.g. 35.994431 for Ponderosa Campground).")
    parser.add_argument("--lon", type=float,
        help="Longitude of the location you want to search for (e.g. -121.394325 for Ponderosa Campground).")
    parser.add_argument("-r", "--radius", type=int,
        help="Radius in miles of the area you want to search, centered on lat/lon (e.g. 25).")
    parser.add_argument("--campground_ids", type=parse_id_args,
        help="Comma-separated list of campground facility IDs you want to check (e.g. `233116,231962`).")
    args = parser.parse_args()

    # validate lat/lon/radius arguments prior to checking RIDB and forming CampgroundList
    ridb_args = {args.lat, args.lon, args.radius}
    ridb_facilities = None
    # logging.debug("len ridb_args = %s, %s", len(ridb_args), ridb_args)
    if None not in ridb_args:
        ridb_facilities = get_facilities_from_ridb(args.lat, args.lon, args.radius)
    elif None in ridb_args and (args.lat is not None or args.lon is not None or args.radius is not None):
        RIDB_ARGS_ERROR_MSG = ("daemon.py:__main__: At least one RIDB argument was passed but at least one "
            "RIDB arg is missing or None; combination fails. Check CLI args and try again.")
        raise ValueError(RIDB_ARGS_ERROR_MSG)

    campgrounds = get_all_campgrounds_by_id(args.campground_ids, ridb_facilities)
    print(json.dumps(campgrounds.serialize(), indent=2))

    driver = create_selenium_driver()
    compare_availability(driver, campgrounds, args.start_date, args.num_days)
    driver.close()

    # check campground availability until stopped by user or start_date has passed
    # while True:
    #     if args.start_date < datetime.now():
    #         exit()
    #     compare_availability(campgrounds, args.start_date, args.num_days)
    #     sleep(RETRY_WAIT)  # sleep for RETRY_WAIT time before checking campgrounds again
