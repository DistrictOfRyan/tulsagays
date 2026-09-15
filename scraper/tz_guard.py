"""Time-zone and yearless-date guards shared by every scraper (2026-09-15).

Why this file exists. The 2026-W38 deck shipped two classes of wrong fact that
nothing in the pipeline could see:

1. EVERY Facebook time was one hour early. Facebook renders event times in the
   BROWSER's time zone. The scrape runs on a machine in Puerto Vallarta (UTC-6,
   no DST), so a 7:00 PM Tulsa event (CDT, UTC-5) rendered as "6 PM CST" and
   shipped that way to the website, the carousel, the newsletter and the
   schema.org startDate. 39 of 44 Facebook rows carried a CST label in a month
   when Tulsa is on CDT. The label itself was the tell; nobody read it.

2. A 2025 event was projected onto 2026. twistedfest.org still lists the
   inaugural Tulsa Fringe Festival as "Friday, September 19 & Saturday,
   September 20" with no year. Sept 19 is a FRIDAY only in 2025; in 2026 it is a
   Saturday. The scraper assumed the current year, the weekday disagreed, and
   the event became Event of the Week for a weekend it did not exist in.

Both are the same defect: a claim the source made (a tz label, a weekday name)
that we discarded instead of checking. This module keeps them.

Public helpers
    local_offset_hours(d)            -> int   (America/Chicago offset on that date)
    local_abbrev(d)                  -> "CDT" | "CST"
    fix_tz_labeled_time(t, date)     -> (fixed_str, changed, note, day_delta)
    resolve_yearless(month, day, weekday_idx=None, today=None) -> "YYYY-MM-DD" | ""
    weekday_index(name)              -> 0..6 | None
    weekday_mismatch_in_text(text, date_str) -> reason | ""
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - py<3.9 never runs here
    ZoneInfo = None  # type: ignore

try:  # config is optional so this module stays importable from tests/tools
    import config as _config
    _TZ_NAME = getattr(_config, "TIMEZONE", None) or "America/Chicago"
except Exception:  # pragma: no cover
    _TZ_NAME = "America/Chicago"

LOCAL_TZ = ZoneInfo(_TZ_NAME) if ZoneInfo else None

# Fixed offsets (hours) for the abbreviations a US-facing page can render.
_TZ_OFFSETS = {
    "UTC": 0, "GMT": 0, "Z": 0,
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10,
}
_TZ_LABEL_RX = re.compile(r"(?<![A-Za-z])(UTC|GMT|[ECMP][SD]T|AK[SD]T|HST)(?![A-Za-z])", re.I)
_TIME_TOKEN_RX = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?\s*[Mm]\.?")

_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_WD_ALT = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
_MO_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
# "Friday, September 19" / "Fri Sep 19" / "Friday, Sept. 19th"
_WD_MONTH_RX = re.compile(
    r"\b(" + _WD_ALT + r")\b\.?,?\s+(" + _MO_ALT + r")\b\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.I)
# "Fri 9/19" / "Friday, 9/19/2025"
_WD_SLASH_RX = re.compile(
    r"\b(" + _WD_ALT + r")\b\.?,?\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", re.I)


# ── time zone ────────────────────────────────────────────────────────────────

def _as_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}", d):
        try:
            return date.fromisoformat(d[:10])
        except ValueError:
            pass
    return date.today()


def local_offset_hours(d=None) -> int:
    """UTC offset of the site's local zone at noon on that date (DST-aware)."""
    if LOCAL_TZ is None:
        return -6
    dd = _as_date(d)
    off = datetime(dd.year, dd.month, dd.day, 12, tzinfo=LOCAL_TZ).utcoffset()
    return int(round((off.total_seconds() if off else 0) / 3600))


def local_abbrev(d=None) -> str:
    if LOCAL_TZ is None:
        return "CST"
    dd = _as_date(d)
    return datetime(dd.year, dd.month, dd.day, 12, tzinfo=LOCAL_TZ).strftime("%Z") or "CST"


def _fmt(h24: int, m: int) -> str:
    return datetime(2000, 1, 1, h24 % 24, m).strftime("%I:%M %p").lstrip("0")


def fix_tz_labeled_time(time_str: str, date_str=None):
    """Convert a time string carrying a tz abbreviation into the site's local
    time and strip the label.

    Returns (fixed_str, changed, note, day_delta). `changed` is True only when
    the hour actually moved; a label that already matches local time is merely
    stripped (changed=False, note says so). `day_delta` is -1/0/+1 when the
    shift crossed midnight so the caller can bump the date.

        fix_tz_labeled_time("6 PM CST", "2026-09-16")  -> ("7:00 PM", True, ..., 0)
        fix_tz_labeled_time("7 PM CDT", "2026-09-16")  -> ("7:00 PM", False, ..., 0)
        fix_tz_labeled_time("7:00 PM", "2026-09-16")   -> ("7:00 PM", False, "", 0)
    """
    raw = (time_str or "").strip()
    if not raw:
        return raw, False, "", 0
    labels = [m.group(1).upper() for m in _TZ_LABEL_RX.finditer(raw)]
    if not labels:
        return raw, False, "", 0
    label = labels[0]
    src_off = _TZ_OFFSETS.get(label)
    if src_off is None:
        return raw, False, f"unknown tz label {label}", 0
    dst_off = local_offset_hours(date_str)
    delta = dst_off - src_off

    tokens = list(_TIME_TOKEN_RX.finditer(raw))
    if not tokens:
        # Nothing parseable to shift; just drop the label so it cannot ship.
        stripped = re.sub(r"\s+", " ", _TZ_LABEL_RX.sub("", raw)).strip(" ,-")
        return stripped, False, f"stripped tz label {label} (no time token)", 0

    shifted, day_delta = [], 0
    for i, m in enumerate(tokens):
        h = int(m.group(1)) % 12
        if m.group(3).lower() == "p":
            h += 12
        mins = int(m.group(2) or 0)
        h2 = h + delta
        if i == 0:
            if h2 >= 24:
                day_delta = 1
            elif h2 < 0:
                day_delta = -1
        shifted.append(_fmt(h2 % 24, mins))
    fixed = shifted[0] if len(shifted) == 1 else f"{shifted[0]} - {shifted[1]}"
    if delta == 0:
        return fixed, False, f"stripped tz label {label} (already local)", 0
    note = (f"shifted {delta:+d}h: source rendered in {label} (UTC{src_off:+d}), "
            f"site is {local_abbrev(date_str)} (UTC{dst_off:+d}) on {_as_date(date_str)}")
    return fixed, True, note, day_delta


def foreign_tz_label(time_str: str, date_str=None) -> str:
    """Return the offending label when a time still carries a tz abbreviation
    that does not match local time on that date, else ''. Used by the sanity
    checker and preflight as a fail-closed tripwire: after the runner's fix
    step no shipped time may carry such a label."""
    raw = time_str or ""
    for m in _TZ_LABEL_RX.finditer(raw):
        lab = m.group(1).upper()
        off = _TZ_OFFSETS.get(lab)
        if off is not None and off != local_offset_hours(date_str):
            return lab
    return ""


# ── yearless dates ───────────────────────────────────────────────────────────

def weekday_index(name: str):
    return _WEEKDAYS.get((name or "").strip().lower().rstrip(".,"))


def resolve_yearless(month: int, day: int, weekday_idx=None, today=None,
                     past_grace_days: int = 7, future_horizon_days: int = 400) -> str:
    """Resolve "Month Day" with no year into YYYY-MM-DD, or '' when it cannot
    be done honestly.

    With a weekday name: only a year whose calendar puts that month/day on that
    weekday is acceptable. Candidates are this year, next year, last year. A
    match that lies more than `past_grace_days` in the past is a STALE PAGE
    (last year's festival still listed) and returns ''. No match returns ''.

    Without a weekday: this year, unless the date passed more than
    `past_grace_days` ago, in which case next year (the historical behaviour).
    """
    today = _as_date(today)
    def _mk(y):
        try:
            return date(y, month, day)
        except ValueError:
            return None
    lo = today - timedelta(days=past_grace_days)
    hi = today + timedelta(days=future_horizon_days)
    if weekday_idx is None:
        d = _mk(today.year)
        if d is None:
            return ""
        if d < lo:
            d2 = _mk(today.year + 1)
            return d2.isoformat() if d2 else ""
        return d.isoformat()
    matches = [d for d in (_mk(today.year), _mk(today.year + 1), _mk(today.year - 1))
               if d is not None and d.weekday() == weekday_idx]
    live = [d for d in matches if lo <= d <= hi]
    if live:
        return min(live).isoformat()
    return ""  # stale (only matches in the past) or contradictory (no match)


def weekday_mismatch_in_text(text: str, date_str: str) -> str:
    """When `text` says e.g. "Friday, September 19" and the event is dated
    2026-09-19 (a Saturday), return a human reason; else ''. Only fires when the
    month/day in the text equals the event's own month/day, so unrelated dates
    in a description never trip it."""
    if not text or not date_str:
        return ""
    try:
        ev = date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return ""
    actual = ev.weekday()
    for m in _WD_MONTH_RX.finditer(text):
        wd = weekday_index(m.group(1))
        mo = _MONTHS.get(m.group(2).lower().rstrip("."))
        dd = int(m.group(3))
        if wd is None or mo is None:
            continue
        if (mo, dd) == (ev.month, ev.day) and wd != actual:
            # Which year did the source mean? The nearest year where it fits.
            fit = [y for y in (ev.year - 1, ev.year - 2, ev.year + 1)
                   if _safe(y, mo, dd) and date(y, mo, dd).weekday() == wd]
            hint = f" (that weekday/date pairing fits {fit[0]})" if fit else ""
            return (f"source says '{m.group(0)}' but {ev.isoformat()} is a "
                    f"{ev.strftime('%A')}{hint} - stale yearless date")
    for m in _WD_SLASH_RX.finditer(text):
        wd = weekday_index(m.group(1))
        mo, dd = int(m.group(2)), int(m.group(3))
        yr = m.group(4)
        if wd is None or (mo, dd) != (ev.month, ev.day):
            continue
        if yr:
            y = int(yr) if len(yr) == 4 else 2000 + int(yr)
            if y != ev.year:
                return f"source dates it '{m.group(0)}' ({y}), we scheduled {ev.isoformat()}"
        if wd != actual:
            return (f"source says '{m.group(0)}' but {ev.isoformat()} is a "
                    f"{ev.strftime('%A')} - stale yearless date")
    return ""


_ZONE_SUFFIX_RX = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def iso_to_local(start: str, midnight_utc_is_placeholder: bool = False):
    """schema.org / API startDate -> (YYYY-MM-DD, "HH:MM") in Tulsa local time.

    The ONLY sanctioned way to split an ISO start into date + time (2026-09-15).
    Meetup and Eventbrite emit UTC ('2026-09-17T23:00:00Z' for a 6:00 PM CDT
    event); slicing the string shipped every W38 Meetup row five hours late and
    can land a late-evening event on the next day. The July SeatEngine fix lived
    inside BaseScraper and eight other call sites never used it.

      - no 'T'                    -> (date, "")
      - naive 'T00:00'            -> (date, "")    date-only placeholder
      - naive time                -> passed through (already local)
      - explicit zone (Z / +-HH:MM) -> converted to LOCAL_TZ; date may shift
      - zoned midnight            -> converted (00:00Z is 7:00 PM CDT the day
                                     before) unless midnight_utc_is_placeholder
    """
    start = (start or "").strip()
    if not start:
        return "", ""
    date_str = start[:10]
    if "T" not in start:
        return date_str, ""
    time_part = start.split("T", 1)[1]
    zoned = _ZONE_SUFFIX_RX.search(time_part)
    if not zoned:
        return (date_str, "") if time_part[:5] == "00:00" else (date_str, time_part[:5])
    if time_part[:5] == "00:00" and midnight_utc_is_placeholder:
        return date_str, ""
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if LOCAL_TZ is not None:
            dt = dt.astimezone(LOCAL_TZ)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return date_str, time_part[:5]


# Raw ISO slicing that bypasses iso_to_local. scan_raw_iso_slicing() fails the
# self-test (and preflight) when any scraper reintroduces it.
_RAW_SLICE_RX = re.compile(
    r"""split\(\s*["']T["']\s*\)\s*\[\s*1\s*\]\s*\[\s*:\s*5\s*\]"""   # x.split("T")[1][:5]
    r"""|\[\s*11\s*:\s*16\s*\]"""                                      # x[11:16]
    r"""|T\(\\d\{2\}\):\(\\d\{2\}\)"""                                 # regex T(\d{2}):(\d{2})
)


def scan_raw_iso_slicing(root=None):
    """Return ['file:line: code'] for every raw ISO time slice under scraper/."""
    from pathlib import Path
    base = Path(root) if root else Path(__file__).resolve().parent
    hits = []
    for p in sorted(base.glob("*.py")):
        if p.name == "tz_guard.py":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _RAW_SLICE_RX.search(line):
                hits.append(f"{p.name}:{i}: {line.strip()[:120]}")
    return hits


def _safe(y, m, d) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


# ── self-test ────────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = []
    def ck(name, cond):
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # W38 ground truth: Ecstatic Dance is 7:00 PM Tulsa on Wed 2026-09-16.
    f = fix_tz_labeled_time("6 PM CST", "2026-09-16")
    ck("6 PM CST on a CDT date -> 7:00 PM", f[0] == "7:00 PM" and f[1] is True and f[3] == 0)
    f = fix_tz_labeled_time("7 PM CDT", "2026-09-16")
    ck("7 PM CDT on a CDT date -> 7:00 PM, unchanged", f[0] == "7:00 PM" and f[1] is False)
    f = fix_tz_labeled_time("6 PM CST", "2026-12-16")
    ck("6 PM CST on a CST date -> 6:00 PM, unchanged", f[0] == "6:00 PM" and f[1] is False)
    f = fix_tz_labeled_time("5:30 PM CST - 8 PM CST", "2026-09-15")
    ck("range shifts both ends", f[0] == "6:30 PM - 9:00 PM")
    f = fix_tz_labeled_time("11:30 PM CST", "2026-09-19")
    ck("midnight crossing bumps day", f[0] == "12:30 AM" and f[3] == 1)
    f = fix_tz_labeled_time("7:00 PM", "2026-09-16")
    ck("no label -> untouched", f == ("7:00 PM", False, "", 0))
    ck("foreign label detected", foreign_tz_label("6 PM CST", "2026-09-16") == "CST")
    ck("local label not foreign", foreign_tz_label("7 PM CDT", "2026-09-16") == "")
    ck("'CST' inside a word does not fire", foreign_tz_label("Broadcast 7 PM", "2026-09-16") == "")

    # Fringe: "Friday, September 19" seen on 2026-09-14. 2026-09-19 is a Saturday.
    t = date(2026, 9, 14)
    ck("Friday Sep 19 -> stale (2025), rejected",
       resolve_yearless(9, 19, weekday_idx=4, today=t) == "")
    ck("Saturday Sep 19 -> 2026-09-19",
       resolve_yearless(9, 19, weekday_idx=5, today=t) == "2026-09-19")
    ck("Sunday Sep 20 -> 2026-09-20",
       resolve_yearless(9, 20, weekday_idx=6, today=t) == "2026-09-20")
    ck("Friday Jan 15 (2027) resolves forward",
       resolve_yearless(1, 15, weekday_idx=4, today=t) == "2027-01-15")
    ck("no weekday, future -> this year", resolve_yearless(11, 12, today=t) == "2026-11-12")
    ck("no weekday, long past -> next year", resolve_yearless(3, 1, today=t) == "2027-03-01")
    ck("no weekday, 3 days ago -> this year (grace)", resolve_yearless(9, 11, today=t) == "2026-09-11")

    r = weekday_mismatch_in_text("Location: OKEQ Friday, September 19 & Saturday, September 20",
                                 "2026-09-19")
    ck("text 'Friday, September 19' vs Sat 2026-09-19 -> mismatch", "stale yearless" in r and "2025" in r)
    ck("text 'Saturday, September 19' vs 2026-09-19 -> ok",
       weekday_mismatch_in_text("Saturday, September 19", "2026-09-19") == "")
    ck("unrelated date in text ignored",
       weekday_mismatch_in_text("see you Friday, October 2", "2026-09-19") == "")
    ck("slash form 'Tues 9/9' vs Wed 2026-09-09 -> mismatch",
       "stale yearless" in weekday_mismatch_in_text("Kickball Tues 9/9", "2026-09-09"))
    ck("weekday_index", weekday_index("Thurs.") == 3 and weekday_index("nope") is None)

    # W38 ground truth: Shut Up & Write at Handmade BA is 6:00 PM CDT Thu 9/17;
    # Meetup's JSON-LD says 23:00Z and we shipped 11:00 PM.
    ck("Meetup 23:00Z -> 18:00 same day", iso_to_local("2026-09-17T23:00:00Z") == ("2026-09-17", "18:00"))
    ck("00:00Z is 7 PM CDT the day before", iso_to_local("2026-09-18T00:00:00Z") == ("2026-09-17", "19:00"))
    ck("00:00Z placeholder mode -> date only",
       iso_to_local("2026-09-18T00:00:00Z", midnight_utc_is_placeholder=True) == ("2026-09-18", ""))
    ck("-05:00 offset already local", iso_to_local("2026-09-16T19:00:00-05:00") == ("2026-09-16", "19:00"))
    ck("naive passes through", iso_to_local("2026-09-16T19:30:00") == ("2026-09-16", "19:30"))
    ck("date only", iso_to_local("2026-09-16") == ("2026-09-16", ""))
    ck("CST-season UTC converts -6", iso_to_local("2026-12-02T01:00:00Z") == ("2026-12-01", "19:00"))
    hits = scan_raw_iso_slicing()
    for h in hits:
        print(f"         raw ISO slice: {h}")
    ck(f"no raw ISO time slicing in scraper/ ({len(hits)} found)", not hits)
    print("\nSELFTEST", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
