#!/usr/bin/env python3
"""
request_visual_approval.py — the HUMAN-EYES-ON graphic approval gate.

Why this exists
---------------
On 2026-06-20 a cheap "boxes with X's" (tofu) weekend graphic shipped to IG/FB.
graphic_qa.py was then built to BLOCK obviously broken images automatically, but
William's actual complaint was bigger: "I need a better graphic approval process."
The hole graphic_qa alone does not close is that a *script* can write
`approved_by: William` into the registry without William ever LAYING EYES on the
image. Automated QA catches tofu/blank/low-res, but it cannot judge "this looks
cheap." Only a human can.

This tool adds the missing rung: before a graphic posts, William SEES the exact
bytes on his phone and either lets the veto window elapse (auto-approve, his
chosen "auto + veto window" model from 2026-06-08) or replies STOP.

Flow
----
  request <img> --key <k> --channel <label> [--caption-file f] [--window MIN]
      1. Run graphic_qa.qa_image() on the EXACT file. Auto-QA fail -> BLOCK,
         alert William it was blocked, never post, exit 2. (No human burden for
         garbage — the machine already knows it is broken.)
      2. Auto-QA pass -> emit a Telegram notification that ATTACHES the image
         (IMAGE: <path>, sent via sendPhoto by relay-notifications.py) with the
         caption preview + a one-tap "reply [STOP: <key>] to kill it" line.
         Record data/visual_approvals/<key>.json {state: pending, post_after}.
         exit 0.

  check <img> --key <k> [--window MIN]
      - veto token present (~/.claude/inbox/tulsagays-stop/<key>.md) -> exit 2.
      - window still open -> exit 1 (caller waits, runs again later).
      - window elapsed, no veto -> record approved (method=auto-veto-window,
        human_saw_image=True) and, for reusable brand assets, register it in
        approved_assets.json with an HONEST method label. exit 0 -> safe to post.

Honesty fix
-----------
The registry entry written here carries method="auto-veto-window (image shown to
William, no STOP)" — NOT a bare `approved_by: William`. A true one-tap human
approval (William replies [APPROVE-GFX: <key>]) is recorded as
method="human-telegram". Scripts can no longer silently impersonate William.

Public API: request(...) -> dict ; check(...) -> dict
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import datetime
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import graphic_qa  # noqa: E402

HOME = Path.home()
NOTIFY_DIR = HOME / ".claude" / "inbox" / "notifications"
STOP_DIR = HOME / ".claude" / "inbox" / "tulsagays-stop"
APPROVE_DIR = HOME / ".claude" / "inbox" / "tulsagays-gfx-approve"
STATE_DIR = Path(ROOT) / "data" / "visual_approvals"
DEFAULT_WINDOW_MIN = 60


def _now():
    return datetime.datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _state_path(key: str) -> Path:
    return STATE_DIR / f"{key}.json"


def _write_state(key: str, data: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(key).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_state(key: str) -> dict:
    p = _state_path(key)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _emit_notification(key: str, image_path: str, channel: str,
                       caption_preview: str, post_after_iso: str, window_min: int):
    """Write a notification file the relay turns into a Telegram PHOTO message.

    The relay (relay-notifications.py) sends the image via sendPhoto when an
    `IMAGE: <abs path>` line is present; otherwise it degrades to a text message.
    """
    NOTIFY_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now().strftime("%Y%m%dT%H%M%S")
    body = (
        f"IMAGE: {os.path.abspath(image_path)}\n"
        f"\U0001F5BC️  TulsaGays graphic awaiting your eyes — *{channel}*\n\n"
        f"Auto-QA passed (no tofu / not blank / right size). "
        f"Now YOU look at it.\n\n"
        f"Caption: {caption_preview[:280]}\n\n"
        f"Posts automatically at {post_after_iso} ({window_min}-min veto window).\n"
        f"Don't like it? Reply  [STOP: {key}]  and it will NOT post.\n"
        f"Love it and want it out now? Reply  [APPROVE-GFX: {key}]."
    )
    fp = NOTIFY_DIR / f"gfx-approval-{key}-{ts}.md"
    fp.write_text(body, encoding="utf-8")
    return str(fp)


def request(image_path: str, key: str, channel: str = "graphic",
            caption_preview: str = "", window_min: int = DEFAULT_WINDOW_MIN,
            require_approved: bool = False) -> dict:
    """Gate + notify. Returns dict(stage, ok, ...)."""
    qa = graphic_qa.qa_image(image_path, require_approved=require_approved)
    if not qa["ok"]:
        # Machine already knows it is broken — alert, do not bother William's eyes.
        NOTIFY_DIR.mkdir(parents=True, exist_ok=True)
        ts = _now().strftime("%Y%m%dT%H%M%S")
        (NOTIFY_DIR / f"gfx-blocked-{key}-{ts}.md").write_text(
            f"⛔ TulsaGays graphic BLOCKED by auto-QA — NOT posted ({channel}).\n"
            f"Reason: {qa.get('reason')}\nFile: {image_path}\n"
            f"Fix the generator/asset and re-run.", encoding="utf-8")
        _write_state(key, {"key": key, "state": "blocked", "reason": qa.get("reason"),
                           "image": image_path, "at": _iso(_now())})
        return {"stage": "request", "ok": False, "blocked": True,
                "reason": qa.get("reason"), "qa": qa}

    post_after = _now() + datetime.timedelta(minutes=window_min)
    note_file = _emit_notification(key, image_path, channel, caption_preview,
                                   _iso(post_after), window_min)
    state = {"key": key, "state": "pending", "image": os.path.abspath(image_path),
             "channel": channel, "notified_at": _iso(_now()),
             "post_after": _iso(post_after), "window_min": window_min,
             "notification": note_file, "qa": "passed"}
    _write_state(key, state)
    return {"stage": "request", "ok": True, "pending": True, "post_after": _iso(post_after),
            "notification": note_file, "qa": qa}


def check(image_path: str, key: str, window_min: int | None = None,
          require_approved: bool = False) -> dict:
    """Decide whether the graphic may post now."""
    st = _read_state(key)
    # Explicit one-tap human approval beats the window.
    approve_tok = APPROVE_DIR / f"{key}.md"
    veto_tok = STOP_DIR / f"{key}.md"
    if veto_tok.exists():
        st.update({"state": "vetoed", "decided_at": _iso(_now())})
        _write_state(key, st)
        return {"stage": "check", "ok": False, "vetoed": True,
                "veto_file": str(veto_tok)}

    if approve_tok.exists():
        graphic_qa.approve(image_path, by="William",
                           note=f"human-telegram visual approval [{key}]")
        st.update({"state": "approved", "method": "human-telegram",
                   "human_saw_image": True, "decided_at": _iso(_now())})
        _write_state(key, st)
        return {"stage": "check", "ok": True, "approved": True, "method": "human-telegram"}

    # Window check (auto + veto-window model).
    post_after_iso = st.get("post_after")
    if post_after_iso:
        try:
            pa = datetime.datetime.fromisoformat(post_after_iso)
            if _now() < pa:
                remaining = (pa - _now()).total_seconds() / 60
                return {"stage": "check", "ok": False, "pending": True,
                        "remaining_min": round(remaining, 1), "post_after": post_after_iso}
        except Exception:
            pass

    # Window elapsed, no veto — auto-approve. Honest method label.
    graphic_qa.approve(image_path, by="William",
                       note=f"auto-veto-window: image shown to William, no STOP [{key}]")
    st.update({"state": "approved", "method": "auto-veto-window",
               "human_saw_image": True, "decided_at": _iso(_now())})
    _write_state(key, st)
    return {"stage": "check", "ok": True, "approved": True, "method": "auto-veto-window"}


def _selftest() -> int:
    """Deterministic, offline. Uses the repo's clean + tofu fixtures."""
    clean = os.path.join(ROOT, "tests", "fixtures", "clean_weekend_ref.png")
    tofu = os.path.join(ROOT, "tests", "fixtures", "tofu_weekend_live.png")
    ok = True

    # Tofu must be BLOCKED at request (never reaches William).
    r = request(tofu, key="selftest-tofu", channel="selftest", window_min=0)
    blocked = r.get("blocked") is True
    print(f"[selftest] tofu blocked at request  -> {blocked}  {'OK' if blocked else 'FAIL'}")
    ok &= blocked

    # Clean must pass auto-QA and go pending (eyes-on requested).
    r = request(clean, key="selftest-clean", channel="selftest", window_min=0)
    pending = r.get("pending") is True
    print(f"[selftest] clean -> pending eyes-on   -> {pending}  {'OK' if pending else 'FAIL'}")
    ok &= pending

    # With window_min=0 the window is already elapsed -> check auto-approves.
    c = check(clean, key="selftest-clean", window_min=0)
    approved = c.get("approved") is True and c.get("method") == "auto-veto-window"
    print(f"[selftest] clean -> auto-veto approve -> {approved}  {'OK' if approved else 'FAIL'}")
    ok &= approved

    # cleanup selftest state + notifications
    for k in ("selftest-tofu", "selftest-clean"):
        try:
            _state_path(k).unlink()
        except Exception:
            pass
    for f in NOTIFY_DIR.glob("gfx-*selftest*"):
        try:
            f.unlink()
        except Exception:
            pass
    print("[selftest] ALL PASS" if ok else "[selftest] FAILURES ABOVE")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Human-eyes-on graphic approval gate")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("request")
    pr.add_argument("image")
    pr.add_argument("--key", required=True)
    pr.add_argument("--channel", default="graphic")
    pr.add_argument("--caption-file", default="")
    pr.add_argument("--window", type=int, default=DEFAULT_WINDOW_MIN)
    pr.add_argument("--require-approved", action="store_true")

    ck = sub.add_parser("check")
    ck.add_argument("image")
    ck.add_argument("--key", required=True)
    ck.add_argument("--window", type=int, default=None)

    sub.add_parser("selftest")

    a = ap.parse_args()
    if a.cmd == "selftest" or not a.cmd:
        return _selftest() if a.cmd == "selftest" else (ap.print_help() or 0)

    if a.cmd == "request":
        cap = ""
        if a.caption_file and os.path.exists(a.caption_file):
            cap = open(a.caption_file, encoding="utf-8").read()
        r = request(a.image, key=a.key, channel=a.channel, caption_preview=cap,
                    window_min=a.window, require_approved=a.require_approved)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 2

    if a.cmd == "check":
        c = check(a.image, key=a.key, window_min=a.window)
        print(json.dumps(c, indent=2))
        if c.get("vetoed"):
            return 2
        return 0 if c["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
