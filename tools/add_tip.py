r"""Paste-in DM tip intake -> review queue -> manual_events (always review first).

People DM event tips to the @tulsagays Instagram and the Facebook page. This is
the front door that folds those into the pipeline WITHOUT auto-publishing.

Flow (William picked "build a paste-in tip tool" + "always review first", 2026-06-06):

  1. Paste the raw DM text. The tool best-effort parses name/date/time/venue/url
     out of free-form text and writes a PENDING entry to data/event_tips_inbox.json.
     It NEVER writes straight to the site. Raw text + any screenshot path are kept
     so a reviewer can see exactly what came in.

        python tools/add_tip.py add --text "Hey! Drag brunch at Inner Circle Sun June 22 noon, $15" --channel ig
        echo "<pasted dm>" | python tools/add_tip.py add --channel fb
        python tools/add_tip.py add --file C:\path\dm.txt --image C:\path\screenshot.png

  2. Review. List what's pending, open one to see raw + parsed fields, and fix any
     field (this is where the site voice copy gets written — by a human or a Claude
     session, never by a cheap model, per the brand-voice rule).

        python tools/add_tip.py list
        python tools/add_tip.py review <id>
        python tools/add_tip.py set <id> --name "..." --date 2026-06-22 --time "12:00 PM" \
            --venue "Inner Circle Vodka Bar" --url "https://..." \
            --description "<short slide pitch>" --website-description "<long site copy>"

  3. Approve -> promotes the entry into data/manual_events.json (the scraper already
     reads it) and marks the queue entry approved. Requires name + valid date +
     a non-empty description so nothing half-baked reaches the site. Dedup by name+date.

        python tools/add_tip.py approve <id>
        python tools/add_tip.py reject <id> --reason "duplicate of OKEQ bingo"

Design notes:
  - Free-form parsing is intentionally best-effort. The review gate is the safety
    net, so the parser aims for "good enough to correct fast," not perfection.
  - Voice copy is NOT auto-generated. Manual/submission events carry hand-written
    copy end-to-end (see scraper/manual_input.py); the reviewer supplies it.
  - Promoted entries use source="submission", priority 2 by default (community tip,
    not auto-EOTW). Override with `set <id> --priority N` before approving.

`--selftest` proves parsing + queue add + set + approve/dedup on temp files.
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, date as _date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

INBOX_FILE = os.path.join(config.DATA_DIR, "event_tips_inbox.json")
MANUAL_FILE = os.path.join(config.DATA_DIR, "manual_events.json")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_URL_RE = re.compile(r"(https?://[^\s)>\]]+|www\.[^\s)>\]]+)", re.I)
_DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today():
    return _date.today()


def parse_date(text, today=None):
    """Best-effort: pull a date out of free text. Returns 'YYYY-MM-DD' or ''.

    Handles: ISO (2026-06-11), 6/11 or 6/11/2026 or 06/11/26, and
    'June 11' / 'Jun 11, 2026' / 'Thursday, June 11'. When no year is given,
    infers the next occurrence (this year if not already past, else next year).
    """
    if not text:
        return ""
    today = today or _today()

    # 1) ISO date anywhere
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3])).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2) Month-name forms: "June 11", "Jun 11, 2026"
    m = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?",
        text, re.I,
    )
    if m:
        mon = _MONTHS.get(m[1].lower())
        day = int(m[2])
        year = int(m[3]) if m[3] else None
        if mon and 1 <= day <= 31:
            return _resolve_year(mon, day, year, today)

    # 3) Numeric M/D or M/D/Y
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if m:
        mon, day = int(m[1]), int(m[2])
        year = None
        if m[3]:
            year = int(m[3])
            if year < 100:
                year += 2000
        if 1 <= mon <= 12 and 1 <= day <= 31:
            return _resolve_year(mon, day, year, today)

    return ""


def _resolve_year(mon, day, year, today):
    if year is None:
        year = today.year
        try:
            cand = _date(year, mon, day)
        except ValueError:
            return ""
        if cand < today:
            year += 1
    try:
        return _date(year, mon, day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def parse_time(text):
    """Best-effort time / time-range. Returns a tidy string or ''.

    '6:00pm-7:30pm' -> '6:00 PM - 7:30 PM'; '6 PM' -> '6:00 PM'.
    """
    if not text:
        return ""
    times = re.findall(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)", text, re.I)
    tidy = []
    for hh, mm, ap in times:
        ap = ap.replace(".", "").upper()
        mm = mm or "00"
        tidy.append(f"{int(hh)}:{mm} {ap}")
        if len(tidy) == 2:
            break
    if not tidy:
        return ""
    return " - ".join(tidy)


def parse_url(text):
    if not text:
        return ""
    m = _URL_RE.search(text)
    if not m:
        return ""
    url = m.group(1).rstrip(".,);]")
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def parse_venue(text):
    """Look for 'at <Venue>' / '@ <Venue>'. Best-effort, reviewer confirms."""
    if not text:
        return ""
    m = re.search(r"(?:\bat|@)\s+([A-Z][A-Za-z'&.\- ]{2,60})", text)
    if not m:
        return ""
    venue = m.group(1).strip()
    # Stop at the first scheduling token (date word, weekday, or connective) so
    # the venue doesn't trail into "... June 14 2026 11am". Best-effort; reviewer confirms.
    venue = re.split(
        r"\s+(?:on|this|next|from|starting|tonight|tomorrow|"
        r"(?:mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b",
        venue, maxsplit=1, flags=re.I,
    )[0].strip()
    return venue.rstrip(".,")


def parse_name(text, date_str):
    """Guess the event name: first substantive line, date/time stripped off."""
    if not text:
        return ""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    # Drop common DM greetings.
    first = re.sub(r"^(hey|hi|hello|yo|fyi|psa)[!,. ]+", "", first, flags=re.I).strip()
    # Cut at the first date/time token so the name doesn't trail into scheduling.
    cut = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}|\d{1,2}\s*[ap]\.?m)",
        first, re.I,
    )
    if cut:
        first = first[: cut.start()].strip(" ,-:@")
    # Strip a TRAILING lone weekday ("...Mercury Lounge Fri") without nuking a
    # legit leading weekday name ("Monday Movie Night at the Tulsa Eagle").
    first = re.sub(r"\s+(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*$", "", first, flags=re.I)
    return first[:120].strip()


def parse_tip(text):
    """Run all best-effort parsers over raw DM text. Returns a partial event dict."""
    date_str = parse_date(text)
    return {
        "name": parse_name(text, date_str),
        "date": date_str,
        "time": parse_time(text),
        "venue": parse_venue(text),
        "url": parse_url(text),
        "description": "",
        "website_description": "",
    }


# ---------------------------------------------------------------------------
# Queue persistence
# ---------------------------------------------------------------------------

def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _next_id(inbox):
    n = 0
    for e in inbox:
        m = re.match(r"tip(\d+)", e.get("id", ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"tip{n + 1:03d}"


def _find(inbox, tip_id):
    for e in inbox:
        if e.get("id") == tip_id:
            return e
    return None


def _norm_key(name, date):
    return (re.sub(r"\W+", "", (name or "").lower()), (date or "").strip())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args, now=None, inbox_path=INBOX_FILE):
    text = args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    text = (text or "").strip()
    if not text:
        print("[add_tip] No tip text given (use --text, --file, or pipe via stdin).")
        return 2

    now = now or datetime.now()
    parsed = parse_tip(text)
    inbox = _load(inbox_path, [])
    entry = {
        "id": _next_id(inbox),
        "status": "pending_review",
        "captured_at": now.strftime("%Y-%m-%d %H:%M"),
        "channel": (args.channel or "").lower(),
        "submitted_by": args.submitted_by or "",
        "image": args.image or "",
        "raw_text": text,
        **parsed,
        "priority": 2,
    }
    inbox.append(entry)
    _save(inbox_path, inbox)
    print(f"[add_tip] Queued {entry['id']} (pending_review).")
    _print_entry(entry)
    missing = [k for k in ("name", "date") if not entry.get(k)] + (
        ["description"] if not entry.get("description") else []
    )
    if missing:
        print(f"  NEEDS before approve: {', '.join(missing)}  "
              f"(use: add_tip.py set {entry['id']} --<field> ...)")
    return 0


def cmd_list(args, inbox_path=INBOX_FILE):
    inbox = _load(inbox_path, [])
    pending = [e for e in inbox if e.get("status") == "pending_review"]
    if not args.all:
        shown = pending
    else:
        shown = inbox
    if not shown:
        print("[add_tip] No tips in queue." if args.all else "[add_tip] No pending tips.")
        return 0
    for e in shown:
        flag = "" if e.get("name") and e.get("date") and e.get("description") else "  (incomplete)"
        print(f"  {e['id']}  [{e.get('status'):14}] {e.get('date') or '????-??-??'}  "
              f"{(e.get('name') or '(no name)')[:50]}{flag}")
    return 0


def cmd_review(args, inbox_path=INBOX_FILE):
    inbox = _load(inbox_path, [])
    e = _find(inbox, args.id)
    if not e:
        print(f"[add_tip] No tip {args.id}.")
        return 1
    _print_entry(e, full=True)
    return 0


def cmd_set(args, inbox_path=INBOX_FILE):
    inbox = _load(inbox_path, [])
    e = _find(inbox, args.id)
    if not e:
        print(f"[add_tip] No tip {args.id}.")
        return 1
    fields = {
        "name": args.name, "date": args.date, "time": args.time,
        "venue": args.venue, "url": args.url, "description": args.description,
        "website_description": args.website_description,
        "priority": args.priority, "submitted_by": args.submitted_by,
    }
    changed = []
    for k, v in fields.items():
        if v is not None:
            e[k] = v
            changed.append(k)
    if args.date is not None and args.date and not _DATE_ISO_RE.match(args.date):
        print(f"[add_tip] WARNING: date '{args.date}' is not YYYY-MM-DD; approve will reject it.")
    _save(inbox_path, inbox)
    print(f"[add_tip] Updated {args.id}: {', '.join(changed) if changed else '(nothing)'}.")
    _print_entry(e)
    return 0


def cmd_approve(args, inbox_path=INBOX_FILE, manual_path=MANUAL_FILE):
    inbox = _load(inbox_path, [])
    e = _find(inbox, args.id)
    if not e:
        print(f"[add_tip] No tip {args.id}.")
        return 1
    ok, reason = _validate_for_promote(e)
    if not ok:
        print(f"[add_tip] Cannot approve {args.id}: {reason}")
        print(f"  Fix with: add_tip.py set {args.id} --<field> ...")
        return 1

    manual = _load(manual_path, [])
    key = _norm_key(e.get("name"), e.get("date"))
    if key in {_norm_key(m.get("name"), m.get("date")) for m in manual}:
        e["status"] = "approved"
        e["promoted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save(inbox_path, inbox)
        print(f"[add_tip] {args.id} already present in manual_events.json (dedup). Marked approved.")
        return 0

    note_bits = ["Tip via DM"]
    if e.get("channel"):
        note_bits.append(e["channel"].upper())
    if e.get("submitted_by"):
        note_bits.append(f"from {e['submitted_by']}")
    note_bits.append(f"captured {e.get('captured_at', '')}; reviewed before publish")
    event = {
        "name": e["name"].strip(),
        "date": e["date"].strip(),
        "time": (e.get("time") or "").strip(),
        "venue": (e.get("venue") or "").strip(),
        "description": e["description"].strip(),
        "website_description": (e.get("website_description") or "").strip(),
        "url": (e.get("url") or "").strip(),
        "source": "submission",
        "priority": int(e.get("priority") or 2),
        "lgbtq_relevant": True,
        "source_note": " ".join(note_bits),
    }
    manual.append(event)
    _save(manual_path, manual)
    e["status"] = "approved"
    e["promoted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save(inbox_path, inbox)
    print(f"[add_tip] Approved {args.id} -> manual_events.json ('{event['name']}' on {event['date']}).")
    print("  It will appear at the next scrape for that Mon-Sun week.")
    return 0


def cmd_reject(args, inbox_path=INBOX_FILE):
    inbox = _load(inbox_path, [])
    e = _find(inbox, args.id)
    if not e:
        print(f"[add_tip] No tip {args.id}.")
        return 1
    e["status"] = "rejected"
    e["reject_reason"] = args.reason or ""
    _save(inbox_path, inbox)
    print(f"[add_tip] Rejected {args.id}" + (f": {args.reason}" if args.reason else "."))
    return 0


def _validate_for_promote(e):
    name = (e.get("name") or "").strip()
    date = (e.get("date") or "").strip()
    desc = (e.get("description") or "").strip()
    if len(name) < 3:
        return False, "missing/short name"
    if not _DATE_ISO_RE.match(date):
        return False, "date must be YYYY-MM-DD"
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return False, "invalid calendar date"
    if not desc:
        return False, "missing description (write the site-voice short pitch first)"
    blob = " ".join([name, desc, e.get("website_description", "")])
    if "—" in blob or "--" in blob:
        return False, "contains an em dash (banned in TulsaGays voice) -- rewrite"
    return True, "ok"


def _print_entry(e, full=False):
    print(f"    id:        {e.get('id')}   status: {e.get('status')}   priority: {e.get('priority')}")
    print(f"    name:      {e.get('name') or '(none)'}")
    print(f"    date/time: {e.get('date') or '(none)'}  {e.get('time') or ''}")
    print(f"    venue:     {e.get('venue') or '(none)'}")
    print(f"    url:       {e.get('url') or '(none)'}")
    print(f"    channel:   {e.get('channel') or '(none)'}   from: {e.get('submitted_by') or '(none)'}")
    if e.get("image"):
        print(f"    image:     {e.get('image')}")
    print(f"    short:     {e.get('description') or '(none - write this)'}")
    if full:
        print(f"    long:      {e.get('website_description') or '(none)'}")
        print(f"    captured:  {e.get('captured_at')}")
        print("    --- raw DM ---")
        for ln in (e.get("raw_text") or "").splitlines():
            print(f"    | {ln}")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest():
    import tempfile

    # Parsing
    assert parse_date("Thursday, June 11, 2026 party") == "2026-06-11", parse_date("June 11, 2026")
    assert parse_date("drag show 6/22/2026") == "2026-06-22"
    assert parse_date("see you 2026-07-04") == "2026-07-04"
    # year inference: pick this year if future, else next
    inferred = parse_date("brunch Dec 31", today=_date(2026, 6, 8))
    assert inferred == "2026-12-31", inferred
    rolled = parse_date("brunch Jan 5", today=_date(2026, 6, 8))
    assert rolled == "2027-01-05", rolled
    assert parse_time("6:00pm-7:30pm") == "6:00 PM - 7:30 PM", parse_time("6:00pm-7:30pm")
    assert parse_time("doors 7 PM") == "7:00 PM"
    assert parse_url("info at www.foo.com/x.") == "https://www.foo.com/x"
    assert parse_venue("Drag brunch at Inner Circle Vodka Bar on Sunday") == "Inner Circle Vodka Bar"
    assert parse_venue("picnic at Guthrie Green June 14 2026 11am") == "Guthrie Green"

    tip = parse_tip("Hey! Drag Brunch at Inner Circle Sun June 22 2026 from 12:00pm-2:00pm, tix https://x.co/t")
    assert tip["date"] == "2026-06-22", tip
    assert tip["time"] == "12:00 PM - 2:00 PM", tip
    assert tip["url"] == "https://x.co/t", tip
    assert "Drag Brunch" in tip["name"], tip
    # leading weekday in a real name is preserved; trailing weekday is stripped
    assert parse_name("Monday Movie Night at the Tulsa Eagle June 1", "") == \
        "Monday Movie Night at the Tulsa Eagle"
    assert parse_name("Sapphic mixer at Mercury Lounge Fri June 26", "") == \
        "Sapphic mixer at Mercury Lounge"

    # Queue lifecycle on temp files
    d = tempfile.mkdtemp()
    inbox_p = os.path.join(d, "inbox.json")
    manual_p = os.path.join(d, "manual.json")
    _save(manual_p, [])

    class A:
        pass
    a = A()
    a.text = "Pride Picnic at Guthrie Green June 14 2026 11am"
    a.file = a.image = a.submitted_by = None
    a.channel = "ig"
    assert cmd_add(a, now=datetime(2026, 6, 8, 9, 0), inbox_path=inbox_p) == 0
    inbox = _load(inbox_p, [])
    assert len(inbox) == 1 and inbox[0]["id"] == "tip001", inbox
    assert inbox[0]["date"] == "2026-06-14", inbox[0]

    # cannot approve without a description
    ap = A(); ap.id = "tip001"
    assert cmd_approve(ap, inbox_path=inbox_p, manual_path=manual_p) == 1

    # set description, then approve
    s = A()
    s.id = "tip001"; s.name = None; s.date = None; s.time = None; s.venue = None
    s.url = None; s.description = "Queer picnic vibes on the Green, baby. Bring a blanket."
    s.website_description = None; s.priority = None; s.submitted_by = None
    assert cmd_set(s, inbox_path=inbox_p) == 0
    assert cmd_approve(ap, inbox_path=inbox_p, manual_path=manual_p) == 0
    manual = _load(manual_p, [])
    assert len(manual) == 1 and manual[0]["source"] == "submission", manual
    assert manual[0]["lgbtq_relevant"] is True, manual[0]

    # idempotent: approving again dedups (no second manual row)
    assert cmd_approve(ap, inbox_path=inbox_p, manual_path=manual_p) == 0
    assert len(_load(manual_p, [])) == 1

    # em-dash guard
    s.id = "tip001"
    print("add_tip selftest: passed (parsing + queue add/set/approve/dedup + guards)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paste-in DM event tip intake (review-first).")
    ap.add_argument("--selftest", action="store_true", help="run internal tests and exit")
    sub = ap.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="queue a raw DM tip for review")
    p_add.add_argument("--text", help="the raw DM text")
    p_add.add_argument("--file", help="read raw DM text from a file")
    p_add.add_argument("--image", help="path to a screenshot of the DM (kept for the reviewer)")
    p_add.add_argument("--channel", help="ig | fb")
    p_add.add_argument("--submitted-by", dest="submitted_by", help="who sent it (handle/name)")

    sub.add_parser("list", help="list pending tips").add_argument(
        "--all", action="store_true", help="include approved/rejected")

    p_rev = sub.add_parser("review", help="show one tip in full (raw + parsed)")
    p_rev.add_argument("id")

    p_set = sub.add_parser("set", help="fill/correct fields on a tip")
    p_set.add_argument("id")
    for f in ("name", "date", "time", "venue", "url", "description"):
        p_set.add_argument(f"--{f}")
    p_set.add_argument("--website-description", dest="website_description")
    p_set.add_argument("--priority")
    p_set.add_argument("--submitted-by", dest="submitted_by")

    p_app = sub.add_parser("approve", help="promote a tip into manual_events.json")
    p_app.add_argument("id")

    p_rej = sub.add_parser("reject", help="mark a tip rejected")
    p_rej.add_argument("id")
    p_rej.add_argument("--reason")

    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.cmd:
        ap.print_help()
        return 0
    return {
        "add": cmd_add, "list": cmd_list, "review": cmd_review,
        "set": cmd_set, "approve": cmd_approve, "reject": cmd_reject,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
