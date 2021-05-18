"""
#TODO add module description
"""

from time import sleep
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pandas.core.frame import DataFrame
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
)
l = logging.getLogger(__name__)

def parse_html_table(table: BeautifulSoup) -> DataFrame:
    """
    Parse Beautifulsoup representation of recreation.gov availability table into a pandas dataframe.

    :param table: BeautifulSoup object containing just the availability table HTML
    :returns: pandas dataframe containing column names and row data
    """
    column_names = []
    recgov_row_tags = ['td', 'th']

    # get column names from the "second" row of the <thead> tag because the "first" row just contains the month string
    header_tag = table.find("thead")
    column_tags = header_tag.find_all("tr")
    columns = column_tags[1].find_all('th') 
    if len(columns) > 0 and len(column_names) == 0:
        for th in columns:
            column_names.append(th.get_text())

    # read rows in <tbody> tag for availability data, remove camp name icon if necessary to reduce confusing text
    body_tag = table.find("tbody")
    rows = body_tag.find_all("tr")
    df = DataFrame(columns=column_names, index=range(0,len(rows)))
    for r, row in enumerate(rows):
        cell_tags = row.find_all(recgov_row_tags)
        for c, cell in enumerate(cell_tags):
            icon = cell.find("div", {"class":"camp-location-name--icon"})
            if icon is not None:
                icon.decompose()
            df.iat[r,c] = cell.get_text()
    
    return df

def all_dates_available(df: DataFrame, start_date: datetime, num_days: int) -> bool:
    """
    Parse pandas DataFrame for the specific date columns matching the start date and number
    of nights we want to stay, search for 'A' string in df cells. Return True if every column
    has an availability (inlcuding if the daily availabilities are in different sites).

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
            l.debug("Found column (aka date) with no availability --> breaking")
            break
    l.debug("is available? %s", at_least_one_available)
    
    return at_least_one_available

def do_stuff(url: str, start_date_str: str, num_days: int):
    """
    #TODO rename this function
    #TODO add actual docstring when this function does everything we need it to do
    """
    input_tag_name = "single-date-picker-1"
    availability_table_tag_name = "availability-table"
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    
    try:
        driver.get(url)
        date_input = driver.find_element_by_id(input_tag_name)
        # see for Keys info:
        #   https://selenium-python.readthedocs.io/api.html#module-selenium.webdriver.common.keys
        #   https://stackoverflow.com/a/27799120
        date_input.send_keys(Keys.COMMAND + "a")
        date_input.send_keys(start_date_str)
        date_input.send_keys(Keys.RETURN)
        sleep(5)

        availability_table = driver.find_element_by_id(availability_table_tag_name)
        table_html = availability_table.get_attribute('outerHTML')
        soup = BeautifulSoup(table_html, 'html.parser')
        df = parse_html_table(soup)
        
        start_date = datetime.strptime(start_date_str, '%m/%d/%Y')
        if all_dates_available(df, start_date, num_days):
            l.info("WE HAVE SOMETHING AVAILABLE!")
        else:
            l.info("sad")
    except Exception as e:
        l.critical(print(traceback.format_exc()))
    finally:
        sleep(15)
        driver.close()

if __name__ == "__main__":
    # kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    mcgill = "https://www.recreation.gov/camping/campgrounds/231962/availability"
    # kirk_start_date_str = "09/17/2021"
    mcgill_start_date_str = "05/31/2021"
    num_days = 2
    do_stuff(mcgill, mcgill_start_date_str, num_days)
