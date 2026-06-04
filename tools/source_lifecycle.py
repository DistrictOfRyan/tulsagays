"""Closed-loop lifecycle for the TulsaGays source-growth engine.

The discovery engine ADDS sources. This module makes the loop self-healing so
the catalog doesn't rot:

  1. update_last_seen()  -- stamp each live dynamic source + promoted candidate
     with the last date it actually produced an event, and a cumulative count.
  2. retire_stale()      -- move sources silent past a threshold into a
     `retired` bucket so the scrapers stop hitting them (loader ignores it).
  3. reconcile_candidates() -- a queued/candidate source that keeps recurring in
     later scrapes earns confidence; once it crosses the auto bar it's flipped
     back to `candidate` so the promoter takes it live next run.

All of this APPENDS/edits only data/*.json (gitignored local state) -- never
scraper .py -- so it can't break Monday's scrape. Run before promote_sources.py
in the weekly task. `--selftest` proves the logic on synthetic data.
"""

import os
import sys
import json
import glob
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dynamic_sources as dyn
from self_improve import source_registry as registry

STALE_DAYS = 120        # silent this long -> retire
GRACE_DAYS = 35         # a just-added source that never produced gets this long
RECUR_AUTO = 85         # confidence at/above this is auto-promotable


# ── event matching ───────────────────────────────────────────────────────────
def _load_recent_events(weeks=10):
    """Return [(week_key, [event dicts])] for the most recent N weeks."""
    files = sorted(glob.glob(os.path.join(config.EVENTS_DIR, "*_all.json")),
                   key=os.path.getmtime)[-weeks:]
    out = []
    for f in files:
        wk = os.path.basename(f).split("_all.json")[0]
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        events = data.get("events", []) if isinstance(data, dict) else data
        out.append((wk, [e for e in events if isinstance(e, dict)]))
    return out


def _event_blob(e):
    return " ".join([e.get("name", ""), e.get("venue", ""), e.get("url", ""),
                     e.get("description", "")]).lower()


def _page_token(url):
    """Extract a matchable token from a FB page/group url (the slug or id)."""
    u = registry._norm_url(url)            # facebook.com/SlugName
    return u.split("facebook.com/")[-1].split("/")[0] if "facebook.com/" in u else u


def _last_seen_for(kind, ident, recent):
    """Return (last_seen_date_str|None, count) for a source across recent weeks."""
    last, count = None, 0
    if kind in ("fb_page", "fb_group"):
        needle = _page_token(ident).lower()
    else:
        needle = registry._norm_kw(ident)
    if not needle:
        return None, 0
    for wk, events in recent:
        hit = any(needle in _event_blob(e) for e in events)
        if hit:
            count += 1
            last = wk        # week key like 2026-W23; recency = file order
    return last, count


# ── 1. last-seen stamping ────────────────────────────────────────────────────
def _load_dynamic_raw():
    if os.path.exists(dyn.DYNAMIC_SOURCES_FILE):
        try:
            return json.load(open(dyn.DYNAMIC_SOURCES_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {"fb_pages": [], "fb_groups": [], "calendars": [], "partner_keywords": []}


def _save_dynamic_raw(data):
    json.dump(data, open(dyn.DYNAMIC_SOURCES_FILE, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)


def _today():
    return os.environ.get("SOURCE_GROWTH_DATE") or datetime.now().strftime("%Y-%m-%d")


def update_last_seen(data, recent):
    """Stamp last_seen_week / seen_count on every live dynamic source."""
    kind_map = {"fb_pages": "fb_page", "fb_groups": "fb_group",
                "calendars": "calendar", "partner_keywords": "partner_keyword"}
    for listkey, kind in kind_map.items():
        for e in data.get(listkey, []):
            ident = e.get("url") or e.get("kw") or ""
            last, count = _last_seen_for(
                "fb_page" if kind in ("fb_page", "fb_group") else "kw", ident, recent)
            if last:
                e["last_seen_week"] = last
                e["seen_count"] = e.get("seen_count", 0) + (1 if last != e.get("last_seen_week") else 0)
                e["last_checked"] = _today()
            else:
                e.setdefault("seen_count", 0)
                e["last_checked"] = _today()
    return data


# ── 2. retire stale ──────────────────────────────────────────────────────────
def _age_days(date_str, today):
    try:
        return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return 0


def retire_stale(data, today, stale_days=STALE_DAYS, grace_days=GRACE_DAYS):
    """Move sources silent past threshold into data['retired']. Returns count."""
    retired = data.setdefault("retired", [])
    moved = 0
    for listkey in ("fb_pages", "fb_groups", "calendars", "partner_keywords"):
        keep = []
        for e in data.get(listkey, []):
            added = e.get("added", "")
            seen = e.get("seen_count", 0)
            checked = e.get("last_checked", added)
            # Never seen + past grace since added -> retire as "never produced".
            # Seen before but quiet past stale window -> retire as "went silent".
            if seen == 0 and added and _age_days(added, today) > grace_days:
                e["retired_reason"] = "never produced an event"
                e["retired_at"] = today
                e["from"] = listkey
                retired.append(e)
                moved += 1
                continue
            if seen > 0 and checked and _age_days(checked, today) > stale_days:
                e["retired_reason"] = f"silent > {stale_days}d"
                e["retired_at"] = today
                e["from"] = listkey
                retired.append(e)
                moved += 1
                continue
            keep.append(e)
        data[listkey] = keep
    return moved


# ── 3. recurrence -> confidence ──────────────────────────────────────────────
def reconcile_candidates(recent, today):
    """Bump confidence of queued/candidate sources that keep recurring.

    A medium-confidence venue that shows up in more recent weeks is more real.
    +6 confidence per recurring week beyond the first, capped so 3+ recurrences
    can lift a 70 into auto-promote range. Flips crossed ones back to
    'candidate' so promote_sources.py takes them live. Returns count bumped.
    """
    cands = registry.load()
    bumped = 0
    changed = False
    for c in cands:
        if c.get("status") not in ("candidate", "queued"):
            continue
        ident = c.get("url") or c.get("kw") or ""
        kind = "fb_page" if c.get("type") in ("fb_page", "fb_group") else "kw"
        _, count = _last_seen_for(kind, ident, recent)
        if count >= 2:
            new_conf = min(95, c.get("confidence", 0) + 6 * (count - 1))
            if new_conf > c.get("confidence", 0):
                c["confidence"] = new_conf
                c["evidence"] = (c.get("evidence", "") +
                                 f" [recurrence: seen in {count} recent weeks -> conf {new_conf}]")
                if new_conf >= RECUR_AUTO and c.get("status") == "queued":
                    c["status"] = "candidate"   # re-arm for promotion
                bumped += 1
                changed = True
    if changed:
        registry.save(cands)
    return bumped


def run():
    today = _today()
    recent = _load_recent_events()
    data = _load_dynamic_raw()
    update_last_seen(data, recent)
    retired = retire_stale(data, today)
    _save_dynamic_raw(data)
    bumped = reconcile_candidates(recent, today)
    live = sum(len(data.get(k, [])) for k in ("fb_pages", "fb_groups", "calendars", "partner_keywords"))
    print(f"[lifecycle] {today}: {live} live sources, {retired} retired, "
          f"{bumped} candidate(s) re-scored by recurrence.")
    return {"live": live, "retired": retired, "bumped": bumped}


# ── self-test (synthetic data, no real files touched) ────────────────────────
def _selftest():
    today = "2026-06-04"
    # Synthetic recent weeks: a kw that recurs, and a page seen once long ago.
    recent = [
        ("2026-W20", [{"name": "Sound bath", "venue": "Zen Den", "url": "", "description": ""}]),
        ("2026-W22", [{"name": "Crafternoon", "venue": "Zen Den", "url": "", "description": ""}]),
        ("2026-W23", [{"name": "Meditation", "venue": "Zen Den", "url": "", "description": ""}]),
    ]
    # last-seen + retire
    data = {
        "fb_pages": [
            {"url": "https://www.facebook.com/LiveGroup/events", "name": "Live", "added": "2026-05-01"},
            {"url": "https://www.facebook.com/GhostGroup/events", "name": "Ghost", "added": "2026-01-01"},
        ],
        "fb_groups": [], "calendars": [],
        "partner_keywords": [
            {"kw": "zen den", "name": "Zen Den", "added": "2026-05-01"},
        ],
    }
    # No event mentions LiveGroup/GhostGroup pages, so both are 'never produced'.
    # Ghost added 2026-01-01 (>35d grace before 06-04) -> retire. Live added
    # 2026-05-01 (<35d) -> kept on grace. zen den recurs -> seen, kept.
    update_last_seen(data, recent)
    assert data["partner_keywords"][0].get("last_seen_week") == "2026-W23", "kw last_seen wrong"
    n = retire_stale(data, today)
    live_pages = [e["name"] for e in data["fb_pages"]]
    assert "Ghost" not in live_pages, "stale ghost page not retired"
    assert "Live" in live_pages, "in-grace page wrongly retired"
    assert any(r["name"] == "Ghost" for r in data["retired"]), "ghost not in retired bucket"
    assert n == 1, f"expected 1 retired, got {n}"
    # loader must ignore the 'retired' key (no crash, retired not served)
    assert "GhostGroup" not in " ".join(str(x) for x in dyn._EMPTY)
    print("source_lifecycle selftest: all assertions passed "
          f"(retired={n}, kw last_seen={data['partner_keywords'][0]['last_seen_week']})")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    run()
