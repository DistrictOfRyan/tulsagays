"""HHHH/TulsaGays IG follower-growth task (scheduled_tasks/hhhh-follower-growth).

Drives the already-authenticated fb_auto_profile headless Chrome session
(the same one used by scraper/instagram_web.py + posting/group_blast.py) to:
  1. read the @tulsagays notifications 'Follow Back' queue,
  2. mine followers of local LGBTQ+ seed accounts,
  3. check bios for Tulsa/OK + LGBTQ+ signals,
  4. follow up to FOLLOW_TARGET verified real local people (never bots/brands).

Reuses IG's own web API (x-ig-app-id header, no separate credentials) rather
than instagrapi — instagrapi login hits the bloks challenge wall for this
account (see feedback_instagram_bloks_challenge_wall) and its session file
has repeatedly expired; the web session persists for months.

Usage:
    python tools/hhhh_follower_growth.py scan            # dump notifications Follow-Back queue
    python tools/hhhh_follower_growth.py mine SEED...     # dump follower bios for seed accounts
    python tools/hhhh_follower_growth.py check USER...    # print current follow-button state
    python tools/hhhh_follower_growth.py follow USER...   # click Follow, verify -> Following/Requested
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "fb_auto_profile"
APP_ID = "936619743392459"

SEEDS = ["clubmajestictulsa", "tulsaybr", "twistedartstulsa",
         "oklahomansforequality", "blackqueertulsa", "qwc_tul"]

JS_UID = """
async (user) => {
  const H = {'x-ig-app-id': '%s'};
  const r = await fetch(`/api/v1/users/web_profile_info/?username=${user}`, {headers: H});
  const u = (await r.json())?.data?.user;
  return u ? u.id : null;
}
""" % APP_ID

JS_FOLLOWERS = """
async (uid) => {
  const H = {'x-ig-app-id': '%s'};
  try {
    const r = await fetch(`/api/v1/friendships/${uid}/followers/?count=40`, {headers: H});
    const j = await r.json();
    return (j.users || []).map(u => ({username: u.username, full_name: u.full_name, is_private: u.is_private}));
  } catch (e) { return []; }
}
""" % APP_ID

JS_BIO = """
async (user) => {
  const H = {'x-ig-app-id': '%s'};
  try {
    const r = await fetch(`/api/v1/users/web_profile_info/?username=${user}`, {headers: H});
    if (!r.ok) return {err: 'HTTP ' + r.status};
    const u = (await r.json())?.data?.user;
    if (!u) return {err: 'no user'};
    return {
      full_name: u.full_name, biography: u.biography, is_private: u.is_private,
      is_business_account: u.is_business_account,
      follower_count: u.edge_followed_by ? u.edge_followed_by.count : null,
      following_count: u.edge_follow ? u.edge_follow.count : null,
    };
  } catch (e) { return {err: String(e).slice(0,120)}; }
}
""" % APP_ID


def _launch(p):
    return p.chromium.launch_persistent_context(
        str(PROFILE), channel="chrome", headless=True,
        viewport={"width": 1280, "height": 900})


def scan_notifications() -> dict:
    """Return {username: status} from the @tulsagays notifications feed,
    status in {'Following','Follow Back','Requested'} (dedup, most-recent-first)."""
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        ctx = _launch(p)
        try:
            page = ctx.new_page()
            page.goto("https://www.instagram.com/accounts/activity/",
                      wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            text = page.inner_text("body")
        finally:
            ctx.close()
    import re
    for m in re.finditer(r"(\w[\w.]*)\s*\n started following you.*?\n(Following|Follow Back|Requested)", text):
        uname, status = m.group(1), m.group(2)
        out.setdefault(uname, status)
    return out


def fetch_bios(usernames: list[str]) -> dict:
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        ctx = _launch(p)
        try:
            page = ctx.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            for u in usernames:
                out[u] = page.evaluate(JS_BIO, u)
                page.wait_for_timeout(1000)
        finally:
            ctx.close()
    return out


def mine_seed_followers(seeds: list[str], per_seed: int = 40) -> dict:
    """Followers of each seed, deduped, with bios for public accounts."""
    from playwright.sync_api import sync_playwright
    candidates = []
    with sync_playwright() as p:
        ctx = _launch(p)
        try:
            page = ctx.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            for seed in seeds:
                uid = page.evaluate(JS_UID, seed)
                if not uid:
                    continue
                candidates.extend(page.evaluate(JS_FOLLOWERS, uid))
                page.wait_for_timeout(1200)
            seen = {}
            for c in candidates:
                seen.setdefault(c["username"], c)
            pub = [c for c in seen.values() if not c["is_private"]]
            bios = {}
            for c in pub:
                bios[c["username"]] = {**c, **page.evaluate(JS_BIO, c["username"])}
                page.wait_for_timeout(800)
        finally:
            ctx.close()
    return bios


def check_state(usernames: list[str]) -> dict:
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        ctx = _launch(p)
        try:
            page = ctx.new_page()
            for u in usernames:
                page.goto(f"https://www.instagram.com/{u}/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                btn = page.locator('button:has-text("Follow Back"), button:has-text("Follow"), '
                                    'button:has-text("Following"), button:has-text("Requested")').first
                out[u] = btn.inner_text() if btn.count() else "NONE"
        finally:
            ctx.close()
    return out


def do_follow(usernames: list[str], pace_seconds: int = 18) -> list[dict]:
    """Click Follow/Follow Back for each; verify the button flips. Never
    force-follows an account already in Following/Requested state."""
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        ctx = _launch(p)
        try:
            page = ctx.new_page()
            for uname in usernames:
                entry = {"username": uname}
                try:
                    page.goto(f"https://www.instagram.com/{uname}/",
                              wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2500)
                    btn = page.locator('button:has-text("Follow Back"), button:has-text("Follow")').first
                    pre = btn.inner_text() if btn.count() else "NONE"
                    entry["pre_state"] = pre
                    if pre in ("Follow Back", "Follow"):
                        btn.click(timeout=10000)
                        page.wait_for_timeout(2500)
                        post = page.locator('button:has-text("Following"), button:has-text("Requested")').first
                        entry["post_state"] = post.inner_text() if post.count() else "UNKNOWN"
                        entry["action"] = "clicked_follow"
                    else:
                        entry["action"] = "skipped_already_" + pre
                except Exception as e:
                    entry["error"] = f"{type(e).__name__}: {str(e)[:150]}"
                results.append(entry)
                time.sleep(pace_seconds)
        finally:
            ctx.close()
    return results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    args = sys.argv[2:]
    if cmd == "scan":
        print(json.dumps(scan_notifications(), indent=2, ensure_ascii=False))
    elif cmd == "mine":
        print(json.dumps(mine_seed_followers(args or SEEDS), indent=2, ensure_ascii=False))
    elif cmd == "check":
        print(json.dumps(check_state(args), indent=2, ensure_ascii=False))
    elif cmd == "follow":
        print(json.dumps(do_follow(args), indent=2, ensure_ascii=False))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
