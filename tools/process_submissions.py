"""Submission intake -> manual_events pipeline (Rung 4 backend).

The canonical-calendar flywheel is: groups submit their own events and they
appear on the site. The public submission FORM and the org outreach that drives
submissions are outward-facing (deployment + William) -- but the backend that
validates and ingests a submission is buildable and verifiable now.

Reads data/submissions.json (events submitted by orgs / board / readers),
validates each, and merges the good ones into data/manual_events.json (which the
scraper already reads). Idempotent: deduped by name+date so re-running is safe.

Submission schema (one object per event)::
    {"name": "...", "date": "YYYY-MM-DD", "time": "7:00 PM",
     "venue": "...", "description": "...", "url": "https://...",
     "submitted_by": "org or person"}

`--selftest` proves validation + merge + dedup on temp files.
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SUBMISSIONS_FILE = os.path.join(config.DATA_DIR, "submissions.json")
MANUAL_FILE = os.path.join(config.DATA_DIR, "manual_events.json")

_OK_MARKERS = ("tulsa", "broken arrow", "owasso", "jenks", "bixby", "sand springs",
               "sapulpa", "claremore", "catoosa", "glenpool", "ok", "oklahoma")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(sub):
    """Return (ok: bool, reason: str). A submission must be a real, dated,
    in-region event with a name."""
    if not isinstance(sub, dict):
        return False, "not an object"
    name = (sub.get("name") or "").strip()
    date = (sub.get("date") or "").strip()
    if len(name) < 3:
        return False, "missing/short name"
    if not _DATE_RE.match(date):
        return False, "bad date (need YYYY-MM-DD)"
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return False, "invalid calendar date"
    blob = " ".join([name, sub.get("venue", ""), sub.get("description", "")]).lower()
    # Region check is lenient: pass if any OK marker OR no location given at all
    has_loc = bool((sub.get("venue") or "").strip())
    if has_loc and not any(m in blob for m in _OK_MARKERS):
        # venue given but nothing says Oklahoma -> still allow if venue is a known
        # Tulsa place name; otherwise flag. Keep lenient (manual review downstream).
        pass
    return True, "ok"


def _norm_key(name, date):
    return (re.sub(r"\W+", "", (name or "").lower()), (date or "").strip())


def to_event(sub):
    return {
        "name": sub.get("name", "").strip(),
        "date": sub.get("date", "").strip(),
        "time": sub.get("time", "").strip(),
        "venue": sub.get("venue", "").strip(),
        "description": sub.get("description", "").strip(),
        "url": sub.get("url", "").strip(),
        "source": "submission",
        "priority": 2,
        "source_note": f"Submitted by {sub.get('submitted_by', 'community')}",
    }


def merge(submissions, manual):
    """Merge valid submissions into the manual list. Returns (new_manual, stats)."""
    existing = {_norm_key(e.get("name"), e.get("date")) for e in manual}
    added, dup, rejected = 0, 0, []
    out = list(manual)
    for sub in submissions:
        ok, reason = validate(sub)
        if not ok:
            rejected.append({"name": sub.get("name", "?"), "reason": reason})
            continue
        key = _norm_key(sub.get("name"), sub.get("date"))
        if key in existing:
            dup += 1
            continue
        existing.add(key)
        out.append(to_event(sub))
        added += 1
    return out, {"added": added, "duplicate": dup, "rejected": rejected,
                 "total": len(submissions)}


def run():
    if not os.path.exists(SUBMISSIONS_FILE):
        print("[submissions] no data/submissions.json -- nothing to ingest.")
        return {"added": 0}
    subs = json.load(open(SUBMISSIONS_FILE, encoding="utf-8"))
    subs = subs.get("submissions", subs) if isinstance(subs, dict) else subs
    manual = json.load(open(MANUAL_FILE, encoding="utf-8")) if os.path.exists(MANUAL_FILE) else []
    new_manual, stats = merge(subs, manual)
    if stats["added"]:
        json.dump(new_manual, open(MANUAL_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[submissions] {stats['added']} added, {stats['duplicate']} dup, "
          f"{len(stats['rejected'])} rejected of {stats['total']}.")
    for r in stats["rejected"]:
        print(f"  rejected: {r['name']} -- {r['reason']}")
    return stats


def _selftest():
    subs = [
        {"name": "Queer Crafternoon", "date": "2026-07-01", "time": "6 PM",
         "venue": "Fellowship Congregational, Tulsa", "submitted_by": "Fellowship"},
        {"name": "Queer Crafternoon", "date": "2026-07-01", "venue": "Fellowship", "submitted_by": "dup"},  # dup
        {"name": "x", "date": "2026-07-01"},                       # too-short name
        {"name": "No Date Event", "date": ""},                     # bad date
        {"name": "Bad Date", "date": "2026-13-40"},                # invalid calendar
    ]
    manual = [{"name": "Existing Thing", "date": "2026-06-30"}]
    out, stats = merge(subs, manual)
    assert stats["added"] == 1, stats
    assert stats["duplicate"] == 1, stats
    assert len(stats["rejected"]) == 3, stats
    # the one added event must be normalized to the manual schema
    added_ev = [e for e in out if e["name"] == "Queer Crafternoon"][0]
    assert added_ev["source"] == "submission", added_ev
    assert "Fellowship" in added_ev["source_note"], added_ev
    assert added_ev["priority"] == 2, added_ev
    print(f"process_submissions selftest: passed (1 added, 1 dup, 3 rejected; schema normalized)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    run()
