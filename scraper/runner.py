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
    specific_orgs,
    eventbrite_meetup,
    community_calendars,
    extended_calendars,
    aa_meetings,
    homo_hotel,
    okeq,
    community_groups,
    qlist,
    churches,
    bars,
    manual_input,
    tulsa_arts_district,
    facebook_events,
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

LGBTQ_SOURCES = {
    "recurring", "okeq", "okeq_calendar", "specific_orgs",
    "aa_meetings", "homo_hotel", "community_groups", "twisted_arts",
    "qlist", "pflag_tulsa", "black_queer_tulsa", "freedom_oklahoma",
    "council_oak", "hotmess_sports", "all_souls_special", "utulsa_pride",
    "osu_tulsa", "manual",
    # Arts/culture venues (LGBTQ-filtered at scraper level)
    "circle_cinema", "philbrook_museum", "tulsa_arts_district",
    # Facebook events (LGBTQ-filtered at scraper level)
    "facebook_events",
}

LGBTQ_KEYWORDS = [
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic",
]

# Community partners: LGBTQ-adjacent orgs whose events are always welcome
# even if their names don't contain LGBTQ keywords
COMMUNITY_PARTNER_KEYWORDS = [
    "the sonic ray", "sonic ray", "sonicray",
]

# Events matching ANY of these keywords are explicitly excluded — even from trusted sources
NON_LGBTQ_BLOCKLIST = [
    # College/pro sports (non-LGBTQ-specific)
    "football game", "football season", "nfl ", " nfl", "nba ", " nba",
    "mlb ", " mlb", "nhl ", " nhl", "college football", "college basketball",
    "oral roberts university", "oru football", "oru basketball", "oru baseball",
    "golden eagles football", "golden eagles basketball",
    "tu football", "osu football", "ou football", "sooners football",
    "nascar", "ufc ", " ufc", "mma fight",
    # Petroleum/energy industry conferences
    "society of petroleum", "spe tulsa", "petroleum engineers",
    "spe ior", "spe improved", "improved oil recovery",
    "reservoir heterogeneity", "reservoir characterization",
    "oil and gas conference", "oil & gas conference",
    "drilling conference", "pipeline conference", "petroleum conference",
    # Non-LGBTQ religious mass events
    "revival meeting", "men's prayer breakfast", "prayer rally",
    "women's prayer breakfast",
]

# These are clearly nav/junk strings that get scraped as "event names"
JUNK_NAMES = {
    "map", "google calendar", "get your tickets", "buy tickets",
    "learn more", "view all", "see more", "load more", "rsvp",
    "register", "sign up", "donate", "subscribe", "contact us",
    "home", "about", "menu", "calendar", "events", "back",
}


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
                if event["priority"] < existing["priority"]:
                    unique[i] = event
                elif event["priority"] == existing["priority"]:
                    event_info = sum(1 for v in event.values() if v)
                    existing_info = sum(1 for v in existing.values() if v)
                    if event_info > existing_info:
                        unique[i] = event
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
    if len(name) > 200:  # Way too long for an event name
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

    # Homo Hotel always in both groups
    hh = [e for e in events if e.get("source") == "homo_hotel" or "homo hotel" in e.get("name", "").lower()]
    for h in hh:
        if h not in weekday:
            weekday.insert(0, h)
        if h not in weekend:
            weekend.insert(0, h)

    return {"weekday": weekday, "weekend": weekend}


# ── Homo Hotel guarantee ──────────────────────────────────────────────────────

def ensure_homo_hotel(events: List[Dict]) -> List[Dict]:
    """Always ensure Homo Hotel Happy Hour is present and at the top."""
    has_hh = any(e.get("source") == "homo_hotel" for e in events)

    if not has_hh:
        hh_events = homo_hotel.scrape()
        # Apply lgbtq_relevant annotation
        for e in hh_events:
            e["lgbtq_relevant"] = True
        events = hh_events + events
        logger.info("Injected Homo Hotel Happy Hour events (were missing)")
    else:
        hh = [e for e in events if e.get("source") == "homo_hotel"]
        others = [e for e in events if e.get("source") != "homo_hotel"]
        events = hh + others

    return events


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
        ("specific_orgs", specific_orgs.scrape),
        ("eventbrite_meetup", eventbrite_meetup.scrape),
        ("meetup", None),  # Already included in eventbrite_meetup.scrape
        ("homo_hotel", homo_hotel.scrape),
        ("community_calendars", community_calendars.scrape),
        ("extended_calendars", extended_calendars.scrape),
        ("aa_meetings", aa_meetings.scrape),
        ("okeq", okeq.scrape),
        ("qlist", qlist.scrape),
        ("community_groups", community_groups.scrape),
        ("churches", churches.scrape),
        ("bars", bars.scrape),
        ("tulsa_arts_district", tulsa_arts_district.scrape),
        ("facebook_events", facebook_events.scrape),
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


def main():
    """Main entry point: run all scrapers, filter, deduplicate, sort, save."""
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
