"""
daemon.py

Main module for recgov daemon. Runs scrape_availabilty methods in a loop to detect new availability
for a list of campgrounds provided by the user or found in RIDB search.
"""

from signal import signal, SIGINT
import json
import logging
import argparse
import smtplib
import ssl
import os
from datetime import datetime
from typing import List
from time import sleep
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from selenium.webdriver.chrome.webdriver import WebDriver
from scrape_availability import create_selenium_driver, scrape_campground
from ridb_interface import get_facilities_from_ridb
from campground import Campground, CampgroundList
from utils import exit_gracefully, setup_logging

logger = logging.getLogger(__name__)

# set in ~/.virtualenvs/recgov_daemon/bin/postactivate
GMAIL_USER = os.environ.get("gmail_user")
GMAIL_APP_PASSWORD = os.environ.get("gmail_app_password")
RETRY_WAIT = 300

def send_email_alert(available_campgrounds: CampgroundList):
    """
    Send email alert to email address provided by argparse, from email address (and password)
    retrieved from environment variables. Currently use Google Mail to facilitate email
    alerts. Currently using Google App Password to avoid "less secure app access" problems.
    See references:
        https://levelup.gitconnected.com/an-alternative-way-to-send-emails-in-python-5630a7efbe84

    :param available_campgrounds: CampgroundList object containing available campgrounds
        found in caller
    :returns: N/A
    """
    logger.info("Sending email alert for %d available campgrounds to %s.", len(available_campgrounds), args.email)
    smtp_server = "smtp.gmail.com"
    port = 587  # For starttls
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = args.email
    msg["Subject"] = f"Alert for {len(available_campgrounds)} Available Campground on Recreation.gov"
    content = "The following campgrounds are now available!  Please excuse ugly JSON formatting.\n"
    content += json.dumps(available_campgrounds.serialize(), indent=4)
    body_text = MIMEText(content, 'plain')  # don't bother with HTML formatting for now
    msg.attach(body_text)
    context = ssl.create_default_context()
    try:
        server = smtplib.SMTP(smtp_server, port)
        server.ehlo()                       # check connection
        server.starttls(context=context)    # Secure the connection
        server.ehlo()                       # check connection
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, args.email, msg.as_string())
        logger.debug("\tEmail sent!")
    except Exception as e:
        logger.error("FAILURE: could not send email due to the following exception:\n%s",e)
    finally:
        server.quit()

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

        # if campground parsing has errored more than 5 times in a row
        # remove it from the CampgroundList so we can stop checking it and failing
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

def run():
    """
    Run the daemon after SIGINT has been captured and arguments have been parsed.
    """
    # validate lat/lon/radius arguments prior to checking RIDB and forming CampgroundList
    ridb_args = {args.lat, args.lon, args.radius}
    ridb_facilities = None
    if None not in ridb_args:
        ridb_facilities = get_facilities_from_ridb(args.lat, args.lon, args.radius)
    elif None in ridb_args and (args.lat is not None or args.lon is not None or args.radius is not None):
        ridb_args_error_msg = ("daemon.py:__main__: At least one RIDB argument was passed but at least one "
            "RIDB arg is missing or None; combination fails. Check CLI args and try again.")
        raise ValueError(ridb_args_error_msg)
    campgrounds = get_all_campgrounds_by_id(args.campground_ids, ridb_facilities)
    logger.info(json.dumps(campgrounds.serialize(), indent=2))

    driver = create_selenium_driver()

    # check campground availability until stopped by user or start_date has passed
    while True:
        if args.start_date < datetime.now():
            logger.info("Desired start date has passed, ending process...")
            exit_gracefully(None, None, driver)
        compare_availability(driver, campgrounds, args.start_date, args.num_days)
        sleep(RETRY_WAIT)  # sleep for RETRY_WAIT time before checking campgrounds again

if __name__ == "__main__":
    signal(SIGINT, exit_gracefully)     # add custom handler for SIGINT/CTRL-C
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
    setup_logging()
    run()
