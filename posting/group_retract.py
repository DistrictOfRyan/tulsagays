"""Delete the Tulsa Gays Page's recent posts from Facebook groups (2026-09-15).

Why. posting/group_blast.py pushes the weekly carousel graphics into ~17 groups
as the Page. When a deck turns out to be WRONG after the blast (W38: a 2025
festival as Event of the Week, every Facebook time an hour early) those group
posts have to come down too, and there is no API for group content. This tool
drives the same persistent real-Chrome profile the blast uses, opens each
group's "Your content" page (which lists the Page's published AND pending posts
in that group), and deletes every post of ours newer than --since-hours.

Usage
  python posting/group_retract.py --week 2026-W38 --discover   # read-only: screenshots + text per group
  python posting/group_retract.py --week 2026-W38               # delete our posts from the last 48h
  python posting/group_retract.py --week 2026-W38 --since-hours 72 --headed

Reads the group list from data/posts/<week>/group_blast_results*.json (the
retracted ledger is fine). Writes data/posts/<week>/group_retract_results.json
and screenshots under data/posts/<week>/_group_retract/.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from posting.group_blast import _switch_to_page, PAGE_NAME, get_group_url  # noqa: E402

PROFILE_DIR = ROOT / "data" / "fb_auto_profile"


FB_SESSION_FILE = ROOT / "data" / "fb_session.json"


def ensure_fb_login(ctx, page) -> bool:
    """True when the context is logged into Facebook. The persistent profile's
    session can lapse while data/fb_session.json (refreshed by every scrape)
    is still live: 2026-09-15 the retract reported AUTH_DEAD against a profile
    whose cookies had expired while the scraper's c_user/xs ran to 2027. Load
    those cookies into the profile and re-check before declaring auth dead."""
    if "c_user" in {c["name"] for c in ctx.cookies()}:
        return True
    try:
        state = json.loads(FB_SESSION_FILE.read_text(encoding="utf-8"))
        cookies = [c for c in state.get("cookies", [])
                   if "facebook.com" in (c.get("domain") or "") or "instagram.com" in (c.get("domain") or "")]
        if not cookies:
            return False
        ctx.add_cookies(cookies)
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"[auth] fb_session.json restore failed: {type(e).__name__}: {e}")
        return False
    ok = "c_user" in {c["name"] for c in ctx.cookies()} and "/login" not in page.url
    print(f"[auth] restored Facebook session from fb_session.json: {ok} ({page.url[:60]})")
    return ok


def _groups_from_ledgers(week: str) -> list:
    seen, out = set(), []
    for p in sorted(glob.glob(str(ROOT / "data" / "posts" / week / "group_blast_results*.json"))):
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in data.get("results", []):
            if r.get("status") in ("live", "pending", "submitted") and r.get("id") not in seen:
                seen.add(r["id"])
                out.append({"name": r.get("name"), "id": r.get("id"), "url": r.get("url"),
                            "blast_status": r.get("status"), "blast_at": r.get("at")})
    return out


def _shot(page, d: Path, tag: str) -> str:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{tag}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
    except Exception:
        pass
    return str(p)


def _body(page) -> str:
    try:
        return page.inner_text("body", timeout=8000)
    except Exception:
        return ""


# Post text and timestamps on "Your content" are obfuscated ("Facebook
# Facebook ..."), so age/text matching is blind: the first draft of this tool
# would have matched a May deck. Photo ids are Page-sequential and date a post
# exactly. We start from each post's ACTION element ("View in group" on the
# Published tab, the "Delete" button on Pending), walk up to the first ancestor
# holding photo links, and tag the action element with data-tg-retract=<i>.
_MARK_JS = r"""() => {
  document.querySelectorAll('[data-tg-retract]').forEach(e => e.removeAttribute('data-tg-retract'));
  const acts = Array.from(document.querySelectorAll('div[role=button], a[role=link], a'))
    .filter(b => { const t = (b.innerText || '').trim(); return t === 'Delete' || t === 'View in group'; });
  const out = [];
  for (const b of acts) {
    let c = b, fbids = [];
    for (let i = 0; i < 30 && c; i++) {
      c = c.parentElement;
      if (!c) break;
      fbids = Array.from(c.querySelectorAll('a[href*="fbid="]')).map(x => (x.href.match(/fbid=(\d+)/) || [])[1]).filter(Boolean);
      if (fbids.length) break;
    }
    if (!fbids.length) continue;
    const idx = out.length;
    b.setAttribute('data-tg-retract', String(idx));
    out.push({i: idx, kind: (b.innerText || '').trim() === 'Delete' ? 'pending' : 'published', fbids: Array.from(new Set(fbids))});
  }
  return out;
}"""


def _our_recent_posts(page, min_fbid: int) -> list:
    """[(action_locator, kind)] for posts whose carousel photos were uploaded at
    or after `min_fbid` (the retracted week's blast)."""
    try:
        marked = page.evaluate(_MARK_JS)
    except Exception:
        return []
    hits = []
    for m in marked:
        ids = [int(x) for x in m.get("fbids") or [] if str(x).isdigit()]
        if ids and min(ids) >= min_fbid:
            hits.append((page.locator(f'[data-tg-retract="{m["i"]}"]'), m["kind"]))
    return hits


def _week_photo_ids(week: str) -> list:
    ids = []
    for p in glob.glob(str(ROOT / "data" / "posts" / week / "post_results*.json")):
        try:
            ids += [int(x) for x in json.loads(Path(p).read_text(encoding="utf-8")).get("photo_ids", [])]
        except Exception:
            continue
    return ids


def _min_fbid_for_week(week: str, margin: int = 50_000_000_000) -> int:
    """Lowest photo fbid that can belong to this week's blast: the Page post's
    first carousel photo minus ~8 hours of id space. Measured 2026-09-15: one
    week of Page uploads spans ~9.9e11 ids (W37 122129165006.. -> W38
    122130156692..); the W38 group uploads began 7.8e9 below the Page post.
    A first draft used 3e13 and its dry run matched W36 and W37 posts too, so
    the cutoff is now asserted to sit above the previous week's photos."""
    ids = _week_photo_ids(week)
    if not ids:
        raise SystemExit(f"no post_results photo_ids for {week}: cannot date group posts safely")
    cutoff = min(ids) - margin
    try:
        y, w = week.split("-W")
        prev = date.fromisocalendar(int(y), int(w), 1) - timedelta(days=7)
        pk = f"{prev.isocalendar()[0]}-W{prev.isocalendar()[1]:02d}"
        prev_ids = _week_photo_ids(pk)
        if prev_ids and max(prev_ids) >= cutoff:
            raise SystemExit(f"unsafe cutoff {cutoff}: {pk} photos reach {max(prev_ids)}")
    except SystemExit:
        raise
    except Exception:
        pass
    return cutoff


_DIALOG_FBIDS_JS = r"""() => {
  const d = Array.from(document.querySelectorAll('div[role=dialog]')).pop();
  if (!d) return [];
  return Array.from(new Set(Array.from(d.querySelectorAll('a[href*="fbid="]')).map(x => (x.href.match(/fbid=(\d+)/) || [])[1]).filter(Boolean)));
}"""


def _confirm_delete(page) -> bool:
    for sel in ('div[role="dialog"] div[aria-label="Delete"][role="button"]',
                'div[role="dialog"] div[role="button"]:text-is("Delete")',
                'div[role="dialog"] span:text-is("Delete")'):
        c = page.locator(sel).last
        try:
            if c.count():
                c.click(timeout=5000)
                page.wait_for_timeout(4000)
                return True
        except Exception:
            continue
    return False


def _delete_post(page, target, d: Path, tag: str, min_fbid: int = 0) -> str:
    """Delete one post. `target` is (action_locator, kind) from _our_recent_posts."""
    act, kind = target
    try:
        act.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    if kind == "pending":
        act.click(timeout=5000)
        page.wait_for_timeout(2000)
        _shot(page, d, f"{tag}_confirm")
        ok = _confirm_delete(page)
        _shot(page, d, f"{tag}_after")
        return "deleted" if ok else "pending confirm not found"
    # Published: the list's "..." menu has no Delete for Page posts; the post
    # dialog opened by "View in group" does ("Actions for this post by <Page>").
    act.click(timeout=5000)
    page.wait_for_timeout(6000)
    ids = [int(x) for x in page.evaluate(_DIALOG_FBIDS_JS) if str(x).isdigit()]
    if not ids or min(ids) < min_fbid:
        page.keyboard.press("Escape")
        return f"dialog photos {min(ids) if ids else 'none'} outside scope; skipped"
    menu = page.locator('div[role="dialog"] div[role="button"][aria-label^="Actions for this post"]').last
    if not menu.count():
        page.keyboard.press("Escape")
        return "dialog actions menu not found"
    menu.click(timeout=5000)
    page.wait_for_timeout(2000)
    _shot(page, d, f"{tag}_menu")
    item = page.locator('div[role="menuitem"]:has-text("Delete post")').first
    if not item.count():
        page.keyboard.press("Escape")
        return "no Delete post in dialog menu"
    item.click(timeout=5000)
    page.wait_for_timeout(2000)
    _shot(page, d, f"{tag}_confirm")
    ok = _confirm_delete(page)
    _shot(page, d, f"{tag}_after")
    return "deleted" if ok else "confirm button not found"


def run(week: str, discover: bool = False, headed: bool = False, since_hours: int = 48, only: str = "") -> dict:
    min_fbid = _min_fbid_for_week(week)
    print(f"[scope] deleting only group posts whose photos have fbid >= {min_fbid}")
    groups = [g for g in _groups_from_ledgers(week) if not only or str(g["id"]) == only]
    if not groups:
        raise SystemExit(f"no group ledger for {week}")
    out_dir = ROOT / "data" / "posts" / week / "_group_retract"
    results = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="chrome", headless=not headed,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport={"width": 1280, "height": 1000}, locale="en-US",
            timezone_id="America/Chicago")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20000)
        page.set_default_navigation_timeout(35000)
        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            if not ensure_fb_login(ctx, page):
                raise SystemExit("AUTH_DEAD: profile not logged into Facebook and "
                                 "data/fb_session.json did not restore it")
            if not _switch_to_page(page):
                raise SystemExit("could not act as the Page (anonymity guard)")
            print(f"[ok] acting as {PAGE_NAME}")
            deadline = time.monotonic() + 1500
            for g in groups:
                if time.monotonic() > deadline:
                    results.append({**g, "status": "skipped", "error": "wall-clock cap"})
                    continue
                gid = g["id"]
                tag = re.sub(r"[^A-Za-z0-9]+", "_", str(g["name"]))[:40]
                r = {**g, "deleted": 0, "found": 0, "notes": []}
                try:
                    remaining = 0
                    for tab in ("my_posted_content", "my_pending_content"):
                        page.goto(f"https://www.facebook.com/groups/{gid}/{tab}", wait_until="domcontentloaded")
                        page.wait_for_timeout(6000)
                        _shot(page, out_dir, f"{tag}_{tab}_before")
                        # Delete loop: re-mark after each delete since the DOM re-renders.
                        for attempt in range(8):
                            posts = _our_recent_posts(page, min_fbid)
                            if attempt == 0:
                                r["found"] += len(posts)
                            if not posts:
                                break
                            if discover:
                                r["notes"].append(f"{tab}: {len(posts)} W-post(s) would be deleted")
                                break
                            st = _delete_post(page, posts[0], out_dir, f"{tag}_{tab}_{attempt}", min_fbid)
                            r["notes"].append(f"{tab}:{st}")
                            if st != "deleted":
                                break
                            r["deleted"] += 1
                            # A published delete leaves the post dialog and FB
                            # redirects to the home feed; always return to the tab.
                            page.goto(f"https://www.facebook.com/groups/{gid}/{tab}", wait_until="domcontentloaded")
                            page.wait_for_timeout(6000)
                        if not discover:
                            page.goto(f"https://www.facebook.com/groups/{gid}/{tab}", wait_until="domcontentloaded")
                            page.wait_for_timeout(6000)
                            remaining += len(_our_recent_posts(page, min_fbid))
                            _shot(page, out_dir, f"{tag}_{tab}_after")
                    r["remaining"] = remaining
                    if discover:
                        r["status"] = "discovered"
                    else:
                        r["status"] = "ok" if remaining == 0 else "partial"
                except Exception as e:
                    r["status"] = "error"
                    r["error"] = str(e)[:200]
                r["at"] = datetime.now(timezone.utc).isoformat()
                results.append(r)
                print(f"  [{r.get('status','?'):10}] {g['name']}: found={r.get('found')} deleted={r.get('deleted')} remaining={r.get('remaining')} {r.get('notes') or ''}")
                time.sleep(4)
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    out = {"week": week, "ran_at": datetime.now(timezone.utc).isoformat(), "discover": discover,
           "min_fbid": min_fbid, "results": results,
           "deleted_total": sum(r.get("deleted", 0) for r in results)}
    ledger = ROOT / "data" / "posts" / week / ("group_retract_discovery.json" if discover else "group_retract_results.json")
    ledger.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nledger -> {ledger}  deleted_total={out['deleted_total']}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--since-hours", type=int, default=48)
    ap.add_argument("--only", default="", help="single group id")
    a = ap.parse_args()
    run(a.week, discover=a.discover, headed=a.headed, since_hours=a.since_hours, only=a.only)
