"""One-shot wrapper to re-run the scrape with the week range pinned to W20 (May 11-17, 2026).

Used by the Sunday pre-scrape automation when today (Sunday) is the last day of the
prior ISO week and the upcoming-week target is the next ISO week.
"""
import sys, os, logging
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import scraper.runner as rn

W20_MONDAY = datetime(2026, 5, 11, 0, 0, 0)
W20_SUNDAY = datetime(2026, 5, 17, 23, 59, 59, 999999)

def patched_week_range():
    return W20_MONDAY, W20_SUNDAY

def patched_week_key(date=None):
    return "2026-W20"

rn._get_week_range = patched_week_range
rn.get_week_key = patched_week_key

print("=" * 50)
print("SCRAPING EVENTS (forced W20: May 11-17 2026)")
print("=" * 50)
events = rn.main()
print(f"\nFinished: {len(events) if events else 0} events")
