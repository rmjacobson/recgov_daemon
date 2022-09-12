"""
utils.py

fill this out later
"""

import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from selenium.webdriver.chrome.webdriver import WebDriver

logger = logging.getLogger(__name__)

# pylint: disable-next=unused-argument
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
    exit_msg = ("Received CTRL-C/SIGNINT or daemon completed;",
                "exiting gracefully/closing WebDriver if initialized.")
    logger.info(exit_msg)
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

    Note on logging:
    Python 3 logging is annoyingly confusing because of how inheiritance from the root logger works
    and how multiple modules all need to log to the same file. It's also annoying that no tutorial
    or official doc agrees on what is "best practice" between manually naming the loggers across
    modules vs. using __name__, or if it's best practice to create config/ini files, etc.

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
    rotating_handler = TimedRotatingFileHandler("logs/recgov.log",
                                                when="d", interval=1, backupCount=5)
    rotating_handler.suffix = "%Y-%m-%d"
    logging.basicConfig(
        handlers=[rotating_handler],
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-8s [%(filename)s:%(lineno)d:%(funcName)s] %(message)s",
    )
