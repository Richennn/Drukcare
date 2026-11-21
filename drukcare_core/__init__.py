"""DrukCare shared core.

This package is used by all three apps (Tkinter, Gradio and Streamlit) so they
read and write the same local CSV files and behave the same way.

Time zone: every date and time in DrukCare is Bhutan time (BTT, UTC+6).
Online hosts such as Streamlit Cloud run on UTC, which made "now", "today",
overdue doses and reminders six hours early.  Setting the process time zone
here, before any app reads the clock, fixes datetime.now() and date.today()
everywhere.  Set the DRUKCARE_TZ environment variable to use another zone.
"""
import os
import time

APP_TIMEZONE = os.environ.get("DRUKCARE_TZ", "Asia/Thimphu")

os.environ["TZ"] = APP_TIMEZONE
if hasattr(time, "tzset"):          # Linux / macOS (e.g. Streamlit Cloud)
    time.tzset()
# On Windows time.tzset() does not exist; there the computer's own clock is used,
# which is already Bhutan time on a PC in Bhutan.
