#!/usr/bin/env python3
"""
live_asset_guard.py — nightly drift/tofu watch on LIVE-served brand assets.

The 2026-06-20 incident: docs/assets/weekend-preview-bg.png was rebuilt clean
LOCALLY but never committed/deployed, so the LIVE url kept serving the old tofu
image — and the Saturday task posts straight from that live url. Local selftests
were green; the live bytes were broken. Nothing watched the live bytes.

This guard closes that blind spot. For each reusable asset that a posting task
fetches by URL, it downloads the LIVE bytes and:
  1. runs the graphic QA gate (tofu/blank/resolution), and
  2. checks the live sha256 against the human-approved registry hash (drift).
Any failure writes an alert to pending-william-actions.md and exits non-zero so
the scheduled runner logs FAIL.

Run:  python tools/live_asset_guard.py
"""
from __future__ import annotations

import os
import sys
import json
import hashlib
import datetime
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import graphic_qa  # noqa: E402

PENDING = r"C:\Users\willi\.claude\pending-william-actions.md"

# Reusable assets that a posting task fetches LIVE by URL → must stay clean.
# (local registry path, live url)
WATCHED = [
    ("docs/assets/weekend-preview-bg.png",
     "https://www.tulsagays.com/assets/weekend-preview-bg.png"),
]


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TulsaGays-guard)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    fd, path = tempfile.mkstemp(prefix="tg_guard_", suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path, hashlib.sha256(data).hexdigest()


def _alert(lines: list[str]) -> None:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(f"\n## [{stamp}] TulsaGays LIVE asset guard found a problem\n")
            for ln in lines:
                f.write(f"- {ln}\n")
    except Exception:
        pass


def main() -> int:
    reg = graphic_qa._load_registry()
    problems = []
    for rel, url in WATCHED:
        try:
            tmp, live_sha = _download(url)
        except Exception as e:
            problems.append(f"{url}: could not fetch live asset ({e})")
            continue
        try:
            v = graphic_qa.qa_image(tmp)
            if not v["ok"]:
                problems.append(f"{url}: LIVE bytes FAIL graphic QA — {v['reason']}")
            approved_sha = (reg.get(rel) or {}).get("sha256")
            if approved_sha and approved_sha != live_sha:
                problems.append(
                    f"{url}: LIVE bytes DRIFTED from the approved asset "
                    f"(live sha {live_sha[:12]}… != approved {approved_sha[:12]}…) "
                    f"— the deployed file is not the one William signed off on")
            tag = "OK" if v["ok"] and (not approved_sha or approved_sha == live_sha) else "PROBLEM"
            print(f"[{tag}] {url} — qa_ok={v['ok']} live_sha={live_sha[:12]}…")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
    if problems:
        _alert(problems)
        print("\n[GUARD] PROBLEMS:")
        for p in problems:
            print("   -", p)
        return 1
    print("\n[GUARD] all watched live assets are clean and match the approved registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
