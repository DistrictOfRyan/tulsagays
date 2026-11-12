"""Scraper for affirming church events: All Souls Unitarian Church.

NOTE: Church of the Restoration (churchoftherestoration.org) is DNS-dead as of 2026
and has been removed from this scraper.

All Souls Unitarian regular Sunday services are handled in recurring.py.
This scraper looks for special events beyond weekly services.

REPAIRED 2026-11-06. Until then it returned 0 on every scrape because it read pages
that are not calendars:
  /events, /upcoming-events, /whats-happening -> HTTP 404 "Page Not Found".
  /calendar -> HTTP 200, but the page is only an iframe of
      secure.accessacs.com/calendar/publiccalendar.html?token=CZPDMAV2FB (ACS
      Technologies). That host does not resolve from Google DNS (SERVFAIL), this
      machine's resolver (timeout) or Anthropic's fetcher (EAI_AGAIN). Cloudflare
      resolves it to 165.166.75.180, but TCP 443 times out there and on
      165.166.75.177. The church's own calendar page is broken for its visitors too.
  Control: allsoulschurch.org and its WordPress REST API answer HTTP 200.
Where the events actually are: All Souls announces each special event as a
WordPress post that opens with a "Details at a Glance:" block, e.g.
    Saturday, November 7, 2026
    10:00 AM – 5:00 PM
    Emerson Hall, All Souls Unitarian Church
or with "When:" / "Where:" / "Time:" labels. A post's publish date is NOT the event
date, so the date comes from that block, and a row is kept only when the weekday the
post names matches the calendar weekday of the parsed date: a wrong year or a typo
fails that check instead of shipping a wrong date. Posts without such a block
(sermons, the monthly theme, prose-only posts) are skipped, and so are worship
services. Precision over recall.
"""

import sys
import os
import re
import html
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

API_POSTS = "https://allsoulschurch.org/wp-json/wp/v2/posts"
DEFAULT_VENUE = "All Souls Unitarian Church, 2952 S Peoria Ave"
LOOKAHEAD_DAYS = 120

_WD = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day"
_MON = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
        r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_DATE_RE = re.compile(
    rf"(?P<wd>{_WD}(?:\s*(?:&|and)\s*{_WD})*),?\s+(?P<mon>{_MON})\.?\s+(?P<d1>\d{{1,2}})"
    rf"(?:st|nd|rd|th)?(?:\s*[-–]\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?)?(?:,?\s+(?P<yr>\d{{4}}))?",
    re.I)
_AP = r"[AaPp]\.?\s?[Mm]\.?"
_TIME_RE = re.compile(
    rf"(?<!\d)(?P<h>\d{{1,2}})(?::(?P<m>\d{{2}}))?\s*(?P<ap>{_AP})?"
    rf"(?:\s*[-–]\s*(?P<h2>\d{{1,2}})(?::(?P<m2>\d{{2}}))?\s*(?P<ap2>{_AP}))?")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_VENUE_HINT = re.compile(r"All Souls|\bHall\b|\bPark\b|\bChurch\b|\d+\s+[NSEW]\.?\s+\w+", re.I)
_LABEL_RE = re.compile(r"^(when|date|time|where|location)\s*:\s*(.*)$", re.I)


def _parse_dates(line: str, published: date) -> Tuple[List[date], str]:
    """All event dates named in `line`, each checked against the weekday the
    line gives for it. Returns (dates, reason-if-empty)."""
    out: List[date] = []
    for m in _DATE_RE.finditer(line):
        month = _MONTHS[m.group("mon")[:3].lower()]
        d1 = int(m.group("d1"))
        d2 = int(m.group("d2")) if m.group("d2") else d1
        if d2 < d1 or d2 - d1 > 6:
            return [], f"odd day range in {line!r}"
        if m.group("yr"):
            year = int(m.group("yr"))
        else:
            year = published.year
            if date(year, month, d1) < published - timedelta(days=14):
                year += 1
        try:
            days = [date(year, month, d) for d in range(d1, d2 + 1)]
        except ValueError:
            return [], f"impossible date in {line!r}"
        named = [w[:3].lower() for w in re.findall(_WD, m.group("wd"), re.I)]
        pairs = list(zip(named, days)) if len(named) == len(days) else [(named[0], days[0])]
        for wd, dt in pairs:
            if _WEEKDAYS[dt.weekday()] != wd:
                return [], f"weekday {wd} != {dt.isoformat()} ({_WEEKDAYS[dt.weekday()]}) in {line!r}"
        out.extend(days)
    return out, "" if out else "no date"


def _parse_time(line: str) -> str:
    """First clock time in `line` that carries AM/PM (on itself or on the end of
    its range), as "7:00 PM". Bare numbers (addresses, counts) never qualify."""
    for m in _TIME_RE.finditer(line or ""):
        ap = m.group("ap") or m.group("ap2")
        if not ap:
            continue
        h, mm = int(m.group("h")), int(m.group("m") or 0)
        if not 1 <= h <= 12 or mm > 59:
            continue
        pm = ap.lower().startswith("p")
        if not m.group("ap") and m.group("h2"):
            # "2:00-4:00 PM": the start borrows the end's meridiem, unless that
            # would put the start after the end ("11:00-1:00 PM" starts at 11 AM).
            h2 = int(m.group("h2"))
            if pm and h != 12 and h2 != 12 and h > h2:
                pm = False
        return f"{h}:{mm:02d} {'PM' if pm else 'AM'}"
    return ""


def _post_lines(rendered: str) -> List[str]:
    from bs4 import BeautifulSoup
    text = BeautifulSoup(rendered or "", "html.parser").get_text("\n")
    return [re.sub(r"\s+", " ", l).strip() for l in html.unescape(text).split("\n") if l.strip()]


def _details(lines: List[str]) -> Optional[Dict[str, str]]:
    """The post's event block as {date, time, venue, rest_from}, or None.

    Formats seen on allsoulschurch.org (2026-03..11): a "Details at a Glance:"
    block of bare lines (date / time / venue), or labelled lines "When:" or
    "Date:" / "Time:" / "Where:" or "Location:", with the value on the same line
    or the next one. Some glance blocks use the labels, so a block with no bare
    date line falls through to the label parse. Prose-only posts return None:
    their venue lives in a sentence, and guessing it is how a wrong address ships."""
    for i, line in enumerate(lines):
        if re.match(r"details at a glance", line, re.I):
            block = lines[i + 1:i + 5]
            di = next((k for k, l in enumerate(block)
                       if _DATE_RE.search(l) and not _LABEL_RE.match(l)), None)
            if di is None:
                break
            ti = next((k for k in range(di, len(block)) if _parse_time(block[k])), None)
            venue = ""
            if ti is not None and ti + 1 < len(block) and _VENUE_HINT.search(block[ti + 1]):
                venue = re.sub(r"^location\s*:\s*", "", block[ti + 1], flags=re.I)
            return {"date": block[di], "time": block[ti] if ti is not None else "",
                    "venue": venue, "rest_from": i + 1 + (ti if ti is not None else di) + 1}
    labels: Dict[str, str] = {}
    last = 0
    for i, line in enumerate(lines):
        m = _LABEL_RE.match(line)
        if m:
            key = m.group(1).lower()
            val = m.group(2).strip() or (lines[i + 1] if i + 1 < len(lines) else "")
            key = {"where": "venue", "location": "venue", "date": "when"}.get(key, key)
            labels.setdefault(key, val)
            last = i + 2
    if "when" in labels and _DATE_RE.search(labels["when"]):
        return {"date": labels["when"], "time": labels.get("time") or labels["when"],
                "venue": labels.get("venue", ""), "rest_from": last}
    return None


class AllSoulsScraper(BaseScraper):
    """Special events from All Souls Unitarian Church's WordPress announcements."""

    source_name = "all_souls"

    def scrape(self) -> List[Dict]:
        posts = self.fetch_json(API_POSTS, params={
            "per_page": 30, "_fields": "date,title,content,link"}, timeout=20)
        if not isinstance(posts, list):
            logger.warning("[all_souls] WordPress posts API gave no list")
            return []
        today = datetime.now().date()
        events: List[Dict] = []
        for post in posts:
            title = html.unescape((post.get("title") or {}).get("rendered", "")).strip()
            lines = _post_lines((post.get("content") or {}).get("rendered", ""))
            info = _details(lines)
            if not title or not info:
                continue
            if re.search(r"\bservices?\b", f"{title} {info['time']}", re.I):
                continue  # worship services: recurring.py carries the Sunday ones
            try:
                published = datetime.fromisoformat(post.get("date", "")[:19]).date()
            except ValueError:
                published = today
            dates, why = _parse_dates(info["date"], published)
            if not dates:
                logger.info("[all_souls] skipped %r: %s", title, why)
                continue
            desc = " ".join(lines[info["rest_from"]:])[:500]
            for dt in dates:
                if not (today - timedelta(days=1) <= dt <= today + timedelta(days=LOOKAHEAD_DAYS)):
                    continue
                events.append(self.make_event(
                    name=title,
                    date=dt.isoformat(),
                    time=_parse_time(info["time"]),
                    venue=info["venue"] or DEFAULT_VENUE,
                    description=desc,
                    url=post.get("link", ""),
                    priority=2,
                ))
        events = [e for e in events if "sunday service" not in e.get("name", "").lower()]
        logger.info("[all_souls] %d upcoming events from %d posts", len(events), len(posts))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return AllSoulsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['date']} {e['time']:>8} | {e['name']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
