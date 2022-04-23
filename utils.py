"""
utils.py

fill this out later
"""

import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from selenium.webdriver.chrome.webdriver import WebDriver

logger = logging.getLogger(__name__)

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
        logger.info("WebDriver Quit Successfully")
    sys.exit(0)

def set_low_network_quality(driver: WebDriver) -> None:
    """
    Set WebDriver to simulate low network quality -- 5ms additional latency, only 500kb
    throughput. Mostly used when testing the load actions of the availability table; sometimes
    there is a web element that shows up and spins for a while while the wait happens and it
    can be difficult to find the name for that without the appropriate delays set.

    Should never be used in production code, but left here for future testing needs.
    """
    latency_delay_ms = 5
    download_throughput_kb = 500
    upload_throughput_kb = 500
    driver.set_network_conditions(
        offline=False,
        latency=latency_delay_ms,
        download_throughput=download_throughput_kb,
        upload_throughput=upload_throughput_kb)

def setup_logging() -> None:
    """
    Set logging for whole project. This function is called from wherever the program
    is invoked. Could be from different places given development of different components
    separately.
    """
    rotating_handler = TimedRotatingFileHandler("logs/recgov.log", when="d", interval=1,  backupCount=5)
    rotating_handler.suffix = "%Y-%m-%d"
    logging.basicConfig(
        handlers=[rotating_handler],
        level=logging.INFO,
        format="[%(asctime)s] %(filename)s:%(lineno)d [%(name)s]%(levelname)s - %(message)s",
    )
