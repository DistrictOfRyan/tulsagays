"""Orchestrator that runs all scrapers, deduplicates, sorts, and saves events."""

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

from scraper import homo_hotel, okeq, twisted_arts, churches, bars, eventbrite_meetup, facebook_scraper, tulsa_arts_district

logger = logging.getLogger(__name__)

# ── Similarity threshold for deduplication ───────────────────────────────
SIMILARITY_THRESHOLD = 0.75


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace/punctuation."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _are_similar(name_a: str, name_b: str) -> bool:
    """Check if two event names are similar enough to be duplicates."""
    a = _normalize(name_a)
    b = _normalize(name_b)
    if not a or not b:
        return False
    # Exact match after normalization
    if a == b:
        return True
    # Fuzzy match
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


def _same_date(date_a: str, date_b: str) -> bool:
    """Check if two date strings refer to the same date (or either is empty)."""
    if not date_a or not date_b:
        return True  # If either date is unknown, consider them potentially the same
    return date_a.strip() == date_b.strip()


def deduplicate(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events based on name + date similarity.

    Keeps the event with the lower (better) priority number, or from the
    more specific source.
    """
    if not events:
        return []

    unique = []
    for event in events:
        is_dup = False
        for i, existing in enumerate(unique):
            if _are_similar(event["name"], existing["name"]) and _same_date(event["date"], existing["date"]):
                is_dup = True
                # Keep the one with better priority (lower number)
                if event["priority"] < existing["priority"]:
                    unique[i] = event
                # If same priority, prefer the one with more info
                elif event["priority"] == existing["priority"]:
                    event_info = sum(1 for v in event.values() if v)
                    existing_info = sum(1 for v in existing.values() if v)
                    if event_info > existing_info:
                        unique[i] = event
                break
        if not is_dup:
            unique.append(event)

    return unique


def sort_events(events: List[Dict]) -> List[Dict]:
    """Sort events by priority (ascending) then by date (ascending).

    Events without dates go to the end within their priority group.
    """
    def sort_key(e):
        priority = e.get("priority", 99)
        date = e.get("date", "")
        # Ensure Homo Hotel is always first
        is_homo_hotel = 0 if e.get("source") == "homo_hotel" else 1
        # Parse date for sorting; undated events sort last
        date_sort = date if date else "9999-99-99"
        return (is_homo_hotel, priority, date_sort)

    return sorted(events, key=sort_key)


def split_weekday_weekend(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Split events into weekday (Mon-Thu) and weekend (Fri-Sun) groups.

    Events without parseable dates go into both groups.
    """
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
            day_of_week = dt.weekday()  # 0=Mon, 6=Sun
            if day_of_week >= 4:  # Fri=4, Sat=5, Sun=6
                weekend.append(event)
            else:
                weekday.append(event)
        except ValueError:
            undated.append(event)

    # Add undated events to both groups so they aren't lost
    weekday.extend(undated)
    weekend.extend(undated)

    # ALWAYS include Homo Hotel Happy Hour in BOTH groups
    # It's the signature event and must be featured in every post
    homo_hotel_events = [e for e in events if e.get("source", "").lower() == "homo_hotel"
                         or "homo hotel" in e.get("name", "").lower()]
    for hh in homo_hotel_events:
        if hh not in weekday:
            weekday.insert(0, hh)
        if hh not in weekend:
            weekend.insert(0, hh)

    return {
        "weekday": weekday,
        "weekend": weekend,
    }


def get_week_key(date: datetime = None) -> str:
    """Get a key for the week like '2026-W13'."""
    if date is None:
        date = datetime.now()
    return f"{date.year}-W{date.isocalendar()[1]:02d}"


def ensure_homo_hotel(events: List[Dict]) -> List[Dict]:
    """ALWAYS ensure Homo Hotel Happy Hour is in the results and at the top."""
    # Check if Homo Hotel is already present
    has_homo_hotel = any(e.get("source") == "homo_hotel" for e in events)

    if not has_homo_hotel:
        # Generate Homo Hotel events and prepend them
        hh_events = homo_hotel.scrape()
        events = hh_events + events
        logger.info("Injected Homo Hotel Happy Hour events (were missing)")
    else:
        # Move Homo Hotel events to the front
        hh = [e for e in events if e.get("source") == "homo_hotel"]
        others = [e for e in events if e.get("source") != "homo_hotel"]
        events = hh + others

    return events


def save_results(events: List[Dict], week_key: str = None):
    """Save events to JSON files in the data/events directory, keyed by week."""
    config.ensure_dirs()

    if week_key is None:
        week_key = get_week_key()

    # Split into weekday/weekend
    split = split_weekday_weekend(events)

    # Save combined file
    combined_path = os.path.join(config.EVENTS_DIR, f"{week_key}_all.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "generated_at": datetime.now().isoformat(),
            "total_events": len(events),
            "events": events,
        }, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(events)} events to {combined_path}")

    # Save weekday file
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
    logger.info(f"Saved {len(split['weekday'])} weekday events to {weekday_path}")

    # Save weekend file
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
    logger.info(f"Saved {len(split['weekend'])} weekend events to {weekend_path}")

    return combined_path, weekday_path, weekend_path


def run_all_scrapers() -> List[Dict]:
    """Run all scrapers and return their combined raw results."""
    all_events = []

    scrapers = [
        ("homo_hotel", homo_hotel.scrape),
        ("okeq", okeq.scrape),
        ("twisted_arts", twisted_arts.scrape),
        ("churches", churches.scrape),
        ("bars", bars.scrape),
        ("eventbrite_meetup", eventbrite_meetup.scrape),
        ("facebook_scraper", facebook_scraper.scrape),
        ("tulsa_arts_district", tulsa_arts_district.scrape),
    ]

    for name, scrape_fn in scrapers:
        logger.info(f"Running scraper: {name}")
        try:
            events = scrape_fn()
            logger.info(f"  {name}: {len(events)} events")
            all_events.extend(events)
        except Exception as e:
            logger.error(f"  {name}: FAILED - {e}", exc_info=True)

    return all_events


def main():
    """Main entry point: run all scrapers, deduplicate, sort, save."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Tulsa Gays Event Scraper - Starting")
    logger.info("=" * 60)

    # 1. Run all scrapers
    raw_events = run_all_scrapers()
    logger.info(f"\nTotal raw events: {len(raw_events)}")

    # 2. Deduplicate
    unique_events = deduplicate(raw_events)
    logger.info(f"After deduplication: {len(unique_events)}")

    # 3. Ensure Homo Hotel is present and at top
    unique_events = ensure_homo_hotel(unique_events)

    # 4. Sort by priority then date
    sorted_events = sort_events(unique_events)

    # 5. Save results
    week_key = get_week_key()
    paths = save_results(sorted_events, week_key)

    logger.info(f"\nResults saved for week {week_key}:")
    for p in paths:
        logger.info(f"  {p}")

    # Summary
    split = split_weekday_weekend(sorted_events)
    logger.info(f"\nSummary:")
    logger.info(f"  Total unique events: {len(sorted_events)}")
    logger.info(f"  Weekday events (Mon-Thu): {len(split['weekday'])}")
    logger.info(f"  Weekend events (Fri-Sun): {len(split['weekend'])}")

    sources = {}
    for e in sorted_events:
        src = e.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    logger.info(f"  By source: {dict(sorted(sources.items()))}")

    logger.info("=" * 60)
    logger.info("Done!")
    logger.info("=" * 60)

    return sorted_events


if __name__ == "__main__":
    main()
