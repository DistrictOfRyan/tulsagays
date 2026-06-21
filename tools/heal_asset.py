#!/usr/bin/env python3
"""
heal_asset.py — self-healing regeneration for LIVE-served brand assets.

Ceiling rung (2026-06-20): the graphic QA gate (graphic_qa.py) can DETECT a
broken/tofu/drifted live asset, but detection alone still leaves a broken image
on the feed until a human reacts. The 2026-06-20 incident root cause was exactly
that gap: a regenerable asset (docs/assets/weekend-preview-bg.png) was broken on
the live URL and nothing rebuilt it automatically.

This module closes the loop. Every regenerable live asset is mapped to the
generator that produces it cleanly. `heal(rel_path)` runs that generator, then
re-runs the QA gate, and reports whether the asset is now clean. The nightly
live_asset_guard calls this BEFORE alerting, so a broken asset auto-repairs and
only escalates to William if the regenerator itself cannot produce a clean image.

A heal NEVER ships a worse asset: the generators each self-verify (tofu gate)
before replacing the file, and heal() re-QAs the result. If regen fails, the
prior file is left untouched and heal returns healed=False.

Run:  python tools/heal_asset.py [--dry-run] [REL_PATH ...]
      python tools/heal_asset.py --selftest
"""
from __future__ import annotations

import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import graphic_qa  # noqa: E402

PY = sys.executable or "python"

# Each regenerable LIVE asset -> the generator script that rebuilds it cleanly.
# The generator MUST self-verify (tofu/QA gate) before replacing the file.
HEALERS = {
    "docs/assets/weekend-preview-bg.png": ["tools/gen_weekend_preview_bg.py"],
    "docs/images/og-event.png":          ["tools/gen_og_event_image.py"],
}


def _abs(rel: str) -> str:
    return os.path.join(ROOT, rel.replace("/", os.sep))


def heal(rel_path: str, dry_run: bool = False) -> dict:
    """Regenerate one asset and re-QA it.

    Returns {rel, regenerable, ran, healed, reason}.
    healed=True  -> file now passes graphic QA (either it already did, or regen fixed it)
    healed=False -> still broken (no healer, regen failed, or regen produced bad output)
    """
    rel_path = rel_path.replace("\\", "/")
    cmd = HEALERS.get(rel_path)
    if not cmd:
        return {"rel": rel_path, "regenerable": False, "ran": False,
                "healed": False, "reason": "no registered healer for this asset"}

    if dry_run:
        return {"rel": rel_path, "regenerable": True, "ran": False,
                "healed": False, "reason": f"would run: {' '.join(cmd)}"}

    script = _abs(cmd[0])
    if not os.path.exists(script):
        return {"rel": rel_path, "regenerable": True, "ran": False,
                "healed": False, "reason": f"healer script missing: {cmd[0]}"}

    try:
        proc = subprocess.run([PY, script, *cmd[1:]], cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
    except Exception as e:
        return {"rel": rel_path, "regenerable": True, "ran": False,
                "healed": False, "reason": f"healer crashed: {e}"}

    # Re-QA the (possibly) regenerated file — the source of truth, not the exit code.
    target = _abs(rel_path)
    v = graphic_qa.qa_image(target)
    healed = bool(v["ok"]) and proc.returncode == 0
    reason = ("regenerated clean" if healed
              else f"regen rc={proc.returncode}; qa={v['reason']}; "
                   f"stderr={(proc.stderr or '').strip()[:160]}")
    return {"rel": rel_path, "regenerable": True, "ran": True,
            "healed": healed, "reason": reason}


def heal_all(rels=None, dry_run: bool = False) -> list[dict]:
    rels = rels or list(HEALERS.keys())
    return [heal(r, dry_run=dry_run) for r in rels]


def _selftest() -> int:
    """Break the live weekend asset, heal it, prove it comes back clean."""
    import shutil
    rel = "docs/assets/weekend-preview-bg.png"
    target = _abs(rel)
    if not os.path.exists(target):
        print("[selftest] SKIP — live asset not present yet")
        return 0

    backup = target + ".heal_selftest.bak"
    shutil.copy2(target, backup)
    try:
        # 1) A clean asset heals to clean (idempotent — regen still passes QA).
        r = heal(rel)
        ok1 = r["healed"]
        print(f"[selftest] heal clean asset -> {'OK' if ok1 else 'FAIL'} ({r['reason']})")

        # 2) Corrupt the live asset to a blank canvas (fails QA), then heal it.
        from PIL import Image
        Image.new("RGB", (1080, 1080), (10, 10, 10)).save(target)
        broken = graphic_qa.qa_image(target)
        ok2a = not broken["ok"]
        print(f"[selftest] corrupted asset fails QA -> {'OK' if ok2a else 'FAIL'} ({broken['reason']})")
        r2 = heal(rel)
        after = graphic_qa.qa_image(target)
        ok2b = r2["healed"] and after["ok"]
        print(f"[selftest] heal corrupted asset -> {'OK' if ok2b else 'FAIL'} ({r2['reason']})")

        # 3) Unknown asset is reported non-regenerable (not a crash).
        r3 = heal("docs/does-not-exist.png")
        ok3 = (not r3["regenerable"]) and (not r3["healed"])
        print(f"[selftest] unknown asset -> {'OK' if ok3 else 'FAIL'} ({r3['reason']})")

        allok = ok1 and ok2a and ok2b and ok3
        print(f"[selftest] {'ALL PASS' if allok else 'FAILURES'}")
        return 0 if allok else 1
    finally:
        shutil.move(backup, target)  # always restore the real asset


def main(argv) -> int:
    if "--selftest" in argv:
        return _selftest()
    dry = "--dry-run" in argv
    rels = [a for a in argv if not a.startswith("--")] or None
    results = heal_all(rels, dry_run=dry)
    bad = 0
    for r in results:
        tag = "HEALED" if r["healed"] else ("DRY" if dry and r["regenerable"]
              else ("SKIP" if not r["regenerable"] else "FAIL"))
        if tag == "FAIL":
            bad += 1
        print(f"[{tag}] {r['rel']} — {r['reason']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
