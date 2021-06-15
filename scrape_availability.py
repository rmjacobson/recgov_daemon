"""
#TODO add module description
"""

from campground import Campground
from time import sleep
import logging
import traceback
from datetime import datetime, timedelta
from pandas.core.frame import DataFrame
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# tag names needed for html interaction/parsing found via manual inspection of
# recreation.gov -- DO NOT CHANGE unless recreation.gov changes its layout!
INPUT_TAG_NAME = "single-date-picker-1"
AVAILABILITY_TABLE_TAG_NAME = "availability-table"
CAMP_LOCATION_NAME_ICON = "camp-location-name--icon"
PAGE_LOAD_WAIT = 5

def parse_html_table(table: BeautifulSoup) -> DataFrame:
    """
    Parse Beautifulsoup representation of recreation.gov availability table into a pandas dataframe.

    :param table: BeautifulSoup object containing just the availability table HTML
    :returns: pandas dataframe containing column names and row data
    """
    column_names = []
    recgov_row_tags = ['td', 'th']

    # get column names from the "second" row of the <thead> tag because the "first" row just contains the month string
    column_tags = table.find("thead").find_all("tr")
    columns = column_tags[1].find_all('th')
    if len(columns) > 0 and len(column_names) == 0:
        for h_tag in columns:
            column_names.append(h_tag.get_text())

    # read rows in <tbody> tag for availability data, remove camp name icon if necessary to reduce confusing text
    body_tag = table.find("tbody")
    rows = body_tag.find_all("tr")
    df = DataFrame(columns=column_names, index=range(0,len(rows)))
    for r, row in enumerate(rows):
        cell_tags = row.find_all(recgov_row_tags)
        for c, cell in enumerate(cell_tags):
            icon = cell.find("div", {"class":CAMP_LOCATION_NAME_ICON})
            if icon is not None:
                icon.decompose()
            df.iat[r,c] = cell.get_text()

    return df

def all_dates_available(df: DataFrame, start_date: datetime, num_days: int) -> bool:
    """
    Parse pandas DataFrame for the specific date columns matching the start date and number
    of nights we want to stay, search for 'A' string in df cells. Return True if every column
    has an availability (inlcuding if the daily availabilities are in different sites/rows).

    :param df: pandas DataFrame parsed from recreation.gov campground website
    :returns: True if every relevant date column contains at least one available 'A' cell,
        False otherwise
    """
    # get column names corresponding to days we want to stay at the campground
    abbr_dates = []
    for date in range(num_days):
        abbr_date = start_date + timedelta(days=date)
        abbr_date_str = abbr_date.strftime("%a%-d")
        abbr_dates.append(abbr_date_str)

    # cycle through date columns to check if there's at least one available site for each day
    at_least_one_available = True
    for col in df[abbr_dates].columns:
        at_least_one_available = (df[col] == "A").any()
        if not at_least_one_available:
            logger.debug("Found column (aka date) with no availability --> stopping search of table")
            break

    return at_least_one_available

def create_selenium_driver() -> WebDriver:
    """
    Initialize Selenium WebDriver object and return it to the caller. Do this in a separate
    function to allow driver re-use across rounds of scraping.

    :returns: Selenium WebDriver object
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    return webdriver.Chrome(ChromeDriverManager().install(), options=options)

def scrape_campground(driver: WebDriver, campground: Campground, start_date: datetime, num_days: int) -> bool:
    """
    Use Selenium WebDriver to load page, input desired start date, identify availability table
    for new data, use BeautifulSoup to parse html table, and use pandas DataFrame to identify
    availability inside the parsed table.

    Use Selenium's send_keys functionality to enter start date, see below for info:
        https://selenium-python.readthedocs.io/api.html#module-selenium.webdriver.common.keys
        https://stackoverflow.com/a/27799120

    :param driver: WebDriver object previously instantiated
    :param campground: Campground object; url field will be loaded with driver
    :param start_date: datetime object identifying the date user wishes to arrive at campground
    :param num_days: int representation of number of nights user wishes to stay at campground
    :returns: True if start_date/num_days are available, False otherwise
    """
    try:
        logger.debug("\tGetting campground.url (%s) with driver", campground.url)
        driver.get(campground.url)
        sleep(PAGE_LOAD_WAIT)    # allow the page to fully load before looking at tags
        logger.debug("\tFinding input box tag")
        date_input = driver.find_element_by_id(INPUT_TAG_NAME)
        logger.debug("\tSending new date with send_keys")
        date_input.send_keys(Keys.COMMAND + "a")
        date_input.send_keys(start_date.strftime("%m/%d/%Y"))
        date_input.send_keys(Keys.RETURN)
        sleep(PAGE_LOAD_WAIT)    # allow new data to load in the table
        logger.debug("\tFinding availability table tag")
        availability_table = driver.find_element_by_id(AVAILABILITY_TABLE_TAG_NAME)
        table_html = availability_table.get_attribute('outerHTML')
        soup = BeautifulSoup(table_html, 'html.parser')
        df = parse_html_table(soup)
        dates_available = all_dates_available(df, start_date, num_days)
        campground.error_count = 0      # if not errored -> reset error count to 0
        return dates_available
    except Exception as e:
        logger.exception(e)
        logger.exception(str(traceback.format_exc()))
        campground.error_count += 1     # if errored -> inc error count
        return False

if __name__ == "__main__":
    # kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    # kirk_start_date_str = "09/17/2021"
    mcgill = "https://www.recreation.gov/camping/campgrounds/231962/availability"
    mcgill_start_date_str = "05/31/2021"
    num_days = 2

    driver = create_selenium_driver()
    if scrape_campground(driver, mcgill, mcgill_start_date_str, num_days):
        logger.info("WE HAVE SOMETHING AVAILABLE!")
    else:
        logger.info("sad")
