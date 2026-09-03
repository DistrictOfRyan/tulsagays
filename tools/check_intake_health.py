#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end health check (canary) for the events@tulsagays.com intake pipeline.

Why this exists (William 2026-07-10): the intake task logs "0 new submissions"
whether the inbox is quiet OR the whole forward chain is broken. That silent
success is exactly the failure mode [[feedback_tulsagays_silent_success]] warns
about. A passive check can't tell a dead pipe from a slow week. Only a CANARY
can: send a uniquely-tagged email through the REAL public path and confirm it
comes out the other end.

Chain proven:  Brevo (external infra, NOT William's Gmail -> no self-dedup)
  -> events@tulsagays.com (Namecheap forward)
  -> williamryanhunt@gmail.com  (polled via the fleet IMAP token)

Each run also verifies (read-only, safe any day):
  - IMAP auth still works (token alive)
  - email_intake_config.json still says forwarding_live + alias_verified
  - the tulsagays-email-intake task actually ran recently (freshness)
  - any canary PENDING from a prior run has since arrived (latency-tolerant)

The canary body is deliberately NON-event (no date, no venue, no event keyword)
so the intake's event-shaped gate drops it; belt-and-suspenders, once detected we
also append its Message-ID to the intake seen-list so it can never become a fake
tip.

The native Meta Business Suite Auto reply (IG/Messenger DM -> events@) cannot be
read via the current API scopes, so this checker cannot verify it programmatically
-- it emits a standing reminder to spot-check it (see AUTO_REPLY_NOTE).

Usage:
  python tools/check_intake_health.py            # full: read-only checks + send a canary + verify pending
  python tools/check_intake_health.py --no-send  # read-only checks + verify pending only (no email sent)
  python tools/check_intake_health.py --selftest # offline logic test, no network
State: data/intake_health_state.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CLAUDE = Path.home() / ".claude"
STATE_FILE = ROOT / "data" / "intake_health_state.json"
CONFIG_FILE = ROOT / "data" / "email_intake_config.json"
INTAKE_STATE = ROOT / "data" / "email_intake_state.json"
RUNNER_LOG = CLAUDE / "task-runner" / "logs" / "runner.log"
GAP_LEDGER = CLAUDE / "scripts" / "gap_ledger.py"
LOG_TASK_RUN = CLAUDE / "scripts" / "log-task-run.py"

TASK_NAME = "tulsagays-intake-health"
INTAKE_ADDR = "events@tulsagays.com"

# How long a canary may take to traverse Brevo -> Namecheap -> Gmail before we
# call the forward broken. Generous: forwarding is usually seconds, but greylisting
# and Brevo queueing can add minutes. A pending canary older than this = FAILURE.
CANARY_SLA_HOURS = 6
# In-run poll: after sending, look for it for up to this long before deferring to
# the next run's pending-check (so a slow forward is not a false alarm).
INRUN_POLL_SECONDS = 180
INRUN_POLL_EVERY = 20
# The intake task should run at least this often (2:30a + 6:30p => <=16h apart).
INTAKE_FRESH_HOURS = 26

AUTO_REPLY_NOTE = (
    "Meta Business Suite Auto reply (IG/Messenger DM -> events@) is a native "
    "setting, not code; verify monthly it is still ON for both channels "
    "(business.facebook.com -> Inbox -> Automations -> Auto reply)."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[intake-health] WARN could not save state: {e}")


# ---- individual checks -----------------------------------------------------

def check_config() -> tuple[bool, str]:
    cfg = _load(CONFIG_FILE, {})
    if not cfg:
        return False, "email_intake_config.json missing/unreadable"
    if not cfg.get("forwarding_live"):
        return False, "config forwarding_live is not true"
    if not cfg.get("alias_verified"):
        return False, "config alias_verified is not true"
    return True, "config ok (forwarding_live + alias_verified)"


def check_intake_freshness() -> tuple[bool, str]:
    """Confirm the tulsagays-email-intake task actually ran recently."""
    if not RUNNER_LOG.exists():
        return False, f"runner.log not found at {RUNNER_LOG}"
    last = None
    try:
        for line in RUNNER_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            if "tulsagays-email-intake" in line:
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if m:
                    last = m.group(1)
    except Exception as e:
        return False, f"could not read runner.log: {e}"
    if not last:
        return False, "no tulsagays-email-intake run found in runner.log"
    try:
        # runner.log stamps are LOCAL time; compare loosely against local now.
        dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        age_h = (datetime.now() - dt).total_seconds() / 3600.0
    except Exception:
        return True, f"last run {last} (unparsed age)"
    if age_h > INTAKE_FRESH_HOURS:
        return False, f"intake task stale: last ran {last} ({age_h:.1f}h ago > {INTAKE_FRESH_HOURS}h)"
    return True, f"intake task fresh: last ran {last} ({age_h:.1f}h ago)"


def _imap():
    """Reuse the intake module's authenticated IMAP connection."""
    from scraper.email_tips import _imap_connect  # noqa: E402
    return _imap_connect()


def check_imap_auth() -> tuple[bool, str]:
    try:
        conn = _imap()
    except Exception as e:
        return False, f"IMAP connect raised: {type(e).__name__}: {e}"
    if conn is None:
        return False, "IMAP auth failed (no token or bad credentials)"
    try:
        conn.logout()
    except Exception:
        pass
    return True, "IMAP auth ok"


def _search_token(token: str) -> list[str]:
    """Return Message-IDs of messages whose subject contains the token.

    Searches "[Gmail]/All Mail", not INBOX (fixed 2026-09-03, G499/G500/G637):
    a Gmail filter on the forwarded events@tulsagays.com mail skips the inbox
    (archives on arrival, marks read) -- confirmed via X-GM-LABELS on the two
    canaries this checker had wrongly flagged as "never arrived". The real
    intake scanner (scraper/email_tips.py collect()) already searches All Mail
    for exactly this reason; this checker hadn't matched it, so every canary
    was a guaranteed false FORWARD CHAIN BROKEN alert regardless of pipeline
    health. Real event submissions were never affected -- only this checker.
    """
    conn = _imap()
    if conn is None:
        raise RuntimeError("IMAP unavailable")
    found = []
    try:
        conn.select('"[Gmail]/All Mail"')
        typ, data = conn.search(None, "SUBJECT", f'"{token}"')
        if typ == "OK" and data and data[0]:
            for num in data[0].split():
                typ2, msg = conn.fetch(num, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
                if typ2 == "OK" and msg and msg[0]:
                    raw = msg[0][1].decode("utf-8", "replace") if isinstance(msg[0][1], bytes) else str(msg[0][1])
                    m = re.search(r"Message-ID:\s*(<[^>]+>)", raw, re.I)
                    found.append(m.group(1) if m else f"num:{num.decode()}")
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return found


def _mark_seen_in_intake(msg_ids: list[str]) -> None:
    """Append canary Message-IDs to the intake seen-list so it never queues them."""
    if not msg_ids:
        return
    st = _load(INTAKE_STATE, {"seen_message_ids": []})
    seen = st.get("seen_message_ids", [])
    for mid in msg_ids:
        if mid and mid not in seen:
            seen.append(mid)
    st["seen_message_ids"] = seen[-2000:]
    try:
        INTAKE_STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[intake-health] WARN could not update intake seen-list: {e}")


def _send_canary(token: str) -> tuple[bool, str]:
    from tools.brevo_send import send  # noqa: E402
    subject = f"[TG-CANARY {token}] intake pipeline health check"
    body = (
        "This is an automated delivery test for the TulsaGays event intake "
        "pipeline. No action needed and nothing to publish. If you are a human "
        "reading this, it just confirms events@tulsagays.com is reaching the "
        f"inbox. Token: {token}"
    )
    return send(INTAKE_ADDR, subject, body)


# ---- main flow -------------------------------------------------------------

def run(no_send: bool = False) -> dict:
    state = _load(STATE_FILE, {"pending": [], "history": []})
    pending = state.get("pending", [])
    failures: list[str] = []
    notes: list[str] = []

    ok, msg = check_imap_auth()
    notes.append(("PASS " if ok else "FAIL ") + msg)
    imap_ok = ok
    if not ok:
        failures.append(msg)

    ok, msg = check_config()
    notes.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)

    ok, msg = check_intake_freshness()
    notes.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)

    # 1) Verify prior pending canaries (latency-tolerant).
    still_pending = []
    if imap_ok:
        for c in pending:
            try:
                hits = _search_token(c["token"])
            except Exception as e:
                notes.append(f"WARN pending search error: {e}")
                still_pending.append(c)
                continue
            if hits:
                _mark_seen_in_intake(hits)
                notes.append(f"PASS pending canary {c['token']} arrived (chain OK)")
            else:
                sent = datetime.fromisoformat(c["sent_ts"])
                age_h = (_now() - sent).total_seconds() / 3600.0
                if age_h > CANARY_SLA_HOURS:
                    failures.append(
                        f"canary {c['token']} sent {c['sent_ts']} never arrived "
                        f"({age_h:.1f}h > {CANARY_SLA_HOURS}h) -> FORWARD CHAIN BROKEN")
                else:
                    still_pending.append(c)
    else:
        still_pending = pending  # can't verify without IMAP

    # 2) Send a fresh canary and try to confirm in-run.
    if not no_send and imap_ok:
        token = "TGH" + uuid.uuid4().hex[:12].upper()
        sent_ok, detail = _send_canary(token)
        if not sent_ok:
            failures.append(f"canary SEND failed: {detail}")
        else:
            sent_ts = _now().isoformat()
            confirmed = False
            deadline = time.time() + INRUN_POLL_SECONDS
            while time.time() < deadline:
                time.sleep(INRUN_POLL_EVERY)
                try:
                    hits = _search_token(token)
                except Exception:
                    hits = []
                if hits:
                    _mark_seen_in_intake(hits)
                    confirmed = True
                    notes.append(f"PASS canary {token} round-trip confirmed in-run (chain OK)")
                    break
            if not confirmed:
                still_pending.append({"token": token, "sent_ts": sent_ts})
                notes.append(f"INFO canary {token} sent, not yet arrived; will confirm next run")
    elif no_send:
        notes.append("INFO --no-send: skipped sending a new canary")

    state["pending"] = still_pending
    result = "FAIL" if failures else "PASS"
    entry = {"ts": _now().isoformat(), "result": result,
             "failures": failures, "pending": len(still_pending)}
    state["history"] = (state.get("history", []) + [entry])[-50:]
    state["last_result"] = result
    _save_state(state)

    notes.append("REMINDER " + AUTO_REPLY_NOTE)
    return {"result": result, "failures": failures, "notes": notes,
            "pending": len(still_pending)}


def _log_task_run(result: str, note: str) -> None:
    try:
        subprocess.run([sys.executable, str(LOG_TASK_RUN), TASK_NAME, result,
                        "--note", note[:300]], timeout=30)
    except Exception as e:
        print(f"[intake-health] WARN log-task-run failed: {e}")


def _file_gap(failures: list[str]) -> None:
    detail = "Intake canary/health FAIL: " + "; ".join(failures[:5])
    try:
        subprocess.run([sys.executable, str(GAP_LEDGER), "add",
                        "--title", "events@tulsagays.com intake pipeline unhealthy",
                        "--detail", detail[:500],
                        "--severity", "high",
                        "--system", "tulsagays-intake",
                        "--impact", "Event submissions via events@ / IG DM auto-reply may be silently lost.",
                        "--fix", "python tulsagays/tools/check_intake_health.py ; check Namecheap forward, IMAP token, Brevo key."],
                       timeout=30)
    except Exception as e:
        print(f"[intake-health] WARN gap_ledger add failed: {e}")


def _selftest() -> int:
    """Offline: exercise config + freshness parsing + state IO, no network/send."""
    print("== selftest ==")
    ok, msg = check_config(); print("config:", ok, msg)
    ok, msg = check_intake_freshness(); print("freshness:", ok, msg)
    # state round-trip
    st = _load(STATE_FILE, {"pending": [], "history": []})
    assert isinstance(st.get("pending", []), list)
    # SLA math
    old = (_now() - timedelta(hours=CANARY_SLA_HOURS + 1)).isoformat()
    age = (_now() - datetime.fromisoformat(old)).total_seconds() / 3600.0
    assert age > CANARY_SLA_HOURS
    print(f"SLA math ok (aged {age:.1f}h > {CANARY_SLA_HOURS}h)")
    print("selftest PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true",
                    help="run read-only checks + verify pending only; do not send a new canary")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    out = run(no_send=args.no_send)
    for n in out["notes"]:
        print(n)
    print(f"\n== RESULT: {out['result']}  (pending canaries: {out['pending']}) ==")
    note = " | ".join(out["failures"]) if out["failures"] else \
        f"chain healthy; {out['pending']} canary pending confirm"
    _log_task_run(out["result"], note)
    if out["result"] == "FAIL":
        _file_gap(out["failures"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
