"""
Pre-slide verification for the Tulsa Gays weekly pipeline.

Runs AFTER scraping, BEFORE slide generation.

Usage:
    python tools/verify_week.py                  # uses current week
    python tools/verify_week.py --week 2026-W18  # specific week

Exit codes:
    0 = all PASS or only WARN (auto-fixable)
    1 = at least one FAIL (manual fix required)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Constants that mirror main.py and image_maker.py ──────────────────────

_GARBAGE_NAMES = {
    "(map)",
    "stay connected!",
    "our partners",
    "event application",
    "event calendar",
    "bruce goff event center",
}

# True gay bars — any event here should score 5
_GAY_BAR_VENUES = {
    "club majestic", "tulsa eagle", "yellow brick", "majestic tulsa",
    "1330 e 3rd", "1338 e 3rd", "the vanguard",
    "pump bar", "602 south lewis", "602 s. lewis", "602 s lewis",
}

_DRAG_KEYWORDS = {
    # Specific drag performance keywords — intentionally NOT "drag" alone
    # to avoid false-positives on "Midnight Drags" (car racing), etc.
    "drag show", "drag bingo", "drag brunch", "drag queen", "drag king",
    "drag race night", "drag night", "drag perform", "drag along",
    "drag sing", "dragnificent",
    "twisted arts drag", "inner circle drag", "open talent",
    "variety show",
}

_HHHH_KEYWORDS = {"homo hotel", "hhhh"}

_NEVER_FEATURE = {
    "mix and mingle",
    "aa meeting",
    "aa meetings",
    "book club - tulsa",
    "shut up & write",
    "raise your spiritual iq",
    "okeq senior",
    "girl scout",
}

_RECURRING_NAME_FRAGMENTS = {
    "bowling league", "support group", "lambda unity",
    "outreach group", "monthly meeting",
    "happy hour!",
    "touchtunes",
    "ttrpg", "tabletop",
}

_DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

_DATE_TO_DAY = {
    0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
    4: "friday", 5: "saturday", 6: "sunday",
}

DOUBLETREE_VENUE = "DoubleTree Tulsa Downtown"


# ── Helpers ────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def _norm_time(t: str) -> str:
    """Normalize time strings to HH:MM for comparison (strip seconds/ranges)."""
    if not t:
        return ""
    t = t.strip().split("-")[0].split("–")[0].strip()
    # Normalize "6 PM" -> "6:00 PM"
    t = re.sub(r"^(\d{1,2})\s*(AM|PM)$", r"\1:00 \2", t, flags=re.IGNORECASE)
    return t.upper()


def _event_day_name(ev: dict) -> str:
    """Return lowercase day-of-week name for the event's date, or ''."""
    date_str = ev.get("date", "")
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return _DATE_TO_DAY[dt.weekday()]
    except (ValueError, KeyError):
        return ""


def _is_hhhh(ev: dict) -> bool:
    name = (ev.get("name") or "").lower()
    return any(kw in name for kw in _HHHH_KEYWORDS)


def _flamingo_score(ev: dict) -> int:
    """Minimal flamingo scorer matching image_maker logic (5 / 4 / 2)."""
    name = (ev.get("name") or "").lower()
    venue = (ev.get("venue") or "").lower()
    source = (ev.get("source") or "").lower()
    content = f"{name} {venue}"

    _FIVE_KW = [
        "drag show", "drag bingo", "drag brunch", "drag queen", "drag king",
        "drag race", "drag sing", "drag along", "drag perform", "drag night",
        "pride show", "pride party", "pride dance", "pride night", "queer night",
        "gay night", "lgbtq+ night", "homo hotel", "hhhh", "rainbow night",
        "twisted arts", "queer cabaret", "dragnificent", "lambda bowling",
        "queer support group", "lgbtq support group", "gender outreach support",
        "queer women", "sapphic social", "queer social", "trans support group",
        "osu tulsa queer", "pflag tulsa", "queer support", "pflag", "lambda unity",
        "bar crawl", "pub crawl", "pride crawl", "gabbin with gabbi",
        "pride nation entertainment", "brad lee", "lesbian attachment",
    ]
    if any(kw in content for kw in _FIVE_KW):
        return 5
    if any(bar in venue for bar in _GAY_BAR_VENUES):
        return 5
    if source in ("homo_hotel", "okeq"):
        return 4
    return 2


# ── Week loading ───────────────────────────────────────────────────────────

def load_week_events(week_key: str) -> list:
    """Load all events for a week from the events JSON files."""
    events_dir = config.EVENTS_DIR
    events = []
    for suffix in ("_all", "_weekday", "_weekend"):
        path = os.path.join(events_dir, f"{week_key}{suffix}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        batch = data if isinstance(data, list) else data.get("events", [])
        # Avoid duplicates when _all contains everything
        if suffix == "_all":
            events = batch
            break
        events.extend(batch)
    return events


def save_week_events(week_key: str, events: list) -> None:
    """Write back the corrected event list to the _all JSON."""
    events_dir = config.EVENTS_DIR
    path = os.path.join(events_dir, f"{week_key}_all.json")
    if not os.path.exists(path):
        return  # only update if file exists
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    else:
        raw["events"] = events
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)


# ── Check A: same-venue/time/date duplicates ──────────────────────────────

def check_a_venue_time_duplicates(events: list) -> tuple:
    """
    Group events by (date, normalized_venue, normalized_time).
    Flag any group with 2+ events as potential duplicates.
    Returns (status, messages) where status is 'PASS', 'WARN', or 'FAIL'.
    """
    messages = []
    groups = {}
    for ev in events:
        date = ev.get("date", "")
        venue = _norm(ev.get("venue", ""))
        time = _norm_time(ev.get("time", ""))
        if not date or not venue:
            continue
        key = (date, venue, time)
        groups.setdefault(key, []).append(ev)

    dupes = {k: v for k, v in groups.items() if len(v) >= 2}
    for (date, venue, time), evs in dupes.items():
        names = [ev.get("name", "?") for ev in evs]
        messages.append(
            f"  DUPLICATE ALERT: {' / '.join(names)} "
            f"on {date} at '{venue}' {time}".strip()
        )

    if not messages:
        return "PASS", ["  No same-venue/time/date duplicates found."]
    return "FAIL", messages


# ── Check B: HHHH venue validation ────────────────────────────────────────

def check_b_hhhh_venue(events: list) -> tuple:
    """
    Any HHHH event must have 'doubletree' in venue.
    Auto-fixes wrong venue in-place on the event dicts.
    Returns (status, messages, fixed_count).
    """
    messages = []
    fixed = 0
    for ev in events:
        if not _is_hhhh(ev):
            continue
        venue = (ev.get("venue") or "")
        if "doubletree" not in venue.lower():
            old = venue or "(no venue)"
            ev["venue"] = DOUBLETREE_VENUE
            messages.append(
                f"  AUTO-FIXED venue: \"{old}\" -> \"{DOUBLETREE_VENUE}\" "
                f"(event: {ev.get('name', '?')})"
            )
            fixed += 1

    if fixed == 0:
        return "PASS", ["  All HHHH events have correct DoubleTree venue."], 0
    return "WARN", messages, fixed


# ── Check C: day-of-week description validation ───────────────────────────

def check_c_day_description_mismatch(events: list) -> tuple:
    """
    For each event, check if description contains a day name that doesn't
    match the event's actual date.
    Returns (status, messages).
    """
    messages = []
    for ev in events:
        actual_day = _event_day_name(ev)
        if not actual_day:
            continue
        for field in ("slide_description", "website_description", "description"):
            desc = (ev.get(field) or "").lower()
            if not desc:
                continue
            for day in _DAY_NAMES:
                if day in desc and day != actual_day:
                    messages.append(
                        f"  DAY MISMATCH: \"{ev.get('name', '?')}\" "
                        f"is on {actual_day.capitalize()} but "
                        f"'{field}' mentions {day.capitalize()}"
                    )
                    break  # one message per event per field is enough
            break  # only check first non-empty description field

    if not messages:
        return "PASS", ["  All day-of-week references in descriptions match event dates."]
    return "FAIL", messages


# ── Check D: garbage event filter ────────────────────────────────────────

def check_d_garbage_events(events: list) -> tuple:
    """
    Check every event name against the known garbage list.
    Returns (status, messages).
    """
    messages = []
    for ev in events:
        name = (ev.get("name") or "").strip()
        name_lower = name.lower()
        if name_lower in _GARBAGE_NAMES:
            messages.append(f"  GARBAGE EVENT: \"{name}\" (exact match)")
        elif len(name) < 4:
            messages.append(f"  GARBAGE EVENT: \"{name}\" (name under 4 chars)")
        else:
            # Partial match for multi-word garbage strings
            for g in _GARBAGE_NAMES:
                if len(g) > 4 and g in name_lower:
                    messages.append(f"  GARBAGE EVENT: \"{name}\" (contains '{g}')")
                    break

    if not messages:
        return "PASS", ["  No garbage events detected."]
    return "FAIL", messages


# ── Check E: flamingo score sanity ────────────────────────────────────────

def check_e_flamingo_sanity(events: list) -> tuple:
    """
    Spot-check flamingo scores:
    - True gay bar venue -> should be 5
    - Event name contains a drag keyword -> should be 4+
    - HHHH event -> should be 5
    Returns (status, messages).
    """
    messages = []
    for ev in events:
        name = (ev.get("name") or "").lower()
        venue = (ev.get("venue") or "").lower()
        score = _flamingo_score(ev)

        # Gay bar: must be 5
        if any(bar in venue for bar in _GAY_BAR_VENUES) and score < 5:
            messages.append(
                f"  FLAMINGO UNDER-SCORED: \"{ev.get('name','?')}\" "
                f"at gay bar venue scores {score} (expected 5)"
            )

        # Drag keyword: must be 4+
        if any(kw in name for kw in _DRAG_KEYWORDS) and score < 4:
            messages.append(
                f"  FLAMINGO UNDER-SCORED: \"{ev.get('name','?')}\" "
                f"has drag keyword but scores {score} (expected 4+)"
            )

        # HHHH: must be 5
        if _is_hhhh(ev) and score < 5:
            messages.append(
                f"  FLAMINGO UNDER-SCORED: \"{ev.get('name','?')}\" "
                f"is HHHH but scores {score} (expected 5)"
            )

    if not messages:
        return "PASS", ["  Flamingo scores look sane."]
    return "WARN", messages


# ── Check F: never-feature ordering ──────────────────────────────────────

def check_f_never_feature_ordering(events: list) -> tuple:
    """
    For each day, check that the first event (the one that would be featured/lead)
    is not in _NEVER_FEATURE.

    We replicate the main.py sort by building a simplified priority key.
    Returns (status, messages).
    """
    from collections import defaultdict
    messages = []

    # Group events by date/day
    days_events = defaultdict(list)
    for ev in events:
        date_str = ev.get("date", "")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            days_events[dt.strftime("%A")].append(ev)
        except ValueError:
            continue

    for day, day_evs in days_events.items():
        if not day_evs:
            continue
        # Sort by a simplified priority: never-feature events sink to the bottom
        def _priority(e):
            name = (e.get("name") or "").lower()
            # Is it in the _NEVER_FEATURE list?
            for nf in _NEVER_FEATURE:
                if nf in name:
                    return (1, name)  # worst = leads last (sorted ascending, so 1 = worst)
            # Is it a recurring name fragment?
            for frag in _RECURRING_NAME_FRAGMENTS:
                if frag in name:
                    return (1, name)
            return (0, name)  # good to feature

        sorted_evs = sorted(day_evs, key=_priority)
        leader = sorted_evs[0]
        leader_name = (leader.get("name") or "").lower()

        for nf in _NEVER_FEATURE:
            if nf in leader_name:
                messages.append(
                    f"  NEVER-FEATURE LEADS: \"{leader.get('name','?')}\" "
                    f"would lead {day} (matches _NEVER_FEATURE: '{nf}')"
                )
                break

    if not messages:
        return "PASS", ["  No never-feature events leading any day."]
    return "FAIL", messages


# ── Main runner ────────────────────────────────────────────────────────────

def run_verification(week_key: str) -> int:
    """
    Run all checks. Returns exit code (0=pass/warn, 1=fail).
    """
    print(f"\n{'=' * 50}")
    print("  TULSA GAYS WEEKLY VERIFICATION")
    print(f"  Week: {week_key}")
    print(f"{'=' * 50}\n")

    events = load_week_events(week_key)
    if not events:
        print(f"[ERROR] No events found for week {week_key}")
        print(f"        Expected file: data/events/{week_key}_all.json")
        print(f"        Run 'py main.py scrape' first.")
        return 1

    print(f"  Loaded {len(events)} events\n")

    results = []
    any_fail = False
    total_warnings = 0
    total_failures = 0

    # Check A
    status_a, msgs_a = check_a_venue_time_duplicates(events)
    results.append(("A", "Same-venue/time/date duplicates", status_a, msgs_a))

    # Check B (may modify events in-place)
    status_b, msgs_b, fixed_b = check_b_hhhh_venue(events)
    results.append(("B", "HHHH venue validation", status_b, msgs_b))
    if fixed_b > 0:
        save_week_events(week_key, events)
        print(f"  [auto-fix] Wrote corrected HHHH venues back to {week_key}_all.json\n")

    # Check C
    status_c, msgs_c = check_c_day_description_mismatch(events)
    results.append(("C", "Day-of-week description match", status_c, msgs_c))

    # Check D
    status_d, msgs_d = check_d_garbage_events(events)
    results.append(("D", "Garbage event filter", status_d, msgs_d))

    # Check E
    status_e, msgs_e = check_e_flamingo_sanity(events)
    results.append(("E", "Flamingo score sanity", status_e, msgs_e))

    # Check F
    status_f, msgs_f = check_f_never_feature_ordering(events)
    results.append(("F", "Priority ordering (never-feature)", status_f, msgs_f))

    # Print results
    for check_id, label, status, msgs in results:
        bracket = f"[{status}]"
        print(f"{bracket:<8} Check {check_id}: {label}")
        for msg in msgs:
            print(msg)
        print()
        if status == "FAIL":
            total_failures += 1
        elif status == "WARN":
            total_warnings += 1

    # Summary line
    if total_failures == 0 and total_warnings == 0:
        print("RESULT: ALL CHECKS PASSED")
        exit_code = 0
    elif total_failures == 0:
        plural = "s" if total_warnings > 1 else ""
        print(f"RESULT: {total_warnings} WARNING{plural} (auto-fixed) — OK to proceed")
        exit_code = 0
    else:
        w_str = f"{total_warnings} WARNING{'s' if total_warnings != 1 else ''}, " if total_warnings else ""
        f_str = f"{total_failures} FAILURE{'s' if total_failures != 1 else ''}"
        print(f"RESULT: {w_str}{f_str} (manual fix required before generating slides)")
        exit_code = 1

    print()
    return exit_code


def validate_day_references(descriptions: dict, events: list) -> None:
    """
    Standalone helper: warn if any description dict entry contains a day name
    that doesn't match the corresponding event's actual date.

    descriptions: {event_name_lower_key: (website_desc, slide_desc)}
    events:       list of event dicts
    """
    # Build a map of event name -> actual day
    name_to_day = {}
    for ev in events:
        name_lower = (ev.get("name") or "").lower()
        actual_day = _event_day_name(ev)
        if actual_day:
            name_to_day[name_lower] = actual_day

    for key, descs in descriptions.items():
        # Find the matching event
        actual_day = None
        for ev_name, day in name_to_day.items():
            if key in ev_name or ev_name in key:
                actual_day = day
                break
        if not actual_day:
            continue

        for desc_label, desc_text in zip(("website", "slide"), descs):
            if not desc_text:
                continue
            desc_lower = desc_text.lower()
            for day in _DAY_NAMES:
                if day in desc_lower and day != actual_day:
                    print(
                        f"  [WARNING] Day mismatch in '{key}' ({desc_label} desc): "
                        f"says '{day.capitalize()}' but event is on {actual_day.capitalize()}"
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pre-slide verification for the Tulsa Gays weekly pipeline."
    )
    parser.add_argument(
        "--week",
        help="Week key like 2026-W18 (default: current week)",
        default=None,
    )
    args = parser.parse_args()

    week_key = args.week or config.current_week_key()
    exit_code = run_verification(week_key)
    sys.exit(exit_code)
