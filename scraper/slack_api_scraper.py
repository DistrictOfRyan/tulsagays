"""TulsaRemote Slack event scraper — Slack Web API (conversations.history).

Replaces the dead browser-scrolling approach (0% success, retired 2026-07-02).
Reads the last ~14 days of messages from three TulsaRemote channels via the
official Web API using a user token, extracts event-shaped messages, and writes
data/slack_events_browser.json in the EXACT format scraper/slack_browser_scraper.py
already consumes — so the main scrape pipeline needs no changes.

Channels:
  - #events-local      (CGV2YLJSG): general Tulsa community events (all included)
  - #unite-lgbtq-plus  (C0262PQNUDD): LGBTQ+-specific events
  - #gradient          (resolved by name via conversations.list)

Token: SLACK_TULSAREMOTE_TOKEN in ~/.credentials/api_keys.env (or env var).
  User token (xoxp-...) with scopes: channels:history, channels:read, users:read.
  The token's user must be a MEMBER of each channel (API returns not_in_channel
  otherwise — join in the Slack client once, membership persists).

Never writes an empty current-week events file: on token-missing, API failure,
or zero extracted events it leaves slack_events_browser.json untouched so the
stale-file/flag retry signal keeps firing (hard rule, see SKILL.md).

Exit codes (used by the task-runner handler):
  0 = wrote fresh file with >=1 event
  2 = token missing/unreadable (blocked on William)
  3 = Slack API error (auth revoked, network, all channels failed)
  4 = ran clean but 0 event-shaped messages found (file left untouched)

Standalone:
  python scraper/slack_api_scraper.py --run        # real run
  python scraper/slack_api_scraper.py --dry-run    # fetch+extract, no file write
  python scraper/slack_api_scraper.py --selftest   # offline extractor tests
"""

import sys
import os
import re
import json
import time as _time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

API_BASE = "https://slack.com/api"
CREDS_ENV_FILE = os.path.join(os.path.expanduser("~"), ".credentials", "api_keys.env")
TOKEN_VAR = "SLACK_TULSAREMOTE_TOKEN"

BROWSER_JSON = os.path.join(config.DATA_DIR, "slack_events_browser.json")
FLAG_FILE = os.path.join(config.DATA_DIR, "slack_browser_needed.flag")
CHANNEL_CACHE = os.path.join(config.DATA_DIR, "slack_channel_ids.json")

# name -> known ID. Verified live via the session 2026-07-17 (William confirmed we
# want #events-local COMMUNITY events, NOT #-events-tr-hosted CF07NK2RJ which is
# deliberately excluded). unite-lgbtq-plus is CU36YG88K (the OLD C0262PQNUDD was
# stale and returned channel_not_found). #gradient isn't in the workspace.
CHANNELS = {
    "events-local": "CGV2YLJSG",       # community events (the one we want)
    "unite-lgbtq-plus": "CU36YG88K",   # LGBTQ+ events (corrected ID)
    # NOTE: #-events-tr-hosted (CF07NK2RJ) is TulsaRemote's OWN events — EXCLUDED on purpose.
}

LOOKBACK_DAYS = 14
FORWARD_WINDOW_DAYS = 60   # keep events dated up to ~2 months out
MAX_PAGES_PER_CHANNEL = 3  # 3 x 200 messages / 14 days is plenty

NOISE_SUBTYPES = {
    "channel_join", "channel_leave", "channel_topic", "channel_purpose",
    "channel_name", "channel_archive", "channel_unarchive", "pinned_item",
}

GREETING_LINE = re.compile(
    r"^(hey|hi|hello|howdy|good\s+(morning|afternoon|evening)|happy\s+\w+day"
    r"|friends|y'?all|everyone|folks|fyi|reminder|psa)\b[\s!,:.]*$|"
    r"^(hey|hi|hello|howdy)\b[\s!,:.]{0,3}(all|everyone|y'?all|friends|folks|tulsa)?[\s!,:.]*$",
    re.IGNORECASE,
)

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})
WEEKDAYS = {d.lower(): i for i, d in enumerate(
    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
WEEKDAYS.update({d[:3].lower(): i for d, i in list(WEEKDAYS.items())})

_MONTH_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun[e]?|jul[y]?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_WD_RE = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"

TIME_RE = re.compile(
    r"\b(\d{1,2}(?::\d{2})?)\s*(am|pm|a\.m\.|p\.m\.)\b"
    r"|\b(\d{1,2}:\d{2})\b(?!\s*(?:am|pm))", re.IGNORECASE)

URL_JUNK_DOMAINS = ("slack.com", "tulsaremote.slack.com", "giphy.com", "tenor.com")


# ── token ────────────────────────────────────────────────────────────────────

def load_token() -> Optional[str]:
    tok = os.environ.get(TOKEN_VAR, "").strip()
    if tok:
        return tok
    try:
        with open(CREDS_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(TOKEN_VAR + "="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    except OSError:
        pass
    return None


# ── slack api ────────────────────────────────────────────────────────────────

def _api(token: str, method: str, params: dict, retries: int = 3) -> dict:
    """Call a Slack Web API method with 429 handling. Returns the JSON body."""
    url = f"{API_BASE}/{method}"
    for attempt in range(retries):
        resp = requests.get(url, params=params,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "10"))
            logger.warning(f"[slack_api] 429 on {method}, sleeping {wait}s")
            _time.sleep(min(wait, 60))
            continue
        resp.raise_for_status()
        return resp.json()
    return {"ok": False, "error": "rate_limited"}


def resolve_channels(token: str) -> Tuple[Dict[str, str], List[str]]:
    """Resolve CHANNELS name->id via conversations.list; fall back to hardcoded.

    Returns (resolved {name: id}, notes[]).
    """
    notes: List[str] = []
    by_name: Dict[str, str] = {}
    cursor = ""
    try:
        for _ in range(20):  # paginate, TulsaRemote is a big workspace
            params = {"types": "public_channel", "limit": 999,
                      "exclude_archived": "true"}
            if cursor:
                params["cursor"] = cursor
            body = _api(token, "conversations.list", params)
            if not body.get("ok"):
                notes.append(f"conversations.list failed: {body.get('error')}")
                break
            for ch in body.get("channels", []):
                by_name[ch.get("name", "")] = ch.get("id", "")
            cursor = (body.get("response_metadata") or {}).get("next_cursor", "")
            if not cursor:
                break
    except requests.RequestException as e:
        notes.append(f"conversations.list request error: {e}")

    resolved: Dict[str, str] = {}
    for name, fallback in CHANNELS.items():
        cid = by_name.get(name)
        if cid:
            resolved[name] = cid
            if fallback and cid != fallback:
                notes.append(f"#{name} resolved to {cid} (code had {fallback})")
        elif fallback:
            resolved[name] = fallback
            notes.append(f"#{name} not in conversations.list, using fallback {fallback}")
        else:
            notes.append(f"#{name} could not be resolved (no fallback ID) — skipped")

    if resolved:
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            with open(CHANNEL_CACHE, "w", encoding="utf-8") as f:
                json.dump({"resolved_at": datetime.now().isoformat(),
                           "channels": resolved}, f, indent=2)
        except OSError:
            pass
    return resolved, notes


def fetch_history(token: str, channel_id: str) -> Tuple[List[dict], Optional[str]]:
    """Return (messages, error). Messages are top-level, newest first."""
    oldest = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).timestamp()
    messages: List[dict] = []
    cursor = ""
    for _ in range(MAX_PAGES_PER_CHANNEL):
        params = {"channel": channel_id, "oldest": f"{oldest:.6f}", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        try:
            body = _api(token, "conversations.history", params)
        except requests.RequestException as e:
            return messages, f"request error: {e}"
        if not body.get("ok"):
            return messages, body.get("error", "unknown_error")
        messages.extend(body.get("messages", []))
        if not body.get("has_more"):
            break
        cursor = (body.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break
    return messages, None


_user_cache: Dict[str, str] = {}


def user_display(token: str, user_id: str) -> str:
    if not user_id:
        return ""
    if user_id in _user_cache:
        return _user_cache[user_id]
    name = ""
    try:
        body = _api(token, "users.info", {"user": user_id})
        if body.get("ok"):
            prof = body["user"].get("profile", {})
            name = (prof.get("display_name") or prof.get("real_name")
                    or body["user"].get("name") or "")
    except requests.RequestException:
        pass
    _user_cache[user_id] = name  # cache misses too (no users:read scope etc.)
    return name


# ── message -> event extraction ──────────────────────────────────────────────

def clean_slack_text(text: str) -> str:
    """Strip Slack markup: <url|label> -> label, <url> -> url, <@U..> -> '', entities."""
    if not text:
        return ""
    text = re.sub(r"<(https?://[^|>]+)\|([^>]*)>", r"\2 (\1)", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    text = re.sub(r"<[@#!][^>]*>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r":[a-z0-9_+\-]+:", "", text)  # :emoji: codes
    return text.strip()


def full_message_text(msg: dict) -> str:
    """text + any attachment titles/text (event flyers often unfurl there)."""
    parts = [msg.get("text", "")]
    for att in msg.get("attachments", []) or []:
        for k in ("title", "text"):
            v = att.get(k)
            if v:
                parts.append(v)
    return clean_slack_text("\n".join(p for p in parts if p))


def _pick_year(month: int, day: int, anchor: datetime) -> Optional[datetime]:
    """Choose the year that puts month/day within [anchor-7d, anchor+300d]."""
    for year in (anchor.year, anchor.year + 1):
        try:
            dt = datetime(year, month, day)
        except ValueError:
            continue
        if anchor - timedelta(days=7) <= dt <= anchor + timedelta(days=300):
            return dt
    return None


def extract_date(text: str, anchor: datetime) -> str:
    """Find the first event date in text, anchored to the message timestamp.

    Returns YYYY-MM-DD or "".
    """
    t = text.lower()

    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", t)
    if m:
        return m.group(0)

    # "July 11th", "Jul 11, 2026" (optionally "Friday, July 11")
    m = re.search(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(20\d{{2}}))?\b", t)
    if m:
        month = MONTHS.get(m.group(1)[:3])
        day = int(m.group(2))
        if m.group(3):
            try:
                return datetime(int(m.group(3)), month, day).strftime("%Y-%m-%d")
            except ValueError:
                pass
        dt = _pick_year(month, day, anchor)
        if dt:
            return dt.strftime("%Y-%m-%d")

    # "11th of July"
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+of\s+({_MONTH_RE})\b", t)
    if m:
        dt = _pick_year(MONTHS.get(m.group(2)[:3]), int(m.group(1)), anchor)
        if dt:
            return dt.strftime("%Y-%m-%d")

    # "7/11" or "7/11/2026" — skip obvious times like 7/11pm is impossible, fine
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            if m.group(3):
                year = int(m.group(3))
                year = year + 2000 if year < 100 else year
                try:
                    return datetime(year, month, day).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            dt = _pick_year(month, day, anchor)
            if dt:
                return dt.strftime("%Y-%m-%d")

    # today / tonight / tomorrow
    if re.search(r"\b(today|tonight)\b", t):
        return anchor.strftime("%Y-%m-%d")
    if re.search(r"\btomorrow\b", t):
        return (anchor + timedelta(days=1)).strftime("%Y-%m-%d")

    # "this Saturday" / "next Saturday" / bare "Saturday"
    m = re.search(rf"\b(this|next)?\s*({_WD_RE})\b", t)
    if m:
        wd = WEEKDAYS.get(m.group(2)[:3])
        if wd is not None:
            delta = (wd - anchor.weekday()) % 7
            if m.group(1) == "next" and delta <= 1:
                delta += 7
            if delta == 0 and m.group(1) is None:
                delta = 0  # "Saturday" posted on Saturday = today
            return (anchor + timedelta(days=delta)).strftime("%Y-%m-%d")

    return ""


def extract_time(text: str) -> str:
    m = TIME_RE.search(text)
    if not m:
        return ""
    if m.group(1) and m.group(2):
        hhmm = m.group(1) if ":" in m.group(1) else f"{m.group(1)}:00"
        ampm = m.group(2).replace(".", "").upper()
        return f"{hhmm} {ampm}"
    if m.group(3):
        try:
            h, mi = m.group(3).split(":")
            h = int(h)
            if 0 <= h <= 23:
                ampm = "AM" if h < 12 else "PM"
                h12 = h % 12 or 12
                return f"{h12}:{int(mi):02d} {ampm}"
        except ValueError:
            pass
    return ""


def extract_venue(text: str) -> str:
    for pattern in (
        r"(?:location|where|venue)\s*[:\-]\s*([^\n|]+)",
        r"\bat\s+(?:the\s+)?([A-Z][^\n,.!?(]{2,60})",
        r"@\s*([A-Z][^\n,.!?(]{2,60})",
    ):
        m = re.search(pattern, text)
        if m:
            venue = re.sub(r"\s+", " ", m.group(1)).strip(" -.")
            venue = re.sub(r"\s*\(?https?://\S+\)?", "", venue).strip()
            if 3 <= len(venue) <= 80:
                return venue
    return ""


def extract_url(text: str) -> str:
    for url in re.findall(r"https?://\S+", text):
        url = url.rstrip(".,;:!)>")
        if not any(d in url for d in URL_JUNK_DOMAINS):
            return url
    return ""


def extract_name(text: str) -> str:
    for line in text.split("\n"):
        line = re.sub(r"https?://\S+", "", line)
        line = re.sub(r"[*_~`]", "", line).strip(" -••!")
        line = re.sub(r"^\W+", "", line).strip()
        if len(line) < 5 or GREETING_LINE.match(line):
            continue
        return line[:120]
    return ""


def message_to_event(msg: dict, channel_name: str, token: str = "",
                     now: Optional[datetime] = None) -> Optional[dict]:
    """Convert one Slack message to the slack_events_browser.json event format."""
    if msg.get("subtype") in NOISE_SUBTYPES:
        return None
    text = full_message_text(msg)
    if len(text) < 30:
        return None

    try:
        anchor = datetime.fromtimestamp(float(msg.get("ts", "0")))
    except (ValueError, OSError):
        anchor = now or datetime.now()
    now = now or datetime.now()

    date_str = extract_date(text, anchor)
    if not date_str:
        return None
    try:
        event_dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    # keep current week + near future; drop clearly-past events
    week_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    if not (week_monday <= event_dt <= now + timedelta(days=FORWARD_WINDOW_DAYS)):
        return None

    name = extract_name(text)
    if not name:
        return None

    author = user_display(token, msg.get("user", "")) if token else ""
    posted = anchor.strftime("%Y-%m-%d")
    description = re.sub(r"\s+", " ", text)[:400]

    return {
        "name": name,
        "date": date_str,
        "time": extract_time(text),
        "venue": extract_venue(text),
        "description": description,
        "url": extract_url(text),
        "source_channel": f"#{channel_name}",
        "source_note": (f"Posted by {author} on {posted}" if author
                        else f"Posted on {posted} (Slack API)"),
    }


# ── orchestration ────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> Tuple[int, dict]:
    summary = {"ok": False, "token_present": False, "channels": {},
               "events_total": 0, "wrote_file": False, "notes": []}

    token = load_token()
    if not token:
        summary["notes"].append(
            f"{TOKEN_VAR} not found in env or {CREDS_ENV_FILE}. "
            "Create a Slack user token (channels:history + channels:read + users:read) "
            "and add it — see pending-william-actions.")
        return 2, summary
    summary["token_present"] = True

    # auth sanity
    try:
        auth = _api(token, "auth.test", {})
    except requests.RequestException as e:
        summary["notes"].append(f"auth.test request error: {e}")
        return 3, summary
    if not auth.get("ok"):
        summary["notes"].append(f"auth.test failed: {auth.get('error')}")
        return 3, summary
    if auth.get("team_id") and auth["team_id"] != "TF1E6FCR5":
        summary["notes"].append(
            f"token is for workspace {auth.get('team')} ({auth.get('team_id')}), "
            "expected TulsaRemote (TF1E6FCR5) — refusing to scrape the wrong workspace.")
        return 3, summary

    resolved, notes = resolve_channels(token)
    summary["notes"].extend(notes)

    all_events: List[dict] = []
    hard_errors = 0
    for name, cid in resolved.items():
        msgs, err = fetch_history(token, cid)
        ch_info = {"id": cid, "messages": len(msgs), "events": 0, "error": err}
        if err:
            hard_errors += 1
            if err == "not_in_channel":
                ch_info["fix"] = ("token user must JOIN #%s in the Slack client "
                                  "once (membership persists)" % name)
        else:
            events = []
            for m in msgs:
                ev = message_to_event(m, name, token=token)
                if ev:
                    events.append(ev)
            # dedupe within channel by (name, date)
            seen = set()
            uniq = []
            for ev in events:
                key = (ev["name"].lower(), ev["date"])
                if key not in seen:
                    seen.add(key)
                    uniq.append(ev)
            ch_info["events"] = len(uniq)
            all_events.extend(uniq)
        summary["channels"][name] = ch_info

    summary["events_total"] = len(all_events)

    if resolved and hard_errors == len(resolved):
        return 3, summary

    if not all_events:
        summary["notes"].append(
            "0 event-shaped messages found; leaving slack_events_browser.json "
            "untouched (never write an empty current-week file).")
        return 4, summary

    if dry_run:
        summary["ok"] = True
        summary["notes"].append("dry-run: file not written")
        return 0, summary

    week_key = f"{datetime.now().year}-W{datetime.now().isocalendar()[1]:02d}"
    payload = {
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "week": week_key,
        "channels": [f"#{n}" for n in resolved],
        "extraction_method": "slack_web_api",
        "events": all_events,
    }
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = BROWSER_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, BROWSER_JSON)
    summary["wrote_file"] = True
    summary["ok"] = True
    if os.path.exists(FLAG_FILE):
        try:
            os.remove(FLAG_FILE)
            summary["notes"].append("removed slack_browser_needed.flag")
        except OSError:
            pass
    return 0, summary


# ── selftest ─────────────────────────────────────────────────────────────────

def selftest() -> int:
    anchor = datetime(2026, 7, 6, 9, 0)  # a Monday
    fails = []

    def check(label, got, want):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    check("iso date", extract_date("Market on 2026-07-11 at 6pm", anchor), "2026-07-11")
    check("month day", extract_date("Join us Saturday, July 11th!", anchor), "2026-07-11")
    check("slash date", extract_date("Art show 7/11 6-9pm", anchor), "2026-07-11")
    check("tomorrow", extract_date("Free yoga tomorrow morning", anchor), "2026-07-07")
    check("weekday", extract_date("See you this friday", anchor), "2026-07-10")
    check("year roll", extract_date("Gala on January 10", anchor), "2027-01-10")
    check("no date", extract_date("Great meeting everyone", anchor), "")

    check("time pm", extract_time("doors at 7:30 PM"), "7:30 PM")
    check("time bare", extract_time("starts 7pm sharp"), "7:00 PM")
    check("time 24h", extract_time("from 18:30 onward"), "6:30 PM")

    check("clean url", clean_slack_text("<https://x.com/e|Tickets here>"),
          "Tickets here (https://x.com/e)")
    check("clean mention", clean_slack_text("<@U123> posted"), "posted")

    msg = {"ts": str(anchor.timestamp()),
           "text": ("*Second Saturday Art Market*\nSaturday, July 11th, 6-9pm "
                    "at Living Arts of Tulsa\nFree entry! <https://livingarts.org/market>")}
    ev = message_to_event(msg, "events-local", now=anchor)
    assert ev, "flyer message should extract"
    check("ev name", ev["name"], "Second Saturday Art Market")
    check("ev date", ev["date"], "2026-07-11")
    check("ev url", ev["url"], "https://livingarts.org/market")
    assert "Living Arts" in ev["venue"], f"venue: {ev['venue']}"

    noise = {"ts": str(anchor.timestamp()), "subtype": "channel_join",
             "text": "user joined #events-local on July 11"}
    check("noise skipped", message_to_event(noise, "events-local", now=anchor), None)

    chatter = {"ts": str(anchor.timestamp()),
               "text": "Thanks everyone for showing up, that was so fun!!"}
    check("chatter skipped", message_to_event(chatter, "events-local", now=anchor), None)

    past = {"ts": str(anchor.timestamp()),
            "text": "Recap: the June 20 potluck was great, thanks to all who came out to Whiteside Park"}
    check("past-date skipped", message_to_event(past, "events-local", now=anchor), None)

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (18 checks)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if "--selftest" in sys.argv:
        sys.exit(selftest())

    rc, summary = run(dry_run="--dry-run" in sys.argv)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n=== slack_api_scraper rc={rc} events={summary['events_total']} ===")
    sys.exit(rc)
