"""
Generate the weekly approval email draft for William.

Loads the current week's *_all.json, groups events by day, picks the
Event of the Week candidate, and formats a clean plain-text email.

Output:
  - Prints subject + body to stdout
  - Writes draft to data/posts/{week_key}/approval_email_draft.txt

Usage:
    python tools/generate_approval_email.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

# Allow running from project root or tools/ folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# Priority sources for Event of the Week selection (checked in order)
EOTW_SOURCE_PRIORITY = [
    "homo_hotel",
    "twisted_arts",
    "council_oak_chorus",
    "black_queer_tulsa",
    "antss",
    "tulsa_fringe",
    "okeq",
]

# Keywords in name/description that flag strong LGBTQ+ identity events
LGBTQ_KEYWORDS = [
    "drag", "queer", "lgbtq", "lgbt", "gay", "lesbian", "trans",
    "pride", "homo", "bisexual", "nonbinary", "two-spirit", "twospirit",
    "equality", "okeq", "stonewall", "rainbow",
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHORT_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def load_events(week_key):
    """Load the all-events JSON for the given week. Returns list of event dicts."""
    events_file = os.path.join(config.EVENTS_DIR, f"{week_key}_all.json")
    if not os.path.exists(events_file):
        return None, events_file

    with open(events_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        return data.get("events", []), events_file
    return data, events_file


def week_date_range(week_key):
    """Return (monday_date, sunday_date) for the given week key like '2026-W18'."""
    year, week_num = week_key.split("-W")
    # ISO week: Monday is day 1
    jan4 = datetime(int(year), 1, 4)  # Jan 4 is always in week 1
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    monday = week1_monday + timedelta(weeks=int(week_num) - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def format_date_range_label(monday, sunday):
    """Returns e.g. 'Mon Apr 28 - Sun May 4'."""
    def fmt(dt):
        return f"{DAY_NAMES[dt.weekday()][:3]} {SHORT_MONTHS[dt.month]} {dt.day}"
    return f"{fmt(monday)} - {fmt(sunday)}"


def is_lgbtq_relevant(event):
    """True if event is LGBTQ-specific based on source, flag, or keyword match."""
    if event.get("lgbtq_relevant"):
        return True
    source = event.get("source", "").lower()
    if source in EOTW_SOURCE_PRIORITY:
        return True
    text = (event.get("name", "") + " " + event.get("description", "")).lower()
    return any(kw in text for kw in LGBTQ_KEYWORDS)


def pick_event_of_week(events):
    """
    Choose the best Event of the Week candidate.
    Rules (in order):
      1. Source matches EOTW_SOURCE_PRIORITY list (earlier = better)
      2. LGBTQ-relevant events with priority == 1
      3. Any priority-1 event
      4. Fallback: first event in list
    """
    lgbtq_events = [e for e in events if is_lgbtq_relevant(e)]

    # Try EOTW_SOURCE_PRIORITY sources first
    for preferred_source in EOTW_SOURCE_PRIORITY:
        for event in lgbtq_events:
            if event.get("source", "").lower() == preferred_source:
                return event

    # Fallback: priority-1 LGBTQ event
    p1_lgbtq = [e for e in lgbtq_events if e.get("priority", 3) == 1]
    if p1_lgbtq:
        return p1_lgbtq[0]

    # Fallback: any priority-1
    p1 = [e for e in events if e.get("priority", 3) == 1]
    if p1:
        return p1[0]

    return events[0] if events else None


def group_by_day(events, monday):
    """
    Group events into a dict keyed by date string (YYYY-MM-DD).
    Only include events that fall within Mon-Sun of the given week.
    """
    week_dates = set()
    for i in range(7):
        week_dates.add((monday + timedelta(days=i)).strftime("%Y-%m-%d"))

    by_day = defaultdict(list)
    for event in events:
        date_str = event.get("date", "")
        if date_str in week_dates:
            by_day[date_str].append(event)

    return by_day


def day_heading(date_str):
    """Returns e.g. 'MONDAY, APRIL 28'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    month_full = dt.strftime("%B").upper()
    return f"{DAY_NAMES[dt.weekday()].upper()}, {month_full} {dt.day}"


def format_event_line(event):
    """Single-line event entry: name | time | venue"""
    name = event.get("name", "Unknown Event").strip()
    time = event.get("time", "").strip()
    venue = event.get("venue", "").strip()

    parts = [name]
    if time:
        parts.append(time)
    if venue:
        parts.append(venue)

    return "- " + " | ".join(parts)


def count_by_source(events):
    """Returns a dict of source -> count."""
    counts = defaultdict(int)
    for e in events:
        counts[e.get("source", "unknown")] += 1
    return dict(counts)


def build_email(week_key):
    """
    Build the subject line and plain-text body for the approval email.
    Returns (subject, body) tuple, or raises if events file not found.
    """
    events, events_file = load_events(week_key)

    monday, sunday = week_date_range(week_key)
    date_range_label = format_date_range_label(monday, sunday)
    subject = f"[TULSA GAYS] Event list for approval - {date_range_label}"

    if events is None:
        body = (
            f"Hi William,\n\n"
            f"The scrape for {week_key} hasn't run yet. No events file found at:\n"
            f"  {events_file}\n\n"
            f"Run 'python main.py scrape' from the tulsagays project folder, then "
            f"re-run generate_approval_email.py to get your approval draft.\n\n"
            f"-- Tulsa Gays Auto"
        )
        return subject, body

    if not events:
        body = (
            f"Hi William,\n\n"
            f"The events file for {week_key} exists but is empty. "
            f"The scrape may have had issues.\n\n"
            f"-- Tulsa Gays Auto"
        )
        return subject, body

    eotw = pick_event_of_week(events)
    by_day = group_by_day(events, monday)
    source_counts = count_by_source(events)

    # Format EOTW line
    if eotw:
        eotw_name = eotw.get("name", "Unknown")
        eotw_date = eotw.get("date", "")
        eotw_time = eotw.get("time", "")
        eotw_venue = eotw.get("venue", "")

        eotw_day_label = ""
        if eotw_date:
            try:
                dt = datetime.strptime(eotw_date, "%Y-%m-%d")
                eotw_day_label = DAY_NAMES[dt.weekday()]
            except ValueError:
                eotw_day_label = eotw_date

        eotw_parts = [eotw_day_label] if eotw_day_label else []
        if eotw_time:
            eotw_parts.append(eotw_time)
        if eotw_venue:
            eotw_parts.append(eotw_venue)

        eotw_detail = ", ".join(eotw_parts) if eotw_parts else "see below"
        eotw_line = f"SUGGESTED EVENT OF THE WEEK: {eotw_name} ({eotw_detail})"
    else:
        eotw_line = "SUGGESTED EVENT OF THE WEEK: (none identified)"

    # Build day sections
    day_sections = []
    for i in range(7):
        date_str = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
        day_events = by_day.get(date_str, [])

        heading = day_heading(date_str)
        if day_events:
            lines = [heading]
            for ev in day_events:
                lines.append(format_event_line(ev))
            day_sections.append("\n".join(lines))
        else:
            day_sections.append(f"{heading}\n(no events scraped)")

    # Source summary
    source_summary_parts = [f"{src} ({cnt})" for src, cnt in sorted(source_counts.items())]
    source_summary = ", ".join(source_summary_parts)

    body_parts = [
        f"Hi William,",
        "",
        "Here's this week's event list for your review. Reply APPROVED (with any changes) to greenlight Monday's post.",
        "",
        eotw_line,
        "",
    ]
    body_parts.extend(day_sections)
    body_parts.extend([
        "",
        f"Total events this week: {len(events)}",
        f"Sources: {source_summary}",
        "",
        "Reply APPROVED or include changes.",
        "-- Tulsa Gays Auto",
    ])

    body = "\n".join(body_parts)
    return subject, body


def save_draft(week_key, subject, body):
    """Write the draft to data/posts/{week_key}/approval_email_draft.txt"""
    posts_dir = os.path.join(config.DATA_DIR, "posts", week_key)
    os.makedirs(posts_dir, exist_ok=True)

    draft_path = os.path.join(posts_dir, "approval_email_draft.txt")
    content = f"Subject: {subject}\n\n{body}"
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(content)

    return draft_path


def main():
    week_key = config.current_week_key()
    print(f"Generating approval email for week: {week_key}")

    subject, body = build_email(week_key)

    print("\n" + "=" * 60)
    print(f"SUBJECT: {subject}")
    print("=" * 60)
    print(body)
    print("=" * 60)

    draft_path = save_draft(week_key, subject, body)
    print(f"\nDraft saved to: {draft_path}")


if __name__ == "__main__":
    main()
