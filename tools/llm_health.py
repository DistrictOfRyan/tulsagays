#!/usr/bin/env python3
"""Fail-loud health probe for the `claude -p` CLI LLM layer (gap G46).

Root cause of G46: a `claude -p` DEFAULT-auth 401 silently killed EVERY
tulsagays CLI LLM layer at once — sanity_check_events, voice_pass,
final_deck_review, and description enrichment all just degraded to rule-based
copy, and nothing surfaced that the LLM was completely dead. The degrade is by
design (the deck must still ship), so the failure was invisible for days.

This tool turns that silent outage into a LOUD, detectable signal:
  * `probe()` runs a trivial round-trip through content.generator._call_claude_cli
    (which already does dual-token failover + strips the nested-session
    CLAUDE_CODE_* vars that cause the 401). It writes data/llm_health.json and
    returns ok/detail.
  * exit code is NON-ZERO when the LLM is unreachable, so any wrapping
    scheduled task (e.g. tulsagays-scraper-health) escalates instead of
    logging a false PASS.

Usage:
  python tools/llm_health.py --probe       # real probe; exit 1 if LLM down
  python tools/llm_health.py --status      # read last recorded health, no call
  python tools/llm_health.py --selftest    # logic test, no network
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEALTH_FILE = REPO_ROOT / "data" / "llm_health.json"

# The literal error prefixes generator treats as a failed (non-answer) response.
_ERR_PREFIXES = (
    "prompt is too long", "error:", "rate limit", "api error", "execution error",
    "credit balance", "unable to connect", "overloaded", "internal server error",
    "failed to authenticate", "invalid authentication", "401", "403",
)


def _load_generator_caller():
    sys.path.insert(0, str(REPO_ROOT))
    from content.generator import _call_claude_cli  # noqa: E402
    return _call_claude_cli


def probe(timeout: int = 60) -> dict:
    """Round-trip a 1-word prompt through the real CLI. Returns a health dict
    and persists it to data/llm_health.json."""
    caller = _load_generator_caller()
    out = ""
    detail = ""
    try:
        out = (caller("Reply with exactly the single word: pong",
                      "You are a health probe. Answer in one word.",
                      model="haiku", timeout=timeout) or "").strip()
    except Exception as e:  # pragma: no cover - defensive
        detail = f"probe raised: {e}"
    ok = bool(out) and not out.lower().startswith(_ERR_PREFIXES)
    if not ok and not detail:
        detail = f"empty/failed response: {out[:120]!r}" if out else "no response from any auth path"
    payload = {
        "auth_ok": ok,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": int(time.time()),
        "detail": (detail or f"pong received: {out[:40]!r}")[:200],
    }
    try:
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HEALTH_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
    except Exception:
        pass
    return payload


def read_status() -> dict:
    if HEALTH_FILE.exists():
        try:
            return json.load(open(HEALTH_FILE, encoding="utf-8"))
        except Exception:
            return {"auth_ok": None, "detail": "health file unreadable"}
    return {"auth_ok": None, "detail": "no health record yet"}


def is_auth_broken() -> bool:
    """True only when the last recorded probe explicitly failed."""
    return read_status().get("auth_ok") is False


def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS" if cond else "FAIL") + " " + msg)
        ok = ok and cond

    # Simulate the exact G46 outage: monkeypatch the generator caller to return
    # "" (all auth paths dead) and confirm probe records a LOUD down-state.
    sys.path.insert(0, str(REPO_ROOT))
    import content.generator as g
    orig = g._call_claude_cli
    try:
        g._call_claude_cli = lambda *a, **k: ""  # total auth failure
        # re-point our loader to the patched module function
        global _load_generator_caller
        _saved = _load_generator_caller
        _load_generator_caller = lambda: g._call_claude_cli
        p = probe(timeout=1)
        check(p["auth_ok"] is False, "outage -> auth_ok False (loud)")
        check(is_auth_broken() is True, "is_auth_broken() True during outage")

        g._call_claude_cli = lambda *a, **k: "pong"  # recovered
        _load_generator_caller = lambda: g._call_claude_cli
        p2 = probe(timeout=1)
        check(p2["auth_ok"] is True, "recovery -> auth_ok True")
        check(is_auth_broken() is False, "is_auth_broken() False after recovery")
        _load_generator_caller = _saved
    finally:
        g._call_claude_cli = orig

    print("SELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(_selftest())
    if "--status" in args:
        s = read_status()
        print(json.dumps(s, indent=1))
        sys.exit(0 if s.get("auth_ok") in (True, None) else 1)
    if "--probe" in args:
        idx = args.index("--timeout") if "--timeout" in args else -1
        to = int(args[idx + 1]) if idx >= 0 else 60
        s = probe(timeout=to)
        print(json.dumps(s, indent=1))
        if not s.get("auth_ok"):
            print("[LLM-DOWN] claude -p LLM layer is unreachable — tulsagays LLM "
                  "layers (sanity/voice/final-review/enrichment) are degrading to "
                  "rule-based copy. Fix auth before the next weekly prep.",
                  file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    print(__doc__)
    sys.exit(0)
