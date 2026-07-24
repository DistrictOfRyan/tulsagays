#!/usr/bin/env python3
"""
preflight_image.py — the LAST line of defense before any image is posted.

WHY THIS EXISTS
---------------
graphic_qa.py / detect_tofu.py existed for weeks but were wired into NOTHING.
The Saturday "This Weekend in Tulsa" task posted an Instagram image by handing
Meta a REMOTE URL (https://www.tulsagays.com/assets/weekend-preview-bg.png) and
never looked at the pixels. The live asset was a stale, cheap "boxes with X's"
(tofu) graphic, so it shipped blind on 2026-06-20.

This module makes that impossible. It gates BOTH:
  - a LOCAL file path, and
  - a REMOTE URL (it downloads the exact bytes Meta would fetch and QA's those).

Any caller that posts an image must run this first. social_lib.post_*_photo()
call it automatically, so every python posting path is gated by construction.

It returns a verdict and (on block) writes an alert to pending-william-actions
and the QA log. require_approved=True additionally enforces the human approval
registry (data/approved_assets.json) for reusable brand assets.

CLI
---
    python tools/preflight_image.py <url-or-path> [<url-or-path> ...]
    python tools/preflight_image.py --require-approved <url-or-path> ...
    python tools/preflight_image.py --selftest
Exit 0 = every image is safe to post. Exit 1 = at least one BLOCKED.

Public API
----------
    preflight(src, require_approved=False, alert=True) -> dict(ok, reason, ...)
    assert_postable(src, require_approved=False)  # raises RuntimeError on block
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import datetime
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import graphic_qa  # noqa: E402

PENDING = r"C:\Users\willi\.claude\pending-william-actions.md"
ALERT_LOG = os.path.join(ROOT, "data", "image_preflight_alerts.json")


def _is_url(src: str) -> bool:
    return src.lower().startswith(("http://", "https://"))


def _download(url: str) -> str:
    """Fetch the exact bytes Meta would fetch; return a local temp path."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TulsaGays-preflight)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    suffix = os.path.splitext(url.split("?")[0])[1] or ".img"
    fd, path = tempfile.mkstemp(prefix="tg_preflight_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


_NO_ALERT_SIGNALS = ("tests/fixtures", "tests\\fixtures", "_diag_", "selftest",
                     "tofu_weekend_live", "clean_weekend_ref")


def _alert(src: str, reason: str) -> None:
    """Record a BLOCK so William sees it and it isn't silent.

    Selftests / regression runs gate KNOWN-BAD fixtures on purpose; those must
    NOT spam the Action Inbox (they did on 2026-06-21 — 19 false 'BLOCKED'
    entries). Skip alerting when the source is a test fixture / diagnostic image,
    or when TULSAGAYS_QA_SILENT is set. Real production sources still alert."""
    low = str(src).lower()
    if os.environ.get("TULSAGAYS_QA_SILENT") or any(s in low for s in _NO_ALERT_SIGNALS):
        return
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(
                f"\n## [{stamp}] TulsaGays graphic BLOCKED before posting\n"
                f"- Source: {src}\n"
                f"- Reason: {reason}\n"
                f"- The post was STOPPED by the image preflight gate (no cheap/broken graphic went out).\n"
                f"- Fix the asset, then re-run the task.\n"
            )
    except Exception:
        pass
    try:
        log = []
        if os.path.exists(ALERT_LOG):
            log = json.load(open(ALERT_LOG, encoding="utf-8"))
        log.append({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "src": src, "reason": reason})
        os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)
        json.dump(log[-200:], open(ALERT_LOG, "w", encoding="utf-8"), indent=2)
    except Exception:
        pass


def preflight(src: str, require_approved: bool = False, alert: bool = True) -> dict:
    """QA one image (local path or remote URL) before it can be posted."""
    tmp = None
    local = src
    try:
        if _is_url(src):
            try:
                local = tmp = _download(src)
            except Exception as e:
                verdict = {"ok": False, "src": src, "reason": f"could not download image to QA it: {e}"}
                if alert:
                    _alert(src, verdict["reason"])
                return verdict
        r = graphic_qa.qa_image(local, require_approved=require_approved,
                                 approval_key=(src if _is_url(src) else None))
        verdict = {"ok": r["ok"], "src": src, "reason": r["reason"], "checks": r.get("checks", {})}
        if not r["ok"] and alert:
            _alert(src, r["reason"])
        return verdict
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def assert_postable(src: str, require_approved: bool = False) -> dict:
    """Raise RuntimeError if the image must not post. Use to guard publishers."""
    v = preflight(src, require_approved=require_approved)
    if not v["ok"]:
        raise RuntimeError(
            f"IMAGE PREFLIGHT BLOCKED — refusing to post {src}: {v['reason']}"
        )
    return v


def gate_images(srcs, require_approved: bool = False) -> None:
    """Gate a list of image paths/URLs before posting.

    Raises RuntimeError on the FIRST real block (tofu / blank / broken /
    under-resolution). Callers MUST let it propagate so the post aborts. This is
    the single chokepoint every low-level posting primitive routes through, so a
    cheap "boxes with X's" graphic cannot ship no matter which path posts it.
    """
    for s in srcs:
        assert_postable(str(s), require_approved=require_approved)


def _selftest() -> int:
    fx = os.path.join(ROOT, "tests", "fixtures")
    bad = os.path.join(fx, "tofu_weekend_live.png")
    good = os.path.join(fx, "clean_weekend_ref.png")
    ok = True
    if os.path.exists(bad):
        v = preflight(bad, alert=False)
        print(f"[selftest] KNOWN-BAD tofu_weekend_live.png -> "
              f"{'BLOCK OK' if not v['ok'] else 'PASS FAIL'} ({v['reason']})")
        ok = ok and (not v["ok"])
    if os.path.exists(good):
        v = preflight(good, alert=False)
        print(f"[selftest] KNOWN-GOOD clean_weekend_ref.png -> "
              f"{'PASS OK' if v['ok'] else 'BLOCK FAIL'} ({v['reason']})")
        ok = ok and v["ok"]
    # assert_postable must raise on the bad one
    raised = False
    try:
        assert_postable(bad)
    except RuntimeError:
        raised = True
    print(f"[selftest] assert_postable raises on tofu -> {'OK' if raised else 'FAIL'}")
    ok = ok and raised
    print("[selftest]", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    require_approved = "--require-approved" in argv
    srcs = [a for a in argv if not a.startswith("--")]
    if not srcs:
        print(__doc__.strip())
        return 2
    all_ok = True
    for s in srcs:
        v = preflight(s, require_approved=require_approved)
        print(f"[{'PASS' if v['ok'] else 'BLOCK'}] {s}: {v['reason']}")
        all_ok = all_ok and v["ok"]
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
