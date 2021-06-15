# recgov_daemon

Python app to check the recreation.gov Recreation Information Database (RIDB) for a variable set of campsites and notify given email address when campsite availability changes. Creation inspired by looking at campgrounds on recreation.gov after to the 2020 pandemic and finding that every campground in the entire Sierra Nevada mountain range was booked for every weekend until 6 months out. This is useful if you have a campground you want to visit at a specific time, but there's no current availability. If this daemon is running when somebody cancels their reservation, you will get an email and might be able to act on it quicker than others.

## Installation

After cloning this repo, follow the below steps to create a virtual environment and a logfile directory for recgov_daemon:

1. Use `virtualenvwrapper` to make a new Python 3 Virtual Environment. See [the official guide](https://virtualenvwrapper.readthedocs.io/en/latest/install.html#basic-installation) or [this easier-to-follow guide](https://medium.com/@gitudaniel/installing-virtualenvwrapper-for-python3-ad3dfea7c717) for details.
2. Run `workon <virtualenvname>` to activate venv.
3. Run `pip3 install -r requirements.txt` to install required packages.
4. Run `mkdir logs` (or equivalent command on Windows) to create directory for log files.
5. Set environment variables for `ridb_api_key`, `gmail_user` and `gmail_password` -- these are required to connect to the RIDB API and to the email account you wish to use as a notification-sender. Note that you can automate this inside the `virtualenvwrapper` setup by editing the `/path/to/virtualenvs/config/dir/<virtualenvname>/bin/postactivate` file.

## Running the daemon

Ensure the venv created in the [Installation](#installation) section is activated by running `workon <virtualenvname>`, then run:

```bash
python3 daemon.py -s <MM/DD/YYYY> -n <number of days you want to camp> -e <email address you want to be notified at> [--lat <latitude> --lon <longitude> -r <radius in miles>] [--campground_ids <campground_id1,id2,...idN>] &
```

- `-s` specifies the date you want to start camping (e.g. your arrival date).
- `-n` specifies the number of days you want to camp (e.g. 2); this must be a number greater than 0.
- `-e` specifies the email you want to be notified at (the daemon will send emails from the email address you specify in the environment variables mentioned above).
- You _must_ provide either a latitude/longitude/radius, or a specific set of campground IDs, or both.
  - The daemon will search RIDB for campground facilities within a circle of the provided radius centered at the given latitude/longitude, and/or search speficially for campgrounds specified by ID.
  - A "campground ID" is an integer GUID associated with a campground facility in RIDB/recreation.gov. If you are unsure what this is, find the campground you want to visit on recreation.gov, and look at the URL for the element _after_ the `camping/campgrounds/` path. For example, the McGill Campground has the URL `<https://www.recreation.gov/camping/campgrounds/231962/` and its campground ID would be `231962`.
- `&` will run the process in the background. If you aren't running this in a tmux session, you probably want to do this and then keep track of the PID.
- `-h` will print out a help/usage message.

A working example to search for both campgrounds in a radius of a given lat/lon and specific campgrounds is provided below. The options translate to "I want to camp starting on June 25, 2021 for 2 nights, either within a 20 mile radius of 35.994431 North by -121.394325 West, or specifically at the Kirk Creek (233116) or McGill (231962) Campgrounds; please send notification emails about specific available campgrounds to some.emai@gmail.com."

```bash
python daemon.py -s 06/25/2021 -n 2 -e some.email@gmail.com --lat 35.994431 --lon -121.394325 -r 20 --campground_ids 233116,231962 &
```

The daemon will run (and continue to print logging messages) until either the start date has passed or the daemon is killed manually. Use the `fg` command to foreground the process, `less logs/recgov.log` to view the most current logging output. If the process is in the foreground, use `CTRL-C` once to end the process gracefully. If the process is in the background, use `kill -INT <PID>` to send `SIGINT` to end the process gracefully.

## Further Development

There is a small list of issues/bugs/feature reqs at <https://github.com/rmjacobson/recgov_daemon/issues>, please use this if you have recommendations or requests.

## References

This project involved a lot of googling.  For easy viewing, see the sections for most-googled topics below.

### RIDB API

- <https://www.recreation.gov/use-our-data>
- <https://ridb.recreation.gov/docs#/>

### Parsing

- Sending keystrokes to webpages:
  - <https://selenium-python.readthedocs.io/api.html#module-selenium.webdriver.common.keys>
  - <https://stackoverflow.com/a/27799120>
- Difference between quitting and closing a selenium webdriver: <https://stackoverflow.com/questions/15067107/difference-between-webdriver-dispose-close-and-quit>

### Logging

- Refs used to create this specific logging regime:
  - <https://gist.github.com/gene1wood/73b715434c587d2240c21fc83fad7962>
  - <https://timber.io/blog/the-pythonic-guide-to-logging/>
- Ref for format: <https://www.pylenin.com/blogs/python-logging-guide/#configuring-a-main-logger>
- Ref for file config (not used):
  - <https://www.internalpointers.com/post/logging-python-sub-modules-and-configuration-files>
  - <http://antonym.org/2005/03/a-real-python-logging-example.html>
- Generic Logging Principles: <https://peter.bourgon.org/blog/2017/02/21/metrics-tracing-and-logging.html>
