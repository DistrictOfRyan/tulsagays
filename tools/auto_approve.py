"""
Auto-approval gate for the Tulsa Gays weekly carousel.

William chose "auto + veto window" (2026-06-08): the weekly post must run
hands-off with ZERO buttons in the happy path. This tool replaces the manual
human-review gate with a preflight-gated auto-approval plus a Telegram veto
window.

Flow (split across the Monday 6:00am notify task and the 7:00am publish task
so the 60-minute window elapses between two short runs instead of one long
in-session sleep):

  notify   Run the preflight safety checks for the current week.
           - preflight FAILS -> exit 1. Caller (the Monday agent) Telegrams
             William the blocking reasons and does NOT post.
           - preflight PASSES -> write pending_autopost.json {week_key,
             notified_at, post_after}. Print a JSON summary (caption preview +
             cover slide path) the agent uses to build the veto Telegram. exit 0.

  approve  Run at/after post_after. Requires pending_autopost.json for the
           current week (proves preflight passed at notify time).
           - veto file present -> exit 2 (agent confirms cancellation).
           - no veto -> write approval_status.json {approved:true,...}. exit 0
             (agent proceeds to run post_weekly.py + elevate_blog + groups).

  status   Print the current gate state as JSON (for debugging / the agent).

Veto file: ~/.claude/inbox/tulsagays-stop/<week_key>.md
The Telegram relay creates it when William replies [STOP: <week_key>].

Safe to run repeatedly; all writes are idempotent.
"""
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

VETO_WINDOW_MIN = 60
VETO_DIR = Path.home() / ".claude" / "inbox" / "tulsagays-stop"


def _week_key():
    return config.current_week_key()


def _slides_dir(week_key):
    return ROOT / "data" / "posts" / week_key


def _pending_path(week_key):
    return _slides_dir(week_key) / "pending_autopost.json"


def _approval_path(week_key):
    return _slides_dir(week_key) / "approval_status.json"


def _veto_path(week_key):
    return VETO_DIR / f"{week_key}.md"


def _run_preflight(week_key):
    """Return (ok: bool, errors: list, warnings: list)."""
    try:
        from tools.preflight_post import run as pf_run
    except Exception:
        try:
            import preflight_post as _pf
            pf_run = _pf.run
        except Exception:
            return None, ["preflight_post module not importable"], []
    # Suppress preflight's own human report so this tool emits clean JSON on
    # stdout; we read the structured result back from preflight_status.json.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        ok = pf_run(week_key)
    # preflight writes preflight_status.json in the week dir; read reasons back
    errors, warnings = [], []
    status_p = _slides_dir(week_key) / "preflight_status.json"
    if status_p.exists():
        try:
            s = json.loads(status_p.read_text(encoding="utf-8"))
            errors = s.get("errors", [])
            warnings = s.get("warnings", [])
        except Exception:
            pass
    return bool(ok), errors, warnings


_HARNESS_MARKERS = [
    "SUPERVISOR_TASK_COMPLETE", "SUPERVISOR:", "TASK_COMPLETE",
    "system-reminder", "</system-reminder>", "<commentary>",
]


def _sanitize_caption(week_key):
    """Scrub leaked harness/agent markers from the week's caption BEFORE the
    preflight gate sees it. The Monday post is a claude-tier task that is itself
    instructed to emit SUPERVISOR_TASK_COMPLETE, so that marker periodically
    leaks into all_post.json. preflight hard-blocks on it (correctly), which
    would silently kill the auto-post. Stripping it here makes the pipeline
    self-healing. Returns True if it changed the file.
    """
    import re
    post_json = _slides_dir(week_key) / "all_post.json"
    if not post_json.exists():
        return False
    try:
        data = json.loads(post_json.read_text(encoding="utf-8"))
    except Exception:
        return False
    cap = data.get("caption")
    if not isinstance(cap, str) or not cap:
        return False
    # Cut everything from the first trailing marker onward (matches post_weekly's
    # strip), then remove any stray marker substrings that remain.
    cleaned = re.split(
        r"\s*(?:SUPERVISOR_TASK_COMPLETE|SUPERVISOR:|TASK_COMPLETE)\b.*$",
        cap, flags=re.S)[0]
    for mk in _HARNESS_MARKERS:
        cleaned = cleaned.replace(mk, "")
    cleaned = cleaned.rstrip()
    if cleaned != cap:
        data["caption"] = cleaned
        post_json.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return True
    return False


def _caption_preview(week_key, limit=600):
    post_json = _slides_dir(week_key) / "all_post.json"
    if not post_json.exists():
        return ""
    try:
        data = json.loads(post_json.read_text(encoding="utf-8"))
    except Exception:
        return ""
    cap = ""
    if isinstance(data, dict):
        cap = data.get("caption") or data.get("post_text") or data.get("text") or ""
        if not cap and isinstance(data.get("slides"), list) and data["slides"]:
            cap = data["slides"][0].get("description", "")
    return cap[:limit]


def _cover_slide(week_key):
    d = _slides_dir(week_key)
    for pat in ("all__01.png", "weekday__01.png"):
        p = d / pat
        if p.exists():
            return str(p)
    pngs = sorted(d.glob("all__*.png")) or sorted(d.glob("weekday__*.png"))
    return str(pngs[0]) if pngs else ""


def cmd_notify():
    wk = _week_key()
    sd = _slides_dir(wk)
    if not sd.exists():
        print(json.dumps({"ok": False, "stage": "notify", "week_key": wk,
                          "error": f"no slides dir {sd} - generation did not run"}))
        return 1
    scrubbed = _sanitize_caption(wk)
    ok, errors, warnings = _run_preflight(wk)
    if not ok:
        print(json.dumps({"ok": False, "stage": "notify", "week_key": wk,
                          "preflight": "FAILED", "errors": errors,
                          "warnings": warnings}, indent=2))
        return 1
    now = datetime.now()
    pending = {
        "week_key": wk,
        "notified_at": now.isoformat(timespec="seconds"),
        "post_after": (now + timedelta(minutes=VETO_WINDOW_MIN)).isoformat(timespec="seconds"),
        "veto_instruction": f"[STOP: {wk}]",
        "preflight": "PASSED",
    }
    _pending_path(wk).write_text(json.dumps(pending, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True, "stage": "notify", "week_key": wk, "preflight": "PASSED",
        "post_after": pending["post_after"],
        "veto_instruction": pending["veto_instruction"],
        "veto_window_min": VETO_WINDOW_MIN,
        "caption_preview": _caption_preview(wk),
        "cover_slide": _cover_slide(wk),
        "warnings": warnings,
    }, indent=2))
    return 0


def cmd_approve(force_window=False):
    wk = _week_key()
    pending_p = _pending_path(wk)
    if not pending_p.exists():
        print(json.dumps({"ok": False, "stage": "approve", "week_key": wk,
                          "error": "no pending_autopost.json - notify stage did not "
                                   "pass preflight; refusing to approve"}))
        return 1
    pending = json.loads(pending_p.read_text(encoding="utf-8"))

    # Veto check
    vp = _veto_path(wk)
    if vp.exists():
        print(json.dumps({"ok": False, "stage": "approve", "week_key": wk,
                          "vetoed": True, "veto_file": str(vp),
                          "veto_content": vp.read_text(encoding="utf-8")[:200],
                          "action": "POST CANCELLED per William's STOP"}, indent=2))
        return 2

    # Window check (skip with force_window for same-minute manual runs)
    if not force_window:
        try:
            post_after = datetime.fromisoformat(pending["post_after"])
            if datetime.now() < post_after:
                remaining = (post_after - datetime.now()).total_seconds() / 60
                print(json.dumps({"ok": False, "stage": "approve", "week_key": wk,
                                  "error": f"veto window still open ({remaining:.1f} min "
                                           f"left until {pending['post_after']}); "
                                           f"run again after that, or pass --force"}))
                return 1
        except Exception:
            pass

    approval = {
        "approved": True,
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "approved_by": "auto-gate (preflight passed + veto window elapsed, no STOP)",
        "week_key": wk,
        "notified_at": pending.get("notified_at"),
    }
    _approval_path(wk).write_text(json.dumps(approval, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "stage": "approve", "week_key": wk,
                      "approved": True, "approval_file": str(_approval_path(wk)),
                      "action": "APPROVED - safe to run post_weekly.py"}, indent=2))
    return 0


def cmd_status():
    wk = _week_key()
    out = {
        "week_key": wk,
        "slides_dir_exists": _slides_dir(wk).exists(),
        "pending_exists": _pending_path(wk).exists(),
        "approval_exists": _approval_path(wk).exists(),
        "veto_exists": _veto_path(wk).exists(),
        "veto_dir": str(VETO_DIR),
    }
    if _approval_path(wk).exists():
        try:
            out["approval"] = json.loads(_approval_path(wk).read_text(encoding="utf-8"))
        except Exception:
            pass
    print(json.dumps(out, indent=2))
    return 0


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    force = "--force" in args
    if cmd == "notify":
        return cmd_notify()
    if cmd == "approve":
        return cmd_approve(force_window=force)
    if cmd == "status":
        return cmd_status()
    print(f"usage: python tools/auto_approve.py [notify|approve|status] [--force]\n"
          f"unknown command: {cmd}")
    return 64


if __name__ == "__main__":
    sys.exit(main())
