"""
scrape_availability.py

Webpage interface for recov daemon. Responsible for interacting with recreation.gov via selenium
webdriver and with beautifulsoup after selenium has retrieved the availability table.
"""

import logging
import traceback
from datetime import datetime, timedelta
from pandas.core.frame import DataFrame
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from campground import Campground

logger = logging.getLogger(__name__)

# tag names needed for html interaction/parsing found via manual inspection of
# recreation.gov -- DO NOT CHANGE unless recreation.gov changes its layout!
INPUT_TAG_NAME = "single-date-picker-1"
AVAILABILITY_TABLE_TAG_NAME = "availability-table"
TABLE_LOADING_TAG_CLASS = "rec-table-overlay"
CAMP_LOCATION_NAME_ICON = "camp-location-name--icon"
AVAILABILITY_TABLE_REFRESH_XPATH = """//*[@id="page-body"]/div/div[1]/div[1]/div[3]/div[1]/div[1]/div/div/button[1]"""
PAGE_LOAD_WAIT = 60

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
    for row_idx, row in enumerate(rows):
        cell_tags = row.find_all(recgov_row_tags)
        for cell_idx, cell in enumerate(cell_tags):
            icon = cell.find("div", {"class":CAMP_LOCATION_NAME_ICON})
            if icon is not None:
                icon.decompose()
            df.iat[row_idx,cell_idx] = cell.get_text()
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
    function to allow driver re-use across rounds of scraping.  Note: the remote debugging port
    option seems to be required for raspberry pi operation: https://stackoverflow.com/a/56638103

    :returns: Selenium WebDriver object
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--remote-debugging-port=9222")
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(PAGE_LOAD_WAIT)
    return driver

def wait_for_page_element_load(driver: WebDriver, elem_id: str):
    """
    Force WebDriver to wait for element to load before continuing. Timeout of PAGE_LOAD_WAIT
    (defaults to 60s).
    https://www.guru99.com/implicit-explicit-waits-selenium.html -- explanation of selenium wait types

    :param driver: WebDriver object we are forcing to wait
    :param elem_id: element id string we want to wait for
    :returns: webdriver element that has correctly loaded
    """
    try:
        # loaded_elem = WebDriverWait(driver, PAGE_LOAD_WAIT).until(EC.presence_of_element_located((By.ID, elem_id)))
        return WebDriverWait(driver, PAGE_LOAD_WAIT).until(EC.visibility_of_element_located((By.ID, elem_id)))
    except TimeoutException:
        logger.exception("Loading %s element on page took too much time; skipping this load.", elem_id)
        return None

def scrape_campground(driver: WebDriver, campground: Campground, start_date: datetime, num_days: int) -> bool:
    """
    Use Selenium WebDriver to load page, input desired start date, identify availability table
    for new data, use BeautifulSoup to parse html table, and use pandas DataFrame to identify
    availability inside the parsed table.

    Use Selenium's send_keys functionality to enter start date, see below for info:
        https://selenium-python.readthedocs.io/api.html#module-selenium.webdriver.common.keys
        https://stackoverflow.com/a/27799120
        platform-specific "select-all": https://stackoverflow.com/a/29807390
    Note on why we loop through ARROW_LEFT and BACKSPACE:
        - COMMAND/CTRL + 'a' doesn't work on linux
        - date_input.clear() doesn't work on any platform
        - BACKSPACE prior to sending date doesn't work on any platform
        - seems to be because recreation.gov auto-fills the date field if it is ever empty,
          which prevents us from clearing it. This way, we put in the date, backtrack to
          delete the old date, and then manually refresh the table. Works on mac/linux
          and headless/nonheadless.

    :param driver: WebDriver object previously instantiated
    :param campground: Campground object; url field will be loaded with driver
    :param start_date: datetime object identifying the date user wishes to arrive at campground
    :param num_days: int representation of number of nights user wishes to stay at campground
    :returns: True if start_date/num_days are available, False otherwise
    """
    try:
        logger.debug("\tGetting campground.url (%s) with driver", campground.url)
        driver.get(campground.url)
        logger.debug("\tFinding input box tag")
        date_input = wait_for_page_element_load(driver, INPUT_TAG_NAME)
        if date_input is None:  # if wait for page element load fails -> abandon this check immediately
            return False
        # date_input = driver.find_element_by_id(INPUT_TAG_NAME)
        logger.debug("\tSending new date with send_keys")
        date_input.send_keys(start_date.strftime("%m/%d/%Y"))
        for _ in range(10):     # backtrack to start of our input date
            date_input.send_keys(Keys.ARROW_LEFT)
        for _ in range(10):     # delete default start date
            date_input.send_keys(Keys.BACKSPACE)
        date_input.send_keys(Keys.RETURN)
        # manually click refresh table button to ensure valid table data
        # (if you don't do this every cell might be filled with 'x')
        refresh_table = driver.find_elements_by_xpath(AVAILABILITY_TABLE_REFRESH_XPATH)[0]
        refresh_table.click()

        # wait for table refresh/loading spinning wheel to disappear, otherwise table contents are gibberish/NaN
        # https://stackoverflow.com/a/29084080 -- wait for element to *not* be visible
        loading_tag = driver.find_element_by_class_name(TABLE_LOADING_TAG_CLASS)
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(EC.invisibility_of_element(loading_tag))
        logger.debug("\tFinding availability table tag")
        availability_table = wait_for_page_element_load(driver, AVAILABILITY_TABLE_TAG_NAME)
        if availability_table is None:  # if wait for page element load fails -> abandon this check immediately
            return False
        table_html = availability_table.get_attribute('outerHTML')
        soup = BeautifulSoup(table_html, 'html.parser')
        df = parse_html_table(soup)
        dates_available = all_dates_available(df, start_date, num_days)
        campground.error_count = 0      # if not errored -> reset error count to 0
        return dates_available
    except Exception as e:
        campground.error_count += 1     # if errored -> inc error count
        logger.exception("Campground %s (%s) parsing error!\n%s", campground.name, campground.id, e)
        logger.exception(str(traceback.format_exc()))
        return False

def run():
    """
    Runs scrape availability module for specific values, should be used for debugging only.
    """
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

if __name__ == "__main__":
    run()
