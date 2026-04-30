"""TimeTree public calendar scraper for 'Tulsa Isn't Boring'.

Fetch order:
  1. iCal feed (.ics) -- fastest, most reliable
  2. Playwright headless browser -- JS-rendered page fallback
  3. Flag file written -- signals SKILL.md to use Claude-in-Chrome as final fallback

The flag file path: data/timetree_browser_needed.flag
If that file exists after `python main.py scrape`, the SKILL.md browser fallback
step will use Claude-in-Chrome to extract events manually and inject them.
"""

import os
import re
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper
import config

logger = logging.getLogger(__name__)

TIMETREE_URL = "https://timetreeapp.com/public_calendars/tulsa_isnt_boring"
ICAL_URL     = "https://timetreeapp.com/public_calendars/tulsa_isnt_boring.ics"
FLAG_FILE    = os.path.join(config.DATA_DIR, "timetree_browser_needed.flag")
SOURCE_NAME  = "tulsa_isnt_boring"


# ── Week range helpers ────────────────────────────────────────────────────────

def _get_week_range():
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        monday.replace(hour=0,  minute=0,  second=0,  microsecond=0),
        sunday.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


def _is_in_range(date_str: str) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday, sunday = _get_week_range()
        return monday <= dt <= sunday
    except ValueError:
        return False


# ── iCal parser ───────────────────────────────────────────────────────────────

def _parse_ical_datetime(raw: str):
    """Parse an iCal datetime value like 20260428T190000Z or 20260428.
    Returns (date_str, time_str) as ('YYYY-MM-DD', '7:30 PM') or ('', '').
    """
    raw = raw.strip()
    # Strip TZID=... prefix e.g. DTSTART;TZID=America/Chicago:20260428T190000
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1]
    raw = raw.rstrip("Z")
    try:
        if "T" in raw:
            dt = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
            return dt.strftime("%Y-%m-%d"), dt.strftime("%I:%M %p").lstrip("0")
        else:
            dt = datetime.strptime(raw[:8], "%Y%m%d")
            return dt.strftime("%Y-%m-%d"), ""
    except ValueError:
        return "", ""


def _parse_ical(text: str) -> List[Dict]:
    """Parse full iCal text and return this-week events as scraper dicts."""
    scraper = BaseScraper()
    scraper.source_name = SOURCE_NAME
    events = []

    for block in re.split(r"BEGIN:VEVENT", text)[1:]:
        end = block.find("END:VEVENT")
        if end != -1:
            block = block[:end]

        # Unfold RFC 5545 continuation lines (whitespace-prefixed)
        block = re.sub(r"\r?\n[ \t]", "", block)

        def _field(name):
            m = re.search(rf"^{name}[;:][^\r\n]*", block, re.MULTILINE | re.IGNORECASE)
            if not m:
                return ""
            raw = m.group(0)
            return raw.split(":", 1)[-1].strip() if ":" in raw else ""

        date_str, time_str = _parse_ical_datetime(_field("DTSTART"))
        if not _is_in_range(date_str):
            continue

        def _clean(s):
            return s.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").strip()

        name        = _clean(_field("SUMMARY"))
        description = _clean(_field("DESCRIPTION"))
        venue       = _clean(_field("LOCATION"))
        url         = _field("URL") or TIMETREE_URL

        if not name:
            continue

        events.append(scraper.make_event(
            name=name, date=date_str, time=time_str,
            venue=venue, description=description, url=url, priority=1,
        ))

    return events


def _scrape_ical() -> Optional[List[Dict]]:
    """Try the .ics feed. Returns event list on success, None on failure."""
    import requests
    try:
        resp = requests.get(ICAL_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TulsaGays/1.0)",
            "Accept": "text/calendar, text/plain, */*",
        })
        resp.raise_for_status()
        if "BEGIN:VCALENDAR" not in resp.text:
            logger.warning(f"[{SOURCE_NAME}] iCal response missing BEGIN:VCALENDAR")
            return None
        events = _parse_ical(resp.text)
        logger.info(f"[{SOURCE_NAME}] iCal: {len(events)} this-week events")
        return events
    except Exception as e:
        logger.warning(f"[{SOURCE_NAME}] iCal failed: {e}")
        return None


# ── Playwright fallback ───────────────────────────────────────────────────────

def _scrape_playwright() -> Optional[List[Dict]]:
    """Try headless Playwright. Returns event list on success, None on failure."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"[{SOURCE_NAME}] playwright not installed, skipping")
        return None

    scraper = BaseScraper()
    scraper.source_name = SOURCE_NAME
    events = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page    = browser.new_page()
            page.goto(TIMETREE_URL, timeout=30000)
            # Wait for event content to render
            try:
                page.wait_for_selector(
                    "[class*='event'], [class*='Event'], article, [class*='schedule']",
                    timeout=12000,
                )
            except Exception:
                pass  # Proceed with whatever loaded
            html = page.content()
            browser.close()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Pass 1: JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    if item.get("@type") not in ("Event", "SocialEvent", "MusicEvent"):
                        continue
                    raw_start = item.get("startDate", "")
                    if "T" in raw_start:
                        dt       = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                        date_str = dt.strftime("%Y-%m-%d")
                        time_str = dt.strftime("%I:%M %p").lstrip("0")
                    else:
                        date_str = raw_start[:10]
                        time_str = ""
                    if not _is_in_range(date_str):
                        continue
                    loc   = item.get("location", {})
                    venue = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                    events.append(scraper.make_event(
                        name=item.get("name", ""), date=date_str, time=time_str,
                        venue=venue, description=item.get("description", ""),
                        url=item.get("url", TIMETREE_URL), priority=1,
                    ))
            except Exception:
                continue

        if events:
            logger.info(f"[{SOURCE_NAME}] Playwright/JSON-LD: {len(events)} events")
            return events

        # Pass 2: Heuristic card parsing
        for elem in soup.select(
            "[class*='event'], [class*='Event'], [class*='card'], "
            "[class*='schedule'], article"
        ):
            text  = elem.get_text(" ", strip=True)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            date_match = re.search(
                r"\b(\w+ \d{1,2},?\s*\d{4}|\d{4}-\d{2}-\d{2})\b", text
            )
            if not date_match:
                continue
            date_str = BaseScraper.parse_date_flexible(date_match.group(1))
            if not _is_in_range(date_str):
                continue
            events.append(scraper.make_event(
                name=lines[0], date=date_str, time="", venue="",
                description=" ".join(lines[1:3]), url=TIMETREE_URL, priority=1,
            ))

        if events:
            logger.info(f"[{SOURCE_NAME}] Playwright/HTML: {len(events)} events")
            return events

        logger.warning(f"[{SOURCE_NAME}] Playwright rendered page but found no events")
        return None

    except Exception as e:
        logger.error(f"[{SOURCE_NAME}] Playwright failed: {e}", exc_info=True)
        return None


# ── Browser flag ──────────────────────────────────────────────────────────────

def _write_browser_flag():
    """Write sentinel file so SKILL.md knows to use Claude-in-Chrome."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(FLAG_FILE, "w") as f:
        f.write(
            f"timetree_browser_needed\n"
            f"generated:{datetime.now().isoformat()}\n"
            f"url:{TIMETREE_URL}\n"
        )
    logger.warning(
        f"[{SOURCE_NAME}] All automated methods failed -- "
        f"browser flag written to {FLAG_FILE}"
    )


# ── Public entry point ────────────────────────────────────────────────────────

def scrape() -> List[Dict]:
    """Try iCal, then Playwright, then write browser flag. Always returns a list."""
    # Clear any stale flag from a previous run
    if os.path.exists(FLAG_FILE):
        os.remove(FLAG_FILE)

    events = _scrape_ical()
    if events is not None:
        return events

    events = _scrape_playwright()
    if events is not None:
        return events

    _write_browser_flag()
    return []


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    results = scrape()
    print(f"\n=== Tulsa Isn't Boring: {len(results)} events this week ===")
    for e in results:
        print(f"  {e['date']} {e['time']:10} | {e['name']} @ {e.get('venue','')}")
