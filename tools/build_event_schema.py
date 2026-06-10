"""Build Event JSON-LD (schema.org ItemList) from events-current.json.

Produces AI-citable structured data for the weekly event listings. Run after
elevate_blog.py each week, then inject the printed block into the homepage
<head> (it survives the scraper regeneration zone).

Usage:
    python tools/build_event_schema.py            # print to stdout
    python tools/build_event_schema.py --out docs/event-schema.jsonld
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVENTS = REPO / "docs" / "events-current.json"
SITE = "https://www.tulsagays.com"


def parse_start(date_str, time_str):
    """Return ISO 8601 datetime (or date-only) for schema startDate."""
    time_str = (time_str or "").replace(" ", " ").strip()
    if not time_str:
        return date_str
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", time_str, re.I)
    if not m:
        return date_str
    hour, minute, mer = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if mer == "PM" and hour != 12:
        hour += 12
    if mer == "AM" and hour == 12:
        hour = 0
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
    except ValueError:
        return date_str
    # Tulsa is America/Chicago. June = CDT (-05:00); Nov-Mar = CST (-06:00).
    month = dt.month
    offset = "-05:00" if 3 <= month <= 10 else "-06:00"
    return dt.strftime("%Y-%m-%dT%H:%M:00") + offset


def split_venue(venue):
    """Split 'Name, 123 Street, City, OK' into (name, street_address)."""
    venue = (venue or "").strip()
    if not venue:
        return ("Tulsa, OK", "")
    parts = [p.strip() for p in venue.split(",")]
    name = parts[0]
    street = parts[1] if len(parts) > 1 and re.search(r"\d", parts[1]) else ""
    return (name, street)


def build(events):
    items = []
    for i, ev in enumerate(events, start=1):
        venue_name, street = split_venue(ev.get("venue", ""))
        location = {
            "@type": "Place",
            "name": venue_name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Tulsa",
                "addressRegion": "OK",
                "addressCountry": "US",
            },
        }
        if street:
            location["address"]["streetAddress"] = street
        event = {
            "@type": "Event",
            "name": ev.get("name", "").strip(),
            "startDate": parse_start(ev.get("date", ""), ev.get("time", "")),
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "eventStatus": "https://schema.org/EventScheduled",
            "location": location,
            "organizer": {
                "@type": "Organization",
                "name": "Tulsa Gays",
                "url": SITE,
            },
        }
        items.append({"@type": "ListItem", "position": i, "item": event})

    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "LGBTQ+ Events in Tulsa, Oklahoma This Week",
        "description": "This week's LGBTQ+ events, drag shows, bar nights, and community "
                       "gatherings in Tulsa, Oklahoma, updated weekly by Tulsa Gays.",
        "url": SITE + "/",
        "numberOfItems": len(items),
        "itemListElement": items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    schema = build(events)
    block = ('<script type="application/ld+json">\n'
             + json.dumps(schema, indent=2, ensure_ascii=False)
             + "\n</script>")
    if args.out:
        Path(args.out).write_text(block, encoding="utf-8")
        print(f"Wrote {args.out} ({len(events)} events)")
    else:
        print(block)


if __name__ == "__main__":
    main()
