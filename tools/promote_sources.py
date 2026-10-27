"""Promote discovered source candidates into the live scraper.

Reads data/source_candidates.json (written by the weekly source-growth engine)
and acts on every candidate still in "candidate" status:

    confidence >= AUTO_PROMOTE  -> append to data/dynamic_sources.json (LIVE)
    QUEUE <= confidence < AUTO  -> file to the TODAY dashboard for review
    confidence <  QUEUE         -> mark rejected

Promotion only ever APPENDS to a JSON data file -- it never edits scraper .py
source -- so it cannot break Monday's scrape. Fully idempotent: re-running
skips anything already promoted/queued and de-dups against the live scraper.

Usage:
    python tools/promote_sources.py            # act for real
    python tools/promote_sources.py --dry-run  # show what would happen
    python tools/promote_sources.py --auto 85 --queue 60   # tune thresholds
"""

import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dynamic_sources as dyn
from self_improve import source_registry as registry

AUTO_PROMOTE_DEFAULT = 85
QUEUE_DEFAULT = 60

# Read-only since 2026-10-27: only consulted so ids queued there before the
# switch to the dashboard are not filed a second time.
PENDING_ACTIONS_FILE = r"C:\Users\willi\.claude\pending-william-actions.md"
QUEUED_IDS_FILE = os.path.join(config.DATA_DIR, "source_review_queued.json")
SUBMIT_BRIEF = os.path.join(os.path.expanduser("~"), ".claude", "chief-of-staff", "submit_brief.py")


# ── dynamic_sources.json writing ─────────────────────────────────────────────
def _load_dynamic():
    if os.path.exists(dyn.DYNAMIC_SOURCES_FILE):
        try:
            with open(dyn.DYNAMIC_SOURCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"fb_pages": [], "fb_groups": [], "calendars": [], "partner_keywords": []}


def _save_dynamic(data):
    with open(dyn.DYNAMIC_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _events_tab(url: str) -> str:
    """Normalize a Facebook page/group URL to its /events tab."""
    u = url.rstrip("/")
    if not u.endswith("/events"):
        u = u + "/events"
    return u


def _already_in_dynamic(data, cand) -> bool:
    t = cand["type"]
    if t == "fb_page":
        return any(registry._norm_url(e.get("url", "")) == registry._norm_url(cand["url"])
                   for e in data["fb_pages"])
    if t == "fb_group":
        return any(registry._norm_url(e.get("url", "")) == registry._norm_url(cand["url"])
                   for e in data["fb_groups"])
    if t == "calendar":
        return any(registry._norm_url(e.get("url", "")) == registry._norm_url(cand["url"])
                   for e in data["calendars"])
    # venue_keyword / org_keyword
    return any(registry._norm_kw(e.get("kw", "")) == registry._norm_kw(cand["kw"])
               for e in data["partner_keywords"])


def _add_to_dynamic(data, cand, today) -> bool:
    """Append cand to the right list. Returns True if newly added."""
    if _already_in_dynamic(data, cand):
        return False
    t = cand["type"]
    if t == "fb_page":
        data["fb_pages"].append({"url": _events_tab(cand["url"]), "name": cand["name"],
                                 "added": today, "via": cand.get("discovered_via", "")})
    elif t == "fb_group":
        data["fb_groups"].append({"url": _events_tab(cand["url"]), "name": cand["name"],
                                  "added": today, "via": cand.get("discovered_via", "")})
    elif t == "calendar":
        data["calendars"].append({"url": cand["url"], "name": cand["name"],
                                  "category": cand.get("category", "community"),
                                  "added": today, "via": cand.get("discovered_via", "")})
    else:  # venue_keyword / org_keyword
        data["partner_keywords"].append({"kw": cand["kw"].lower(), "name": cand["name"],
                                         "added": today, "via": cand.get("discovered_via", "")})
    return True


# ── review queue (TODAY dashboard) ───────────────────────────────────────────
def _queue_for_review(rows, today):
    """File a dated block of medium-confidence candidates to the TODAY dashboard.
    Skips ids already queued. Until 2026-10-27 this appended to William's Action
    Inbox; reviewing a candidate source is fleet work a session can do, so it is
    a dashboard report now (5 inbox entries in the archive came from here)."""
    if not rows:
        return 0
    existing = ""
    if os.path.exists(PENDING_ACTIONS_FILE):
        with open(PENDING_ACTIONS_FILE, "r", encoding="utf-8", errors="replace") as f:
            existing = f.read()
    try:
        with open(QUEUED_IDS_FILE, "r", encoding="utf-8") as f:
            queued = set(json.load(f))
    except Exception:
        queued = set()

    fresh = [r for r in rows if r["id"] not in existing and r["id"] not in queued]
    if not fresh:
        return 0

    lines = ["These were found but scored medium-confidence. To approve one, add it "
             "to `data/dynamic_sources.json`.\n"]
    for r in fresh:
        loc = r.get("url") or r.get("kw")
        lines.append(f"- **{r['name']}** ({r['type']}, conf {r['confidence']}) - {loc}  \n"
                     f"  {r['evidence']}  \n"
                     f"  id: {r['id']}\n")
    import subprocess
    if not os.path.exists(SUBMIT_BRIEF):
        print(f"[promote] {SUBMIT_BRIEF} not found; {len(fresh)} candidate(s) not filed")
        return 0
    rc = subprocess.run(
        [sys.executable, SUBMIT_BRIEF, "--task", "tulsagays-source-growth", "--priority", "low",
         "--subject", f"TulsaGays source-growth: {len(fresh)} new source(s) to review ({today})",
         "--body", "\n".join(lines)],
        capture_output=True, text=True, timeout=60).returncode
    if rc != 0:
        return 0
    with open(QUEUED_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(queued | {r["id"] for r in fresh}), f, indent=1)
    return len(fresh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--auto", type=int, default=AUTO_PROMOTE_DEFAULT,
                    help="confidence >= this is auto-promoted into the live scraper")
    ap.add_argument("--queue", type=int, default=QUEUE_DEFAULT,
                    help="confidence >= this (but < auto) is queued for review")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="date stamp (YYYY-MM-DD); pass explicitly in scheduled runs")
    args = ap.parse_args()

    cands = registry.pending()
    if not cands:
        print("[promote] no pending candidates.")
        return

    dynamic = _load_dynamic()
    promoted, queued, rejected = [], [], []
    queue_rows = []

    for c in sorted(cands, key=lambda x: -x.get("confidence", 0)):
        conf = c.get("confidence", 0)
        if conf >= args.auto:
            if args.dry_run:
                promoted.append(c)
            else:
                if _add_to_dynamic(dynamic, c, args.date):
                    registry.set_status(c["id"], "promoted", args.date)
                    promoted.append(c)
                else:
                    registry.set_status(c["id"], "promoted", args.date)  # already live = done
        elif conf >= args.queue:
            queued.append(c)
            queue_rows.append(c)
        else:
            rejected.append(c)
            if not args.dry_run:
                registry.set_status(c["id"], "rejected")

    if not args.dry_run:
        if promoted:
            _save_dynamic(dynamic)
        n_q = _queue_for_review(queue_rows, args.date)
        for c in queued:
            registry.set_status(c["id"], "queued")
    else:
        n_q = len(queue_rows)

    print(f"[promote] {'DRY RUN -- ' if args.dry_run else ''}"
          f"{len(promoted)} promoted (live), {n_q} queued for review, {len(rejected)} rejected.")
    for c in promoted:
        print(f"  + LIVE  [{c['type']}] {c['name']} (conf {c['confidence']})")
    for c in queued:
        print(f"  ~ QUEUE [{c['type']}] {c['name']} (conf {c['confidence']})")


if __name__ == "__main__":
    main()
