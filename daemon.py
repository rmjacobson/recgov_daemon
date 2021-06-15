"""
daemon.py

Main module for recgov daemon. Runs scrape_availabilty methods in a loop to detect new availability
for a list of campgrounds provided by the user or found in RIDB search.
"""
import sys
from signal import signal, SIGINT
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import argparse
import smtplib
import ssl
import os
from datetime import datetime
from typing import List
from time import sleep
from email.message import EmailMessage
from selenium.webdriver.chrome.webdriver import WebDriver
from scrape_availability import create_selenium_driver, scrape_campground
from ridb_interface import get_facilities_from_ridb
from campground import Campground, CampgroundList

"""
Note on logging:
Python 3 logging is annoyingly confusing because of how inheiritance from the root logger works
and how multiple modules all need to log to the same file. It's also annoying that no tutorial
or official doc agrees on what is "best practice" between manually naming the loggers across
modules vs. using __name__, or whether or not it's best practice to create config/ini files, etc.

For this project, I have chosen to programatically configure logging as below, using basicConfig
to also reconfigure the root logger (which affects Selenium mostly), and have other modules get
configs from here by just using getLogger in those files because it is the simplest thing I've
tried that actually works as needed. The log:
  - is set to INFO by default
  - rotates to a new file every day
  - will save logs for 7 days max
  - saves to a local logs/ directory inside this repo (excluded from git) because doing so
    elsewhere does not guarantee user will have permissions to create files

Refs used to create this:
  - https://gist.github.com/gene1wood/73b715434c587d2240c21fc83fad7962
  - https://timber.io/blog/the-pythonic-guide-to-logging/
Ref for format:
  - https://www.pylenin.com/blogs/python-logging-guide/#configuring-a-main-logger
Ref for file config (not used):
  - https://www.internalpointers.com/post/logging-python-sub-modules-and-configuration-files
  - http://antonym.org/2005/03/a-real-python-logging-example.html
Generic Logging Principles:
  - https://peter.bourgon.org/blog/2017/02/21/metrics-tracing-and-logging.html
"""
rotating_handler = handler = TimedRotatingFileHandler("logs/recgov.log", when="d", interval=1,  backupCount=5)
rotating_handler.suffix = "%Y-%m-%d"
logging.basicConfig(
    handlers=[rotating_handler],
    level=logging.INFO,
    format="[%(asctime)s] %(filename)s:%(lineno)d [%(name)s]%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# set in ~/.virtualenvs/recgov_daemon/bin/postactivate
GMAIL_USER = os.environ.get("gmail_user")
GMAIL_PASSWORD = os.environ.get("gmail_password")
RETRY_WAIT = 300

def exit_gracefully(signal_received, frame, close_this_driver: WebDriver=None):
    """
    Handler for SIGINT that will close webdriver carefully if necessary.
    Ref: https://www.devdungeon.com/content/python-catch-sigint-ctrl-c
         https://docs.python.org/3/library/signal.html

    :param signal_received: signal object received by handler
    :param frame: actually have no idea what this is and we never use it...
    :param driver: Selenium WebDriver to close before exiting
    :returns: N/A
    """
    logger.info("Received CTRL-C/SIGNINT or daemon completed; exiting gracefully/closing WebDriver if initialized.")
    if close_this_driver is not None:
        # use quit instead of close to avoid tons of leftover chrome processes
        # https://stackoverflow.com/questions/15067107/difference-between-webdriver-dispose-close-and-quit
        close_this_driver.quit()
    sys.exit(0)

def send_email_alert(available_campgrounds: CampgroundList):
    """
    Send email alert to email address provided by argparse, from email address (and password)
    retrieved from environment variables. Currently use Google Mail to facilitate email
    alerts. See references:
        https://zetcode.com/python/smtplib/
        https://realpython.com/python-send-email/#option-1-using-smtp_ssl
        https://docs.python.org/3/library/smtplib.html

    :param available_campgrounds: CampgroundList object containing available campgrounds
        found in caller
    :returns: N/A
    """
    logger.info("Sending email alert for %d available campgrounds to %s.", len(available_campgrounds), args.email)

    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = args.email
    msg["Subject"] = f"Alert for {len(available_campgrounds)} Available Campground on Recreation.gov"
    content = "The following campgrounds are now available!  Please excuse ugly JSON formatting.\n"
    content += json.dumps(available_campgrounds.serialize(), indent=4)
    msg.set_content(content)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.send_message(msg)
        logger.debug("\tEmail sent!")
    except Exception as e:
        logger.error("FAILURE: could not send email due to the following exception:\n%s",e)

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
                logger.debug("\tRemoving facility ID %s from user_facs because \
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
        logger.debug("\tCreating Campground obect for facility id: %s", facility[1])
        camp = Campground(name=facility[0], facility_id=facility[1])
        campgrounds_from_facilities.append(camp)

    return campgrounds_from_facilities

def compare_availability(selenium_driver: WebDriver, campground_list: CampgroundList, start_date, num_days) -> None:
    """
    Given a list of Campground objects, find out if any campgrounds' availability has changed
    since the last time we looked.

    :param campgrounds: list of Campground objects we want to check against
    :returns: N/A
    """
    available = CampgroundList()
    for campground in campground_list:
        logger.debug("\tComparing availability for %s (%s)", campground.name, campground.id)
        if campground.available:
            logger.debug("Skipping %s (%s) because an available site already found", campground.name, campground.id)
        elif (not campground.available and scrape_campground(selenium_driver, campground, start_date, num_days)):
            logger.info("%s (%s) is now available! Adding to email list.", campground.name, campground.id)
            campground.available = True
            available.append(campground)
            logger.debug("\tAdding the following to available list %s", json.dumps(campground.jsonify()))
        else:
            logger.info("%s (%s) is not available, trying again in %s seconds",
                campground.name, campground.id, RETRY_WAIT)

        # if campground parsing has errored more than 5 times in a row, remove it from the CampgroundList
        if campground.error_count > 5:
            err_msg = f"Campground errored more than 5 times in a row, removing it from list:\n{campground.pretty()}"
            logger.error(err_msg)
            campground_list.remove(campground)

    if len(available) > 0:
        send_email_alert(available)

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
    signal(SIGINT, exit_gracefully)
    # kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    # mcgill = "https://www.recreation.gov/camping/campgrounds/231962/availability"
    # kirk_start_date_str = "09/17/2021"
    # mcgill_start_date_str = "05/31/2021"
    # num_days = 2
    # do_stuff(mcgill, mcgill_start_date_str, num_days)

    # LAT = 35.994431     # these are the coordinates for Ponderosa Campground
    # LON = -121.394325
    # RADIUS = 20

    ARG_DESC = """Daemon to check recreation.gov and RIDB for new campground availability and send notification email
        when new availability found."""
    parser = argparse.ArgumentParser(description=ARG_DESC)
    parser.add_argument("-s", "--start_date", type=parse_start_day, required=True,
        help="First day you want to reserve a site, represented as Month/Day/Year (e.g. 05/19/2021).")
    parser.add_argument("-n", "--num_days", type=int, required=True,
        help="Number of days you want to camp (e.g. 2).")
    parser.add_argument("-e", "--email", type=str, required=True,
        help="Email address at which you want to receive notifications (ex: first.last@example.com).")
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
    if None not in ridb_args:
        ridb_facilities = get_facilities_from_ridb(args.lat, args.lon, args.radius)
    elif None in ridb_args and (args.lat is not None or args.lon is not None or args.radius is not None):
        RIDB_ARGS_ERROR_MSG = ("daemon.py:__main__: At least one RIDB argument was passed but at least one "
            "RIDB arg is missing or None; combination fails. Check CLI args and try again.")
        raise ValueError(RIDB_ARGS_ERROR_MSG)

    campgrounds = get_all_campgrounds_by_id(args.campground_ids, ridb_facilities)
    logger.info(json.dumps(campgrounds.serialize(), indent=2))

    driver = create_selenium_driver()

    # use this section for one-time check of campgrounds
    # compare_availability(driver, campgrounds, args.start_date, args.num_days)
    # driver.close()

    # check campground availability until stopped by user or start_date has passed
    while True:
        if args.start_date < datetime.now():
            logger.info("Desired start date has passed, ending process...")
            exit_gracefully(None, None, driver)
        compare_availability(driver, campgrounds, args.start_date, args.num_days)
        sleep(RETRY_WAIT)  # sleep for RETRY_WAIT time before checking campgrounds again
