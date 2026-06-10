"""Major Tulsa events loader.

Curated list of Tulsa's marquee / signature civic events (Tulsa Tough, the
Route 66 Centennial, Tulsa State Fair, Oktoberfest, Mayfest, Greek Festival,
etc.). William's rule: "we have to have the major events on our website at
least." These big annual events have fixed, predictable dates and their own
sites are often JS-heavy or flaky, so we keep a curated dated list rather than
depend on a scraper firing perfectly the right week.

Reads data/major_tulsa_events.json — same object shape as manual_events.json:
[
  {
    "name": "Saint Francis Tulsa Tough",
    "date": "2026-06-05",
    "time": "All day",
    "venue": "Tulsa Arts District / Riverside",
    "description": "short slide pitch",
    "website_description": "long website copy",
    "url": "https://www.tulsatough.com/",
    "priority": 3,
    "source_note": "CONFIRMED via tulsatough.com 2026 schedule"
  }
]

Differences from manual_input:
  - source = "major_tulsa" (NOT "manual"): these are civic, not LGBTQ-curated,
    so they should not get the LGBTQ-community rendering treatment. They still
    render on the website (gen_website_html renders every source) and stay in
    the featured-candidate pool for slow weeks via the community_event path.
  - default priority = 3 (website + slow-week feature only) so a city festival
    never bumps an actual LGBTQ event out of the slide's featured slots. An
    explicit per-event priority is honored when set.

Out-of-week dates are dropped by runner.apply_quality_filters Filter 3, so the
full annual list can live here and each event surfaces only in its own week.
"""

import sys
import os
import json
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: F401  (kept for path/config parity with sibling scrapers)

logger = logging.getLogger(__name__)

MAJOR_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "major_tulsa_events.json",
)


def scrape() -> List[Dict]:
    """Read major_tulsa_events.json and return normalized event dicts.

    Returns [] if the file does not exist, is empty, or cannot be parsed.
    All events get source="major_tulsa"; priority defaults to 3.
    """
    if not os.path.exists(MAJOR_EVENTS_PATH):
        logger.info("[major_events] No major_tulsa_events.json found at %s — skipping", MAJOR_EVENTS_PATH)
        return []

    try:
        with open(MAJOR_EVENTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("[major_events] Failed to read major_tulsa_events.json: %s", e)
        return []

    if not isinstance(raw, list):
        logger.error("[major_events] major_tulsa_events.json must be a JSON array — got %s", type(raw).__name__)
        return []

    events = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            logger.warning("[major_events] Skipping entry %d — not an object", i)
            continue

        name = (item.get("name") or "").strip()
        if not name:
            logger.warning("[major_events] Skipping entry %d — missing 'name'", i)
            continue

        try:
            priority = int(item.get("priority")) if item.get("priority") not in (None, "") else 3
        except (TypeError, ValueError):
            priority = 3

        event = {
            "name": name,
            "date": (item.get("date") or "").strip(),
            "time": (item.get("time") or "").strip(),
            "venue": (item.get("venue") or "").strip(),
            "description": (item.get("description") or "").strip(),
            "website_description": (item.get("website_description") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "priority": priority,
            "source": "major_tulsa",
        }

        source_note = item.get("source_note", "")
        if source_note:
            logger.info("[major_events] Loaded '%s' (%s)", name, source_note)
        else:
            logger.info("[major_events] Loaded '%s'", name)

        events.append(event)

    logger.info("[major_events] Loaded %d major event(s) from %s", len(events), MAJOR_EVENTS_PATH)
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['venue']} | P{e['priority']}")
    print(f"\nTotal: {len(results)} major event(s)")
