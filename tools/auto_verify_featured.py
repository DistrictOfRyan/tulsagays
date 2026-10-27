"""Auto-verify featured / EOTW rows by reading their source page.

Why (2026-10-27). preflight blocks any featured or Event-of-the-Week row that is
not positively confirmed (tools/truth_status.py). verify_week_truth.py confirms a
row only from a MACHINE-READABLE date (JSON-LD, a Facebook card, an API), so a
real event whose page simply says "Fri, Oct. 30 at 7:30 PM" in prose, or whose
venue announced it in an Instagram caption, stays "unverifiable" forever. On
2026-10-26 W44 was unblocked by an agent that opened 16 such sources by hand and
wrote `human_verified` on each row. This tool does that read automatically.

It writes `human_verified` ONLY when all of these hold on the fetched text:
  - the row's own date appears in it ("Oct. 30", "October 30th", "10/30",
    "2026-10-30", "30 October" ...);
  - a distinctive word of the event name appears near that date (so a venue
    calendar listing Oct 30 for a different show does not count);
  - no different year sits next to the date, and the page title does not carry
    only a different year (TAFF 2024 is a 2024 page, not this week);
  - a weekday written next to the date matches the row's real weekday;
  - "cancelled" / "postponed" is not next to it.
The record says plainly what it is:
  {"evidence_url", "action": "verified", "seen": "<quoted snippet>",
   "by": "auto-verify: machine read of source, not a human check", "at", "match"}

It never touches `manual` / `submission` rows (organizer word beats a web page),
never overwrites an existing human_verified, never edits a date, time, name or
venue, and never hides or deletes anything. A row it cannot read stays as it was.

Usage:
  python tools/auto_verify_featured.py [--week 2026-W45]   # featured + EOTW rows of the current deck
  python tools/auto_verify_featured.py --candidates          # featurable rows of the week (pre-generate)
  python tools/auto_verify_featured.py --dry-run
  python tools/auto_verify_featured.py --selftest
Exit 0 always on a completed run (the gate decides); 2 on setup error.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from urllib.parse import urlparse

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config  # noqa: E402

BY = "auto-verify: machine read of source, not a human check"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD_RE = re.compile(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day|sday|nesday|rsday|urday)?\b\.?,?\s*$", re.I)
# Organizer-submitted rows: their word beats a page, and they are not ours to stamp.
_SKIP_SOURCES = {"manual", "submission"}
# Hosts whose logged-out page never carries the event text (login wall / JS shell).
_DEAD_HOSTS = ("facebook.com", "fb.me", "patientfusion.com", "docs.google.com", "forms.gle")
_UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
# Instagram and Threads give the post caption to Meta's own link-preview agent.
_UA_META = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_GENERIC = {
    "with", "the", "and", "for", "from", "this", "that", "your", "night", "party", "event",
    "events", "tulsa", "presents", "present", "show", "live", "free", "join", "week",
    "weekly", "monthly", "annual", "club", "lounge", "bar", "special", "edition", "featuring",
    "feat", "plus", "more", "come", "open", "first", "second", "third", "fourth", "okla",
    "oklahoma", "2024", "2025", "2026", "2027", "about", "into", "over", "after", "before",
}


# ── text extraction ───────────────────────────────────────────────────────────

def _is_meta_host(host: str) -> bool:
    return any(h in host for h in ("instagram.com", "threads.net"))


def page_text(raw: str, host: str) -> tuple[str, str]:
    """-> (text_to_search, page_title). For Instagram only the caption counts:
    the rest of the HTML is app chrome, and the og prefix carries the POST date
    ("175 likes, 1 comments - dvltulsa on October 22, 2026:"), which says when it
    was posted, never when the event is."""
    metas = {}
    for prop, val in re.findall(
            r'<meta[^>]+(?:property|name)="(og:title|og:description|description|twitter:title)"[^>]*content="([^"]*)"',
            raw, re.I):
        metas.setdefault(prop.lower(), html.unescape(val))
    for val, prop in re.findall(
            r'<meta[^>]+content="([^"]*)"[^>]*(?:property|name)="(og:title|og:description|description)"',
            raw, re.I):
        metas.setdefault(prop.lower(), html.unescape(val))
    tm = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = html.unescape(tm.group(1)).strip() if tm else ""
    title = metas.get("og:title") or title
    if _is_meta_host(host):
        cap = metas.get("og:description", "") or metas.get("description", "")
        cap = re.sub(r"^\s*[\d.,KkMm]+\s+likes?,\s*[\d.,KkMm]+\s+comments?\s+-\s+\S+\s+on\s+"
                     r"[A-Za-z]+\s+\d{1,2},\s+\d{4}\s*:\s*", "", cap)
        ttl = re.sub(r'\s+on Instagram:.*$', "", title, flags=re.S)
        return f"{ttl} {cap}".strip(), ttl
    body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    body = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr|td|section)>", "\n", body, flags=re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    extra = " ".join(v for k, v in metas.items() if k != "og:title")
    text = re.sub(r"[ \t\r\f\v ]+", " ", f"{title}\n{extra}\n{body}")
    return re.sub(r"\n\s*\n+", "\n", text), title


# ── date matching ─────────────────────────────────────────────────────────────

def _date_patterns(d: date):
    mfull = _MONTHS[d.month - 1]
    mabbr = mfull[:3]
    mopts = f"(?:{mfull}|{mabbr}\\.?{'|sept\\.?' if d.month == 9 else ''})"
    day = f"0?{d.day}(?:st|nd|rd|th)?"
    year_tail = r"(?:,?\s*(?P<y>(?:19|20)\d\d))?"
    return [
        re.compile(rf"\b{mopts}\s*{day}(?!\d){year_tail}", re.I),
        re.compile(rf"\b{day}\s+(?:of\s+)?{mopts}\b{year_tail}", re.I),
        re.compile(rf"(?<![\d/.])0?{d.month}[/.]0?{d.day}(?:[/.](?P<y>\d{{2}}|\d{{4}}))?(?![\d])"),
        re.compile(rf"\b(?P<y>\d{{4}})-{d.month:02d}-{d.day:02d}\b"),
    ]


def _name_tokens(name: str) -> list:
    words = re.findall(r"[a-z0-9']+", (name or "").lower())
    toks = [w.strip("'") for w in words if len(w) >= 4 and w.strip("'") not in _GENERIC]
    if not toks:
        toks = [w for w in words if len(w) >= 3 and w not in _GENERIC]
    return toks


def judge(row: dict, text: str, title: str = "", single_post: bool = False) -> dict:
    """-> {"ok": bool, "reason": str, "seen": str, "match": str}. Pure, offline.
    single_post: the text is ONE post's caption (Instagram/Threads), so a name word
    anywhere in it counts as near the date."""
    try:
        d = date.fromisoformat((row.get("date") or "")[:10])
    except ValueError:
        return {"ok": False, "reason": "row has no usable date"}
    name = row.get("name") or ""
    yr_in_name = re.findall(r"\b(?:19|20)\d\d\b", name)
    if any(int(y) != d.year for y in yr_in_name):
        return {"ok": False, "reason": f"event name carries another year ({', '.join(yr_in_name)}): stale-year listing"}
    t_years = {int(y) for y in re.findall(r"\b(?:19|20)\d\d\b", title or "")}
    if t_years and d.year not in t_years:
        return {"ok": False, "reason": f"page title is about {sorted(t_years)}, not {d.year}"}
    toks = _name_tokens(name)
    if not toks:
        return {"ok": False, "reason": "event name has no distinctive word to anchor on"}
    low = text.lower()
    short = single_post or len(text) <= 600   # one caption / one blurb: all of it is "near"
    reasons = []
    for pat in _date_patterns(d):
        for m in pat.finditer(text):
            y = m.groupdict().get("y")
            if y:
                yy = int(y) + (2000 if len(y) == 2 else 0)
                if yy != d.year:
                    reasons.append(f"'{m.group(0)}' is {yy}")
                    continue
            near = text[max(0, m.start() - 70): m.end() + 70]
            ny = {int(x) for x in re.findall(r"\b(?:19|20)\d\d\b", near)}
            if ny and d.year not in ny:
                reasons.append(f"'{m.group(0)}' sits next to {sorted(ny)}")
                continue
            wd = _WD_RE.search(text[max(0, m.start() - 14): m.start()])
            if wd:
                said = next((i for i, w in enumerate(_WD) if w.startswith(wd.group(1).lower()[:3])), None)
                if said is not None and said != d.weekday():
                    reasons.append(f"'{wd.group(0).strip()} {m.group(0)}' names a {_WD[said].title()}, "
                                   f"{d.isoformat()} is a {DAYS[d.weekday()]}")
                    continue
            ctx = low[max(0, m.start() - 220): m.end() + 220]
            if re.search(r"\b(cancel+ed|cancel+ation|postponed|rescheduled)\b", ctx):
                reasons.append(f"'{m.group(0)}' is next to a cancellation")
                continue
            win = low if short else low[max(0, m.start() - 500): m.end() + 500]
            hit = next((tk for tk in toks if re.search(rf"\b{re.escape(tk)}", win)), None)
            if not hit:
                reasons.append(f"'{m.group(0)}' found, but no word of the event name near it")
                continue
            snip = re.sub(r"\s+", " ", text[max(0, m.start() - 80): m.end() + 80]).strip()
            return {"ok": True, "reason": f"date '{m.group(0)}' with '{hit}' nearby",
                    "seen": snip[:240], "match": m.group(0)}
    return {"ok": False, "reason": "; ".join(reasons[:3]) or "the row's date is not on the page"}


# ── fetch ─────────────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 20) -> tuple[str, str, str]:
    """-> (text, title, error). Never raises."""
    import requests
    host = (urlparse(url).hostname or "").lower()
    if any(h in host for h in _DEAD_HOSTS):
        return "", "", f"{host} needs a login to read"
    ua = _UA_META if _is_meta_host(host) else _UA_CHROME
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
                         timeout=timeout, allow_redirects=True)
    except Exception as e:
        return "", "", f"{type(e).__name__}: {str(e)[:90]}"
    if r.status_code >= 400:
        return "", "", f"HTTP {r.status_code}"
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return "", "", f"not a page ({ctype[:40]})"
    text, title = page_text(r.text[:3_000_000], host)
    return text, title, ""


# ── selection ─────────────────────────────────────────────────────────────────

def _events_path(week: str) -> str:
    return os.path.join(config.EVENTS_DIR, f"{week}_all.json")


def _week_dates(week: str) -> tuple[str, str]:
    y, w = week.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    return mon.isoformat(), date.fromisocalendar(int(y), int(w), 7).isoformat()


def _targets(week: str, events: list, mode: str, limit: int) -> list:
    from tools.truth_status import load as _truth_load
    ts = _truth_load(week)
    mon, sun = _week_dates(week)

    def usable(e):
        url = (e.get("url") or "").strip()
        return (url.startswith("http") and (e.get("source") or "") not in _SKIP_SOURCES
                and not e.get("human_verified") and not e.get("hide_from_site")
                and mon <= (e.get("date") or "") <= sun and not ts.confirmed(e))

    if mode == "featured":
        try:
            with open(os.path.join(config.DATA_DIR, "posts", week, "slide_manifest.json"), encoding="utf-8") as f:
                man = json.load(f)
        except Exception:
            return []
        keys = {(e.get("name"), e.get("date")) for e in man.get("eotw", [])}
        for day in DAYS:
            keys |= {(e.get("name"), e.get("date")) for e in man.get("featured_by_day", {}).get(day, [])}
        return [e for e in events if (e.get("name"), e.get("date")) in keys and usable(e)][:limit]

    # candidates: rows the picker could seat, queer ones first
    try:
        from eotw_selector import _is_lgbtq_strict, _is_skip
    except Exception:
        _is_lgbtq_strict = lambda e: bool(e.get("lgbtq_relevant"))  # noqa: E731
        _is_skip = lambda e: False  # noqa: E731
    pool = [e for e in events if usable(e) and not e.get("never_feature") and not _is_skip(e)]
    pool.sort(key=lambda e: (0 if _is_lgbtq_strict(e) else 1,
                             0 if e.get("lgbtq_relevant") else 1,
                             int(e.get("priority", 3) or 3)))
    return pool[:limit]


def run(week: str | None = None, mode: str = "featured", dry_run: bool = False,
        limit: int = 60, workers: int = 8) -> dict:
    week = week or config.current_week_key()
    p = _events_path(week)
    with open(p, encoding="utf-8") as f:
        container = json.load(f)
    events = container.get("events", container) if isinstance(container, dict) else container
    targets = _targets(week, events, mode, limit)
    urls = sorted({(e.get("url") or "").strip() for e in targets})
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        pages = dict(zip(urls, ex.map(fetch, urls)))
    verified, rejected = [], []
    stamp = datetime.now().isoformat(timespec="seconds")
    for e in targets:
        url = (e.get("url") or "").strip()
        text, title, err = pages.get(url, ("", "", "not fetched"))
        if err or not text:
            rejected.append({"name": e.get("name"), "date": e.get("date"), "url": url,
                             "reason": err or "empty page"})
            continue
        v = judge(e, text, title, single_post=_is_meta_host((urlparse(url).hostname or "").lower()))
        if not v["ok"]:
            rejected.append({"name": e.get("name"), "date": e.get("date"), "url": url, "reason": v["reason"]})
            continue
        host = urlparse(url).hostname or url
        rec = {"evidence_url": url, "action": "verified", "seen": f'{host}: "{v["seen"]}"',
               "by": BY, "at": stamp, "match": v["match"]}
        if not dry_run:
            e["human_verified"] = rec
        verified.append({"name": e.get("name"), "date": e.get("date"), "url": url, "seen": rec["seen"]})
    if verified and not dry_run:
        tmp = p + ".autoverify.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(container, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    report = {"week": week, "mode": mode, "ran_at": stamp, "dry_run": dry_run,
              "targets": len(targets), "fetched_urls": len(urls), "seconds": round(time.time() - t0, 1),
              "verified": verified, "rejected": rejected}
    try:
        out_dir = os.path.join(config.DATA_DIR, "posts", week)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"auto_verify_{mode}.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return report


# ── selftest ──────────────────────────────────────────────────────────────────

def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + msg)
        ok = ok and bool(cond)

    hamlet = {"name": "Tulsa Shakespeare Co. presents Hamlet", "date": "2026-10-30"}
    page = ("Hamlet | Tulsa Shakespeare\nPerformances: Thu, Oct. 29, 7:30 PM\nFri, Oct. 30, 7:30 PM\n"
            "Sat, Oct. 31, 2:00 PM. Lynn Riggs Theatre. Tickets for Hamlet on sale now. " + "x " * 1500)
    v = judge(hamlet, page, "Hamlet | Tulsa Shakespeare")
    check(v["ok"] and "Oct. 30" in v["match"], f"prose date + name nearby verifies ({v['reason']})")
    v = judge(dict(hamlet, date="2026-11-02"), page, "Hamlet")
    check(not v["ok"], "a date the page never states does not verify")

    taff = {"name": "TAFF 2024", "date": "2026-10-27"}
    v = judge(taff, "TAFF film festival October 27, 2024 at Circle Cinema", "2024 TAFF - Twisted Arts")
    check(not v["ok"] and "year" in v["reason"], f"a 2024 page never confirms this week ({v['reason']})")
    v = judge({"name": "Twisted Arts Film Fest", "date": "2026-10-27"},
              "Twisted Arts Film Fest returns Oct 27, 2024 to Circle Cinema", "Twisted Arts")
    check(not v["ok"], f"a different year next to the date rejects ({v['reason']})")

    raw = ('<meta property="og:title" content="DVL Club &amp; Lounge on Instagram: &quot;costume&quot;">'
           '<meta property="og:description" content="175 likes, 1 comments - dvltulsa on October 26, 2026: '
           '&quot;Costume contest FRI, 10/30 with a $500 prize&quot;">')
    text, title = page_text(raw, "www.instagram.com")
    check("October 26" not in text, "Instagram's 'posted on <date>' prefix is stripped")
    row = {"name": "Halloween Costume Contest", "date": "2026-10-30"}
    check(judge(row, text, title, single_post=True)["ok"], "the caption's FRI, 10/30 verifies the 10-30 row")
    check(not judge(dict(row, date="2026-10-26"), text, title, single_post=True)["ok"],
          "the post date does not verify a row dated the day it was posted")

    v = judge({"name": "Drag Brunch", "date": "2026-10-30"}, "Drag Brunch Saturday, October 30", "")
    check(not v["ok"] and "Saturday" in v["reason"], f"a weekday that contradicts the date rejects ({v['reason']})")
    v = judge({"name": "Drag Brunch", "date": "2026-10-30"}, "Drag Brunch Oct 30 has been cancelled", "")
    check(not v["ok"] and "cancel" in v["reason"], "a cancellation next to the date rejects")
    cal = "Oct 30: Pumpkin Patch Story Time. " + "filler " * 300 + "Drag Brunch is every Sunday."
    check(not judge({"name": "Drag Brunch", "date": "2026-10-30"}, cal, "")["ok"],
          "a calendar date belonging to another listing does not count")
    check(not judge({"name": "Oct 3 Show", "date": "2026-10-03"}, "Party Oct 30 ", "")["ok"],
          "Oct 3 does not match inside Oct 30")
    check(judge({"name": "Gaymer Night", "date": "2026-10-26"}, "Gaymer Night 10/26/26 at 8pm", "")["ok"],
          "numeric dates with a 2-digit year verify")

    import tempfile
    d = tempfile.mkdtemp(prefix="autoverify_")
    old = (config.EVENTS_DIR, config.DATA_DIR)
    try:
        config.EVENTS_DIR, config.DATA_DIR = d, d
        os.makedirs(os.path.join(d, "posts", "2026-W44"), exist_ok=True)
        rows = [dict(row, url="https://www.instagram.com/p/X/", source="dvl_ig"),
                dict(row, url="https://www.instagram.com/p/X/", source="manual", name="Manual Row")]
        with open(os.path.join(d, "2026-W44_all.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f)
        with open(os.path.join(d, "posts", "2026-W44", "truth_report.json"), "w", encoding="utf-8") as f:
            json.dump({"confirmed": []}, f)
        global fetch
        _f = fetch
        fetch = lambda u, timeout=20: (text, title, "")  # noqa: E731
        try:
            rep = run("2026-W44", mode="candidates")
        finally:
            fetch = _f
        saved = json.load(open(os.path.join(d, "2026-W44_all.json"), encoding="utf-8"))
        hv = saved[0].get("human_verified") or {}
        check(len(rep["verified"]) == 1 and hv.get("by") == BY and hv.get("evidence_url"),
              "a verified row gets human_verified with the machine-read label")
        check("human_verified" not in saved[1], "manual rows are never stamped")
        from tools.truth_status import load as _tl
        check(_tl("2026-W44").confirmed(saved[0]), "and preflight's truth rule now accepts that row")
    finally:
        config.EVENTS_DIR, config.DATA_DIR = old
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None)
    ap.add_argument("--candidates", action="store_true",
                    help="verify the week's featurable rows (before generate), not just the deck's")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    try:
        rep = run(a.week, mode="candidates" if a.candidates else "featured",
                  dry_run=a.dry_run, limit=a.limit)
    except FileNotFoundError as e:
        print(f"auto_verify_featured: {e}")
        sys.exit(2)
    print(f"auto-verify ({rep['mode']}) {rep['week']}: {len(rep['verified'])} verified, "
          f"{len(rep['rejected'])} not, of {rep['targets']} rows / {rep['fetched_urls']} urls "
          f"in {rep['seconds']}s{' [dry-run]' if rep['dry_run'] else ''}")
    if not a.quiet:
        for v in rep["verified"]:
            print(f"  + {v['name']} {v['date']}: {v['seen'][:140]}")
        for r in rep["rejected"]:
            print(f"  - {r['name']} {r['date']}: {r['reason'][:140]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
