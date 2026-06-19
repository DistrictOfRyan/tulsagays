#!/usr/bin/env python3
"""Weekly source-growth runner - the loop that was built but never wired.

Closes the gap between three existing pieces that were never connected on a
schedule:
  1. self_improve/source_discovery.mine_recent_events() finds venues/orgs that
     recur in recent scrapes but aren't trusted sources yet.
  2. self_improve/source_registry records them as candidates (with dedup against
     the live scraper).
  3. tools/promote_sources promotes high-confidence candidates into the live
     scraper (data/dynamic_sources.json) and queues mid-confidence ones to
     pending-william-actions.md for review.

mine_recent_events() returned candidates but NOTHING registered them, so
promote always saw "no pending candidates" and coverage never grew. This script
registers the mined candidates, then runs promotion. New venues the scraper
keeps seeing (e.g. Inner Circle drag nights, once its FB page feeds in) now get
auto-proposed instead of waiting for someone to notice by hand.

Run standalone:  python tools/run_source_growth.py [--dry-run]
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from self_improve import source_discovery as sd
from self_improve import source_registry as reg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    today = datetime.now().strftime("%Y-%m-%d")

    mined = sd.mine_recent_events()
    counts = {"added": 0, "exists": 0, "known": 0, "invalid": 0}
    for m in mined:
        kw = m.get("kw", "")
        if not kw:
            continue
        if args.dry_run:
            counts["added"] += 1
            continue
        status = reg.add_candidate(
            ctype="venue_keyword",
            name=kw.title(),
            kw=kw,
            category="community",
            confidence=int(m.get("confidence", 0)),
            evidence=f"{m.get('events', 0)} events across {m.get('weeks', 0)} week(s) "
                     f"in recent scrapes; recurring venue not yet a trusted source",
            discovered_via="weekly-mine",
            discovered_at=today,
        )
        counts[status] = counts.get(status, 0) + 1

    print(f"[source-growth] mined {len(mined)} recurring venue(s); "
          f"registered new={counts['added']} exists={counts['exists']} known={counts['known']}")

    # Promote: auto >=85 into the live scraper, queue 60-85 to William's review
    # inbox (which renders on the TODAY dashboard), reject the rest.
    cmd = [sys.executable, str(REPO / "tools" / "promote_sources.py"), "--date", today]
    if args.dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "").strip()
    print(out)
    # Emit a final one-line JSON summary for the scheduler to parse.
    import json
    promoted = out.count("PROMOTE") if "promoted" not in out else None
    print(json.dumps({
        "mined": len(mined),
        "registered_new": counts["added"],
        "promote_stdout_tail": out[-200:],
    }))


if __name__ == "__main__":
    main()
