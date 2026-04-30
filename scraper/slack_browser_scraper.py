"""Slack channel event scraper — browser-extracted results reader.

Slack requires authentication and JavaScript rendering. This module uses a
two-step approach:

  Step 1 (Python): Check for data/slack_events_browser.json written by the
    browser extraction step. If it exists and matches the current week, read
    and return events. If missing or stale, write data/slack_browser_needed.flag
    and return [] so the caller knows to trigger the browser step.

  Step 2 (Claude-in-Chrome, via SKILL.md): Navigate to each Slack channel,
    read all visible messages, extract events, write slack_events_browser.json,
    then re-run the scraper.

Channels scraped:
  - #events-local (CGV2YLJSG): General Tulsa community events. All included —
    the queer community shows up for all of Tulsa, not just LGBTQ-tagged events.
  - #unite-lgbtq-plus (CU36YG88K): LGBTQ+-specific events.

Workspace: TulsaRemote (TF1E6FCR5)
Deep-link: https://tulsaremote.slack.com/archives/CGV2YLJSG

HOW TO EXTRACT (for SKILL.md / Claude-in-Chrome):
  1. Navigate to https://app.slack.com/client/TF1E6FCR5/CGV2YLJSG
     If redirected to desktop, click "open this link in your browser"
  2. Dismiss any cookie/notification banners
  3. Read the page using read_page (ref_99 subtree, depth=12)
  4. Extract events — look for:
     - Event names (first meaningful line of each message)
     - Dates (patterns: "May 1st", "Saturday, May 2", "YYYY-MM-DD", "today/tomorrow/this/next week")
     - Times ("5:00 PM", "5-9PM", "7:30-9:30 PM")
     - Venues (after "at", "@", "Location:", address patterns)
     - URLs (Eventbrite, givebutter, experiencetulsa, etc.)
  5. Include ALL events from current Mon-Sun week — not just LGBTQ-tagged ones
  6. Repeat for #unite-lgbtq-plus: https://app.slack.com/client/TF1E6FCR5/CU36YG88K
  7. Write extracted events to data/slack_events_browser.json (format below)
  8. Delete data/slack_browser_needed.flag if it exists

JSON format for slack_events_browser.json:
  {
    "extracted_at": "YYYY-MM-DDTHH:MM:SS",
    "week": "YYYY-WNN",
    "channels": ["#events-local", "#unite-lgbtq-plus"],
    "events": [
      {
        "name": "Event Name",
        "date": "YYYY-MM-DD",
        "time": "5:00 PM",
        "venue": "Venue, Tulsa, OK",
        "description": "...",
        "url": "https://...",
        "source_channel": "#events-local",
        "source_note": "Posted by username on date"
      }
    ]
  }
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_NAME      = "slack_events_local"
BROWSER_JSON     = os.path.join(config.DATA_DIR, "slack_events_browser.json")
FLAG_FILE        = os.path.join(config.DATA_DIR, "slack_browser_needed.flag")
WORKSPACE_ID     = "TF1E6FCR5"
CHANNEL_EVENTS   = "CGV2YLJSG"   # #events-local
CHANNEL_LGBTQ    = "CU36YG88K"   # #unite-lgbtq-plus


def _get_week_key(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    return f"{date.year}-W{date.isocalendar()[1]:02d}"


def _is_current_week(extracted_at: str) -> bool:
    """Return True if the extracted_at timestamp is from the current Mon-Sun week."""
    try:
        dt = datetime.fromisoformat(extracted_at)
        return _get_week_key(dt) == _get_week_key()
    except Exception:
        return False


def _write_browser_flag():
    """Write sentinel so SKILL.md knows to open Slack with Claude-in-Chrome."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    week_key = _get_week_key()
    with open(FLAG_FILE, "w") as f:
        f.write(
            f"slack_browser_needed\n"
            f"week:{week_key}\n"
            f"generated:{datetime.now().isoformat()}\n"
            f"channels:{CHANNEL_EVENTS},{CHANNEL_LGBTQ}\n"
            f"workspace:{WORKSPACE_ID}\n"
            f"url:https://app.slack.com/client/{WORKSPACE_ID}/{CHANNEL_EVENTS}\n"
        )
    logger.warning(
        f"[{SOURCE_NAME}] No current-week Slack data found — "
        f"browser flag written to {FLAG_FILE}. "
        f"SKILL.md will use Claude-in-Chrome to extract events."
    )


def _load_browser_json() -> Optional[Dict]:
    """Load slack_events_browser.json if it exists and is current-week."""
    if not os.path.exists(BROWSER_JSON):
        logger.info(f"[{SOURCE_NAME}] {BROWSER_JSON} not found")
        return None

    try:
        with open(BROWSER_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"[{SOURCE_NAME}] Failed to read {BROWSER_JSON}: {e}")
        return None

    extracted_at = data.get("extracted_at", "")
    if not _is_current_week(extracted_at):
        logger.info(
            f"[{SOURCE_NAME}] {BROWSER_JSON} is from week {data.get('week')} "
            f"(current: {_get_week_key()}) — stale, triggering browser"
        )
        return None

    return data


def _events_from_json(data: Dict) -> List[Dict]:
    """Convert the browser JSON format to scraper event dicts."""
    scraper = BaseScraper()
    scraper.source_name = SOURCE_NAME

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

    events = []
    raw_events = data.get("events", [])

    for raw in raw_events:
        date_str = raw.get("date", "")

        # Filter to current week
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if not (monday <= dt <= sunday):
                    logger.debug(f"[{SOURCE_NAME}] Skipping out-of-week: {raw.get('name')} on {date_str}")
                    continue
            except ValueError:
                pass  # Include undated events

        event = scraper.make_event(
            name=raw.get("name", ""),
            date=date_str,
            time=raw.get("time", ""),
            venue=raw.get("venue", ""),
            description=raw.get("description", ""),
            url=raw.get("url", ""),
            priority=2,
        )
        # Tag by channel for downstream filtering
        channel = raw.get("source_channel", "#events-local")
        if "lgbtq" in channel.lower() or "unite" in channel.lower():
            event["source"] = "slack_unite_lgbtq_plus"
        else:
            event["source"] = "slack_events_local"

        events.append(event)

    logger.info(f"[{SOURCE_NAME}] Loaded {len(events)} events from {BROWSER_JSON}")
    return events


def scrape() -> List[Dict]:
    """Return Slack events for the current week.

    If slack_events_browser.json is current, read from it.
    Otherwise write the browser flag and return [] — SKILL.md will handle
    the browser extraction and re-run.
    """
    data = _load_browser_json()
    if data is not None:
        return _events_from_json(data)

    _write_browser_flag()
    return []


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    results = scrape()
    print(f"\n=== Slack Events: {len(results)} events this week ===")
    for e in results:
        print(f"  {e['date']} {e.get('time',''):10} | {e['name']} @ {e.get('venue','')}")
