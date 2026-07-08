"""Shared email-intake core: poll events@tulsagays.com -> route -> add to the site.

Called BOTH by the scheduled task (task-runner/tasks/tulsagays_email_tips.py) AND
by main.py cmd_scrape (so every scrape pulls the latest emailed events before it
runs — William 2026-07-07: "when we do the scrape, make sure we're looking in
there and adding them"). Idempotent: the collector dedups by Message-ID, and
approve dedups by name+date.

Routing:
  - TRUSTED sender (data/trusted_submitters.json) + safe + valid -> auto-publish
    to manual_events.json (which the scrape reads) with a ONE-TIME priority boost.
  - everyone else -> held pending_review (spam/hate gate too).
Autoresponse (instructions) fires once per sender, from the events@ alias, HELD
until data/email_intake_config.json alias_verified=true (anonymity).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path.home() / ".claude" / "scripts"
TRUSTED_FILE = ROOT / "data" / "trusted_submitters.json"
CONFIG_FILE = ROOT / "data" / "email_intake_config.json"
AUTOREPLY_LOG = ROOT / "data" / "email_autoreply_log.json"
AUTORESPONSE_TXT = ROOT / "data" / "email_autoresponse.txt"

_UNSAFE = (
    "make money", "crypto", "investor", "mlm", "passive income", "forex",
    "work from home", "weight loss", "viagra", "casino", "loan",
    "faggot", "tranny", "groomer", "degenerate",
)

# Recurrence hints in a submission -> NOT a one-time event (no priority boost).
_RECURRING_HINTS = ("every ", "weekly", "each week", "each month", "monthly",
                    "recurring", "every monday", "every tuesday", "every wednesday",
                    "every thursday", "every friday", "every saturday", "every sunday")


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _is_trusted(sender: str, trusted: dict) -> bool:
    s = (sender or "").lower()
    if s in {a.lower() for a in trusted.get("addresses", [])}:
        return True
    dom = s.split("@")[-1] if "@" in s else ""
    return dom in {d.lower() for d in trusted.get("domains", [])}


def _is_safe(entry: dict) -> bool:
    blob = " ".join(str(entry.get(k, "")) for k in ("name", "raw_text", "description", "website_description")).lower()
    return not any(bad in blob for bad in _UNSAFE)


def _is_one_time(entry: dict) -> bool:
    blob = (str(entry.get("raw_text", "")) + " " + str(entry.get("name", ""))).lower()
    return not any(h in blob for h in _RECURRING_HINTS)


def _autorespond(senders: set, now: datetime) -> str:
    """Auto-reply with submission instructions, from events@tulsagays.com via Brevo
    (anonymous; never William's address). Once per sender."""
    log = _load(AUTOREPLY_LOG, {"replied": []})
    already = {a.lower() for a in log.get("replied", [])}
    fresh = [s for s in senders if s and s.lower() not in already]
    if not fresh:
        return "0"
    from tools import brevo_send
    if not brevo_send._key():
        return f"HELD ({len(fresh)} - no Brevo key)"
    body = AUTORESPONSE_TXT.read_text(encoding="utf-8")
    sent = 0
    for s in fresh:
        ok, detail = brevo_send.send(s, "Thanks for sending us your event", body)
        if ok:
            log.setdefault("replied", []).append(s); sent += 1
        else:
            logger.warning("[email] autoresponse to %s failed: %s", s, detail)
    AUTOREPLY_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return f"{sent} sent"


def ingest(auto_publish: bool = True) -> dict:
    """Poll, route, and (for trusted senders) add events to manual_events.json.
    Returns {collected, auto_published:[ids], held:[ids], autoresponses}."""
    sys.path.insert(0, str(ROOT))
    from scraper import email_tips
    from tools import add_tip, ingest_dm_tips, enrich_tip_links

    msgs = email_tips.collect()
    if not msgs:
        return {"collected": 0, "auto_published": [], "held": [], "autoresponses": "0"}

    inbox = add_tip._load(add_tip.INBOX_FILE, [])
    trusted = _load(TRUSTED_FILE, {})
    now = datetime.now()

    new_ids, sender_by_id = [], {}
    for m in msgs:
        entry = ingest_dm_tips.build_tip_entry(m, inbox, now)
        entry["channel"] = "email"
        try:
            entry = enrich_tip_links.enrich_tip(entry)
        except Exception:
            pass
        entry = ingest_dm_tips.draft_voice_copy(entry)
        # One-time events are the priority (William 2026-07-07: "one-time events
        # are way more important than repeating"). Boost emailed one-offs so the
        # featuring logic floats them up; recurring submissions stay ordinary.
        entry["priority"] = 3 if _is_one_time(entry) else 2
        entry["one_time"] = _is_one_time(entry)
        inbox.append(entry)
        new_ids.append(entry["id"])
        sender_by_id[entry["id"]] = m.get("sender", "")
    add_tip._save(add_tip.INBOX_FILE, inbox)

    entries = {e["id"]: e for e in add_tip._load(add_tip.INBOX_FILE, [])}
    auto, held = [], []
    for tid in new_ids:
        e = entries.get(tid, {})
        if auto_publish and _is_trusted(sender_by_id.get(tid, ""), trusted) and _is_safe(e):
            class _A: pass
            a = _A(); a.id = tid
            try:
                ok = add_tip.cmd_approve(a) == 0
            except Exception as ex:
                logger.warning("[email] auto-publish %s failed: %s", tid, ex); ok = False
            (auto if ok else held).append(tid)
        else:
            held.append(tid)

    replies = _autorespond(set(sender_by_id.values()), now)
    return {"collected": len(msgs), "auto_published": auto, "held": held, "autoresponses": replies}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(ingest(), indent=2))
