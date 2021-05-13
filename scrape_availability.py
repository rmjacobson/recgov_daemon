"""
#TODO add module description
"""

from time import sleep
import logging
import pandas as pd
from bs4 import BeautifulSoup
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

def do_stuff(url, date_str):
    """
    blah
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
        date_input.send_keys(date_str)
        date_input.send_keys(Keys.RETURN)
        sleep(5)

        availability_table = driver.find_element_by_id(availability_table_tag_name)
        table_html = availability_table.get_attribute('outerHTML')
        soup = BeautifulSoup(table_html, 'html.parser')
        df = parse_html_table(soup)
        print(df)
    except Exception as e:
        l.critical(print(traceback.format_exc()))
    finally:
        sleep(15)
        driver.close()

if __name__ == "__main__":
    kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    date_str = "09/19/2021"
    do_stuff(kirk_creek, date_str)
