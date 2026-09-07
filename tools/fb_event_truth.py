#!/usr/bin/env python3
"""
tools/fb_event_truth.py - verify Facebook events against Facebook's OWN metadata.

WHY THIS EXISTS (2026-09-07, W37)
---------------------------------
On Monday 2026-09-07 the weekly prep blocked at preflight and TulsaGays did not
post. The gate that stopped it was the YBR partner-source rule, and it was RIGHT:
the deck's "YBR Luau Party!!" was scheduled for Wednesday 2026-09-09, but
Facebook's own og:description for that event id reads

    "Evento de YBR Pub el sabado, septiembre 9 2023"

September 9 **2023**. A three-year-old event, projected onto this week because
the day-of-month matched. Checking the whole deck the same way found EIGHT such
ghosts (2023, 2024 and 2025 events dated into 2026-W37) plus SEVEN events in
other cities entirely - Puerto Vallarta, plus HotMess Sports chapters in Mobile,
Columbia, Charleston and Knoxville plumbed in as if they were Tulsa.

Every existing layer missed all fifteen:
  - scraper/runner.py runs tools/geo_guard.py, but that guard is a BLOCKLIST of
    known other-metro domains/venues. facebook.com/events/<id> URLs carry no
    geography, so nothing matched.
  - tools/preflight_post.py has no geo assertion and no date-truth assertion.
  - tools/final_deck_review.py has neither either.
  - scraper/instagram_orgs._within_announce_window fixed exactly this
    stale-date-projection class in July, but ONLY for Instagram sources
    ([[feedback_tulsagays_ybr_ig_only]]). Facebook was never given the same guard.

THE IDEA
--------
A Facebook event id is a permanent handle to Facebook's own record. Fetching the
public og: tags gives us the event's TRUE date and TRUE city, straight from the
source, with no login. That is a positive assertion, not a blocklist, so it
catches cities nobody thought to enumerate and years nobody thought to check.

VERDICTS
--------
  stale_year     FB's year != the date we scheduled it on   -> suppress (ghost)
  date_mismatch  FB's month/day != ours, same year          -> suppress (projection)
  foreign_city   FB's city is not in this site's metro       -> suppress (geo leak)
  unknown        no og:description, or the fetch failed      -> WARN only
  ok             FB agrees with us

FAIL-OPEN ON UNKNOWN, FAIL-CLOSED ON KNOWN-BAD. A Facebook outage must never
empty the deck, but a confirmed ghost must never ship. Same doctrine as the
partner rule it backs up: under-promote rather than post a ghost event.

Usage
-----
  python tools/fb_event_truth.py                    # audit this week, exit 1 if ghosts
  python tools/fb_event_truth.py --week 2026-W37
  python tools/fb_event_truth.py --suppress         # mark ghosts never_feature + rewrite
  python tools/fb_event_truth.py --suppress --render  # ...and re-render the deck
  python tools/fb_event_truth.py --selftest         # parser proof, no network
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# UA MATTERS, and not in the way you would guess (measured 2026-09-07). A normal
# Chrome/Firefox UA gets HTTP 400 from Facebook after a few dozen anonymous event
# fetches - a soft rate-limit that looks exactly like "every event is private" and
# would silently fail this gate OPEN on the whole deck. Facebook's OWN crawler UA
# is served the og: tags reliably, on both www and mbasic, and is the honest thing
# to send: we are asking for the Open Graph card, which is what that UA is for.
# Ordered by preference; each is tried before an event is called unverifiable.
UAS = [
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "curl/8.4.0",
]

FB_EVENT_RE = re.compile(r"facebook\.com/events/(\d{6,})")

# og: cards for a given event id do not change week to week, so a small on-disk
# cache keeps the Monday run to a handful of live fetches instead of ~50.
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "fb_event_truth_cache.json")
CACHE_TTL_DAYS = 30

# Facebook serves these og: tags in Spanish for this machine's locale. Both the
# Spanish and English month names are accepted so a locale flip cannot silently
# turn every event into "unknown" (which would fail open and re-open the hole).
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

# "... el sabado, septiembre 9 2023"  /  "... on Saturday, September 9 2023"
DATE_RE = re.compile(
    rf"\b(?:el|on)\s+[^,]{{2,20}},\s*({_MONTH_ALT})\s+(\d{{1,2}})\s+(\d{{4}})",
    re.IGNORECASE)

# "Evento en Tulsa, Estados Unidos de America de Grim House el ..."
# "Evento de Deportes en Mobile, Estados Unidos de America de HotMess Sports ..."
CITY_COUNTRY_RE = re.compile(
    r"\b(?:en|in)\s+([^,]{2,40}),\s*(Estados Unidos de Am\w+rica|United States|"
    r"M\w+xico|Mexico|Canad\w+|Canada)\b", re.IGNORECASE)
# "Evento en Puerto Vallarta de The Swedes Bar & Bistro el lunes, ..." (no country)
CITY_BARE_RE = re.compile(r"\b(?:en|in)\s+([^,]{2,40}?)\s+(?:de|by)\s+", re.IGNORECASE)


def _metro() -> set:
    """Cities that count as local for THIS site. config.py is per-city and is
    preserved by sync_from_tulsa.py, so a metro list belongs there. Falls back to
    the city name alone, which is strict but never wrong."""
    names = getattr(config, "METRO_CITIES", None)
    if not names:
        names = [getattr(config, "CITY_NAME", "") or ""]
    return {str(n).strip().lower() for n in names if str(n).strip()}


def parse_og(desc: str) -> dict:
    """Pull the true (year, month, day) and city out of a Facebook og:description.
    Returns {} for the useless generic blurb Facebook serves on limited events."""
    out = {}
    if not desc or "Ve publicaciones" in desc or "See posts" in desc:
        return out
    m = DATE_RE.search(desc)
    if m:
        out["month"] = MONTHS[m.group(1).lower()]
        out["day"] = int(m.group(2))
        out["year"] = int(m.group(3))
    m = CITY_COUNTRY_RE.search(desc)
    if m:
        out["city"] = m.group(1).strip()
        out["country"] = m.group(2).strip()
    else:
        m = CITY_BARE_RE.search(desc)
        if m:
            out["city"] = m.group(1).strip()
    return out


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def fetch_og(url: str, timeout: int = 25) -> str:
    """Return the og:description, trying each UA before giving up. A 400 from one
    UA is a rate-limit signal, not a verdict about the event."""
    last = None
    for ua in UAS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            h = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
            m = (re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', h)
                 or re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:description"', h))
            if m:
                return html.unescape(m.group(1))
            last = "no og:description in response"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    if last:
        raise RuntimeError(last)
    return ""


def verdict_for(ev: dict, og: dict, metro: set) -> tuple:
    """(verdict, reason). Only a CONFIRMED disagreement suppresses anything."""
    if not og:
        return "unknown", "Facebook served no event metadata (limited/private or removed)"

    ours = str(ev.get("date") or "")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", ours)
    if m and og.get("year"):
        oy, om, od = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if og["year"] != oy:
            return ("stale_year",
                    f"Facebook says {og['year']}-{og['month']:02d}-{og['day']:02d}, "
                    f"we scheduled it {ours} - a {oy - og['year']}-year-old event "
                    f"projected onto this week")
        if (og.get("month"), og.get("day")) != (om, od):
            return ("date_mismatch",
                    f"Facebook says {og['year']}-{og['month']:02d}-{og['day']:02d}, "
                    f"we scheduled it {ours}")

    city = (og.get("city") or "").lower()
    country = (og.get("country") or "").lower()
    if city and metro and city not in metro:
        # A foreign COUNTRY is decisive even if the city name is unfamiliar.
        if country and not re.search(r"estados unidos|united states", country):
            return "foreign_city", f"Facebook places this in {og['city']}, {og['country']}"
        return "foreign_city", f"Facebook places this in {og['city']}, not the {config.CITY_NAME} metro"
    return "ok", ""


def _events_path(week: str) -> str:
    return os.path.join(config.EVENTS_DIR, f"{week}_all.json")


def _week_key() -> str:
    return config.current_week_key()


def audit(week: str, workers: int = 8) -> dict:
    path = _events_path(week)
    with open(path, "r", encoding="utf-8") as f:
        container = json.load(f)
    events = container if isinstance(container, list) else container.get("events", [])
    metro = _metro()

    # One fetch per event id, not per event row - a recurring event repeats the url.
    by_url = {}
    for ev in events:
        for u in [ev.get("url") or ""] + [str(x) for x in (ev.get("source_urls") or [])]:
            if FB_EVENT_RE.search(u):
                by_url.setdefault(u, []).append(ev)
                break

    # A successful og: card for a given event id is stable, so cache it and keep
    # the Monday run to a handful of live fetches. Failures are NOT cached: a
    # rate-limited fetch must be retried next run, never frozen into a permanent
    # "unverifiable" that would quietly fail this gate open forever.
    import time as _time
    cache = _load_cache()
    now = _time.time()
    fresh = {u: c["desc"] for u, c in cache.items()
             if isinstance(c, dict) and c.get("desc")
             and (now - c.get("ts", 0)) < CACHE_TTL_DAYS * 86400}

    def _one(u):
        if u in fresh:
            return u, fresh[u], "", True
        try:
            return u, fetch_og(u), "", False
        except Exception as e:
            return u, "", f"{type(e).__name__}: {e}", False

    ogs, live = {}, 0
    if by_url:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for u, desc, err, cached in ex.map(_one, list(by_url)):
                ogs[u] = (parse_og(desc), err)
                if not cached:
                    live += 1
                    if desc:
                        cache[u] = {"ts": now, "desc": desc}
        _save_cache(cache)

    findings = []
    for u, rows in by_url.items():
        og, err = ogs.get(u, ({}, "no fetch"))
        for ev in rows:
            # Already suppressed (by an earlier run of this tool, geo_guard, or a
            # human). Re-reporting it would spam preflight with warnings about
            # events that are no longer in the deck.
            if ev.get("never_feature") is True:
                continue
            v, why = verdict_for(ev, og, metro)
            if v != "ok":
                findings.append({"name": ev.get("name"), "date": ev.get("date"),
                                 "venue": ev.get("venue"), "source": ev.get("source"),
                                 "url": u, "verdict": v,
                                 "reason": why + (f" [{err}]" if err else ""),
                                 "_ev": ev})
    return {"week": week, "path": path, "container": container,
            "checked": len(by_url), "live_fetches": live, "findings": findings}


def suppress(res: dict) -> int:
    """Mark every CONFIRMED ghost never_feature. Unknowns are left alone."""
    n = 0
    for f in res["findings"]:
        if f["verdict"] == "unknown":
            continue
        ev = f["_ev"]
        if ev.get("never_feature") is not True:
            ev["never_feature"] = True
            ev["_truth_verdict"] = f"{f['verdict']}: {f['reason']}"
            n += 1
    if n:
        with open(res["path"], "w", encoding="utf-8") as fh:
            json.dump(res["container"], fh, ensure_ascii=False, indent=2)
    return n


def render() -> tuple:
    env = dict(os.environ)
    env.update({"TULSAGAYS_SKIP_ENRICH": "1", "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8"})
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "main.py", "generate-all"], cwd=repo,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3000, env=env)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-600:]


def _selftest() -> int:
    """Ground truth: the exact og:description strings Facebook returned on
    2026-09-07 for the events that shipped this bug. No network."""
    cases = [
        # (og:description, event date, expected verdict)
        ("Evento de YBR Pub el sabado, septiembre 9 2023", "2026-09-09", "stale_year"),
        ("Evento de Comida en Sand Springs, Estados Unidos de America el jueves, "
         "septiembre 7 2023", "2026-09-07", "stale_year"),
        ("Evento en Tulsa, Estados Unidos de America de Twisted Arts el miercoles, "
         "septiembre 10 2025", "2026-09-10", "stale_year"),
        ("Evento en Puerto Vallarta de The Swedes Bar & Bistro el lunes, "
         "septiembre 7 2026", "2026-09-07", "foreign_city"),
        ("Evento de Deportes en Mobile, Estados Unidos de America de HotMess Sports "
         "y Marta Opsasnick el martes, septiembre 8 2026", "2026-09-08", "foreign_city"),
        ("Evento en Puerto Vallarta de Recorramos Mexico el domingo, "
         "septiembre 13 2026", "2026-09-13", "foreign_city"),
        ("Evento en Tulsa, Estados Unidos de America de Grim House el miercoles, "
         "septiembre 9 2026", "2026-09-09", "ok"),
        ("Evento de Manualidades en Tulsa, Estados Unidos de America de Oklahomans "
         "for Equality el jueves, septiembre 10 2026", "2026-09-10", "ok"),
        ("Ve publicaciones, fotos y mucho mas en Facebook.", "2026-09-07", "unknown"),
        # English locale must behave identically.
        ("Event by YBR Pub on Saturday, September 9 2023", "2026-09-09", "stale_year"),
    ]
    metro = {"tulsa", "sand springs", "broken arrow", "jenks", "bixby", "owasso",
             "sapulpa", "catoosa", "claremore", "glenpool", "collinsville",
             "skiatook", "coweta", "wagoner", "tulsa county"}
    bad = 0
    for desc, date, want in cases:
        got, why = verdict_for({"date": date}, parse_og(desc), metro)
        ok = got == want
        bad += (not ok)
        print(f"  {'PASS' if ok else 'FAIL'}  want={want:<13} got={got:<13} {desc[:58]}")
        if not ok:
            print(f"        parsed={parse_og(desc)} why={why}")
    print(f"selftest: {len(cases) - bad}/{len(cases)} passed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None)
    ap.add_argument("--suppress", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    week = a.week or _week_key()
    res = audit(week)
    confirmed = [f for f in res["findings"] if f["verdict"] != "unknown"]
    unknown = [f for f in res["findings"] if f["verdict"] == "unknown"]

    if a.json:
        print(json.dumps({"week": week, "checked": res["checked"],
                          "confirmed": [{k: v for k, v in f.items() if k != "_ev"}
                                        for f in confirmed],
                          "unknown": [f["name"] for f in unknown]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"[fb-truth] {week}: checked {res['checked']} Facebook events against "
              f"Facebook's own metadata")
        for f in confirmed:
            print(f"  [X] {f['verdict']:<13} {str(f['name'])[:48]:<48} {f['reason']}")
        for f in unknown:
            print(f"  [?] unknown       {str(f['name'])[:48]:<48} {f['reason']}")
        print(f"[fb-truth] {len(confirmed)} confirmed ghost/foreign, {len(unknown)} unverifiable")

    if a.suppress and confirmed:
        n = suppress(res)
        print(f"[fb-truth] suppressed {n} event(s) (never_feature=True in {res['path']})")
        if a.render and n:
            rc, tail = render()
            print(f"[fb-truth] re-render rc={rc} {tail[-200:]}")
    return 1 if confirmed else 0


if __name__ == "__main__":
    sys.exit(main())
