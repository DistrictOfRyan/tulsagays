"""Optional schema.org Event fields (endDate, performer) built ONLY from source data.

Why this file exists (2026-11-03, project ledger slug tulsagays-schema-gaps): the
2026-10-27 AI-search audit found 0 of 191 homepage Event items carried endDate and
only 2 carried performer. tools/gen_website_html.py builds that Event ItemList as
module-level script code, which cannot be unit-tested, so the rules live here as
pure functions and the generator calls them.

Rules (the point of the whole file: never invent a value)
  endDate    only when the event record carries an end time, either as an explicit
             `end_time` ("9:00 PM", optionally with an `end_date` YYYY-MM-DD) or as
             a range in the display `time` ("7:00 PM - 9:00 PM"). "Evening",
             "Afternoon - late", a lone start time, an unparseable end, a zero or
             negative duration, or a startDate with no time all give NO endDate.
             An end clock time at or before the start on the same date is read as an
             overnight event ("10:00 PM - 2:00 AM" ends the next day) only when that
             makes the event 12 hours or shorter; otherwise it is treated as bad
             data and omitted.
  performer  only when the record has a `performer` / `performers` field. Nothing is
             inferred from the event name or description.
  offset     the UTC offset is America/Chicago's offset on the event's own date.
             The generator used to hard-code -05:00 (CDT) on every event, which put
             every November-March startDate one hour off (Tulsa is -06:00 in CST).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

try:  # config-free tz source shared with the scrapers
    from scraper.tz_guard import LOCAL_TZ as _LOCAL_TZ
except Exception:  # pragma: no cover - tz_guard always importable in this repo
    _LOCAL_TZ = None

# 7:00 PM / 7 pm / 7:00 p.m. (never the "Am" in "9 Amazing")
_TIME_RX = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?\s*[Mm](?![A-Za-z])\.?")
# separator allowed BETWEEN the start and end clock times of a range
_RANGE_SEP_RX = re.compile(r"^\s*(?:-|–|—|to|until|till)\s*$", re.I)
# "7-9 PM": the start has no meridiem of its own and inherits the end's
_SHARED_MERIDIEM_RX = re.compile(
    r"(?<![\d:])(\d{1,2})(?::(\d{2}))?\s*(?:-|–|—|to)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?\s*[Mm](?![A-Za-z])\.?", re.I)
_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_OVERNIGHT_HOURS = 12   # data-sanity guard for the end-before-start rollover


def _h24(hour: str, meridiem: str) -> int:
    h = int(hour) % 12
    return h + 12 if meridiem.lower() == "p" else h


def _valid_hm(h: int, m: int) -> bool:
    return 0 <= h <= 23 and 0 <= m <= 59


def parse_times(time_str):
    """Return (start, end); each is (hour24, minute) or None.

    start is the first clock time in the string, exactly as the pre-2026-11-03
    generator read it. end is set only for an explicit range ("A - B", "A to B",
    "7-9 PM"). Anything else leaves end None."""
    s = (time_str or "").replace(" ", " ").strip()
    if not s:
        return None, None
    toks = list(_TIME_RX.finditer(s))

    # "7-9 PM": first number has no meridiem, so the plain token scan would have
    # taken the END ("9 PM") as the start. Resolve it as a shared-meridiem range.
    sm = _SHARED_MERIDIEM_RX.search(s)
    if sm and (not toks or sm.start(3) <= toks[0].start()):
        h1, m1, h2, m2, mer = sm.group(1), sm.group(2), sm.group(3), sm.group(4), sm.group(5)
        end = (_h24(h2, mer), int(m2 or 0))
        start = (_h24(h1, mer), int(m1 or 0))
        if start >= end:          # "11-1 PM" / "10-2 PM": start is the other half of the day
            start = (_h24(h1, "a" if mer.lower() == "p" else "p"), int(m1 or 0))
        if _valid_hm(*start) and _valid_hm(*end) and start != end:
            return start, end
        return None, None

    if not toks:
        return None, None
    t0 = toks[0]
    start = (_h24(t0.group(1), t0.group(3)), int(t0.group(2) or 0))
    if not _valid_hm(*start):
        return None, None
    end = None
    if len(toks) >= 2:
        t1 = toks[1]
        if _RANGE_SEP_RX.match(s[t0.end():t1.start()]):
            e = (_h24(t1.group(1), t1.group(3)), int(t1.group(2) or 0))
            if _valid_hm(*e):
                end = e
    return start, end


def _parse_single_time(value):
    """Clock time from an explicit end_time field ('9:00 PM') or None."""
    s = (str(value) if value is not None else "").replace(" ", " ").strip()
    m = _TIME_RX.search(s)
    if not m:
        return None
    hm = (_h24(m.group(1), m.group(3)), int(m.group(2) or 0))
    return hm if _valid_hm(*hm) else None


def tz_offset(naive_dt: datetime) -> str:
    """'+HH:MM' America/Chicago offset in force at that local wall-clock time."""
    if _LOCAL_TZ is not None:
        off = naive_dt.replace(tzinfo=_LOCAL_TZ).utcoffset()
    else:  # pragma: no cover
        off = timedelta(hours=-6)
    minutes = int(off.total_seconds() // 60) if off is not None else -360
    sign = "-" if minutes < 0 else "+"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:00") + tz_offset(dt)


def _parse_date(date_str):
    if not date_str or not _DATE_RX.match(str(date_str).strip()):
        return None
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def iso_start(date_str, time_str):
    """Event startDate: full ISO 8601 with the real Tulsa offset when the record has
    a clock time, the bare date otherwise (a date-only startDate is valid), None when
    there is no date at all."""
    if not date_str:
        return None
    d = _parse_date(date_str)
    start, _ = parse_times(time_str)
    if d is None or start is None:
        return date_str
    return _stamp(datetime(d.year, d.month, d.day, start[0], start[1]))


def iso_end(date_str, time_str, end_time=None, end_date=None):
    """Event endDate (ISO 8601) or None. See the module docstring for the rules."""
    d = _parse_date(date_str)
    start, range_end = parse_times(time_str)
    if d is None or start is None:
        return None          # endDate on a date-only/unparseable start would mislead
    end = _parse_single_time(end_time) if (end_time not in (None, "")) else None
    if end is None:
        end = range_end
    if end is None:
        return None

    explicit_end_date = _parse_date(end_date) if end_date else None
    ed = explicit_end_date or d
    start_dt = datetime(d.year, d.month, d.day, start[0], start[1])
    end_dt = datetime(ed.year, ed.month, ed.day, end[0], end[1])
    if end_dt <= start_dt:
        if explicit_end_date is not None:
            return None      # the source gave both and they contradict: omit
        end_dt += timedelta(days=1)        # overnight: "10 PM - 2 AM"
        if end_dt - start_dt > timedelta(hours=MAX_OVERNIGHT_HOURS):
            return None
    return _stamp(end_dt)


def event_performers(ev):
    """schema.org performer value built from the record's own performer field.

    Accepts a string, a {"name":..., "@type"|"type":...} dict, or a list of either.
    A plain string is typed Person (documented default); a source-supplied type of
    Person / Organization / PerformingGroup / MusicGroup is kept as given. Returns
    None when the record names no performer."""
    raw = ev.get("performer") if ev.get("performer") else ev.get("performers")
    if not raw:
        return None
    items = raw if isinstance(raw, list) else [raw]
    out, seen = [], set()
    for it in items:
        if isinstance(it, str):
            name, typ = it.strip(), "Person"
        elif isinstance(it, dict):
            name = str(it.get("name") or "").strip()
            typ = str(it.get("@type") or it.get("type") or "Person")
        else:
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        if typ not in ("Person", "Organization", "PerformingGroup", "MusicGroup"):
            typ = "Person"
        out.append({"@type": typ, "name": name})
    if not out:
        return None
    return out[0] if len(out) == 1 else out


def add_optional_event_fields(obj: dict, ev: dict) -> dict:
    """Add endDate / performer to a schema.org Event dict, only when the source
    record supports them. Mutates and returns obj."""
    end = iso_end(ev.get("date"), ev.get("time"), ev.get("end_time"), ev.get("end_date"))
    if end:
        obj["endDate"] = end
    perf = event_performers(ev)
    if perf:
        obj["performer"] = perf
    return obj
