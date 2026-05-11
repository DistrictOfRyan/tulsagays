"""Regenerate W19 carousel slides with Tulsa Water Lantern Festival forced as EOTW.
Mirrors main.py:generate-all but overrides the pre-selected EOTW.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import config
from content.image_maker import create_carousel, save_carousel

WEEK_KEY = config.current_week_key()
EVENTS_PATH = os.path.join(config.EVENTS_DIR, f"{WEEK_KEY}_all.json")
POST_TYPE = "all"

with open(EVENTS_PATH, encoding="utf-8") as f:
    data = json.load(f)
events = data if isinstance(data, list) else data.get("events", [])

today = datetime.now().date()
mon = today - timedelta(days=today.weekday())
sun = mon + timedelta(days=6)

# Group by weekday name
days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
events_by_day = {d: [] for d in days_of_week}
for e in events:
    d_str = e.get('date', '')
    if not d_str:
        continue
    try:
        dt = datetime.strptime(d_str, '%Y-%m-%d').date()
    except ValueError:
        continue
    if not (mon <= dt <= sun):
        continue
    events_by_day[dt.strftime('%A')].append(e)

# Force EOTW
TARGET_NAME = "Elote's Cinco de Mayo Street Festival"
featured = None
for e in events:
    if (e.get('name') or '').strip() == TARGET_NAME:
        featured = e
        break

if not featured:
    print(f"ERROR: Could not find {TARGET_NAME} in events JSON.")
    sys.exit(1)

print(f"[forced eotw] {featured.get('name')} @ {featured.get('venue')}  date={featured.get('date')} time={featured.get('time')}")

# category_events expected by create_carousel — empty / minimal works
category_events = {}

date_range = f"{mon.strftime('%b %d')} - {sun.strftime('%b %d')}"
logo_path = config.LOGO_PATH if os.path.exists(config.LOGO_PATH) else None

images = create_carousel(
    category_events, POST_TYPE, date_range, logo_path,
    events_by_day=events_by_day,
    featured_event=featured,
)

output_dir = os.path.join(config.DATA_DIR, "posts", WEEK_KEY)
os.makedirs(output_dir, exist_ok=True)
paths = save_carousel(images, output_dir, f"{POST_TYPE}_")
print(f"Wrote {len(paths)} slides to {output_dir}")
for p in paths:
    print(f"  {os.path.basename(p)}")
