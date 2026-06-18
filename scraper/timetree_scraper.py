"""TimeTree public calendar scraper for 'Tulsa Isn't Boring'.

Fetch order:
  1. JSON API (api/v2 public_events) -- the real data source the web app uses.
     Two-step: GET the public page to mint a csrf-token + _session_id cookie,
     then call the public_events endpoint with x-csrf-token + x-timetreea headers.
     Recurring events are returned as series MASTERS (start_at = series start),
     so RRULE strings in `recurrences` are expanded to find THIS WEEK's instances.
  2. Playwright headless browser -- JS-rendered page fallback.
  3. Flag file written -- signals SKILL.md to use Claude-in-Chrome as final fallback.

The .ics feed used by the old version 404s for this calendar (TimeTree never
served one for it), which is why the scraper silently returned 0 events for weeks.

The flag file path: data/timetree_browser_needed.flag
"""

import os
import re
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    _CT = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - fallback for odd installs
    from datetime import timezone as _tz
    _CT = _tz(timedelta(hours=-5))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper
import config

logger = logging.getLogger(__name__)

CAL_SLUG     = "tulsa_isnt_boring"
TIMETREE_URL = f"https://timetreeapp.com/public_calendars/{CAL_SLUG}"
API_EVENTS   = f"https://timetreeapp.com/api/v2/public_calendars/{CAL_SLUG}/public_events"
FLAG_FILE    = os.path.join(config.DATA_DIR, "timetree_browser_needed.flag")
SOURCE_NAME  = "tulsa_isnt_boring"

# Headers the TimeTree web client sends. x-timetreea identifies the web build;
# without it (and a valid csrf token) the API returns {"error":{"code":-401}}.
_CLIENT_HEADER = "web/2.1.0/en"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


# ── Week range helpers ────────────────────────────────────────────────────────

def _get_week_range() -> Tuple[datetime, datetime]:
    """Current Mon 00:00 .. Sun 23:59:59 as NAIVE local (Central) datetimes."""
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        monday.replace(hour=0,  minute=0,  second=0,  microsecond=0),
        sunday.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


def _ms_to_local(ms: int) -> datetime:
    """Convert a UTC epoch-millisecond timestamp to a naive Central datetime."""
    from datetime import timezone
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(_CT)
    return dt.replace(tzinfo=None)


# ── JSON API path ───────────────────────────────────────────────────────────

def _mint_session():
    """GET the public page to obtain a requests.Session (with _session_id
    cookie) and the csrf-token the API requires. Returns (session, csrf) or
    (None, None) on failure."""
    import requests
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA, "Accept": "text/html"})
        r = s.get(TIMETREE_URL, timeout=20)
        r.raise_for_status()
        m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', r.text) \
            or re.search(r'content="([^"]+)"[^>]*name="csrf-token"', r.text)
        if not m:
            logger.warning(f"[{SOURCE_NAME}] csrf-token not found on page")
            return None, None
        return s, m.group(1)
    except Exception as e:
        logger.warning(f"[{SOURCE_NAME}] session mint failed: {e}")
        return None, None


def _expand_occurrences(event: Dict, monday: datetime, sunday: datetime) -> List[datetime]:
    """Return the list of THIS-WEEK occurrence start-datetimes (naive Central)
    for an event, expanding RRULEs when present."""
    start_ms = event.get("start_at")
    if not start_ms:
        return []
    base = _ms_to_local(int(start_ms))

    rules = event.get("recurrences") or []
    if not rules:
        return [base] if monday <= base <= sunday else []

    # Expand each RRULE from the series start; collect in-week occurrences.
    try:
        from dateutil import rrule as _rr
    except ImportError:
        # No dateutil: best effort, treat as single event.
        return [base] if monday <= base <= sunday else []

    occ: List[datetime] = []
    rule_text = "\n".join(r for r in rules if isinstance(r, str))
    try:
        rs = _rr.rrulestr(rule_text, dtstart=base, forceset=True)
        # Cap the window slightly wider than the week to be safe.
        for d in rs.between(monday - timedelta(days=1),
                            sunday + timedelta(days=1), inc=True):
            if monday <= d <= sunday:
                occ.append(d)
    except Exception as e:
        logger.debug(f"[{SOURCE_NAME}] rrule expand failed for "
                     f"{event.get('title','?')}: {e}")
        if monday <= base <= sunday:
            occ.append(base)
    return occ


def _event_to_dicts(scraper: BaseScraper, event: Dict,
                    monday: datetime, sunday: datetime) -> List[Dict]:
    """Convert one API event (possibly recurring) into 0+ scraper event dicts."""
    title = (event.get("title") or "").strip()
    if not title:
        return []

    all_day  = bool(event.get("all_day"))
    venue    = (event.get("location_name") or "").strip()
    addr     = (event.get("location_address") or "").strip()
    if addr and addr not in venue:
        venue = f"{venue}, {addr}".strip(", ") if venue else addr

    desc = (event.get("note") or event.get("headline")
            or event.get("overview") or "").strip()
    url  = (event.get("link_url") or event.get("url")
            or event.get("location_url") or TIMETREE_URL).strip()

    out: List[Dict] = []
    for occ in _expand_occurrences(event, monday, sunday):
        date_str = occ.strftime("%Y-%m-%d")
        time_str = "" if all_day else occ.strftime("%I:%M %p").lstrip("0")
        out.append(scraper.make_event(
            name=title, date=date_str, time=time_str,
            venue=venue, description=desc, url=url, priority=1,
        ))
    return out


def _scrape_api() -> Optional[List[Dict]]:
    """Primary path: the public_events JSON API. Returns list, or None on failure."""
    session, csrf = _mint_session()
    if not session or not csrf:
        return None

    monday, sunday = _get_week_range()
    # Query a window padded around the week so recurrence masters are returned.
    from_ms = int((monday - timedelta(days=2)).timestamp() * 1000)
    to_ms   = int((sunday + timedelta(days=2)).timestamp() * 1000)
    params  = {"from": from_ms, "to": to_ms, "utc_offset": -18000}
    headers = {
        "x-timetreea": _CLIENT_HEADER,
        "x-csrf-token": csrf,
        "Accept": "application/json",
        "referer": TIMETREE_URL,
    }
    try:
        r = session.get(API_EVENTS, params=params, headers=headers, timeout=20)
        if r.status_code != 200:
            logger.warning(f"[{SOURCE_NAME}] API HTTP {r.status_code}: {r.text[:120]}")
            return None
        data = r.json()
    except Exception as e:
        logger.warning(f"[{SOURCE_NAME}] API request failed: {e}")
        return None

    raw = data.get("public_events", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        logger.warning(f"[{SOURCE_NAME}] unexpected API shape")
        return None

    scraper = BaseScraper()
    scraper.source_name = SOURCE_NAME
    events: List[Dict] = []
    for e in raw:
        try:
            events.extend(_event_to_dicts(scraper, e, monday, sunday))
        except Exception as ex:
            logger.debug(f"[{SOURCE_NAME}] event parse skipped: {ex}")

    logger.info(f"[{SOURCE_NAME}] API: {len(events)} this-week events "
                f"from {len(raw)} series")
    return events


# ── Playwright fallback ───────────────────────────────────────────────────────

def _scrape_playwright() -> Optional[List[Dict]]:
    """Capture the public_events API response from inside a real browser.

    Used only if the plain-requests CSRF flow fails (e.g. TimeTree tightens
    csrf minting). The browser performs the same API call the app makes; we
    intercept its JSON and reuse the same parser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"[{SOURCE_NAME}] playwright not installed, skipping")
        return None

    monday, sunday = _get_week_range()
    scraper = BaseScraper()
    scraper.source_name = SOURCE_NAME
    payloads: List[Dict] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page    = browser.new_page()

            def _on_resp(resp):
                if "public_events" in resp.url:
                    try:
                        payloads.append(resp.json())
                    except Exception:
                        pass

            page.on("response", _on_resp)
            page.goto(TIMETREE_URL, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(3000)
            browser.close()
    except Exception as e:
        logger.error(f"[{SOURCE_NAME}] Playwright failed: {e}", exc_info=True)
        return None

    events: List[Dict] = []
    for data in payloads:
        raw = data.get("public_events", []) if isinstance(data, dict) else []
        for e in raw:
            try:
                events.extend(_event_to_dicts(scraper, e, monday, sunday))
            except Exception:
                continue

    if events:
        # De-dupe (same event can appear in multiple captured payloads).
        seen, uniq = set(), []
        for e in events:
            key = (e["name"], e["date"], e["time"])
            if key not in seen:
                seen.add(key)
                uniq.append(e)
        logger.info(f"[{SOURCE_NAME}] Playwright/API-intercept: {len(uniq)} events")
        return uniq

    logger.warning(f"[{SOURCE_NAME}] Playwright captured no event payload")
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
    """Try JSON API, then Playwright, then write browser flag. Always returns a list."""
    if os.path.exists(FLAG_FILE):
        os.remove(FLAG_FILE)

    events = _scrape_api()
    if events:
        return events

    events = _scrape_playwright()
    if events:
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
        nm = e["name"].encode("ascii", "replace").decode()
        vn = e.get("venue", "").encode("ascii", "replace").decode()
        print(f"  {e['date']} {e['time']:10} | {nm} @ {vn}")
