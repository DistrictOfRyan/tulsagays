#!/usr/bin/env python3
"""
graphic_contact_sheet.py — one-image visual approval sheet for a week's graphics.

Ceiling rung (2026-06-20): William's complaint was that a "cheap, poorly done"
graphic shipped. The QA gate catches the mechanical failures (tofu/blank/res),
but TASTE ("this looks cheap") needs a human eye. The old approval flow asked him
to sign off without reliably showing every image. This builds a single contact
sheet montaging every graphic queued to post — each tile labeled with its QA
verdict — so the approval request carries a real visual, not a blind yes/no.

Tiles are bordered GREEN (passes automated QA) or RED (would be blocked), so the
eye goes straight to anything wrong before it ever reaches a feed.

Run:  python tools/graphic_contact_sheet.py --week 2026-W25
      python tools/graphic_contact_sheet.py --dir data/posts/2026-W25
      python tools/graphic_contact_sheet.py --selftest
"""
from __future__ import annotations

import os
import sys
import glob
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PIL import Image, ImageDraw  # noqa: E402
import graphic_qa  # noqa: E402

try:
    from content.image_maker import _font  # reuse the project font loader
except Exception:  # pragma: no cover - fallback if import path differs
    def _font(_name, size):
        from PIL import ImageFont
        return ImageFont.load_default()

TILE = 360          # rendered thumbnail edge
PAD = 18            # gap between tiles
LABEL_H = 34        # caption strip under each tile
COLS = 3
BG = (16, 16, 18)
GREEN = (46, 204, 113)
RED = (231, 76, 60)
WHITE = (240, 240, 240)

# Graphics we never want on the sheet (diagnostics, references, backups).
SKIP_SUBSTRINGS = ("_diag", ".bak", ".tmp", "contact_sheet", "_ref", "fixture")


def _candidate_images(d: str) -> list[str]:
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.png")) +
                    glob.glob(os.path.join(d, "*.jpg"))):
        low = os.path.basename(p).lower()
        if any(s in low for s in SKIP_SUBSTRINGS):
            continue
        out.append(p)
    return out


def build_sheet(image_dir: str, out_path: str | None = None) -> dict:
    imgs = _candidate_images(image_dir)
    if not imgs:
        return {"ok": False, "reason": f"no graphics found in {image_dir}", "out": None,
                "count": 0, "failing": []}

    rows = (len(imgs) + COLS - 1) // COLS
    cell_w = TILE + PAD
    cell_h = TILE + LABEL_H + PAD
    header_h = 64
    W = PAD + COLS * cell_w
    H = header_h + PAD + rows * cell_h
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)

    f_head = _font("segoe-bold", 30)
    f_cap = _font("segoe-bold", 16)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    d.text((PAD, 18), f"TulsaGays graphic approval — {os.path.basename(image_dir)} — {stamp}",
           font=f_head, fill=WHITE)

    failing = []
    for i, p in enumerate(imgs):
        r, c = divmod(i, COLS)
        x = PAD + c * cell_w
        y = header_h + PAD + r * cell_h

        verdict = graphic_qa.qa_image(p)
        color = GREEN if verdict["ok"] else RED
        if not verdict["ok"]:
            failing.append({"file": os.path.basename(p), "reason": verdict["reason"]})

        try:
            thumb = Image.open(p).convert("RGB")
            thumb.thumbnail((TILE, TILE))
        except Exception:
            thumb = Image.new("RGB", (TILE, TILE), (60, 0, 0))
        tx = x + (TILE - thumb.width) // 2
        ty = y + (TILE - thumb.height) // 2
        sheet.paste(thumb, (tx, ty))
        # status border
        d.rectangle([x - 3, y - 3, x + TILE + 2, y + TILE + 2], outline=color, width=4)
        # caption
        name = os.path.basename(p)
        if len(name) > 30:
            name = name[:27] + "..."
        d.text((x, y + TILE + 8), ("PASS  " if verdict["ok"] else "BLOCK ") + name,
               font=f_cap, fill=color)

    if out_path is None:
        out_path = os.path.join(image_dir, "_APPROVAL_contact_sheet.png")
    sheet.save(out_path)
    return {"ok": True, "out": out_path, "count": len(imgs),
            "failing": failing,
            "reason": (f"{len(imgs)} graphics, {len(failing)} would be BLOCKED"
                       if failing else f"{len(imgs)} graphics, all pass automated QA")}


def _selftest() -> int:
    import tempfile
    from PIL import Image as _I
    d = tempfile.mkdtemp(prefix="tg_sheet_")
    # one good (varied) tile, one blank (blocked) tile
    good = _I.new("RGB", (1080, 1080))
    for yy in range(1080):
        for xx in range(0, 1080, 4):
            good.putpixel((xx, yy), ((xx + yy) % 255, (xx * 2) % 255, (yy * 2) % 255))
    good.save(os.path.join(d, "good__01.png"))
    _I.new("RGB", (1080, 1080), (10, 10, 10)).save(os.path.join(d, "blank__02.png"))
    res = build_sheet(d)
    ok = (res["ok"] and res["count"] == 2 and len(res["failing"]) == 1
          and os.path.exists(res["out"]))
    print(f"[selftest] sheet built -> {'OK' if ok else 'FAIL'} ({res['reason']})")
    print(f"[selftest] flagged failing: {[f['file'] for f in res['failing']]}")
    print(f"[selftest] {'ALL PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv) -> int:
    if "--selftest" in argv:
        return _selftest()
    image_dir = None
    if "--dir" in argv:
        image_dir = argv[argv.index("--dir") + 1]
    elif "--week" in argv:
        image_dir = os.path.join(ROOT, "data", "posts", argv[argv.index("--week") + 1])
    if not image_dir:
        # default to the most recent week-post dir
        dirs = sorted(glob.glob(os.path.join(ROOT, "data", "posts", "*")),
                      key=os.path.getmtime, reverse=True)
        image_dir = dirs[0] if dirs else None
    if not image_dir or not os.path.isdir(image_dir):
        print(f"[ERROR] no image dir ({image_dir})")
        return 1
    res = build_sheet(image_dir)
    print(f"[sheet] {res['reason']}")
    if res["out"]:
        print(f"[sheet] wrote {res['out']}")
    for f in res["failing"]:
        print(f"   BLOCK  {f['file']} — {f['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
