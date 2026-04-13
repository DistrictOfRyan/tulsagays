"""Manual event input scraper.

Reads a local JSON file at C:\\Users\\willi\\tulsagays\\data\\manual_events.json.
This is the intake point for events William finds on Slack, in emails, or anywhere else.

The file format is a JSON array of event objects:
[
  {
    "name": "Event Name",
    "date": "2026-04-12",
    "time": "7:00 PM",
    "venue": "Venue Name",
    "description": "...",
    "url": "https://...",
    "source_note": "Tulsa Remote Slack #events"
  }
]

source_note is optional and informational only (not passed to the event dict).
All events are tagged source="manual" and priority=1 so they rank at the top.
If the file doesn't exist or is empty/malformed, returns [] gracefully.
"""

import sys
import os
import json
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

MANUAL_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "manual_events.json",
)


def scrape() -> List[Dict]:
    """Read manual_events.json and return normalized event dicts.

    Returns [] if the file does not exist, is empty, or cannot be parsed.
    All events get source="manual" and priority=1.
    """
    if not os.path.exists(MANUAL_EVENTS_PATH):
        logger.info("[manual_input] No manual_events.json found at %s — skipping", MANUAL_EVENTS_PATH)
        return []

    try:
        with open(MANUAL_EVENTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("[manual_input] Failed to read manual_events.json: %s", e)
        return []

    if not isinstance(raw, list):
        logger.error("[manual_input] manual_events.json must be a JSON array — got %s", type(raw).__name__)
        return []

    events = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            logger.warning("[manual_input] Skipping entry %d — not an object", i)
            continue

        name = (item.get("name") or "").strip()
        if not name:
            logger.warning("[manual_input] Skipping entry %d — missing 'name'", i)
            continue

        event = {
            "name": name,
            "date": (item.get("date") or "").strip(),
            "time": (item.get("time") or "").strip(),
            "venue": (item.get("venue") or "").strip(),
            "description": (item.get("description") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "priority": 1,  # Manually curated events always rank high
            "source": "manual",
        }

        # Log source_note for traceability but don't include in event dict
        source_note = item.get("source_note", "")
        if source_note:
            logger.info("[manual_input] Loaded '%s' (source: %s)", name, source_note)
        else:
            logger.info("[manual_input] Loaded '%s'", name)

        events.append(event)

    logger.info("[manual_input] Loaded %d manual event(s) from %s", len(events), MANUAL_EVENTS_PATH)
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['venue']} | P{e['priority']}")
    print(f"\nTotal: {len(results)} manual event(s)")
