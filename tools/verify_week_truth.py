"""SOURCE-OF-TRUTH RE-VERIFICATION for every event we publish (2026-09-15).

Why. The 2026-W38 deck went out with a 2025 festival as Event of the Week and
39 Facebook times an hour early, and William learned about it from the people
who run those events. Every gate we had validated the deck against ITSELF
(copy, layout, dedup, day names). Nothing re-read the sources. This tool does:
for every event row with a URL it fetches the source and re-derives the date
and start time, then compares. A disagreement is a finding; a featured or
Event-of-the-Week finding is a hard preflight block.

What it can read
  facebook.com/events/<id>    og:description via the facebookexternalhit UA
                              (date + city; Facebook gives no time in og)
  eventbrite / meetup / any   schema.org Event JSON-LD (startDate with offset)
  any HTML page               weekday+date phrases ("Friday, September 19") -
                              a weekday that disagrees with our date means the
                              page is describing a different YEAR (stale page)
  instagram.com / google      unverifiable (recorded, never blocks)

Verdicts per row
  ok               source agrees on date (and time when the source states one)
  date_mismatch    source states a different date
  time_mismatch    source start time differs from ours by 30+ minutes
  stale_page       source text's weekday contradicts our date (last year's page)
  foreign_city     Facebook places it outside the metro
  unverifiable     no machine-readable date on the source (fails OPEN)

Usage
  python tools/verify_week_truth.py                 # current week, report only
  python tools/verify_week_truth.py --week 2026-W38 --fix     # adopt source date/time,
                                                    # hide stale/foreign rows from the site
  python tools/verify_week_truth.py --file data/events/_retracted_2026-W38/2026-W38_all.json
  python tools/verify_week_truth.py --selftest

Writes data/posts/<week>/truth_report.json (preflight reads it; stale >24h = warning).
Exit 0 = no confirmed mismatch left, 1 = confirmed mismatches remain, 2 = setup error.
Fails OPEN on unverifiable, CLOSED on a confirmed disagreement.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html as _html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from scraper.tz_guard import LOCAL_TZ, weekday_mismatch_in_text, local_offset_hours, weekday_index  # noqa: E402

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

CACHE_PATH = os.path.join(ROOT, "data", "truth_cache.json")
CACHE_TTL_H = 20
FB_EVENT_RE = re.compile(r"facebook\.com/events/(\d+)")
UNVERIFIABLE_HOSTS = ("instagram.com", "google.com", "goo.gl", "tiktok.com", "twitter.com", "x.com",
                      "linktr.ee", "slack.com", "meetup.com/find")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
_TIME_RX = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?\s*[Mm]\.?")
_LD_RX = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                    re.S | re.I)
_LONGDATE_RX = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTHS["sept"] = 9


# ── helpers ──────────────────────────────────────────────────────────────────

def _our_start_minutes(time_str: str):
    m = _TIME_RX.search(time_str or "")
    if not m:
        return None
    h = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        h += 12
    return h * 60 + int(m.group(2) or 0)


def _fmt_minutes(mins: int) -> str:
    return datetime(2000, 1, 1, mins // 60, mins % 60).strftime("%I:%M %p").lstrip("0")


def _name_overlap(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[a-z0-9]{3,}", (a or "").lower())}
    wb = {w for w in re.findall(r"[a-z0-9]{3,}", (b or "").lower())}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _walk_events(obj, out):
    if isinstance(obj, dict):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and x.endswith("Event") for x in types):
            out.append(obj)
        for v in obj.values():
            _walk_events(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_events(v, out)


def parse_jsonld_events(html: str) -> list:
    found = []
    for m in _LD_RX.finditer(html or ""):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            try:
                data = json.loads(_html.unescape(raw))
            except Exception:
                continue
        _walk_events(data, found)
    return found


def _iso_to_local(s: str):
    """schema.org startDate -> (date, minutes-of-day | None). Offsets are honoured
    and converted to the site's zone; a naive datetime is taken as local."""
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?)?", s)
    if not m:
        return None, None
    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if not m.group(4):
        return d, None
    hh, mm = int(m.group(4)), int(m.group(5))
    tz = m.group(6)
    if tz:
        try:
            if tz == "Z":
                off_min = 0
            else:
                sign = 1 if tz[0] == "+" else -1
                tzd = tz[1:].replace(":", "")
                off_min = sign * (int(tzd[:2]) * 60 + int(tzd[2:]))
            utc = datetime(d.year, d.month, d.day, hh, mm) - timedelta(minutes=off_min)
            local = utc + timedelta(hours=local_offset_hours(d))
            return local.date(), local.hour * 60 + local.minute
        except Exception:
            pass
    return d, hh * 60 + mm


import threading as _threading
from urllib.parse import urlparse as _urlparse

# One request at a time per host, spaced out, with 429 backoff. Eight parallel
# workers hitting one host made 45 of 312 W38 rows (all of thetulsaartsdistrict.org)
# "unverifiable" on HTTP 429 (2026-09-15): a rate limit is not an unknowable fact.
_HOST_LOCKS: dict = {}
_HOST_LOCKS_GUARD = _threading.Lock()
_HOST_GAP_S = 1.5


def _host_lock(url: str):
    host = _urlparse(url).netloc.lower()
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(host, _threading.Lock())


def _fetch(url: str, timeout: int = 25) -> str:
    if requests is None:
        raise RuntimeError("requests not installed")
    ua = "facebookexternalhit/1.1" if FB_EVENT_RE.search(url) else UA
    with _host_lock(url):
        for attempt in range(4):
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
                             timeout=timeout, allow_redirects=True)
            if r.status_code in (429, 503) and attempt < 3:
                wait = r.headers.get("Retry-After")
                time.sleep(min(float(wait), 60) if wait and wait.isdigit() else 5 * (2 ** attempt))
                continue
            break
        time.sleep(_HOST_GAP_S)
    r.raise_for_status()
    return r.text[:600_000]


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
            json.dump(c, f)
    except Exception:
        pass


def _fb_og(html: str) -> dict:
    """Reuse fb_event_truth's parser so the two tools can never disagree."""
    try:
        from tools.fb_event_truth import parse_og
    except Exception:
        try:
            from fb_event_truth import parse_og  # type: ignore
        except Exception:
            return {}
    m = re.search(r'<meta property="og:description" content="([^"]*)"', html or "")
    if not m:
        return {}
    return parse_og(_html.unescape(m.group(1)))


def _page_text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html or "", flags=re.S | re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


# ── the verdict ──────────────────────────────────────────────────────────────

def verdict_from_source(ev: dict, html: str, url: str, metro: set) -> dict:
    """Return {"verdict", "reason", "src_date", "src_time"} for one row."""
    ours_date = str(ev.get("date") or "")[:10]
    ours_min = _our_start_minutes(ev.get("time") or "")
    out = {"verdict": "unverifiable", "reason": "", "src_date": None, "src_time": None}

    # 1. Facebook event card: date + city (no time).
    if FB_EVENT_RE.search(url):
        og = _fb_og(html)
        if not og or not og.get("year"):
            out["reason"] = "Facebook served no event metadata (private/limited/removed)"
            return out
        src = date(og["year"], og["month"], og["day"])
        out["src_date"] = src.isoformat()
        city = (og.get("city") or "").lower()
        country = (og.get("country") or "").lower()
        if city and metro and city not in metro:
            out["verdict"] = "foreign_city"
            out["reason"] = f"Facebook places this in {og.get('city')}{', ' + og.get('country') if country else ''}"
            return out
        if ours_date and src.isoformat() != ours_date:
            out["verdict"] = "date_mismatch" if src.year == int(ours_date[:4]) else "stale_page"
            out["reason"] = f"Facebook says {src.isoformat()}, we published {ours_date}"
            return out
        out["verdict"] = "ok"
        out["reason"] = "facebook date agrees (time not stated by Facebook)"
        return out

    # 2. schema.org Event JSON-LD.
    events = parse_jsonld_events(html)
    if events:
        cands = []
        for e in events:
            sd = e.get("startDate")
            if isinstance(sd, list):
                sd = sd[0] if sd else None
            d, mins = _iso_to_local(sd) if isinstance(sd, str) else (None, None)
            if d is None:
                continue
            ed = e.get("endDate")
            if isinstance(ed, list):
                ed = ed[0] if ed else None
            end_d, _ = _iso_to_local(ed) if isinstance(ed, str) else (None, None)
            recurring = bool(e.get("eventSchedule")) or bool(e.get("eventAttendanceMode") and e.get("eventSchedule"))
            cands.append((_name_overlap(ev.get("name"), e.get("name") or ""), d, mins, e.get("name") or "",
                          end_d, recurring))
        if cands and ours_date:
            try:
                _ours_d = date.fromisoformat(ours_date)
            except ValueError:
                _ours_d = None
            if _ours_d is not None:
                # Multi-day run (exhibition, gallery hours): our date inside the
                # source's start..end range is correct by construction.
                span = [c for c in cands if c[4] is not None and c[1] <= _ours_d <= c[4] and c[0] >= 0.5]
                if span:
                    out["verdict"] = "ok"
                    out["src_date"] = ours_date
                    out["reason"] = f"inside the source's {span[0][1]}..{span[0][4]} run"
                    return out
                # Weekly / bi-weekly series: schema.org startDate is the FIRST
                # occurrence; our date a whole number of weeks later is the
                # same series (qlist, calendar pages). Accept when the weekday
                # matches; still compare the clock time.
                series = [c for c in cands if c[0] >= 0.5 and c[1] < _ours_d
                          and (_ours_d - c[1]).days % 7 == 0]
                if series:
                    _, d, mins, sname, _, _ = max(series, key=lambda c: c[0])
                    out["src_date"] = ours_date
                    out["src_time"] = _fmt_minutes(mins) if mins is not None else None
                    if mins is not None and ours_min is not None and abs(mins - ours_min) >= 30:
                        out["verdict"] = "time_mismatch"
                        out["reason"] = (f"series '{sname}' (first {d.isoformat()}) runs at {_fmt_minutes(mins)}, "
                                         f"we published {_fmt_minutes(ours_min)}")
                        return out
                    out["verdict"] = "ok"
                    out["reason"] = f"weekly series (source states first occurrence {d.isoformat()})"
                    return out
        cands = [c[:4] for c in cands]
        if cands:
            # Multi-event page (a venue calendar): prefer the entry with the best
            # name overlap; a single-event page is authoritative regardless.
            if len(cands) > 1:
                best = max(cands, key=lambda c: c[0])
                if best[0] < 0.5:
                    # Same page lists many events; accept if ANY of them matches our
                    # date (recurring series), else we cannot pin the row.
                    same_day = [c for c in cands if c[1].isoformat() == ours_date]
                    if same_day:
                        best = max(same_day, key=lambda c: c[0])
                    else:
                        out["reason"] = f"calendar page lists {len(cands)} events, none named like ours"
                        return out
            else:
                best = cands[0]
            _, d, mins, sname = best
            out["src_date"] = d.isoformat()
            out["src_time"] = _fmt_minutes(mins) if mins is not None else None
            if ours_date and d.isoformat() != ours_date:
                # Recurring series: another entry may match our date.
                if any(c[1].isoformat() == ours_date for c in cands):
                    same = [c for c in cands if c[1].isoformat() == ours_date]
                    _, d, mins, sname = max(same, key=lambda c: c[0])
                    out["src_date"], out["src_time"] = d.isoformat(), (_fmt_minutes(mins) if mins is not None else None)
                else:
                    out["verdict"] = "stale_page" if d.year != int(ours_date[:4]) else "date_mismatch"
                    out["reason"] = f"source JSON-LD '{sname}' starts {d.isoformat()}, we published {ours_date}"
                    return out
            if mins is not None and ours_min is not None and abs(mins - ours_min) >= 30:
                out["verdict"] = "time_mismatch"
                out["reason"] = (f"source says {_fmt_minutes(mins)}, we published "
                                 f"{_fmt_minutes(ours_min)} ('{ev.get('time')}')")
                return out
            out["verdict"] = "ok"
            out["reason"] = "JSON-LD agrees"
            return out

    # 3. Plain text: weekday/date phrases and explicit "Month D, YYYY".
    text = _page_text(html)
    stale = weekday_mismatch_in_text(text, ours_date)
    if stale:
        out["verdict"] = "stale_page"
        out["reason"] = stale
        return out
    if ours_date:
        yrs = set()
        for m in _LONGDATE_RX.finditer(text):
            mo = _MONTHS.get(m.group(1).lower()[:4].rstrip("."), _MONTHS.get(m.group(1).lower()[:3]))
            try:
                dd = date(int(m.group(3)), mo, int(m.group(2)))
            except Exception:
                continue
            if (dd.month, dd.day) == (int(ours_date[5:7]), int(ours_date[8:10])):
                yrs.add(dd.year)
        if yrs and int(ours_date[:4]) not in yrs:
            out["verdict"] = "stale_page"
            out["reason"] = f"page dates this event {sorted(yrs)}, we published {ours_date}"
            return out
        if yrs:
            out["verdict"] = "ok"
            out["src_date"] = ours_date
            out["reason"] = "page text states our date with the right year"
            return out
    out["reason"] = "no machine-readable date on the source page"
    return out


# ── the audit ────────────────────────────────────────────────────────────────

def _metro() -> set:
    return {c.lower() for c in getattr(config, "METRO_CITIES", [])} | {"tulsa"}


LIVEWHALE_HOSTS = ("calendar.tulsacc.edu",)


def _verify_livewhale(rows: list) -> None:
    """Institutional LiveWhale calendars render nothing without JS, so every
    row from them used to land in 'unverifiable'. Their native JSON API lists
    each occurrence with a local ISO date: check the row's name + date against
    it. W38: 18 of 19 TCC rows matched; 'Paw Pals - Therapy Dogs' was listed on
    Tue 9/15 but only occurs 9/17 and later (2026-09-15)."""
    by_host: dict = {}
    for r in rows:
        host = _urlparse(r.get("url") or "").netloc.lower()
        if host in LIVEWHALE_HOSTS and r.get("verdict") == "unverifiable":
            by_host.setdefault(host, []).append(r)
    for host, rs in by_host.items():
        try:
            data = json.loads(_fetch(f"https://{host}/live/json/events"))
        except Exception as e:
            for r in rs:
                r["reason"] = f"LiveWhale API fetch failed: {type(e).__name__}"
            continue
        dates: dict = {}
        for x in data.get("data", []) if isinstance(data, dict) else []:
            key = re.sub(r"\W+", " ", str(x.get("title") or "").lower()).strip()
            dates.setdefault(key, set()).add(str(x.get("date_iso") or "")[:10])
        for r in rs:
            key = re.sub(r"\W+", " ", str(r.get("name") or "").lower()).strip()
            ds = dates.get(key)
            ours = str(r.get("date") or "")[:10]
            if not ds:
                r["reason"] = "not found in the calendar's LiveWhale API (first page)"
            elif ours in ds:
                r["verdict"], r["src_date"] = "ok", ours
                r["reason"] = "LiveWhale API lists this occurrence"
            else:
                r["verdict"] = "stale_page"
                r["reason"] = f"LiveWhale API has no occurrence on {ours} (occurs {sorted(ds)[:4]})"


def _reconcile_series(rows: list) -> None:
    """Several of OUR rows (same url + name, different dates) all 'disagree' with
    one source startDate: the page exposes only the FIRST occurrence of a daily
    run (gallery hours, an exhibition, a study sign-up window). Moving every row
    onto that date collapsed 'September Gallery Hours' Wed-Sat into four copies
    on Tuesday (2026-09-15). Rows dated BEFORE the start cannot happen: stale.
    Rows after it are unconfirmable from this page: unverifiable, left as-is."""
    groups: dict = {}
    for r in rows:
        if r.get("verdict") == "date_mismatch" and r.get("src_date"):
            key = (r.get("url"), re.sub(r"\W+", " ", str(r.get("name") or "")).strip().lower(), r["src_date"])
            groups.setdefault(key, []).append(r)
    for (_, _, src), grp in groups.items():
        dates = {str(g.get("date"))[:10] for g in grp}
        if len(dates) < 2:
            continue
        for g in grp:
            if str(g.get("date"))[:10] < src:
                g["verdict"] = "stale_page"
                g["reason"] = f"dated before the source's first occurrence {src} ({g['reason']})"
            else:
                g["verdict"] = "unverifiable"
                g["reason"] = f"source exposes only the series start {src}; later dates unconfirmable here"


def audit(events: list, workers: int = 8, only: set | None = None) -> dict:
    metro = _metro()
    cache = _load_cache()
    now = time.time()
    by_url: dict[str, list] = {}
    skipped = 0
    skipped_rows: list = []
    for ev in events:
        url = (ev.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        if only is not None and (ev.get("name"), ev.get("date")) not in only:
            continue
        if any(h in url for h in UNVERIFIABLE_HOSTS):
            # Recorded, never silently dropped: W38 featured four Instagram-
            # sourced drag nights that appeared in no report at all (2026-09-15).
            skipped += 1
            skipped_rows.append({"name": ev.get("name"), "date": ev.get("date"), "time": ev.get("time"),
                                 "venue": ev.get("venue"), "source": ev.get("source"), "url": url,
                                 "verdict": "unverifiable", "src_date": None, "src_time": None,
                                 "reason": "source host is not machine-readable (Instagram / form / link page)",
                                 "_ev": ev})
            continue
        by_url.setdefault(url, []).append(ev)

    def _one(u):
        c = cache.get(u)
        if isinstance(c, dict) and c.get("html") and now - c.get("ts", 0) < CACHE_TTL_H * 3600:
            return u, c["html"], "", True
        try:
            return u, _fetch(u), "", False
        except Exception as e:
            return u, "", f"{type(e).__name__}: {str(e)[:120]}", False

    pages, live = {}, 0
    if by_url:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for u, html, err, cached in ex.map(_one, list(by_url)):
                pages[u] = (html, err)
                if not cached:
                    live += 1
                    if html:
                        cache[u] = {"ts": now, "html": html[:250_000]}
        _save_cache(cache)

    rows = []
    for u, evs in by_url.items():
        html, err = pages.get(u, ("", "no fetch"))
        for ev in evs:
            if not html:
                v = {"verdict": "unverifiable", "reason": f"fetch failed: {err}", "src_date": None, "src_time": None}
            else:
                try:
                    v = verdict_from_source(ev, html, u, metro)
                except Exception as e:  # never let one page kill the audit
                    v = {"verdict": "unverifiable", "reason": f"parser error {type(e).__name__}: {e}",
                         "src_date": None, "src_time": None}
            rows.append({"name": ev.get("name"), "date": ev.get("date"), "time": ev.get("time"),
                         "venue": ev.get("venue"), "source": ev.get("source"), "url": u, **v,
                         "_ev": ev})
    rows.extend(skipped_rows)
    _reconcile_series(rows)
    _verify_livewhale(rows)
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"checked_urls": len(by_url), "live_fetches": live, "skipped_unverifiable_hosts": skipped,
            "counts": counts, "rows": rows}


CONFIRMED = ("date_mismatch", "time_mismatch", "stale_page", "foreign_city")

RECURRING_CONFLICTS = os.path.join(ROOT, "data", "recurring_truth_conflicts.json")


def _log_recurring_conflict(ev: dict, r: dict) -> None:
    """Append a recurring-table row that its source contradicts, deduped by
    (name, verdict, src_time/src_date), so data/recurring.py can be corrected."""
    try:
        cur = json.load(open(RECURRING_CONFLICTS, encoding="utf-8"))
    except Exception:
        cur = []
    key = (ev.get("name"), r.get("verdict"), r.get("src_time") or r.get("src_date"))
    for c in cur:
        if (c.get("name"), c.get("verdict"), c.get("src_time") or c.get("src_date")) == key:
            c["last_seen"] = datetime.now().isoformat(timespec="seconds")
            c["count"] = c.get("count", 1) + 1
            break
    else:
        cur.append({"name": ev.get("name"), "venue": ev.get("venue"), "date": ev.get("date"),
                    "time": ev.get("time"), "verdict": r.get("verdict"), "reason": r.get("reason"),
                    "src_date": r.get("src_date"), "src_time": r.get("src_time"), "url": r.get("url"),
                    "first_seen": datetime.now().isoformat(timespec="seconds"), "count": 1})
    try:
        with open(RECURRING_CONFLICTS, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_WEEKDAY_WORD_RX = re.compile(r"\b(mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:days?)?\b", re.I)


def _names_other_weekday(name, iso_date: str) -> bool:
    """True when the event name contains a weekday word that is not iso_date's weekday."""
    try:
        wd = date.fromisoformat(str(iso_date)[:10]).weekday()
    except ValueError:
        return False
    named = {weekday_index(m.group(0)) for m in _WEEKDAY_WORD_RX.finditer(str(name or ""))}
    named.discard(None)
    return bool(named) and wd not in named


def apply_fixes(res: dict) -> dict:
    """Adopt the source's date/time where the source is confident; hide stale /
    foreign rows from the site and bar them from featuring. Mutates the event
    dicts in place (they are the same objects as the loaded container)."""
    n_time = n_date = n_hide = 0
    try:
        wk_mon = date.fromisocalendar(*[int(x) for x in config.current_week_key().replace("W", "").split("-")], 1)
        wk_sun = wk_mon + timedelta(days=6)
    except Exception:
        wk_mon = wk_sun = None
    for r in res["rows"]:
        ev = r["_ev"]
        v = r["verdict"]
        if v not in CONFIRMED:
            continue
        # Organizer-submitted rows (manual entries, direct submissions) came from
        # the people running the event, which beats a web page: reported, never
        # auto-edited. The RECURRING table is not organizer truth; it is our own
        # copy of a schedule and goes stale. W38 shipped OSU Tulsa Queer Support
        # Group at 6:00 PM while its official calendar said 3:00 PM because
        # recurring rows were review-only and nobody reviewed. They are now fixed
        # like any scraped row, and the conflict is logged so the table gets
        # corrected at its source.
        _src = ev.get("source") or ""
        if _src in ("manual", "submission"):
            r["review_only"] = True
            continue
        if _src == "recurring":
            _log_recurring_conflict(ev, r)
        if v == "date_mismatch" and r.get("src_date") and wk_mon is not None:
            try:
                sd = date.fromisoformat(r["src_date"])
            except ValueError:
                sd = None
            if sd is None or not (wk_mon <= sd <= wk_sun):
                # The source puts it outside the publishing week: it is not
                # this week's event. Hide it rather than move it.
                ev["never_feature"] = True
                ev["hide_from_site"] = True
                ev["_truth_verdict"] = f"{v}: {r['reason']}"
                n_hide += 1
                continue
        if v == "time_mismatch" and r.get("src_time"):
            ev["time_before_truth_fix"] = ev.get("time")
            ev["time"] = r["src_time"]
            ev["truth_fixed"] = f"time from source: {r['reason']}"
            n_time += 1
        elif v == "date_mismatch" and r.get("src_date") and _names_other_weekday(ev.get("name"), r["src_date"]):
            # "Free Lunch Monday" matched a Tuesday "Mentor Lunch" on the same
            # calendar page (2026-09-15): the match is wrong, not the date.
            # Never move a row onto a weekday its own name contradicts; hide it.
            ev["never_feature"] = True
            ev["hide_from_site"] = True
            ev["_truth_verdict"] = f"{v}: {r['reason']} (name names a different weekday; unresolved)"
            n_hide += 1
        elif v == "date_mismatch" and r.get("src_date"):
            # Only move within the same publishing week; otherwise hide it.
            ev["date_before_truth_fix"] = ev.get("date")
            ev["date"] = r["src_date"]
            ev["truth_fixed"] = f"date from source: {r['reason']}"
            n_date += 1
        elif v in ("stale_page", "foreign_city"):
            ev["never_feature"] = True
            ev["hide_from_site"] = True
            ev["_truth_verdict"] = f"{v}: {r['reason']}"
            n_hide += 1
    return {"time_fixed": n_time, "date_fixed": n_date, "hidden": n_hide}


def _events_container(path: str):
    with open(path, "r", encoding="utf-8") as f:
        container = json.load(f)
    events = container if isinstance(container, list) else container.get("events", [])
    return container, events


def _shown_keys(week: str) -> set | None:
    p = os.path.join(ROOT, "data", "posts", week, "slide_manifest.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            man = json.load(f)
    except Exception:
        return None
    keys = set()
    for e in (man.get("eotw") or []):
        keys.add((e.get("name"), e.get("date")))
    for evs in (man.get("featured_by_day") or {}).values():
        for e in evs:
            keys.add((e.get("name"), e.get("date")))
    return keys


def write_report(week: str, res: dict, fixes: dict | None, path_checked: str) -> str:
    out_dir = os.path.join(ROOT, "data", "posts", week)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "truth_report.json")
    findings = []
    for r in res["rows"]:
        if r["verdict"] not in CONFIRMED:
            continue
        ev = r["_ev"]
        f = {k: v for k, v in r.items() if k != "_ev"}
        f["fixed"] = bool(ev.get("truth_fixed") or ev.get("hide_from_site"))
        f["review_only"] = bool(r.get("review_only"))
        findings.append(f)
    unver = [{k: v for k, v in r.items() if k != "_ev"} for r in res["rows"] if r["verdict"] == "unverifiable"]
    # Positive confirmations, so preflight can require them for featured slots.
    confirmed = [{"name": r.get("name"), "date": r.get("date"), "reason": r.get("reason")}
                 for r in res["rows"] if r["verdict"] == "ok"]
    payload = {"week": week, "ran_at": datetime.now().isoformat(timespec="seconds"),
               "events_file": path_checked, "checked_urls": res["checked_urls"],
               "live_fetches": res["live_fetches"], "counts": res["counts"],
               "skipped_unverifiable_hosts": res.get("skipped_unverifiable_hosts"),
               "fixes_applied": fixes or {}, "findings": findings, "unverifiable": unver,
               "confirmed": confirmed}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out


# ── selftest ─────────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = []
    def ck(name, cond, detail=""):
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)
    metro = _metro()
    # Fringe: the real twistedfest.org phrasing, no year, seen in 2026.
    html = "<html><body>Location: OKEQ (621 E 4th St,) Friday, September 19 &amp; Saturday, September 20 Join us</body></html>"
    v = verdict_from_source({"name": "Fringe Festival", "date": "2026-09-19", "time": ""}, html, "https://twistedfest.org/fringe-festival/", metro)
    ck("Fringe page -> stale_page", v["verdict"] == "stale_page", v["reason"])
    # JSON-LD with an offset: 7 PM CDT event we published as 6 PM.
    ld = json.dumps({"@context": "https://schema.org", "@type": "Event", "name": "Ecstatic Dance",
                     "startDate": "2026-09-16T19:00:00-05:00"})
    html = f'<script type="application/ld+json">{ld}</script>'
    v = verdict_from_source({"name": "Ecstatic Dance - Fall", "date": "2026-09-16", "time": "6:00 PM"}, html, "https://x.org/e", metro)
    ck("JSON-LD 7 PM vs our 6 PM -> time_mismatch", v["verdict"] == "time_mismatch" and v["src_time"] == "7:00 PM", str(v))
    v = verdict_from_source({"name": "Ecstatic Dance - Fall", "date": "2026-09-16", "time": "7:00 PM"}, html, "https://x.org/e", metro)
    ck("JSON-LD 7 PM vs our 7 PM -> ok", v["verdict"] == "ok")
    # UTC offset conversion: 00:00Z on the 17th is 7 PM CDT on the 16th.
    ld = json.dumps({"@type": "Event", "name": "Late Show", "startDate": "2026-09-17T00:00:00Z"})
    v = verdict_from_source({"name": "Late Show", "date": "2026-09-16", "time": "7:00 PM"}, f'<script type="application/ld+json">{ld}</script>', "https://x.org/e2", metro)
    ck("UTC startDate converts to local date+time", v["verdict"] == "ok", str(v))
    # Calendar page listing many events: pick ours by name.
    ld = json.dumps([{"@type": "Event", "name": "Drag Bingo", "startDate": "2026-09-18T20:00:00-05:00"},
                     {"@type": "Event", "name": "Karaoke Night", "startDate": "2026-09-19T21:00:00-05:00"}])
    v = verdict_from_source({"name": "Karaoke Night at the bar", "date": "2026-09-19", "time": "9:00 PM"}, f'<script type="application/ld+json">{ld}</script>', "https://x.org/cal", metro)
    ck("multi-event page matched by name -> ok", v["verdict"] == "ok", str(v))
    v = verdict_from_source({"name": "Karaoke Night at the bar", "date": "2026-09-19", "time": "7:00 PM"}, f'<script type="application/ld+json">{ld}</script>', "https://x.org/cal", metro)
    ck("multi-event page, wrong time -> time_mismatch", v["verdict"] == "time_mismatch", str(v))
    # Facebook card in Spanish (the machine's IP locale) for a foreign chapter.
    fb = '<meta property="og:description" content="Evento de Deportes en Fruitville, Estados Unidos de Am&#xe9;rica de HotMess Sports el jueves, septiembre 17 2026">'
    v = verdict_from_source({"name": "HotMess Sports Sarasota", "date": "2026-09-17", "time": "5:30 PM"}, fb, "https://www.facebook.com/events/1023410050476588/", metro)
    ck("FB Fruitville -> foreign_city", v["verdict"] == "foreign_city", str(v))
    fb = '<meta property="og:description" content="Evento en Tulsa, Estados Unidos de Am&#xe9;rica de Taylor Berghoff el mi&#xe9;rcoles, septiembre 16 2026">'
    v = verdict_from_source({"name": "Ecstatic Dance", "date": "2026-09-16", "time": "7:00 PM"}, fb, "https://www.facebook.com/events/1074371482000910/", metro)
    ck("FB Tulsa same date -> ok", v["verdict"] == "ok", str(v))
    fb = '<meta property="og:description" content="Event in Tulsa, OK by Tulsa YBR on Saturday, September 20 2025">'
    v = verdict_from_source({"name": "YBR Night", "date": "2026-09-20", "time": ""}, fb, "https://www.facebook.com/events/1/", metro)
    ck("FB 2025 card vs 2026 row -> stale_page", v["verdict"] == "stale_page", str(v))
    # Page with explicit "September 19, 2025".
    v = verdict_from_source({"name": "Fest", "date": "2026-09-19", "time": ""}, "<p>Join us September 19, 2025 at OKEQ</p>", "https://x.org/f", metro)
    ck("explicit past-year long date -> stale_page", v["verdict"] == "stale_page", str(v))
    v = verdict_from_source({"name": "Fest", "date": "2026-09-19", "time": ""}, "<p>nothing dated here</p>", "https://x.org/g", metro)
    ck("no date on page -> unverifiable (fails open)", v["verdict"] == "unverifiable")
    # Daily run whose page exposes only the first day (W38 September Gallery Hours).
    rs = [{"name": "September Gallery Hours", "url": "https://g.org/h", "date": d, "verdict": "date_mismatch",
           "src_date": "2026-09-15", "reason": "x"} for d in ("2026-09-14", "2026-09-16", "2026-09-17")]
    rs.append({"name": "Open Mic Night", "url": "https://g.org/o", "date": "2026-09-17", "verdict": "date_mismatch",
               "src_date": "2026-09-16", "reason": "y"})
    _reconcile_series(rs)
    ck("series row before start -> stale_page", rs[0]["verdict"] == "stale_page")
    ck("series rows after start -> unverifiable, not moved", rs[1]["verdict"] == rs[2]["verdict"] == "unverifiable")
    ck("single-row mismatch still a date_mismatch", rs[3]["verdict"] == "date_mismatch")
    print("\nSELFTEST", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week")
    ap.add_argument("--file", help="events JSON to audit (default data/events/<week>_all.json)")
    ap.add_argument("--fix", action="store_true", help="adopt source date/time; hide stale/foreign rows")
    ap.add_argument("--only-shown", action="store_true", help="only featured/EOTW rows from the manifest")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    week = a.week or config.current_week_key()
    path = a.file or os.path.join(config.EVENTS_DIR, f"{week}_all.json")
    if not os.path.exists(path):
        print(f"[truth] no events file at {path}")
        return 2
    container, events = _events_container(path)
    only = _shown_keys(week) if a.only_shown else None
    res = audit(events, workers=a.workers, only=only)
    fixes = apply_fixes(res) if a.fix else None
    if a.fix and any(fixes.values()):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(container, f, ensure_ascii=False, indent=2)
    report = write_report(week, res, fixes, path)
    confirmed = [r for r in res["rows"] if r["verdict"] in CONFIRMED]
    print(f"[truth] {week}: {len(events)} rows, {res['checked_urls']} source urls checked "
          f"({res['live_fetches']} live fetches), counts={res['counts']}")
    if not a.quiet:
        for r in confirmed:
            print(f"  [{r['verdict']:14}] {r['date']} {r['time'] or '':>18} | {str(r['name'])[:55]:55} | {r['reason'][:110]}")
    if fixes:
        print(f"[truth] fixes applied: {fixes}")
    print(f"[truth] report -> {report}")
    remaining = [r for r in confirmed if not (r["_ev"].get("truth_fixed") or r["_ev"].get("hide_from_site"))]
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
