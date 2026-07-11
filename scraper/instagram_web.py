"""Instagram WEB-SESSION fetcher — the tier that works when everything else is walled.

Why (2026-07-06, William: "solve the Instagram wall"):
  - Logged-out web-profile JSON: HTTP 429 on every handle (Instagram closed it).
  - instagrapi private-API login: bloks challenge wall (unresolvable via code).
  - FB-OAuth session mint (ig_login_via_fb.py): dead-ends at /accounts/login.
  - Meta App Review / business_discovery: BOTH YBR accounts (@tulsaybr,
    @imvalpal) are PERSONAL accounts — the official API can never read them.

What works (verified live 2026-07-06 from a logged-in browser): a normal WEB
session in real Chrome can read any public profile via Instagram's own web API:
    /api/v1/users/web_profile_info/?username=<user>   (uid + meta)
    /api/v1/feed/user/<uid>/?count=12                 (posts + captions + dates)

This module drives the dedicated automation profile (data/fb_auto_profile — the
same one the FB group blast uses headless) with launch_persistent_context
(channel="chrome", headless). The one-time human step is tools/ig_profile_login.py
(William logs in as @tulsagays in a real Chrome window; session persists months).

Design:
  - ONE browser launch per scrape run fetches ALL orgs (module-level cache),
    so 7 venues cost one launch, not seven.
  - Profile-lock aware: if the profile is busy (group blast / keepalive / the
    login window itself), retries briefly then degrades to {} with a warning —
    never crashes the scrape.
  - Post shape matches instagram_orgs extractors: {caption, url, posted_on}.

Selftest (needs the session): python scraper/instagram_web.py --selftest
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "fb_auto_profile"
IG_WEB_APP_ID = "936619743392459"
POSTS_TO_SCAN = 12
LOCK_RETRIES = 3
LOCK_WAIT_S = 20

_JS_FETCH = """
async (user) => {
  const H = {'x-ig-app-id': '%s'};
  try {
    const r1 = await fetch(`/api/v1/users/web_profile_info/?username=${user}`, {headers: H});
    if (!r1.ok) return {err: 'profile HTTP ' + r1.status};
    const u = (await r1.json())?.data?.user;
    if (!u || !u.id) return {err: 'no uid (private/renamed?)'};
    const r2 = await fetch(`/api/v1/feed/user/${u.id}/?count=%d`, {headers: H});
    if (!r2.ok) return {err: 'feed HTTP ' + r2.status};
    const j = await r2.json();
    const bestImg = (o) => {
      const c = (o && o.image_versions2 && o.image_versions2.candidates) || [];
      return c.length ? c[0].url : '';
    };
    return {items: (j.items || []).map(it => ({
      caption: (it.caption && it.caption.text) || '',
      code: it.code || '',
      taken_at: it.taken_at || 0,
      image_url: bestImg(it) || (it.carousel_media && it.carousel_media.length ? bestImg(it.carousel_media[0]) : '')
    }))};
  } catch (e) { return {err: String(e).slice(0, 120)}; }
}
""" % (IG_WEB_APP_ID, POSTS_TO_SCAN)

# One fetch pass per process: {source_name: [post, ...]}. None = not yet run.
_CACHE: Dict[str, List[Dict]] | None = None


def _to_posts(items: list, profile_url: str) -> List[Dict]:
    posts = []
    for it in items:
        caption = (it.get("caption") or "").strip()
        if not caption:
            continue
        code = it.get("code") or ""
        url = f"https://www.instagram.com/p/{code}/" if code else profile_url
        posted_on = ""
        ts = it.get("taken_at") or 0
        if ts:
            try:
                posted_on = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except (ValueError, OverflowError, OSError):
                posted_on = ""
        posts.append({"caption": caption, "url": url, "posted_on": posted_on,
                      "image_url": it.get("image_url") or ""})
    return posts


def _collect(handles_by_org: Dict[str, List[str]]) -> Dict[str, List[Dict]]:
    """One headless launch; fetch every org's first yielding handle."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[ig_web] playwright not installed — web-session tier unavailable")
        return {}
    if not PROFILE.exists():
        logger.warning("[ig_web] profile dir missing (%s) — run tools/ig_profile_login.py", PROFILE)
        return {}

    results: Dict[str, List[Dict]] = {}
    with sync_playwright() as p:
        ctx = None
        for attempt in range(1, LOCK_RETRIES + 1):
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(PROFILE), channel="chrome", headless=True,
                    viewport={"width": 1280, "height": 900})
                break
            except Exception as e:
                msg = str(e)[:150]
                if attempt < LOCK_RETRIES:
                    logger.warning("[ig_web] profile busy/launch failed (try %d/%d): %s — retrying in %ds",
                                   attempt, LOCK_RETRIES, msg, LOCK_WAIT_S)
                    time.sleep(LOCK_WAIT_S)
                else:
                    logger.warning("[ig_web] profile unavailable after %d tries: %s", LOCK_RETRIES, msg)
                    return {}
        try:
            page = ctx.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            cookies = {c["name"] for c in ctx.cookies("https://www.instagram.com")}
            if "ds_user_id" not in cookies:
                logger.warning("[ig_web] SESSION_MISSING — no Instagram login in the automation "
                               "profile. One-time fix: python tools/ig_profile_login.py")
                return {}
            for org, handles in handles_by_org.items():
                profile_url = f"https://www.instagram.com/{handles[0]}/"
                for user in handles:
                    try:
                        data = page.evaluate(_JS_FETCH, user)
                    except Exception as e:
                        logger.warning("[ig_web] %s @%s evaluate failed: %s", org, user, str(e)[:120])
                        continue
                    if data.get("err"):
                        logger.info("[ig_web] %s @%s: %s — trying next handle", org, user, data["err"])
                        continue
                    posts = _to_posts(data.get("items") or [], profile_url)
                    if posts:
                        logger.info("[ig_web] %s: %d captioned posts via @%s", org, len(posts), user)
                        results[org] = posts
                        break
                    logger.info("[ig_web] %s @%s: 0 captioned posts", org, user)
                time.sleep(1.5)  # polite pacing between venues
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    return results


def posts_for(source_name: str, usernames: List[str]) -> List[Dict]:
    """Cached entry point for InstagramOrgScraper: first call fetches ALL orgs
    in one launch; later calls read the cache."""
    global _CACHE
    if _CACHE is None:
        try:
            from scraper.instagram_orgs import ORGS
            handles = {o["source_name"]: [o["username"]] + list(o.get("alt_usernames") or [])
                       for o in ORGS}
        except Exception:
            handles = {}
        handles.setdefault(source_name, list(usernames))
        _CACHE = _collect(handles)
    return _CACHE.get(source_name, [])


def _selftest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = _collect({"ybr_ig": ["tulsaybr", "imvalpal"]})
    posts = out.get("ybr_ig", [])
    print(f"ybr_ig posts: {len(posts)}")
    for p_ in posts[:5]:
        print(" ", p_["posted_on"], p_["caption"][:90].replace("\n", " "))
    return 0 if posts else 1


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
