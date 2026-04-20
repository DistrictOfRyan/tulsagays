"""Test the Facebook events scraper.

Usage:
    python tools/test_fb_events.py           # current week
    python tools/test_fb_events.py --next    # next week
    python tools/test_fb_events.py --offset 2  # 2 weeks out
"""

import os
import sys
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from scraper.facebook_events import FacebookEventsScraper, _get_week_range, SESSION_FILE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--next", action="store_true", help="Scrape next week")
    parser.add_argument("--offset", type=int, default=0, help="Week offset (0=current, 1=next, ...)")
    args = parser.parse_args()

    week_offset = 1 if args.next else args.offset
    monday, sunday = _get_week_range(week_offset)

    print()
    print("=" * 65)
    print("Facebook Events Scraper -- Test Run")
    print(f"Target week:  {monday.date()} (Mon) to {sunday.date()} (Sun)")
    print(f"Session file: {SESSION_FILE}")
    print(f"Session exists: {'YES' if os.path.exists(SESSION_FILE) else 'NO -- run tools/fb_login.py first'}")
    print("=" * 65)
    print()

    if not os.path.exists(SESSION_FILE):
        print("ERROR: No saved Facebook session.")
        print("Run this first:  python tools/fb_login.py")
        print("Then re-run:     python tools/test_fb_events.py --next")
        return

    scraper = FacebookEventsScraper(week_offset=week_offset)
    events = scraper.safe_scrape()

    print()
    print("=" * 65)
    print(f"RESULTS: {len(events)} Facebook events found")
    print("=" * 65)

    if not events:
        print()
        print("No events returned. Possible reasons:")
        print("  - Session expired (re-run tools/fb_login.py)")
        print("  - Facebook changed their HTML structure (check scraper logs)")
        print("  - No events found for this week matching the search terms")
        return

    by_date = {}
    no_date = []
    for e in events:
        d = e.get("date", "")
        if d:
            by_date.setdefault(d, []).append(e)
        else:
            no_date.append(e)

    for date in sorted(by_date.keys()):
        from datetime import datetime as dt
        try:
            label = dt.strptime(date, "%Y-%m-%d").strftime("%A %b %d")
        except ValueError:
            label = date
        print(f"\n  [{label}]")
        for e in by_date[date]:
            t = e.get("time", "")
            print(f"    {t:12s}  {e['name'][:52]}")
            if e.get("venue"):
                print(f"                  @ {e['venue'][:48]}")
            if e.get("description"):
                print(f"                  {e['description'][:80]}...")
            print(f"                  {e.get('url', '')}")

    if no_date:
        print(f"\n  [No date -- {len(no_date)} events]")
        for e in no_date:
            print(f"    {e['name'][:60]}")
            print(f"    {e.get('url', '')}")

    print()
    print(f"Sources breakdown:")
    from collections import Counter
    sources = Counter(e.get("source", "?") for e in events)
    for src, count in sources.most_common():
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()
