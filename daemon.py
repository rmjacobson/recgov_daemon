"""
daemon.py

Main module for recgov daemon. Runs scrape_availabilty methods in a loop to detect new availability
for a list of campgrounds provided by the user or found in RIDB search.
"""

from signal import signal, SIGINT
import asyncio
import aiosmtplib
import json
import logging
import argparse
import smtplib
import ssl
import os
import re
from datetime import datetime
from typing import List
from time import sleep
from email.message import EmailMessage
from selenium.webdriver.chrome.webdriver import WebDriver
from scrape_availability import create_selenium_driver, scrape_campground
from ridb_interface import get_facilities_from_ridb
from campground import Campground, CampgroundList
from utils import exit_gracefully, setup_logging

logger = logging.getLogger(__name__)

# set in ~/.virtualenvs/recgov_daemon/bin/postactivate
GMAIL_USER = os.environ.get("gmail_user")
GMAIL_APP_PASSWORD = os.environ.get("gmail_app_password")
CARRIER_MAP = {
    "verizon": "vtext.com",
    "tmobile": "tmomail.net",
    "sprint": "messaging.sprintpcs.com",
    "at&t": "txt.att.net",
    "boost": "smsmyboostmobile.com",
    "cricket": "sms.cricketwireless.net",
    "uscellular": "email.uscc.net",
}
RETRY_WAIT = 300

def send_email(receiver_addr, message: EmailMessage) -> None:
    """
    We send both texts and emails via this base function. For now, we're hardcoding GMAIL
    as our email service because that's what we use in development. Another user/dev should
    be able to change these values fairly easily.

    Retry sending email 5 times before exiting with failure if we can't send an email.
    
    TODO: write docs + finish new SMTP object stuff + deal with error that happens on CTRL-C
    Note that because SMTP is a sequential protocol, `aiosmtplib.send` must be
    executed in sequence as well, which means that doing this asyncronously is essentially
    equivalent to doing it normally. To get the benefit, we need to create a new connection
    object entirely for different emails (in this case we create 2 of them).
    Ref: https://aiosmtplib.readthedocs.io/en/v1.0.6/overview.html#parallel-execution
    """
    logger.info("Sending alert for available campgrounds to %s.", message["To"])
    smtp_server = "smtp.gmail.com"      # hardcode using gmail for now
    port = 465                          # ensure starttls
    num_retries = 5
    
    for attempts in range(num_retries):
        try:
            context = ssl.create_default_context()
            # with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            with smtplib.SMTP(smtp_server, port=587) as server:
                context = ssl.create_default_context()
                server.starttls(context=context)
                # server.ehlo()
                server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                server.send_message(message)
            break
        except (smtplib.SMTPRecipientsRefused, 
                smtplib.SMTPHeloError, 
                smtplib.SMTPSenderRefused, 
                smtplib.SMTPDataError, 
                smtplib.SMTPNotSupportedError, 
                smtplib.SMTPAuthenticationError, 
                smtplib.SMTPException) as e:
            logger.error("FAILURE: could not send email due to the following exception; retrying %d times:\n%s", num_retries-attempts, e)
    else:  # will run if we didn't break out of the loop, so only failures
        logger.error("Failed to send alert %d times; exiting with failure", num_retries)
        return False
    logger.info("Sent alert for available campgrounds to %s.", message["To"])
    return True

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

def compare_availability(selenium_driver: WebDriver, campground_list: CampgroundList, start_date, num_days) -> CampgroundList:
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
    
    return available

def send_alerts(available_campgrounds: CampgroundList) -> None:
    """
    Builds and sends 2 emails:
      - one for an email alert sent to a convetional email address
      - one for a text alert sent via carrier email/text gateway
    Uses asyncio because it saves a *tiny* amount of time and to experiment for later
    asynchronicity.
    """
    # build email message
    email_alert_msg = EmailMessage()
    email_alert_msg["From"] = GMAIL_USER
    email_alert_msg["To"] = args.email
    email_alert_msg["Subject"] = f"Alert for \
        {len(available_campgrounds)} Available Campground on Recreation.gov"
    content = "The following campgrounds are now available! Please excuse ugly JSON formatting.\n"
    content += json.dumps(available_campgrounds.serialize(), indent=4)
    email_alert_msg.set_content(content)
    
    # build text message
    num = args.text
    to_email = CARRIER_MAP[args.carrier]
    text_alert_msg = EmailMessage()
    text_alert_msg["From"] = GMAIL_USER
    text_alert_msg["To"] = f"{num}@{to_email}"
    text_alert_msg["Subject"] = f"{len(available_campgrounds)} New Campgrounds Available"
    content = ""
    for campground in available_campgrounds:
        content += f"\n{campground.url}"
    text_alert_msg.set_content(content)

    # send alerts; retry 5 times if doesn't succeed; exit gracefully if fails repeatedly
    res = send_email(args.email, email_alert_msg) and send_email(f"{num}@{to_email}", text_alert_msg)
    return res

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

def validate_carrier(arg:str) -> str:
    """
    Carrier has to be something that we can map back to a gateway, so
    check that the entered text is a key in the carrier map dict. Accept
    mixture of uppercase/lowercase just to be nice.

    :param arg: the user-entered carrier name
    :returns: lowercase str version of the entered carrier if present in carrier map dict
    """
    lowercase_arg = arg.lower()
    if lowercase_arg not in CARRIER_MAP.keys():
        logger.error("KeyError: carrier '%s' not found in CARRIER_MAP dict:\n%s",
                    lowercase_arg,json.dumps(CARRIER_MAP))
        exit(1)
    return lowercase_arg

def validate_num_sites(arg:int) -> int:
    """
    Number of campsites has to be an integer >0 and <10 for sanity's sake.

    :param arg: user-entered number of sites
    :returns: integer 1-9 inclusive
    """
    if type(arg) != int:
        logger.error("User input for number of campsites not an int.")
        exit(1)
    if arg > 9:
        logger.error("User input for number of campsites (%d) too large (must be <10")
        exit(1)
    if arg < 1:
        logger.error("User input for number of campsites (%d) too small (must be > 1")
        exit(1)
    return arg

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
        available = compare_availability(driver, campgrounds, args.start_date, args.num_days)
        if len(available) > 0:
            if not send_alerts(available):
                exit_gracefully(None, None, driver)
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
    parser.add_argument("-t", "--text", type=str, required=True,
        help="Phone number at which you want to receive text notifications (ex: 9998887777).")
    parser.add_argument("-c", "--carrier", type=validate_carrier, required=True,
        help="Cell carrier for your phone number, required to send texts (ex: 'at&t', 'verison', 'tmobile','sprint', etc.).")
    parser.add_argument("--lat", type=float,
        help="Latitude of location you want to search for (e.g. 35.994431 for Ponderosa Campground).")
    parser.add_argument("--lon", type=float,
        help="Longitude of the location you want to search for (e.g. -121.394325 for Ponderosa Campground).")
    parser.add_argument("-r", "--radius", type=int,
        help="Radius in miles of the area you want to search, centered on lat/lon (e.g. 25).")
    parser.add_argument("--campground_ids", type=parse_id_args,
        help="Comma-separated list of campground facility IDs you want to check (e.g. `233116,231962`).")
    parser.add_argument("--num_sites", type=validate_num_sites,
        help="Number of campsites you need at each campground; defaults to 1, validated to be >0 and <10.")
    args = parser.parse_args()
    setup_logging()
    run()
