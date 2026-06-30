"""
On-demand verification report for recurring events.

Prints the confirmation state of every tracked recurring event (worst tier
first), so you can see at a glance what needs re-confirming -- which events
haven't been corroborated by a live scrape or a human in a while, what venue
each is believed to be at, and how that confirmation was made.

    python tools/verify_recurring.py            # full report
    python tools/verify_recurring.py --stale    # only stale + expired (the to-do list)
    python tools/verify_recurring.py --selftest  # prove the underlying module

The ledger is data/recurring_confirmations.json. To act on a row: confirm it
(set last_verified to today + verified_by 'human:<who>' + the right venue), or
set status 'dead'/'paused' to stop a gone/suspended event from posting.
"""
import os
import sys
from datetime import date

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from scraper.recurring_verify import load_ledger, report_lines, tier_for, _selftest


def main(argv):
    if "--selftest" in argv:
        _selftest()
        return 0
    ledger = load_ledger()
    today = date.today().isoformat()
    lines = report_lines(ledger, today)
    events = ledger.get("events", {})
    counts = {"fresh": 0, "stale": 0, "expired": 0, "dropped": 0}
    for entry in events.values():
        counts[tier_for(entry, today, ledger)[0]] = counts.get(tier_for(entry, today, ledger)[0], 0) + 1

    only_stale = "--stale" in argv
    print("=" * 70)
    print(f"RECURRING EVENT VERIFICATION -- {today}")
    print(f"stale after {ledger.get('stale_after_days')}d, blocks featuring after "
          f"{ledger.get('block_after_days')}d")
    print("=" * 70)
    if not events:
        print("\nLedger is empty -- it auto-populates on the next Monday scrape.")
        print("(scraper/recurring_verify runs inside the scrape and stamps each event.)")
        return 0
    print(f"\n{counts['expired']} expired  {counts['stale']} stale  "
          f"{counts['fresh']} fresh  {counts['dropped']} dropped\n")
    for ln in lines:
        if only_stale and ln.lstrip().startswith("[fresh") or only_stale and ln.lstrip().startswith("[dropped"):
            continue
        print("  " + ln)
    todo = counts["expired"] + counts["stale"]
    if todo:
        print(f"\n>>> {todo} event(s) need a confirmation pass (verify venue + that it still runs).")
    else:
        print("\nAll tracked recurring events are freshly confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
