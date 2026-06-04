"""Promote discovered source candidates into the live scraper.

Reads data/source_candidates.json (written by the weekly source-growth engine)
and acts on every candidate still in "candidate" status:

    confidence >= AUTO_PROMOTE  -> append to data/dynamic_sources.json (LIVE)
    QUEUE <= confidence < AUTO  -> append to pending-william-actions.md for review
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

PENDING_ACTIONS_FILE = r"C:\Users\willi\.claude\pending-william-actions.md"


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


# ── pending-william-actions.md queue ─────────────────────────────────────────
def _queue_for_review(rows, today):
    """Append a dated block of queued candidates. Skips ids already present."""
    if not rows:
        return 0
    existing = ""
    if os.path.exists(PENDING_ACTIONS_FILE):
        with open(PENDING_ACTIONS_FILE, "r", encoding="utf-8") as f:
            existing = f.read()

    fresh = [r for r in rows if r["id"] not in existing]
    if not fresh:
        return 0

    lines = [f"\n## [{today}] TulsaGays source-growth: {len(fresh)} new source(s) to review\n"]
    lines.append("Reply to approve; these were found but scored medium-confidence. "
                 "To approve, add them to `data/dynamic_sources.json` (or tell me to).\n")
    for r in fresh:
        loc = r.get("url") or r.get("kw")
        lines.append(f"- **{r['name']}** ({r['type']}, conf {r['confidence']}) - {loc}  \n"
                     f"  <!-- {r['id']} -->  \n"
                     f"  {r['evidence']}\n")
    block = "\n".join(lines)

    with open(PENDING_ACTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(block)
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
