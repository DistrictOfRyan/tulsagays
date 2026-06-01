"""
Auto-create Facebook Events for top LGBTQ+ events of the week via Graph API.

Usage (standalone):
    python tools/create_fb_events.py [--dry-run]

Called automatically by tools/post_weekly.py after the carousel is posted.
"""

import sys
import os
import json
import logging
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

FB_GRAPH_BASE = "https://graph.facebook.com/v19.0"

_LGBTQ_KW = {
    "lgbtq", "queer", "gay", "lesbian", "trans",
    "bisexual", "nonbinary", "non-binary",
    "pride", "rainbow", "equality",
    "homo", "sapphic", "affirming",
}

# Sources that are explicitly LGBTQ+ orgs — events get bonus score even without keywords
_TRUSTED_LGBTQ_SRCS = {
    "twisted_arts", "freedom_oklahoma", "black_queer_tulsa",
    "okeq", "okeq_calendar", "homo_hotel", "council_oak_chorus",
    "dvl_tulsa", "antss", "qwc_tulsa", "studio_66", "lambda_bowling",
    "hotmess_sports", "pride_sports_tulsa", "taco_ok", "tulsa_fringe",
}


def _parse_start_end_unix(event: dict) -> tuple:
    """
    Parse event date + time string into (start_unix, end_unix).
    Returns (None, None) if parsing fails or event is all-day/ongoing.

    Handles formats like:
      "6:00 PM - 8:00 PM", "7:00 PM", "18:00", "7:00 PM – 10:00 PM"
    """
    date_str = (event.get("date") or "").strip()
    time_str = (event.get("time") or "").strip()

    if not date_str or not time_str:
        return None, None

    lower_time = time_str.lower()
    if any(kw in lower_time for kw in ("all day", "ongoing", "tbd", "tba", "varies")):
        return None, None

    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None, None

    # Split "6:00 PM - 8:00 PM" or "6:00 PM – 8:00 PM" on first dash/en-dash
    normalized = time_str.replace("–", "-").replace("—", "-")
    parts = [p.strip() for p in normalized.split("-", 1)]
    start_time_str = parts[0]
    end_time_str = parts[1] if len(parts) > 1 else None

    def _parse_time(t):
        for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p"):
            try:
                return datetime.strptime(t.strip(), fmt).time()
            except ValueError:
                continue
        return None

    start_t = _parse_time(start_time_str)
    if start_t is None:
        return None, None

    start_dt = datetime.combine(event_date, start_t)
    start_unix = int(start_dt.timestamp())

    if end_time_str:
        end_t = _parse_time(end_time_str)
        if end_t:
            end_dt = datetime.combine(event_date, end_t)
            if end_dt <= start_dt:  # crosses midnight
                end_dt += timedelta(days=1)
            end_unix = int(end_dt.timestamp())
        else:
            end_unix = int((start_dt + timedelta(hours=3)).timestamp())
    else:
        end_unix = int((start_dt + timedelta(hours=3)).timestamp())

    return start_unix, end_unix


def _lgbtq_score(event: dict) -> int:
    """Score how explicitly LGBTQ+ an event is (higher = stronger signal)."""
    score = 0
    if event.get("lgbtq_relevant"):
        score += 3
    if (event.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS:
        score += 2
    text = " ".join([
        event.get("name", ""),
        event.get("description", ""),
        event.get("venue", ""),
        event.get("source", ""),
    ]).lower()
    if any(kw in text for kw in _LGBTQ_KW):
        score += 2
    return score


def select_top_events(events: list, n: int = 2) -> list:
    """
    Pick top n events suitable for FB Event creation:
    - Has a specific start datetime (not 'ongoing' or date-only)
    - Has a venue/location name
    - Prefers explicitly LGBTQ+ events
    - Deduplicates by name

    Scoring weights:
      lgbtq_relevant flag    +3
      trusted LGBTQ source   +2
      LGBTQ keyword in text  +2
      priority=1 source      +2
      priority=2 source      +1
      has description        +1
      has URL                +1

    Returns list of (event_dict, start_unix, end_unix) tuples.
    """
    candidates = []
    seen_names: set = set()

    for e in events:
        name = (e.get("name") or "").strip()
        if not name:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue

        if not (e.get("venue") or "").strip():
            continue

        start_unix, end_unix = _parse_start_end_unix(e)
        if start_unix is None:
            continue

        seen_names.add(name_key)

        score = _lgbtq_score(e)
        priority = e.get("priority", 3)
        if priority == 1:
            score += 2
        elif priority == 2:
            score += 1
        if e.get("description"):
            score += 1
        if e.get("url"):
            score += 1

        candidates.append((score, e, start_unix, end_unix))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [(e, su, eu) for _, e, su, eu in candidates[:n]]


def create_facebook_event(event: dict, page_id: str, access_token: str) -> "str | None":
    """
    Creates a Facebook Event via Graph API.
    POST /{page_id}/events
    Fields: name, description, start_time (Unix timestamp), end_time, place
    Returns FB event ID on success, None on failure.
    """
    name = (event.get("name") or "").strip()

    start_unix, end_unix = _parse_start_end_unix(event)
    if start_unix is None:
        logger.warning("[FB Events] Skipping '%s' — cannot parse start time", name)
        return None

    description_parts = []
    desc = (event.get("description") or event.get("website_description") or "").strip()
    if desc:
        description_parts.append(desc)
    if event.get("url"):
        description_parts.append(f"\nMore info: {event['url']}")
    description_parts.append("\n\nPosted by TulsaGays.com — Your guide to LGBTQ+ Tulsa")
    description = "\n".join(description_parts)

    venue_name = (event.get("venue") or "Tulsa, OK").strip()

    payload = {
        "name": name,
        "description": description,
        "start_time": start_unix,
        "end_time": end_unix,
        "place": json.dumps({"name": venue_name}),
        "access_token": access_token,
    }

    url = f"{FB_GRAPH_BASE}/{page_id}/events"
    logger.info("[FB Events] Creating event '%s' at %s (unix %d)", name, venue_name, start_unix)

    try:
        resp = requests.post(url, data=payload, timeout=30)
        data = resp.json()

        if "error" in data:
            err = data["error"]
            logger.error(
                "[FB Events] Failed to create '%s': %s (code %s)",
                name, err.get("message"), err.get("code"),
            )
            print(f"[FB Events] ERROR creating '{name}': {err.get('message')}")
            return None

        event_id = data.get("id")
        if event_id:
            fb_url = f"https://www.facebook.com/events/{event_id}"
            logger.info("[FB Events] Created '%s': %s", name, fb_url)
            print(f"[FB Events] Created: '{name}' → {fb_url}")
            return event_id

        logger.error("[FB Events] No ID in response for '%s': %s", name, data)
        return None

    except Exception as exc:
        logger.error("[FB Events] Exception creating '%s': %s", name, exc)
        print(f"[FB Events] Exception creating '{name}': {exc}")
        return None


def run_event_creation(events: list, page_id: str, access_token: str) -> None:
    """Select top events and create FB Events for each. Log results."""
    if not page_id or not access_token:
        print("[FB Events] Skipped — PAGE_ID or access_token not configured.")
        return

    if not events:
        print("[FB Events] No events to process.")
        return

    top = select_top_events(events, n=2)

    if not top:
        print("[FB Events] No qualifying events (need date + time + venue).")
        return

    print(f"\n[FB Events] Creating {len(top)} Facebook Event(s)...")
    for event, _su, _eu in top:
        print(f"  → {event['name']}  ({event.get('date', '?')} {event.get('time', '?')}  @ {event.get('venue', '?')})")

    created = []
    for event, _su, _eu in top:
        event_id = create_facebook_event(event, page_id, access_token)
        if event_id:
            created.append((event["name"], event_id))

    print(f"[FB Events] Done. {len(created)}/{len(top)} events created successfully.")


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Create Facebook Events for top LGBTQ+ events")
    parser.add_argument("--dry-run", action="store_true", help="Print selected events without creating")
    args = parser.parse_args()

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    import config

    with open(ROOT / "meta_api_config.json", encoding="utf-8") as f:
        meta_cfg = json.load(f)

    _page_id = meta_cfg.get("page_id") or config.TULSAGAYS_PAGE_ID
    _access_token = config.TULSAGAYS_PAGE_ACCESS_TOKEN

    week_key = config.current_week_key()
    events_file = ROOT / "data" / "events" / f"{week_key}_all.json"
    if not events_file.exists():
        print(f"No events file found: {events_file}")
        sys.exit(1)

    with open(events_file, encoding="utf-8") as f:
        edata = json.load(f)
    events = edata if isinstance(edata, list) else edata.get("events", [])

    if args.dry_run:
        top = select_top_events(events, n=2)
        print(f"DRY RUN — would create {len(top)} Facebook Event(s):")
        for e, su, eu in top:
            dt_start = datetime.fromtimestamp(su).strftime("%Y-%m-%d %H:%M")
            dt_end = datetime.fromtimestamp(eu).strftime("%H:%M")
            print(f"  • {e['name']}")
            print(f"    Time:  {dt_start} – {dt_end}")
            print(f"    Venue: {e.get('venue', 'N/A')}")
            print(f"    Source: {e.get('source', '?')}  lgbtq_relevant={e.get('lgbtq_relevant')}")
        sys.exit(0)

    run_event_creation(events, _page_id, _access_token)
