#!/usr/bin/env python3
"""
graphic_qa.py — the TulsaGays graphic approval gate.

Every image that any task is about to POST must pass through here first. It is
the control that would have stopped the cheap "boxes with X's" weekend graphic
from ever going out. Two layers:

  1. AUTOMATED QA (always runs, free, deterministic):
       - tofu / .notdef missing-glyph boxes   (tools/detect_tofu.py)
       - blank / single-color / near-empty canvas
       - too-small resolution for the target platform
       - extreme aspect ratio (broken crop)
     Any failure => BLOCK.

  2. HUMAN APPROVAL REGISTRY (for reusable brand assets):
       data/approved_assets.json records sha256 + who/when for each asset that
       William has visually signed off on. A reusable asset (e.g.
       docs/assets/weekend-preview-bg.png) must be REGISTERED to post. If the
       file changes, its hash changes and it must be re-approved. The old broken
       asset was never approved, so this layer alone would have blocked it.

CLI
---
    python tools/graphic_qa.py <img> [<img> ...]            # gate: exit 1 on block
    python tools/graphic_qa.py --require-approved <img>...  # also enforce registry
    python tools/graphic_qa.py approve <img> [--by William --note "..."]
    python tools/graphic_qa.py list
    python tools/graphic_qa.py --selftest

Public API:
    qa_image(path, require_approved=False) -> dict(ok: bool, checks: {...}, reason)
    gate(paths, require_approved=False)    -> (ok: bool, results: [dict])
    is_approved(path) -> bool ; approve(path, by, note) -> dict
"""
from __future__ import annotations
import os
import sys
import json
import hashlib
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PIL import Image  # noqa: E402
import detect_tofu  # noqa: E402

REGISTRY = os.path.join(ROOT, "data", "approved_assets.json")
QA_LOG = os.path.join(ROOT, "data", "graphic_qa_log.json")

MIN_EDGE = 600          # px — IG/FB feed images should be >= 600 on the short side
MAX_ASPECT = 2.2        # width/height or height/width beyond this = broken crop


# ── helpers ──────────────────────────────────────────────────────────────────
def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    # Date.now() is unavailable in some sandboxes; datetime.now() is fine here.
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_registry() -> dict:
    if os.path.exists(REGISTRY):
        try:
            return json.load(open(REGISTRY, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_registry(reg: dict):
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), indent=2)


def _rel(path: str) -> str:
    try:
        return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")
    except Exception:
        return path


# ── approval registry ────────────────────────────────────────────────────────
def is_approved(path: str, approval_key: str | None = None) -> bool:
    """Check the approval registry. approval_key overrides the lookup key —
    needed when `path` is a downloaded temp file standing in for a remote URL
    (the registry is keyed by the URL/repo-relative path, not a Temp\\ path)."""
    reg = _load_registry()
    entry = reg.get(approval_key if approval_key is not None else _rel(path))
    if not entry:
        return False
    return entry.get("sha256") == _sha256(path)


def approve(path: str, by: str = "William", note: str = "") -> dict:
    reg = _load_registry()
    entry = {"sha256": _sha256(path), "approved_by": by,
             "approved_at": _now(), "note": note}
    reg[_rel(path)] = entry
    _save_registry(reg)
    return entry


# ── automated checks ─────────────────────────────────────────────────────────
def _check_blank(img) -> tuple[bool, str]:
    """True/ok if the image has visual content (not a single flat color)."""
    small = img.convert("RGB").resize((64, 64))
    colors = small.getcolors(maxcolors=64 * 64)
    if not colors:
        return True, "varied"
    dominant = max(c[0] for c in colors)
    if dominant / (64 * 64) > 0.985:
        return False, "near-single-color / blank canvas"
    return True, "varied"


def qa_image(path: str, require_approved: bool = False, approval_key: str | None = None) -> dict:
    checks: dict = {}
    if not os.path.exists(path):
        return {"ok": False, "path": path, "checks": {}, "reason": f"missing file: {path}"}

    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        return {"ok": False, "path": path, "checks": {}, "reason": f"unreadable: {e}"}

    W, Hh = img.size
    reasons = []

    # tofu
    tof = detect_tofu.scan_image(path)
    checks["tofu_clean"] = tof["clean"]
    if not tof["clean"]:
        reasons.append(f"TOFU: {tof['reason']}")

    # resolution
    short = min(W, Hh)
    checks["resolution_ok"] = short >= MIN_EDGE
    if short < MIN_EDGE:
        reasons.append(f"resolution {W}x{Hh} below {MIN_EDGE}px short edge")

    # aspect
    aspect = max(W / Hh, Hh / W)
    checks["aspect_ok"] = aspect <= MAX_ASPECT
    if aspect > MAX_ASPECT:
        reasons.append(f"aspect ratio {aspect:.2f} looks like a broken crop")

    # blank
    not_blank, blank_msg = _check_blank(img)
    checks["not_blank"] = not_blank
    if not not_blank:
        reasons.append(blank_msg)

    # human approval registry (only enforced when asked)
    if require_approved:
        appr = is_approved(path, approval_key=approval_key)
        checks["approved"] = appr
        if not appr:
            reasons.append("not in approved-assets registry (needs William's visual sign-off)")

    ok = len(reasons) == 0
    return {"ok": ok, "path": path, "checks": checks,
            "reason": "all graphic QA checks passed" if ok else " | ".join(reasons)}


def gate(paths, require_approved: bool = False):
    results = [qa_image(p, require_approved=require_approved) for p in paths]
    ok = all(r["ok"] for r in results)
    _log({"at": _now(), "ok": ok,
          "results": [{"path": _rel(r["path"]), "ok": r["ok"], "reason": r["reason"]}
                      for r in results]})
    return ok, results


def _log(entry: dict):
    log = []
    if os.path.exists(QA_LOG):
        try:
            log = json.load(open(QA_LOG, encoding="utf-8"))
        except Exception:
            log = []
    log.append(entry)
    json.dump(log[-200:], open(QA_LOG, "w", encoding="utf-8"), indent=2)


# ── selftest ─────────────────────────────────────────────────────────────────
def _selftest() -> int:
    bad = os.path.join(ROOT, "docs", "assets", "weekend-preview-bg.png")
    good_dir = os.path.join(ROOT, "data", "posts", "2026-W25")
    ok = True

    # The live asset (now regenerated) must pass automated QA.
    if os.path.exists(bad):
        r = qa_image(bad)
        print(f"[selftest] live weekend-preview-bg.png automated QA -> "
              f"{'PASS OK' if r['ok'] else 'BLOCK'} ({r['reason']})")
        ok = ok and r["ok"]
        # ...but must BLOCK when approval is required and it isn't registered yet
        r2 = qa_image(bad, require_approved=True)
        unregistered_blocks = (not r2["ok"]) or is_approved(bad)
        print(f"[selftest] approval-required gate behaves -> "
              f"{'OK' if unregistered_blocks else 'FAIL'} "
              f"(approved={is_approved(bad)})")
        ok = ok and unregistered_blocks

    # A known-good carousel slide passes.
    g = os.path.join(good_dir, "all__01.png")
    if os.path.exists(g):
        r = qa_image(g)
        print(f"[selftest] carousel all__01.png -> {'PASS OK' if r['ok'] else 'BLOCK FAIL'} ({r['reason']})")
        ok = ok and r["ok"]

    # A blank canvas must BLOCK.
    blank = Image.new("RGB", (1080, 1080), (10, 10, 10))
    tmp = os.path.join(good_dir, "_qa_blank_tmp.png")
    blank.save(tmp)
    r = qa_image(tmp)
    print(f"[selftest] blank canvas -> {'BLOCK OK' if not r['ok'] else 'PASS FAIL'} ({r['reason']})")
    ok = ok and (not r["ok"])
    os.remove(tmp)

    print("[selftest]", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    if argv[0] == "--selftest":
        return _selftest()
    if argv[0] == "approve":
        rest = argv[1:]
        by = "William"
        note = ""
        imgs = []
        i = 0
        while i < len(rest):
            if rest[i] == "--by":
                by = rest[i + 1]; i += 2
            elif rest[i] == "--note":
                note = rest[i + 1]; i += 2
            else:
                imgs.append(rest[i]); i += 1
        for p in imgs:
            e = approve(p, by=by, note=note)
            print(f"[approved] {_rel(p)} sha256={e['sha256'][:12]}… by {e['approved_by']}")
        return 0
    if argv[0] == "list":
        reg = _load_registry()
        if not reg:
            print("(no approved assets registered)")
        for k, v in reg.items():
            print(f"{k}\n    sha256={v['sha256'][:16]}…  by {v['approved_by']}  {v['approved_at']}  {v.get('note','')}")
        return 0

    require_approved = "--require-approved" in argv
    paths = [a for a in argv if not a.startswith("--")]
    ok, results = gate(paths, require_approved=require_approved)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'BLOCK'}] {os.path.basename(r['path'])}: {r['reason']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
