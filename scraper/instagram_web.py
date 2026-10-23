"""Instagram WEB-SESSION fetcher — the tier that works when everything else is walled.

Why (2026-07-06, William: "solve the Instagram wall"):
  - Logged-out web-profile JSON: HTTP 429 on every handle (Instagram closed it).
  - instagrapi private-API login: bloks challenge wall (unresolvable via code).
  - FB-OAuth session mint (ig_login_via_fb.py): dead-ends at /accounts/login.
  - Meta App Review / business_discovery: BOTH YBR accounts (@tulsaybr,
    @imvalpal) are PERSONAL accounts — the official API can never read them.

What works: a normal logged-in WEB session in real Chrome can read any public
profile. Since 2026-10-22 it does so by opening instagram.com/<user>/ like a
person and taking the posts Instagram's own app loads for that page (its
`PolarisProfilePostsQuery` GraphQL response: caption, code, taken_at, images).
The hand-built calls this module used to make (/api/v1/users/web_profile_info +
/api/v1/feed/user/<uid>/) answered HTTP 429 or an HTML wall on every venue from
at least 2026-10-01, while the same session rendered profiles normally. The app's
own request carries whatever headers and doc_id Instagram currently expects, so
it does not rot when those change.

Session: data/fb_session.json (Playwright storage_state, loaded through
tools/group_session.py), not the old persistent data/fb_auto_profile, whose
cookies depended on DPAPI. Re-login: tools/ig_profile_login.py.

Design:
  - ONE browser launch per scrape run fetches ALL orgs (module-level cache).
  - A missing handle (renamed/removed), a private account and a login wall are
    logged by name, then the next alt handle is tried.
  - Post shape matches instagram_orgs extractors: {caption, url, posted_on}.

Selftest (needs the session): python scraper/instagram_web.py --selftest
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
POSTS_QUERY = "PolarisProfilePostsQuery"   # the app's own "posts grid" GraphQL call
POSTS_CONN = "xdt_api__v1__feed__user_timeline_graphql_connection"
POSTS_WAIT_MS = 20000

_PAGE_STATE_JS = """() => {
  const t = (document.body ? document.body.innerText : '') || '';
  return {missing: /page isn.t available/i.test(t),
          private: /this account is private/i.test(t),
          login: !!document.querySelector("input[name='username']") || location.pathname.startsWith('/accounts/login')};
}"""


def _best_img(node: dict) -> str:
    c = ((node or {}).get("image_versions2") or {}).get("candidates") or []
    return c[0].get("url", "") if c else ""


def _profile_posts(page, user: str) -> Tuple[List[Dict], str]:
    """Open instagram.com/<user>/ and return (items, err) from the posts the app
    itself loads for the grid. err names why nothing came back."""
    from playwright.sync_api import TimeoutError as PWTimeout

    def is_posts(r):
        try:
            return "/graphql" in r.url and POSTS_QUERY in (r.request.post_data or "")
        except Exception:
            return False
    try:
        with page.expect_response(is_posts, timeout=POSTS_WAIT_MS) as ri:
            page.goto(f"https://www.instagram.com/{user}/", wait_until="domcontentloaded",
                      timeout=45000)
        resp = ri.value
    except PWTimeout:
        try:
            st = page.evaluate(_PAGE_STATE_JS)
        except Exception:
            st = {}
        if st.get("missing"):
            # Not proof the account is gone: on 2026-10-22 @tulsaybr (4,681 followers,
            # 21+ bio) showed this to the logged-in session while a logged-out browser
            # rendered it fine. Age gates and blocks look identical from here.
            return [], "not visible to this login (removed, renamed, blocked or age-gated)"
        if st.get("private"):
            return [], "private account"
        if st.get("login"):
            return [], "login wall (session not accepted)"
        return [], "profile loaded but no posts query fired"
    except Exception as e:
        return [], f"navigation failed: {str(e)[:100]}"
    if resp.status != 200:
        return [], f"posts query HTTP {resp.status}"
    try:
        text = resp.text()
        if text.startswith("for (;;);"):
            text = text[len("for (;;);"):]
        conn = (json.loads(text).get("data") or {}).get(POSTS_CONN) or {}
    except Exception:
        return [], "posts query returned non-JSON"
    items = []
    for edge in conn.get("edges") or []:
        n = edge.get("node") or {}
        carousel = n.get("carousel_media") or []
        items.append({
            "caption": ((n.get("caption") or {}).get("text") or ""),
            "code": n.get("code") or "",
            "taken_at": n.get("taken_at") or 0,
            "image_url": _best_img(n) or (_best_img(carousel[0]) if carousel else ""),
        })
    return items, ""


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
    # 2026-10-22: the session comes from data/fb_session.json (storage_state, in-memory
    # context), not the persistent data/fb_auto_profile, whose cookies depended on DPAPI
    # and were lost on every Chrome exit while DPAPI was broken (10/7-10/21). An
    # in-memory context also has no profile lock, so the "profile busy" retries are gone.
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.group_session import STATE_PATH, open_context, save_state, IG_DOMAINS
    if not STATE_PATH.exists():
        logger.warning("[ig_web] no saved session at %s — run tools/ig_profile_login.py", STATE_PATH)
        return {}

    results: Dict[str, List[Dict]] = {}
    with sync_playwright() as p:
        try:
            browser, ctx = open_context(p, headless=True)
        except Exception as e:
            logger.warning("[ig_web] browser launch failed: %s", str(e)[:150])
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
                for user in handles:
                    profile_url = f"https://www.instagram.com/{user}/"
                    items, err = _profile_posts(page, user)
                    if err:
                        logger.info("[ig_web] %s @%s: %s — trying next handle", org, user, err)
                        time.sleep(random.uniform(2, 4))
                        continue
                    posts = _to_posts(items, profile_url)
                    if posts:
                        logger.info("[ig_web] %s: %d captioned posts via @%s", org, len(posts), user)
                        results[org] = posts
                        break
                    logger.info("[ig_web] %s @%s: 0 captioned posts", org, user)
                time.sleep(random.uniform(3, 6))  # polite pacing between venues
            try:
                save_state(ctx, IG_DOMAINS)  # keep Instagram's rotated cookies
            except Exception as e:
                logger.warning("[ig_web] could not re-save session: %s", str(e)[:120])
        finally:
            try:
                browser.close()
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
