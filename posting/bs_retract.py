"""Delete a week's Page + Instagram posts through Meta Business Suite (2026-09-15).

Why. When a weekly deck is wrong it has to come off Instagram too, and neither
route that existed could do it: the Graph API token lacks IG delete permission
("(#10) Insufficient permissions") and posting/ig_retract.py needs a logged-in
instagram.com session, which every Chrome on this machine had lost. Business
Suite manages the linked @tulsagays account from the Facebook session the
scraper refreshes every run (data/fb_session.json), so it works with no IG login.

It also exposed what nothing had recorded: W38 was posted TWICE (Instagram at
4:04 PM and 4:20 PM, a second Page post at 4:02 PM). post_results.json only
kept the last run, so the first retraction removed one of four posts.

Matching is deliberately narrow: a row must contain the caption prefix AND the
publish-date label. Every step is screenshotted.

Usage
  python posting/bs_retract.py --caption "We've got rhinestones" --date "Mon Sep 14" --dry-run
  python posting/bs_retract.py --caption "We've got rhinestones" --date "Mon Sep 14" --week 2026-W38
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / "data" / "fb_session.json"
PAGE_ID = "1086906044497675"
BUSINESS_ID = "1966911607366736"
POSTS_URL = (f"https://business.facebook.com/latest/posts/published_posts"
             f"?asset_id={PAGE_ID}&business_id={BUSINESS_ID}")

_ROWS_JS = r"""(args) => {
  const [caption, dateLabel] = args;
  document.querySelectorAll('[data-bs-retract]').forEach(e => e.removeAttribute('data-bs-retract'));
  const leaves = Array.from(document.querySelectorAll('*')).filter(e =>
    e.children.length === 0 && (e.textContent || '').trim().startsWith(caption));
  const out = [];
  for (const leaf of leaves) {
    let c = leaf, dd = null;
    for (let i = 0; i < 18 && c; i++) {
      c = c.parentElement;
      if (!c) break;
      dd = Array.from(c.querySelectorAll('[role=button],button')).find(b => /Open Dropdown/i.test(b.innerText || b.getAttribute('aria-label') || ''));
      if (dd) break;
    }
    if (!c || !dd) continue;
    let row = c;
    for (let i = 0; i < 6 && row && !(row.innerText || '').includes(dateLabel); i++) row = row.parentElement;
    const text = (row && row.innerText || '').replace(/\s+/g, ' ');
    if (!text.includes(dateLabel)) continue;
    const idx = out.length;
    dd.setAttribute('data-bs-retract', String(idx));
    const platform = /tulsagays/.test(text) && /Carousel/.test(text) ? 'instagram' : 'facebook';
    out.push({i: idx, platform, text: text.slice(0, 220)});
  }
  return out;
}"""


def _shot(page, d: Path, tag: str) -> str:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{tag}.png"
    try:
        page.screenshot(path=str(p))
    except Exception:
        pass
    return str(p)


def _load(page):
    page.goto(POSTS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)


def run(caption: str, date_label: str, week: str, dry_run: bool) -> dict:
    from playwright.sync_api import sync_playwright
    out_dir = ROOT / "data" / "posts" / week / "_bs_retract"
    log = {"week": week, "caption": caption, "date": date_label, "dry_run": dry_run,
           "started": datetime.now(timezone.utc).isoformat(), "steps": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(storage_state=str(SESSION), viewport={"width": 1400, "height": 1000},
                                  locale="en-US", timezone_id="America/Chicago")
        page = ctx.new_page()
        try:
            _load(page)
            rows = page.evaluate(_ROWS_JS, [caption, date_label])
            log["found"] = [{k: r[k] for k in ("platform", "text")} for r in rows]
            print(f"[bs] {len(rows)} matching post(s)")
            for r in rows:
                print(f"   - {r['platform']}: {r['text'][:120]}")
            if dry_run:
                return log
            for attempt in range(len(rows) + 3):
                rows = page.evaluate(_ROWS_JS, [caption, date_label])
                if not rows:
                    break
                r = rows[0]
                step = {"platform": r["platform"], "text": r["text"][:120]}
                page.locator('[data-bs-retract="0"]').click(timeout=8000)
                page.wait_for_timeout(2500)
                step["menu_shot"] = _shot(page, out_dir, f"{attempt:02d}_menu")
                # Delete lives under "Manage post >" (View insights / Manage post /
                # Reshare to story / Copy post ID at the top level, 2026-09-15).
                # The submenu opens only when the pointer travels onto the ">" arrow;
                # hover() or click() on the label highlights it but leaves it shut.
                manage = page.get_by_text("Manage post", exact=True).last
                if manage.count():
                    box = manage.bounding_box()
                    if box:
                        y = box["y"] + box["height"] / 2
                        page.mouse.move(box["x"] + 10, y, steps=8)
                        page.wait_for_timeout(600)
                        page.mouse.move(box["x"] + box["width"] + 18, y, steps=8)
                        page.wait_for_timeout(2500)
                    step["submenu_shot"] = _shot(page, out_dir, f"{attempt:02d}_submenu")
                item = page.locator('[role="menuitem"]:has-text("Delete post")').last
                if not item.count():
                    step["result"] = "no Delete in menu"
                    log["steps"].append(step)
                    break
                item.click(timeout=8000)
                page.wait_for_timeout(2500)
                step["confirm_shot"] = _shot(page, out_dir, f"{attempt:02d}_confirm")
                # Instagram confirms with "Delete"; a Facebook Page post with
                # "Move to trash" (30-day recoverable) in a "Move post to trash
                # and pause ads?" dialog (2026-09-15).
                confirm = page.locator('div[role="dialog"] [role="button"]:has-text("Move to trash"), '
                                       'div[role="dialog"] button:has-text("Move to trash"), '
                                       'div[role="dialog"] [role="button"]:has-text("Delete"), '
                                       'div[role="dialog"] button:has-text("Delete")').first
                if not confirm.count():
                    step["result"] = "no confirm button"
                    log["steps"].append(step)
                    break
                confirm.click(timeout=8000)
                page.wait_for_timeout(6000)
                step["after_shot"] = _shot(page, out_dir, f"{attempt:02d}_after")
                before = len(rows)
                _load(page)
                after = len(page.evaluate(_ROWS_JS, [caption, date_label]))
                step["result"] = "deleted (count dropped)" if after < before else "confirm clicked but post still listed"
                log["steps"].append(step)
                print(f"[bs] {step['result']}: {before} -> {after}")
                if after >= before:
                    break
            _load(page)
            remaining = page.evaluate(_ROWS_JS, [caption, date_label])
            log["remaining"] = len(remaining)
            _shot(page, out_dir, "final")
            print(f"[bs] remaining after retract: {len(remaining)}")
        finally:
            log["finished"] = datetime.now(timezone.utc).isoformat()
            (ROOT / "data" / "posts" / week).mkdir(parents=True, exist_ok=True)
            (ROOT / "data" / "posts" / week / "bs_retract_results.json").write_text(
                json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.close()
            browser.close()
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--caption", required=True, help="caption prefix, exact")
    ap.add_argument("--date", required=True, help="Business Suite date label, e.g. 'Mon Sep 14'")
    ap.add_argument("--week", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    log = run(a.caption, a.date, a.week, a.dry_run)
    if a.dry_run:
        return 0
    return 0 if log.get("remaining") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
