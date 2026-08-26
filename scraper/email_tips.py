"""Email event-intake collector for events@tulsagays.com (built 2026-07-07).

William's idea: give the community ONE address to email events to. YBR, PFLAG,
any venue emails their event (with a flyer, or just text), and it flows into the
same review-first tip pipeline the IG DM intake uses (build_tip_entry ->
draft_voice_copy -> trusted-auto / unknown-review), with an autoresponder that
sends the submission instructions back once per sender.

Anonymity (hard rule): the public address is events@tulsagays.com. It is a free
Namecheap forward -> williamryanhunt@gmail.com, so we POLL William's Gmail via
IMAP (the token the fleet already uses) and match on the events@ address in the
To / Delivered-To / Cc headers. Replies go out AS events@tulsagays.com (the
send_gmail.py "tulsagays" alias account), never his real address.

This module ONLY collects + parses; the task (tasks/tulsagays_email_tips.py)
owns queueing, trusted-sender routing, and the autoresponse. Returns [] cleanly
(never raises) so a missing token / unconfigured alias is a no-op, not a failure.

Message dict shape (matches tools/ingest_dm_tips.build_tip_entry):
  {text, channel:"email", sender, subject, source_kind:"email",
   message_id, permalink:"", flyer_images:[...], captured_ts}

Selftest: python scraper/email_tips.py --selftest   (parses a synthetic email)
"""
from __future__ import annotations

import email
import imaplib
import json
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
INTAKE_ADDR = "events@tulsagays.com"
# Token moved to the non-synced credentials vault by the 2026-08 secret sweep
# (no-secrets-on-synced-drives rule); the old .claude/scripts path is dead.
IMAP_TOKEN = Path.home() / ".credentials" / "oauth" / "token_gmail_imap.json"
MAILBOX_USER = "williamryanhunt@gmail.com"
STATE_FILE = ROOT / "data" / "email_intake_state.json"
FLYER_DIR = ROOT / "data" / "email_flyers"
LOOKBACK_DAYS = 10          # matches the Mon-Sun + a buffer window
MAX_BODY = 4000


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_message_ids": []}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # cap the seen list so it never grows unbounded
        state["seen_message_ids"] = state.get("seen_message_ids", [])[-2000:]
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[email_tips] could not save state: %s", e)


def _imap_connect():
    """Authenticated IMAP4_SSL to the personal Gmail, or None on any failure."""
    if not IMAP_TOKEN.exists():
        logger.warning("[email_tips] no IMAP token at %s — cannot poll", IMAP_TOKEN)
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(IMAP_TOKEN))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            IMAP_TOKEN.write_text(creds.to_json(), encoding="utf-8")
        auth = f"user={MAILBOX_USER}\x01auth=Bearer {creds.token}\x01\x01"
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        M.authenticate("XOAUTH2", lambda _: auth.encode())
        return M
    except Exception as e:
        logger.warning("[email_tips] IMAP connect failed: %s %s", type(e).__name__, str(e)[:120])
        return None


def _decode(s) -> str:
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


def _plain_body(msg) -> str:
    """Best-effort plain-text body; falls back to stripped HTML."""
    def _first(mime):
        for part in msg.walk():
            if part.get_content_type() == mime and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        return ""
    body = _first("text/plain")
    if not body:
        html = _first("text/html")
        body = re.sub(r"<[^>]+>", " ", html)
    body = re.sub(r"\r", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    # cut common reply/signature noise so parsing sees the event, not the footer
    body = re.split(r"\n-- \n|On .* wrote:|________________________________", body)[0].strip()
    return body[:MAX_BODY]


def _sender_addr(msg) -> str:
    raw = _decode(msg.get("From", ""))
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    return (m.group(0) if m else raw).lower()


def _addressed_to_intake(msg) -> bool:
    hay = " ".join(_decode(msg.get(h, "")) for h in ("To", "Cc", "Delivered-To", "X-Forwarded-To")).lower()
    return INTAKE_ADDR in hay


def _save_flyers(msg, msg_id: str) -> List[str]:
    saved = []
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        if ctype.startswith("image/") or ("attachment" in disp and ctype.startswith("image")):
            try:
                data = part.get_payload(decode=True)
                if not data or len(data) < 1024:      # skip tracking pixels / tiny inline
                    continue
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                       "image/gif": ".gif"}.get(ctype, ".img")
                FLYER_DIR.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9]", "", msg_id)[-24:] or "msg"
                fp = FLYER_DIR / f"{safe}_{len(saved)}{ext}"
                fp.write_bytes(data)
                saved.append(str(fp))
            except Exception:
                continue
    return saved


def collect(lookback_days: int = LOOKBACK_DAYS, state: dict | None = None) -> List[Dict]:
    """Poll for new emails to events@tulsagays.com; return unseen ones as msg dicts."""
    state = state if state is not None else _load_state()
    seen = set(state.get("seen_message_ids", []))
    M = _imap_connect()
    if M is None:
        return []
    out: List[Dict] = []
    try:
        M.select('"[Gmail]/All Mail"')
        since = (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
        uids = set()
        # Match the intake address in any recipient header form the forwarder may use.
        for crit in (f'(TO "{INTAKE_ADDR}" SINCE {since})',
                     f'(HEADER "Delivered-To" "{INTAKE_ADDR}" SINCE {since})',
                     f'(CC "{INTAKE_ADDR}" SINCE {since})'):
            try:
                typ, data = M.search(None, crit)
                if typ == "OK" and data and data[0]:
                    uids.update(data[0].split())
            except Exception:
                continue
        for uid in sorted(uids):
            try:
                typ, data = M.fetch(uid, "(RFC822)")
                if typ != "OK" or not data or not data[0]:
                    continue
                msg = email.message_from_bytes(data[0][1])
            except Exception:
                continue
            if not _addressed_to_intake(msg):
                continue
            mid = _decode(msg.get("Message-ID", "")) or f"uid-{uid.decode() if isinstance(uid, bytes) else uid}"
            if mid in seen:
                continue
            sender = _sender_addr(msg)
            # never ingest our own forwards / bounces / William himself as a submitter
            if sender in (MAILBOX_USER, INTAKE_ADDR) or "mailer-daemon" in sender or "noreply" in sender:
                seen.add(mid)
                continue
            subject = _decode(msg.get("Subject", ""))
            body = _plain_body(msg)
            flyers = _save_flyers(msg, mid)
            text = (subject + "\n" + body).strip() if subject else body
            if not text and not flyers:
                seen.add(mid)
                continue
            out.append({
                "text": text,
                "channel": "email",
                "sender": sender,
                "subject": subject,
                "source_kind": "email",
                "message_id": mid,
                "permalink": "",
                "flyer_images": flyers,
                "captured_ts": _decode(msg.get("Date", "")),
            })
            seen.add(mid)
    finally:
        try:
            M.logout()
        except Exception:
            pass
    state["seen_message_ids"] = list(seen)
    _save_state(state)
    logger.info("[email_tips] %d new submission(s) to %s", len(out), INTAKE_ADDR)
    return out


def _selftest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Parse a synthetic raw email through the same body/sender helpers.
    raw = (
        "From: Val Pal <events@yellowbrickroad.example>\r\n"
        "To: events@tulsagays.com\r\n"
        "Subject: Karaoke Night this Thursday!\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Hey! We've got Karaoke with Party Possum this Thursday July 10 at 9pm "
        "at Yellow Brick Road, 2630 E 15th St. Free to get in. Come sing!\r\n\r\n"
        "-- \r\nSent from my phone\r\n"
    )
    msg = email.message_from_string(raw)
    assert _addressed_to_intake(msg), "should match intake address"
    assert _sender_addr(msg) == "events@yellowbrickroad.example"
    body = _plain_body(msg)
    assert "Karaoke with Party Possum" in body and "Sent from my phone" not in body, body
    print("sender:", _sender_addr(msg))
    print("body:", body[:120])
    print("email_tips selftest OK")
    return 0


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    # live poll (read-only; prints what it would ingest)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tips = collect()
    print(json.dumps(tips, indent=2)[:2000])
