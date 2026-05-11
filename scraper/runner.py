"""Orchestrator that runs all scrapers, applies quality filters, deduplicates, sorts, and saves events."""

import sys
import os
import json
import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from scraper import (
    recurring,
    okeq_calendar,
    twisted_arts,
    specific_orgs,
    eventbrite_meetup,
    community_calendars,
    extended_calendars,
    aa_meetings,
    homo_hotel,
    community_groups,
    qlist,
    churches,
    bars,
    manual_input,
    tulsa_arts_district,
    facebook_events,
    ticketing_sites,
    timetree_scraper,
    slack_browser_scraper,
)

logger = logging.getLogger(__name__)

# Playwright scrapers are optional -- only available if playwright is installed
try:
    from scraper import playwright_scrapers as _playwright_scrapers
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _playwright_scrapers = None
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed -- playwright_scrapers will be skipped")

# ── Constants ────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.75

# Generic LGBTQ keywords (universal — same across cities).
LGBTQ_KEYWORDS = [
    # Explicit identity
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic", "two-spirit", "twospirit",
    # Queer-adjacent / community-coded: events that reliably draw queer crowds
    # even without explicit LGBTQ branding
    "oddities", "curiosities",          # Oddities & Curiosities touring market
    "burlesque", "cabaret",             # queer performance traditions
    "feminist", "radical",              # progressive cultural events
    "night market", "art market", "bazaar", "market",  # queer-popular market formats
    "wiz",                              # The Wiz (Black/queer cultural touchstone)
    "greenwood", "black wall street",   # Black cultural events (intersectional)
    "boots riley",                      # radical filmmaker, queer community following
    # Cultural event types — these are table stakes for community relevance
    # at arts venues; the venue list (COMMUNITY_PARTNER_KEYWORDS) does the curation
    "screening", "film festival", "documentary",   # film culture
    "exhibition", "opening reception", "art opening",  # art openings
    "workshop", "panel discussion", "panel", "lecture",  # community learning
    "fundraiser", "benefit show", "benefit concert",     # community support
    "cultural festival", "heritage",                     # cultural programming
    "open mic", "poetry",                                # alternative performance
]

# Generic non-LGBTQ blocklist — sports, oil/gas, mass non-LGBTQ religious events.
# Patterns most US cities will share. City-specific additions live in
# config.NON_LGBTQ_BLOCKLIST_CITY (e.g. local college sports team names).
_GENERIC_NON_LGBTQ_BLOCKLIST = [
    # College/pro sports (universal)
    "football game", "football season", "nfl ", " nfl", "nba ", " nba",
    "mlb ", " mlb", "nhl ", " nhl", "college football", "college basketball",
    "nascar", "ufc ", " ufc", "mma fight",
    # Petroleum/energy industry conferences
    "society of petroleum", "petroleum engineers",
    "spe ior", "spe improved", "improved oil recovery",
    "reservoir heterogeneity", "reservoir characterization",
    "oil and gas conference", "oil & gas conference",
    "drilling conference", "pipeline conference", "petroleum conference",
    # Non-LGBTQ religious mass events
    "revival meeting", "men's prayer breakfast", "prayer rally",
    "women's prayer breakfast",
]

# Generic junk names — scraper artifacts to discard regardless of city.
JUNK_NAMES = {
    "map", "google calendar", "get your tickets", "buy tickets",
    "learn more", "view all", "see more", "load more", "rsvp",
    "register", "sign up", "donate", "subscribe", "contact us",
    "home", "about", "menu", "calendar", "events", "back",
}

# Compose city-specific values from config (with safe fallbacks for new-city scaffolds).
LGBTQ_SOURCES = getattr(config, "LGBTQ_SOURCES", set())
COMMUNITY_PARTNER_KEYWORDS = getattr(config, "COMMUNITY_PARTNER_KEYWORDS", [])
NON_LGBTQ_BLOCKLIST = _GENERIC_NON_LGBTQ_BLOCKLIST + getattr(config, "NON_LGBTQ_BLOCKLIST_CITY", [])



# ── Normalization & dedup ─────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _are_similar(name_a: str, name_b: str) -> bool:
    a = _normalize(name_a)
    b = _normalize(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


def _same_date(date_a: str, date_b: str) -> bool:
    if not date_a or not date_b:
        return True
    return date_a.strip() == date_b.strip()


def deduplicate(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events based on name + date similarity."""
    if not events:
        return []

    unique = []
    for event in events:
        is_dup = False
        for i, existing in enumerate(unique):
            if _are_similar(event["name"], existing["name"]) and _same_date(event["date"], existing["date"]):
                is_dup = True
                # Collect all unique URLs from both events before deciding winner
                merged_urls = list(dict.fromkeys(
                    (existing.get("source_urls") or []) + (event.get("source_urls") or [])
                ))
                if event["priority"] < existing["priority"]:
                    unique[i] = event
                elif event["priority"] == existing["priority"]:
                    event_info = sum(1 for v in event.values() if v)
                    existing_info = sum(1 for v in existing.values() if v)
                    if event_info > existing_info:
                        unique[i] = event
                # Apply the merged URL list to whichever event won
                unique[i]["source_urls"] = merged_urls
                break
        if not is_dup:
            unique.append(event)

    return unique


# ── Quality filters ───────────────────────────────────────────────────────────

def _get_week_range():
    """Return (monday, sunday) datetime objects for the current week."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0), sunday.replace(hour=23, minute=59, second=59, microsecond=999999)


def _is_junk_name(name: str) -> bool:
    """Return True if the name is clearly navigation/UI text, not an event."""
    if not name or len(name) < 5:
        return True
    if name.lower().strip() in JUNK_NAMES:
        return True
    if len(name) > 200:
        return True
    return False


def _is_in_current_week(date_str: str) -> bool:
    """Return True if date_str (YYYY-MM-DD) falls within the current Mon-Sun week."""
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday, sunday = _get_week_range()
        return monday <= dt <= sunday
    except ValueError:
        return False


def _is_clearly_not_lgbtq(event: Dict) -> bool:
    """Return True if this event matches the non-LGBTQ blocklist — exclude regardless of source."""
    combined = " ".join([
        (event.get("name") or ""),
        (event.get("description") or ""),
        (event.get("venue") or ""),
    ]).lower()
    return any(kw in combined for kw in NON_LGBTQ_BLOCKLIST)


def _is_lgbtq_relevant(event: Dict) -> bool:
    """Return True if this event is LGBTQ-relevant or from a community partner org."""
    source = event.get("source", "")
    if source in LGBTQ_SOURCES:
        return True
    combined = " ".join([
        event.get("name", ""),
        event.get("description", ""),
        event.get("url", ""),
    ]).lower()
    if any(kw in combined for kw in LGBTQ_KEYWORDS):
        return True
    if any(kw in combined for kw in COMMUNITY_PARTNER_KEYWORDS):
        return True
    return False


def apply_quality_filters(events: List[Dict]) -> List[Dict]:
    """Apply all quality filters and annotate each event with lgbtq_relevant."""
    monday, sunday = _get_week_range()
    filtered = []
    removed_counts = {
        "no_name": 0, "junk_name": 0, "out_of_week": 0,
        "non_lgbtq_blocklist": 0, "not_lgbtq_relevant": 0,
    }

    for event in events:
        name = event.get("name", "")
        date_str = event.get("date", "")
        source = event.get("source", "")

        # Filter 1: no name
        if not name:
            removed_counts["no_name"] += 1
            continue

        # Filter 2: junk name
        if _is_junk_name(name):
            removed_counts["junk_name"] += 1
            logger.debug(f"[filter] Junk name removed: '{name}'")
            continue

        # Filter 3: dated events outside current week
        if date_str:
            if not _is_in_current_week(date_str):
                removed_counts["out_of_week"] += 1
                logger.debug(f"[filter] Out-of-week removed: '{name}' on {date_str}")
                continue

        # Filter 4: non-LGBTQ blocklist — blocks matching events from ANY source
        if _is_clearly_not_lgbtq(event):
            removed_counts["non_lgbtq_blocklist"] += 1
            logger.info(f"[filter] Non-LGBTQ blocklist removed: '{name}' (source={source})")
            continue

        # Annotate LGBTQ relevance
        event["lgbtq_relevant"] = _is_lgbtq_relevant(event)

        # Filter 5: events from non-trusted sources must have LGBTQ keywords
        if source not in LGBTQ_SOURCES and not event["lgbtq_relevant"]:
            removed_counts["not_lgbtq_relevant"] += 1
            logger.info(f"[filter] Not LGBTQ-relevant removed: '{name}' (source={source})")
            continue

        filtered.append(event)

    logger.info(
        f"[filter] Removed: {removed_counts['no_name']} no-name, "
        f"{removed_counts['junk_name']} junk-name, "
        f"{removed_counts['out_of_week']} out-of-week, "
        f"{removed_counts['non_lgbtq_blocklist']} non-LGBTQ blocklist, "
        f"{removed_counts['not_lgbtq_relevant']} not LGBTQ-relevant"
    )
    return filtered


# ── Sorting & grouping ────────────────────────────────────────────────────────

def sort_events(events: List[Dict]) -> List[Dict]:
    """Sort by priority (asc) then by date (asc). Undated events go last in their group."""
    def sort_key(e):
        is_homo_hotel = 0 if e.get("source") == "homo_hotel" else 1
        priority = e.get("priority", 99)
        date_sort = e.get("date", "") or "9999-99-99"
        return (is_homo_hotel, priority, date_sort)

    return sorted(events, key=sort_key)


def split_weekday_weekend(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Split events into weekday (Mon-Thu) and weekend (Fri-Sun) groups."""
    weekday = []
    weekend = []
    undated = []

    for event in events:
        date_str = event.get("date", "")
        if not date_str:
            undated.append(event)
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt.weekday() >= 4:  # Fri=4, Sat=5, Sun=6
                weekend.append(event)
            else:
                weekday.append(event)
        except ValueError:
            undated.append(event)

    weekday.extend(undated)
    weekend.extend(undated)

    # Signature event always in both groups (configured via config.SIGNATURE_EVENT)
    _sig_event = getattr(config, "SIGNATURE_EVENT", None) or {}
    _sig_source_key = _sig_event.get("source_key", "")
    _sig_keywords = _sig_event.get("name_keywords", [])

    def _is_signature(ev: dict) -> bool:
        if _sig_source_key and ev.get("source") == _sig_source_key:
            return True
        name = ev.get("name", "").lower()
        return any(kw in name for kw in _sig_keywords)

    sig_events = [e for e in events if _is_signature(e)]
    for h in sig_events:
        if h not in weekday:
            weekday.insert(0, h)
        if h not in weekend:
            weekend.insert(0, h)

    return {"weekday": weekday, "weekend": weekend}


# ── Signature event guarantee ─────────────────────────────────────────────────

def ensure_signature_event(events: List[Dict]) -> List[Dict]:
    """Always ensure the city's signature event is present and at the top.
    Configured via config.SIGNATURE_EVENT. If a city has no signature event,
    this is a no-op."""
    sig_event = getattr(config, "SIGNATURE_EVENT", None) or {}
    sig_source_key = sig_event.get("source_key", "")

    if not sig_source_key:
        return events

    has_sig = any(e.get("source") == sig_source_key for e in events)

    if not has_sig:
        # Try to import the signature event scraper if it exists
        try:
            from scraper import homo_hotel as _signature_scraper
        except ImportError:
            try:
                _signature_scraper = __import__(f"scraper.{sig_source_key}", fromlist=[""])
            except ImportError:
                logger.warning(f"Signature event source '{sig_source_key}' has no scraper module; skipping inject")
                return events
        sig_events = _signature_scraper.scrape()
        for e in sig_events:
            e["lgbtq_relevant"] = True
        events = sig_events + events
        logger.info(f"Injected {sig_event.get('name', 'signature')} events (were missing)")
    else:
        sig_evs = [e for e in events if e.get("source") == sig_source_key]
        others = [e for e in events if e.get("source") != sig_source_key]
        events = sig_evs + others

    return events


# Backward-compat alias so existing call sites keep working
ensure_homo_hotel = ensure_signature_event


def _normalize_time_str(t: str) -> str:
    """Convert any time string to 12-hour AM/PM format (e.g. '19:00' -> '7:00 PM')."""
    t = t.strip()
    # Handle ranges like "7:00 PM - 9:00 PM" — normalize just the first part
    first = t.split(" - ")[0].split(" to ")[0].strip()
    for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p"]:
        try:
            dt = datetime.strptime(first.upper(), fmt)
            result = dt.strftime("%I:%M %p").lstrip("0")
            # Preserve range suffix if present
            if " - " in t:
                end = t.split(" - ", 1)[1].strip()
                # Normalize end time too
                for efmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p"]:
                    try:
                        edt = datetime.strptime(end.upper(), efmt)
                        end = edt.strftime("%I:%M %p").lstrip("0")
                        break
                    except Exception:
                        pass
                return f"{result} - {end}"
            return result
        except Exception:
            pass
    return t  # Return as-is if unparseable


# ── Save ─────────────────────────────────────────────────────────────────────

def get_week_key(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    return f"{date.year}-W{date.isocalendar()[1]:02d}"


def save_results(events: List[Dict], week_key: str = None):
    config.ensure_dirs()
    if week_key is None:
        week_key = get_week_key()

    split = split_weekday_weekend(events)

    combined_path = os.path.join(config.EVENTS_DIR, f"{week_key}_all.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "generated_at": datetime.now().isoformat(),
            "total_events": len(events),
            "events": events,
        }, f, indent=2, ensure_ascii=False)

    weekday_path = os.path.join(config.EVENTS_DIR, f"{week_key}_weekday.json")
    with open(weekday_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "type": "weekday",
            "days": "Monday - Thursday",
            "generated_at": datetime.now().isoformat(),
            "total_events": len(split["weekday"]),
            "events": split["weekday"],
        }, f, indent=2, ensure_ascii=False)

    weekend_path = os.path.join(config.EVENTS_DIR, f"{week_key}_weekend.json")
    with open(weekend_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "type": "weekend",
            "days": "Friday - Sunday",
            "generated_at": datetime.now().isoformat(),
            "total_events": len(split["weekend"]),
            "events": split["weekend"],
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(events)} events to {combined_path}")
    return combined_path, weekday_path, weekend_path


# ── Main runner ───────────────────────────────────────────────────────────────

def run_all_scrapers() -> List[Dict]:
    """Run all scrapers in priority order and return combined raw results."""
    all_events = []

    # Ordered by importance/reliability
    scrapers = [
        ("manual_input", manual_input.scrape),  # Always first — manually curated, priority=1
        ("recurring", recurring.scrape),
        ("okeq_calendar", okeq_calendar.scrape),
        ("twisted_arts", twisted_arts.scrape),
        ("specific_orgs", specific_orgs.scrape),
        ("eventbrite_meetup", eventbrite_meetup.scrape),
        ("meetup", None),  # Already included in eventbrite_meetup.scrape
        ("homo_hotel", homo_hotel.scrape),
        ("community_calendars", community_calendars.scrape),
        ("extended_calendars", extended_calendars.scrape),
        ("aa_meetings", aa_meetings.scrape),
        ("qlist", qlist.scrape),
        ("community_groups", community_groups.scrape),
        ("churches", churches.scrape),
        ("bars", bars.scrape),
        ("tulsa_arts_district", tulsa_arts_district.scrape),
        ("facebook_events", facebook_events.scrape),
        ("ticketing_sites", ticketing_sites.scrape),
        ("timetree_scraper", timetree_scraper.scrape),  # Tulsa Isn't Boring -- iCal/Playwright/browser-flag
        ("slack_browser_scraper", slack_browser_scraper.scrape),  # TulsaRemote Slack -- browser-extracted JSON or flag
    ]

    # Playwright scrapers run after all static scrapers
    # They supplement (not replace) the existing pipeline
    if _PLAYWRIGHT_AVAILABLE:
        scrapers.append(("playwright_scrapers", _playwright_scrapers.scrape_all))
    else:
        logger.info("Skipping playwright_scrapers -- playwright not installed")

    for name, scrape_fn in scrapers:
        if scrape_fn is None:
            continue  # Skip placeholder entries
        logger.info(f"Running scraper: {name}")
        try:
            events = scrape_fn()
            logger.info(f"  {name}: {len(events)} events")
            all_events.extend(events)
        except Exception as e:
            logger.error(f"  {name}: FAILED - {e}", exc_info=True)

    return all_events


def _append_growth_log(events: List[Dict], week_key: str, start_time: datetime):
    """Append a stats record for this scrape run to the growth log JSON array."""
    try:
        # Build events_per_source (only sources with count > 0)
        source_counts: Dict[str, int] = {}
        for e in events:
            src = e.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
        events_per_source = dict(
            sorted(source_counts.items(), key=lambda x: -x[1])
        )

        # blank_days: Mon-Sun day names with 0 events this week
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts: Dict[str, int] = {d: 0 for d in day_names}
        for e in events:
            date_str = e.get("date", "")
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    day_name = day_names[dt.weekday()]
                    day_counts[day_name] += 1
                except ValueError:
                    pass
        blank_days = [d for d in day_names if day_counts[d] == 0]

        record = {
            "week": week_key,
            "timestamp": datetime.now().isoformat(),
            "total_events": len(events),
            "events_with_dates": sum(1 for e in events if e.get("date", "") != ""),
            "blank_days": blank_days,
            "events_per_source": events_per_source,
            "top_sources": list(events_per_source.keys())[:5],
            "scrape_duration_seconds": round(
                (datetime.now() - start_time).total_seconds(), 1
            ),
        }

        # Load existing log or start fresh
        log_data: List[Dict] = []
        if os.path.exists(config.GROWTH_LOG):
            try:
                with open(config.GROWTH_LOG, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                log_data = []

        # Update in place if same week_key already exists, otherwise append
        updated = False
        for i, existing in enumerate(log_data):
            if existing.get("week") == week_key:
                log_data[i] = record
                updated = True
                break
        if not updated:
            log_data.append(record)

        config.ensure_dirs()
        with open(config.GROWTH_LOG, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Growth log updated: {week_key} - {len(events)} events")

    except Exception as exc:
        logger.error(f"Growth log write failed: {exc}", exc_info=True)


PENDING_ACTIONS_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "pending-william-actions.md"
)
LGBTQ_DATED_MINIMUM = 8
PRIMARY_SOURCE_MINIMUM = 3


def _write_pending_action(message: str, week_key: str) -> None:
    """Append a timestamped entry to pending-william-actions.md."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{timestamp}] TulsaGays scraper HALTED — {week_key}\n- {message}\n"
        with open(PENDING_ACTIONS_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.warning(f"[content-gate] Written to pending-william-actions.md")
    except Exception as exc:
        logger.error(f"[content-gate] Could not write pending action: {exc}")


def main():
    """Main entry point: run all scrapers, filter, deduplicate, sort, save."""
    start_time = datetime.now()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Tulsa Gays Event Scraper - Starting")
    logger.info(f"Week: {get_week_key()}")
    monday, sunday = _get_week_range()
    logger.info(f"Date range: {monday.date()} to {sunday.date()}")
    logger.info("=" * 60)

    # 1. Run all scrapers
    raw_events = run_all_scrapers()
    logger.info(f"\nTotal raw events: {len(raw_events)}")

    # 2. Apply quality filters (junk names, out-of-week dates, lgbtq_relevant annotation)
    filtered_events = apply_quality_filters(raw_events)
    logger.info(f"After quality filters: {len(filtered_events)}")

    # 3. Deduplicate
    unique_events = deduplicate(filtered_events)
    logger.info(f"After deduplication: {len(unique_events)}")

    # 4. Ensure Homo Hotel is present and at top
    unique_events = ensure_homo_hotel(unique_events)

    # 4.5. Slack zero-event warning — must appear before the content gate
    slack_events = [e for e in unique_events if "slack" in (e.get("source") or "").lower()]
    if not slack_events:
        import glob as _glob
        flag_file = os.path.join(config.DATA_DIR, "slack_browser_needed.flag")
        if os.path.exists(flag_file):
            logger.warning(
                "[SLACK] ZERO Slack events found and slack_browser_needed.flag exists. "
                "TulsaRemote Slack (#events-local, #unite-lgbtq-plus) is a REQUIRED source. "
                "Run the browser extraction step before generating slides."
            )
        else:
            logger.warning(
                "[SLACK] ZERO Slack events found. slack_browser_needed.flag not present — "
                "slack_browser_scraper may have failed silently. Check data/slack_events_browser.json."
            )

    # 4.6. LGBTQ content quality gate — halt if event pool is too thin to produce a good post
    lgbtq_dated = [
        e for e in unique_events
        if e.get("lgbtq_relevant") and e.get("date")
    ]
    lgbtq_from_primary = [
        e for e in unique_events
        if (e.get("source") or "") in LGBTQ_SOURCES and e.get("date")
    ]

    week_key = get_week_key()

    if len(lgbtq_dated) < LGBTQ_DATED_MINIMUM or len(lgbtq_from_primary) < PRIMARY_SOURCE_MINIMUM:
        missing_primary = [
            src for src in sorted(LGBTQ_SOURCES)
            if not any((e.get("source") or "") == src for e in unique_events)
        ]
        gate_msg = (
            f"CONTENT GATE FAILED for {week_key}: "
            f"{len(lgbtq_dated)} LGBTQ-relevant dated events "
            f"(minimum {LGBTQ_DATED_MINIMUM}), "
            f"{len(lgbtq_from_primary)} from primary LGBTQ sources "
            f"(minimum {PRIMARY_SOURCE_MINIMUM}). "
            f"Primary sources returning 0 events: {missing_primary}. "
            f"Scrape output is too thin or off-audience to post. "
            f"Fix scrapers, re-run the browser Slack step, then re-run the scraper."
        )
        logger.error(f"[content-gate] {gate_msg}")
        print(f"\n*** CONTENT GATE HALT ***\n{gate_msg}\n")
        _write_pending_action(gate_msg, week_key)
        import sys
        sys.exit(1)

    # 5. Sort by priority then date
    sorted_events = sort_events(unique_events)

    # 5b. Normalize all time strings to 12-hour AM/PM format
    for ev in sorted_events:
        raw_t = (ev.get("time") or "").strip()
        if raw_t:
            ev["time"] = _normalize_time_str(raw_t)

    # 6. Save results
    week_key = get_week_key()
    paths = save_results(sorted_events, week_key)

    logger.info(f"\nResults saved for week {week_key}:")
    for p in paths:
        logger.info(f"  {p}")

    # 6c. Append growth log entry
    _append_growth_log(sorted_events, week_key, start_time)

    # 6b. Date-parse health check
    _events_with_dates = [e for e in sorted_events if e.get("date")]
    _events_without_dates = [e for e in sorted_events if not e.get("date")]
    _total = len(sorted_events)
    print(f"\n[DATE SUMMARY] Events WITH dates: {len(_events_with_dates)} | WITHOUT dates: {len(_events_without_dates)} | Total: {_total}")
    if _total > 0:
        _undated_ratio = len(_events_without_dates) / _total
        if _undated_ratio > 0.70:
            logger.warning(
                "WARNING: Date parsing may be broken — review scrapers before generating slides. "
                "%.0f%% of events (%d/%d) have no date.",
                _undated_ratio * 100,
                len(_events_without_dates),
                _total,
            )
            print(
                f"\n*** WARNING: Date parsing may be broken — review scrapers before generating slides. "
                f"{_undated_ratio:.0%} of events ({len(_events_without_dates)}/{_total}) have no date. ***\n"
            )

    # 7. Summary report
    split = split_weekday_weekend(sorted_events)
    dated = [e for e in sorted_events if e.get("date")]
    undated = [e for e in sorted_events if not e.get("date")]
    lgbtq_relevant = [e for e in sorted_events if e.get("lgbtq_relevant")]

    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"  Total unique events:    {len(sorted_events)}")
    logger.info(f"  Events with dates:      {len(dated)}")
    logger.info(f"  Events without dates:   {len(undated)}")
    logger.info(f"  LGBTQ-relevant events:  {len(lgbtq_relevant)}")
    logger.info(f"  Weekday events (Mo-Th): {len(split['weekday'])}")
    logger.info(f"  Weekend events (Fr-Su): {len(split['weekend'])}")

    sources = {}
    for e in sorted_events:
        src = e.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    logger.info(f"\n  Events by source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        logger.info(f"    {src}: {count}")

    if undated:
        logger.info(f"\n  Sources with undated events (need manual attention):")
        undated_sources = {}
        for e in undated:
            src = e.get("source", "unknown")
            undated_sources[src] = undated_sources.get(src, 0) + 1
        for src, count in sorted(undated_sources.items(), key=lambda x: -x[1]):
            logger.info(f"    {src}: {count} undated")

    logger.info(f"{'='*60}")
    logger.info("Done!")
    logger.info(f"{'='*60}")

    return sorted_events


if __name__ == "__main__":
    main()
