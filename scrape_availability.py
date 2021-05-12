"""
#TODO add module description
"""

from time import sleep
import logging
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
)
l = logging.getLogger(__name__)

def do_stuff(url, date_str):
    """
    blah
    """
    input_tag_name = "single-date-picker-1"
    availability_table_tag_name = "availability-table"
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    # driver = webdriver.Chrome(chrome_options=options)
    driver = webdriver.Chrome(ChromeDriverManager().install(), chrome_options=options)
    
    driver.get(url)
    date_input = driver.find_element_by_id(input_tag_name)
    date_input.send_keys(Keys.COMMAND + "a")
    date_input.send_keys(date_str)
    date_input.send_keys(Keys.RETURN)
    availability_table = driver.find_element_by_id(availability_table_tag_name)
    html = availability_table.get_attribute('innerHTML')
    print(str(html) + "\n\n\n\n\n\n\n\n\n")
    sleep(15)
    driver.close()

if __name__ == "__main__":
    kirk_creek = "https://www.recreation.gov/camping/campgrounds/233116/availability"
    date_str = "09/19/2021"
    do_stuff(kirk_creek, date_str)
