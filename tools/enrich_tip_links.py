"""Follow links on event tips: enrich the event from the linked page, and if the page
looks like a recurring venue/org calendar, suggest it as a new scrape source (review-first).

William, 2026-06-17: "make sure we scrape the sites that may be on the submitted flyers."
When a tip (or a flyer) carries a URL, we:
  1. Fetch the page (timeout-bounded, never crashes the ingest).
  2. Pull event details from schema.org/Event JSON-LD first (most reliable), then fall
     back to OpenGraph/meta tags — and fill ONLY the tip fields that are still empty
     (the submitter's own words win over scraped guesses).
  3. If the domain looks like a venue/org events calendar, append a candidate to
     data/source_candidates.json (status "pending") so a recurring scraper can be added
     after review — same queue the rest of source discovery uses.

Standalone:  python tools/enrich_tip_links.py --url https://example.com/event
"""

from __future__ import annotations

import os
import sys
import re
import json
import logging
from datetime import datetime, date as _date
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

SOURCE_CANDIDATES = os.path.join(config.DATA_DIR, "source_candidates.json")
_URL_RE = re.compile(r"(https?://[^\s)>\]\"']+|www\.[^\s)>\]\"']+)", re.I)
# A path that smells like a recurring calendar rather than a one-off page.
_CALENDAR_HINTS = ("/events", "/event/", "/calendar", "/whats-on", "/shows",
                   "/lineup", "/happenings", "/tickets")
_FETCH_TIMEOUT = 12


def extract_urls(*texts: str) -> list[str]:
    seen, out = set(), []
    for t in texts:
        for m in _URL_RE.finditer(t or ""):
            u = m.group(1).rstrip(".,);]'\"!?")
            if u.lower().startswith("www."):
                u = "https://" + u
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def fetch_page(url: str) -> str:
    """GET the page HTML, or '' on any failure. Bounded by _FETCH_TIMEOUT."""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TulsaGaysBot/1.0)"}
        r = requests.get(url, headers=headers, timeout=_FETCH_TIMEOUT)
        if r.status_code == 200 and r.text:
            return r.text
        logger.info("enrich: %s returned %s", url, r.status_code)
    except Exception as e:
        logger.info("enrich: fetch failed %s: %s", url, e)
    return ""


def parse_event_from_html(html: str) -> dict:
    """Extract {name,date,time,venue,description} from a page. JSON-LD Event first,
    then OpenGraph/meta. Missing fields come back as ''."""
    out = {"name": "", "date": "", "time": "", "venue": "", "description": ""}
    if not html:
        return out
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return out
    soup = BeautifulSoup(html, "html.parser")

    # 1) schema.org/Event JSON-LD
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld(data):
            if not isinstance(node, dict):
                continue
            typ = node.get("@type", "")
            if isinstance(typ, list):
                typ = " ".join(typ)
            if "Event" not in str(typ):
                continue
            out["name"] = out["name"] or str(node.get("name", "")).strip()
            start = str(node.get("startDate", "")).strip()
            if start:
                out["date"] = out["date"] or _iso_date(start)
                out["time"] = out["time"] or _iso_time(start)
            loc = node.get("location")
            if isinstance(loc, dict):
                out["venue"] = out["venue"] or str(loc.get("name", "")).strip()
            elif isinstance(loc, str):
                out["venue"] = out["venue"] or loc.strip()
            desc = str(node.get("description", "")).strip()
            out["description"] = out["description"] or desc[:400]
            if out["name"] and out["date"]:
                return out  # good enough

    # 2) OpenGraph / meta fallback
    def meta(prop):
        el = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return (el.get("content") or "").strip() if el else ""
    out["name"] = out["name"] or meta("og:title") or (soup.title.string.strip() if soup.title else "")
    out["description"] = out["description"] or meta("og:description")[:400]
    return out


def _iter_jsonld(data):
    if isinstance(data, list):
        for x in data:
            yield from _iter_jsonld(x)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_jsonld(data["@graph"])


def _iso_date(s: str) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return _date(int(m[1]), int(m[2]), int(m[3])).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def _iso_time(s: str) -> str:
    m = re.search(r"T(\d{2}):(\d{2})", s)
    if not m:
        return ""
    h, mn = int(m[1]), m[2]
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{mn} {ap}"


def looks_like_calendar(url: str) -> bool:
    p = urlparse(url)
    path = (p.path or "").lower()
    return any(h in path for h in _CALENDAR_HINTS)


def suggest_source(url: str, name: str, tip_id: str, channel: str,
                   path: str = SOURCE_CANDIDATES) -> bool:
    """Append a pending source candidate (dedup by domain+url). Returns True if added."""
    p = urlparse(url)
    domain = p.netloc.lower()
    if not domain:
        return False
    try:
        with open(path, encoding="utf-8") as f:
            cands = json.load(f)
    except (OSError, json.JSONDecodeError):
        cands = []
    for c in cands:
        if (c.get("url") == url) or (urlparse(c.get("url", "")).netloc.lower() == domain
                                     and c.get("discovered_via") == "dm_tip_link"):
            return False  # already known
    slug = re.sub(r"\W+", "-", domain).strip("-")
    cands.append({
        "id": f"tiplink-{slug}-{len(cands)+1}",
        "type": "website",
        "name": name or domain,
        "url": url,
        "kw": [],
        "category": "tip_link",
        "confidence": "low",
        "evidence": f"linked from tip {tip_id} ({channel}); path looks like an events calendar",
        "discovered_at": datetime.now().strftime("%Y-%m-%d"),
        "discovered_via": "dm_tip_link",
        "status": "pending",
        "promoted_at": "",
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cands, f, indent=2, ensure_ascii=False)
    return True


def enrich_tip(entry: dict, fetcher=fetch_page, candidates_path: str = SOURCE_CANDIDATES) -> dict:
    """Fill empty fields on a tip from its linked page(s), and suggest recurring sources.
    Returns the (mutated) entry with an 'enriched_from' / 'source_suggested' trail."""
    urls = extract_urls(entry.get("url", ""), entry.get("raw_text", ""),
                         entry.get("description", ""))
    if not urls:
        return entry
    suggested = []
    for url in urls[:3]:  # cap fetches per tip
        html = fetcher(url)
        parsed = parse_event_from_html(html)
        for k in ("name", "date", "time", "venue", "description"):
            if not (entry.get(k) or "").strip() and parsed.get(k):
                entry[k] = parsed[k]
        if not entry.get("url"):
            entry["url"] = url
        entry.setdefault("enriched_from", []).append(url)
        if looks_like_calendar(url):
            if suggest_source(url, parsed.get("name", ""), entry.get("id", ""),
                              entry.get("channel", ""), candidates_path):
                suggested.append(url)
    if suggested:
        entry["source_suggested"] = suggested
    return entry


def _selftest():
    import tempfile

    assert extract_urls("see www.foo.com/x and https://bar.org/events!") == \
        ["https://www.foo.com/x", "https://bar.org/events"]
    assert looks_like_calendar("https://thetulsan.com/events/")
    assert not looks_like_calendar("https://thetulsan.com/about")

    html = """<html><head><title>Drag Night</title>
    <script type="application/ld+json">
    {"@type":"Event","name":"Drag Night at The Tulsan",
     "startDate":"2026-06-19T21:00:00-05:00",
     "location":{"@type":"Place","name":"The Tulsan"},
     "description":"A wild Friday drag show."}
    </script></head><body></body></html>"""
    p = parse_event_from_html(html)
    assert p["name"] == "Drag Night at The Tulsan", p
    assert p["date"] == "2026-06-19", p
    assert p["time"] == "9:00 PM", p
    assert p["venue"] == "The Tulsan", p

    # enrich fills only empty fields; submitter's typed name wins
    d = tempfile.mkdtemp()
    cand_p = os.path.join(d, "cands.json")
    entry = {"id": "tip001", "channel": "ig", "name": "Tulsan Drag (typed)",
             "date": "", "time": "", "venue": "", "description": "",
             "url": "https://thetulsan.com/events/drag", "raw_text": ""}
    entry = enrich_tip(entry, fetcher=lambda u: html, candidates_path=cand_p)
    assert entry["name"] == "Tulsan Drag (typed)", entry      # typed name preserved
    assert entry["date"] == "2026-06-19", entry               # date filled from page
    assert entry["venue"] == "The Tulsan", entry
    assert "source_suggested" in entry, entry                 # /events path -> candidate
    cands = json.load(open(cand_p))
    assert len(cands) == 1 and cands[0]["status"] == "pending", cands
    # dedup: second tip on same domain adds nothing
    entry2 = {"id": "tip002", "channel": "ig", "name": "x", "url": "https://thetulsan.com/events/drag2",
              "date": "", "time": "", "venue": "", "description": "", "raw_text": ""}
    enrich_tip(entry2, fetcher=lambda u: html, candidates_path=cand_p)
    assert len(json.load(open(cand_p))) == 1, "domain dedup failed"

    print("enrich_tip_links selftest: passed (url extract + JSON-LD + fill-gaps-only + "
          "source suggest + dedup)")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--url")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.url:
        e = enrich_tip({"id": "manual", "channel": "cli", "url": args.url, "raw_text": "",
                        "name": "", "date": "", "time": "", "venue": "", "description": ""})
        print(json.dumps(e, indent=2, ensure_ascii=False))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
