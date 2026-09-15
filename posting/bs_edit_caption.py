"""Fix a published Page / Instagram caption in place through Meta Business Suite (2026-09-15).

Why. W37's live caption opened with a leaked model note ("HHHH is in this
week's list (event #5/#9), so it leads with full hype per the rules." + '---')
and dated Prime Timers "Mon 9/8" when 9/8/2026 was a Tuesday. Past-week posts
stay on the profile, so their text still has to be right. This edits only the
caption: it strips a leading note block that ends in a '---' line and corrects
"<Weekday> M/D" pairs whose weekday disagrees with the post's year. It reads the
editor back and publishes ONLY if the editor holds exactly the intended text.

Usage
  python posting/bs_edit_caption.py --match "HHHH is in this week's list" --date "Mon Sep 7" --year 2026 --dry-run
  python posting/bs_edit_caption.py --match "HHHH is in this week's list" --date "Mon Sep 7" --year 2026
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from posting.bs_retract import _ROWS_JS, POSTS_URL, SESSION  # noqa: E402

_WD = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_PAIR_RX = re.compile(r"\b(Mon|Tues?|Wed|Thu(?:rs?)?|Fri|Sat|Sun)\b(\.?\s+)(\d{1,2})/(\d{1,2})\b")


def corrected(caption: str, year: int) -> tuple[str, list]:
    notes = []
    m = re.match(r"^[^\n]{0,400}\n\s*\n?\s*-{3,}\s*\n+", caption)
    if m:
        notes.append(f"stripped leading note: {caption[:m.end()].strip()[:90]!r}")
        caption = caption[m.end():]

    def fix(mm):
        wd = _WD[mm.group(1).lower()]
        try:
            actual = date(year, int(mm.group(3)), int(mm.group(4))).weekday()
        except ValueError:
            return mm.group(0)
        if actual == wd:
            return mm.group(0)
        new = f"{_NAMES[actual]}{mm.group(2)}{mm.group(3)}/{mm.group(4)}"
        notes.append(f"weekday fix: {mm.group(0)!r} -> {new!r}")
        return new

    return _PAIR_RX.sub(fix, caption), notes


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def run(match: str, date_label: str, year: int, dry_run: bool, week: str) -> int:
    from playwright.sync_api import sync_playwright
    out_dir = ROOT / "data" / "posts" / week / "_bs_edit"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(storage_state=str(SESSION), viewport={"width": 1400, "height": 1000},
                            locale="en-US", timezone_id="America/Chicago")
        page = ctx.new_page()
        try:
            for attempt in range(4):
                page.goto(POSTS_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(10000)
                rows = page.evaluate(_ROWS_JS, [match, date_label])
                if not rows:
                    print(f"[edit] no remaining post matching {match!r} on {date_label}")
                    break
                r = rows[0]
                page.locator('[data-bs-retract="0"]').click(timeout=8000)
                page.wait_for_timeout(2500)
                mg = page.get_by_text("Manage post", exact=True).last
                bx = mg.bounding_box()
                y = bx["y"] + bx["height"] / 2
                page.mouse.move(bx["x"] + 10, y, steps=8)
                page.wait_for_timeout(500)
                page.mouse.move(bx["x"] + bx["width"] + 18, y, steps=8)
                page.wait_for_timeout(2500)
                page.locator('[role="menuitem"]:has-text("Edit post")').last.click(timeout=8000)
                page.wait_for_timeout(8000)
                box = page.locator('[contenteditable="true"]').first
                current = box.inner_text()
                new, notes = corrected(current, year)
                entry = {"platform": r["platform"], "notes": notes}
                print(f"[edit] {r['platform']}: {notes or 'no change needed'}")
                if not notes or dry_run:
                    entry["result"] = "dry-run" if dry_run else "unchanged"
                    log.append(entry)
                    page.get_by_role("button", name="Cancel").last.click()
                    if dry_run or not notes:
                        # a dry run only inspects the first match
                        break
                box.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                page.wait_for_timeout(500)
                page.keyboard.insert_text(new)
                page.wait_for_timeout(1500)
                back = box.inner_text()
                page.screenshot(path=str(out_dir / f"{attempt:02d}_{r['platform']}_typed.png"))
                if _norm(back) != _norm(new):
                    entry["result"] = "editor text did not match; cancelled"
                    log.append(entry)
                    print("[edit] editor readback mismatch; NOT publishing")
                    page.get_by_role("button", name="Cancel").last.click()
                    break
                page.get_by_role("button", name="Publish").last.click(timeout=8000)
                page.wait_for_timeout(9000)
                page.screenshot(path=str(out_dir / f"{attempt:02d}_{r['platform']}_after.png"))
                entry["result"] = "published edit"
                log.append(entry)
        finally:
            (out_dir / "edit_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.close()
            b.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--week", default="2026-W37")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(a.match, a.date, a.year, a.dry_run, a.week)


if __name__ == "__main__":
    sys.exit(main())
