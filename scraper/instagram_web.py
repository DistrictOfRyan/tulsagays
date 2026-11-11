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

LOGGED-OUT PAGE READ (added 2026-10-26). The login can be the thing that hides
a profile. @tulsaybr (YBR, a partner venue and a 21+ bar) answers "page isn't
available" to the logged-in session, almost certainly the age gate applied to
that account, while a browser with NO cookies renders the profile normally. So
the scraper fell back to @imvalpal, the owner's personal feed, which carries no
events, and ybr_ig produced 0 events every week from W35 to W44. When the login
cannot see a handle (or there is no login at all), the same browser now opens a
fresh cookie-less context and reads the posts Instagram server-renders into the
logged-out page (`xig_user_by_username.polaris_ordered_timeline_connection`:
caption, code, image, and the date in the image's alt text). This is page
rendering, not the logged-out JSON endpoint that 429s.

POST TIME FROM THE SHORTCODE (2026-11-11). A post's shortcode is its media id
in base64, and the top bits of that id are the creation time in milliseconds
since Instagram's epoch. Checked against all 14 real @tulsaeagle posts in
tests/fixtures/tulsa_eagle_ig_captions_2026-09-09.json: 14/14 decode to the
date recorded from the post page, at the venue's documented 12:03pm CT slot.
Until this change each recent logged-out post was opened on its own page to
read `taken_at`, up to a dozen extra logged-out page loads per handle.
Instagram rate-limits logged-out viewing: a limited view is redirected to
/accounts/login?...&is_from_rle instead of rendering the profile (observed from
a datacenter IP on its very first load, 2026-11-11). Every extra load raised the
odds that the one load that matters, the profile, got that redirect. The date
now comes from the code with zero requests, and a post whose alt text carries
no date is no longer dropped.

Design:
  - ONE browser launch per scrape run fetches ALL orgs (module-level cache).
  - A missing handle (renamed/removed), a private account and a login wall are
    logged by name; a handle hidden from the login is re-read logged out, then
    the next alt handle is tried.
  - Post shape matches instagram_orgs extractors: {caption, url, posted_on}.
  - A logged-out post with no readable date (no taken_at, no decodable code,
    no alt-text date) is dropped, never guessed.
  - Every org's outcome (handle used, via, posts, each failed attempt) is kept
    in _STATUS so instagram_orgs can write it to data/ig_scrape_health.json.

Selftest (live, no login needed for YBR): python scraper/instagram_web.py --selftest
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
LOGGED_OUT_CONN = "polaris_ordered_timeline_connection"   # server-rendered grid, no cookies
_SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_IG_EPOCH_MS = 1314220021721     # Instagram's media-id epoch (2011-08-24 21:07:01.721 UTC)
_SHORTCODE_MIN_TS = 1356998400   # 2013-01-01: earlier codes used a different scheme
# _profile_posts errors that mean the login could not see the profile, so a cookie-less
# read is worth one try. "No posts query" is in here because an age-gated profile is
# exactly the kind of page whose shape Instagram may change without notice.
_HIDDEN_FROM_LOGIN = ("not visible to this login", "login wall",
                      "profile loaded but no posts query fired")

_JSON_SCRIPTS_JS = """() => Array.from(document.querySelectorAll('script[type="application/json"]'))
  .map(s => s.textContent || '')"""
_ALT_DATE_RX = re.compile(r"\bon ([A-Z][a-z]+ \d{1,2}, \d{4})")

_PAGE_STATE_JS = """() => {
  const t = (document.body ? document.body.innerText : '') || '';
  return {missing: /page isn.t available/i.test(t),
          private: /this account is private/i.test(t),
          login: !!document.querySelector("input[name='username']") || location.pathname.startsWith('/accounts/login')};
}"""


def shortcode_taken_at(code: str) -> int:
    """Creation time (UTC epoch seconds) encoded in a post's shortcode, or 0.

    The shortcode is the media id written in URL-safe base64; the media id's
    bits above the low 23 are milliseconds since _IG_EPOCH_MS. Long (private
    or share) codes carry the 11-character media code first. A code shorter
    than 10 characters, or a result outside [2013, now + 2 days], is not a
    media code and returns 0 (the caller then falls back to the alt text)."""
    code = (code or "").strip()
    if len(code) > 11:
        code = code[:11]
    if len(code) < 10:
        return 0
    n = 0
    for ch in code:
        i = _SHORTCODE_ALPHABET.find(ch)
        if i < 0:
            return 0
        n = n * 64 + i
    ts = ((n >> 23) + _IG_EPOCH_MS) // 1000
    if ts < _SHORTCODE_MIN_TS or ts > time.time() + 2 * 86400:
        return 0
    return int(ts)


def _local_date(epoch_s) -> str:
    """Tulsa calendar day of a UTC epoch time (not the scrape machine's zone)."""
    import sys as _sys
    if str(ROOT) not in _sys.path:          # standalone `python scraper/instagram_web.py`
        _sys.path.insert(0, str(ROOT))
    from scraper.tz_guard import local_date_from_epoch
    return local_date_from_epoch(epoch_s)


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


def _find(obj, pred):
    """Depth-first: the first dict in obj for which pred(dict) is true, else None."""
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if pred(o):
                return o
            stack.extend(reversed(list(o.values())))
        elif isinstance(o, list):
            stack.extend(reversed(o))
    return None


def _page_json(page) -> list:
    """Every server-rendered JSON blob on the page, parsed; unparseable ones skipped."""
    out = []
    for text in page.evaluate(_JSON_SCRIPTS_JS) or []:
        try:
            out.append(json.loads(text))
        except Exception:
            continue
    return out


def _alt_date(text: str) -> str:
    """'Photo by Ybr Tulsa on October 24, 2026. ...' -> '2026-10-24', else ''."""
    m = _ALT_DATE_RX.search(text or "")
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _loggedout_posts(page, user: str) -> Tuple[List[Dict], str]:
    """Read instagram.com/<user>/ in a cookie-less context. Returns (items, err)
    with the same item keys _profile_posts uses. ONE page load: each post's exact
    time comes from its own taken_at or its shortcode, the alt-text date only
    when neither is readable (see the module docstring)."""
    try:
        page.goto(f"https://www.instagram.com/{user}/", wait_until="domcontentloaded",
                  timeout=45000)
        page.wait_for_timeout(2500)
        conn = None
        for blob in _page_json(page):
            hit = _find(blob, lambda d: LOGGED_OUT_CONN in d)
            if hit:
                conn = hit[LOGGED_OUT_CONN]
                break
    except Exception as e:
        return [], f"logged-out navigation failed: {str(e)[:100]}"
    if not conn:
        try:
            st = page.evaluate(_PAGE_STATE_JS)
        except Exception:
            st = {}
        if st.get("missing"):
            return [], "page isn't available logged out either"
        if st.get("private"):
            return [], "private account"
        return [], "logged-out page carried no post data (login wall or layout change)"

    items, undated, exact = [], 0, 0
    for edge in conn.get("edges") or []:
        n = edge.get("node") or {}
        code = n.get("code") or ""
        try:
            taken_at = int(n.get("taken_at") or 0)
        except (TypeError, ValueError):
            taken_at = 0
        taken_at = taken_at or shortcode_taken_at(code)
        # The alt text's date is in an unstated zone (an evening "tonight" post can
        # read as the next day), so it is the last resort, not the source.
        posted_on = _local_date(taken_at) if taken_at else _alt_date(
            n.get("accessibility_caption") or "")
        if not posted_on:
            undated += 1
            continue
        exact += bool(taken_at)
        items.append({
            "caption": ((n.get("caption") or {}).get("text") or ""),
            "code": code,
            "taken_at": taken_at,
            "posted_on": posted_on,
            "image_url": n.get("display_uri") or "",
        })
    if undated:
        logger.info("[ig_web] @%s logged out: dropped %d post(s) with no readable date",
                    user, undated)
    logger.info("[ig_web] @%s logged out: %d posts, %d with exact timestamps (1 page load)",
                user, len(items), exact)
    return items, ""


# One fetch pass per process: {source_name: [post, ...]}. None = not yet run.
_CACHE: Dict[str, List[Dict]] | None = None
# What happened per org on that pass, for data/ig_scrape_health.json:
# {source_name: {"handle", "via", "posts", "attempts": ["@h: why", ...]}}
_STATUS: Dict[str, Dict] = {}
# Whether the pass ran logged in, and why not when it did not.
_SESSION: Dict[str, object] = {}


def _to_posts(items: list, profile_url: str) -> List[Dict]:
    posts = []
    for it in items:
        caption = (it.get("caption") or "").strip()
        if not caption:
            continue
        code = it.get("code") or ""
        url = f"https://www.instagram.com/p/{code}/" if code else profile_url
        posted_on = it.get("posted_on") or ""   # logged-out alt-text date, if that is all we have
        try:
            ts = int(it.get("taken_at") or 0)
        except (TypeError, ValueError):
            ts = 0
        ts = ts or shortcode_taken_at(code)
        if ts:
            # Tulsa's calendar day, not the scrape machine's (Puerto Vallarta).
            posted_on = _local_date(ts) or posted_on
        posts.append({"caption": caption, "url": url, "posted_on": posted_on,
                      "taken_at": ts, "image_url": it.get("image_url") or ""})
    return posts


def _collect(handles_by_org: Dict[str, List[str]]) -> Dict[str, List[Dict]]:
    """One headless launch; fetch every org's first yielding handle."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[ig_web] playwright not installed — web-session tier unavailable")
        _STATUS.clear()
        _SESSION.clear()
        _SESSION.update({"logged_in": False, "note": "playwright not installed"})
        return {}
    # 2026-10-22: the session comes from data/fb_session.json (storage_state, in-memory
    # context), not the persistent data/fb_auto_profile, whose cookies depended on DPAPI
    # and were lost on every Chrome exit while DPAPI was broken (10/7-10/21). An
    # in-memory context also has no profile lock, so the "profile busy" retries are gone.
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.group_session import STATE_PATH, open_context, save_state, IG_DOMAINS, _ua
    logged_in = STATE_PATH.exists()
    _STATUS.clear()
    _SESSION.clear()
    _SESSION.update({"logged_in": logged_in,
                     "note": "" if logged_in else f"no saved session at {STATE_PATH.name}"})
    if not logged_in:
        logger.warning("[ig_web] no saved session at %s — run tools/ig_profile_login.py; "
                       "reading logged out only", STATE_PATH)

    results: Dict[str, List[Dict]] = {}
    with sync_playwright() as p:
        try:
            browser, ctx = open_context(p, headless=True)
        except Exception as e:
            logger.warning("[ig_web] browser launch failed: %s", str(e)[:150])
            _SESSION["note"] = f"browser launch failed: {str(e)[:120]}"
            return {}
        anon = None   # cookie-less page, opened the first time the login can't see a handle
        try:
            page = ctx.new_page()
            if logged_in:
                page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                cookies = {c["name"] for c in ctx.cookies("https://www.instagram.com")}
                if "ds_user_id" not in cookies:
                    logger.warning("[ig_web] SESSION_MISSING — no Instagram login in the automation "
                                   "profile; reading logged out only. One-time fix: "
                                   "python tools/ig_profile_login.py")
                    logged_in = False
                    _SESSION.update({"logged_in": False,
                                     "note": "session file present but Instagram did not "
                                             "accept it (no ds_user_id cookie)"})
            for org, handles in handles_by_org.items():
                st = _STATUS[org] = {"handle": "", "via": "", "posts": 0, "attempts": []}
                for user in handles:
                    profile_url = f"https://www.instagram.com/{user}/"
                    items, err = _profile_posts(page, user) if logged_in else ([], "no Instagram login")
                    via = "login"
                    if err and (not logged_in or err.startswith(_HIDDEN_FROM_LOGIN)):
                        logger.info("[ig_web] %s @%s: %s — reading the logged-out page", org, user, err)
                        if anon is None:
                            anon = browser.new_context(
                                user_agent=_ua(browser.version), locale="en-US",
                                viewport={"width": 1280, "height": 900}).new_page()
                        items, anon_err = _loggedout_posts(anon, user)
                        if anon_err:
                            err = f"{err}; logged out: {anon_err}"
                        else:
                            err, via = "", "logged-out page"
                    if err:
                        logger.info("[ig_web] %s @%s: %s — trying next handle", org, user, err)
                        st["attempts"].append(f"@{user}: {err}"[:240])
                        time.sleep(random.uniform(2, 4))
                        continue
                    posts = _to_posts(items, profile_url)
                    if posts:
                        logger.info("[ig_web] %s: %d captioned posts via @%s (%s)",
                                    org, len(posts), user, via)
                        results[org] = posts
                        st.update({"handle": user, "via": via, "posts": len(posts)})
                        break
                    logger.info("[ig_web] %s @%s: 0 captioned posts", org, user)
                    st["attempts"].append(f"@{user} ({via}): profile read, 0 captioned posts")
                time.sleep(random.uniform(3, 6))  # polite pacing between venues
            if logged_in:
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


def status_for(source_name: str) -> Dict:
    """What the web pass did for one org (handle, via, posts, failed attempts),
    plus the session state. {} if the web pass has not run."""
    if _CACHE is None:
        return {}
    out = dict(_STATUS.get(source_name) or {"handle": "", "via": "", "posts": 0,
                                             "attempts": ["not attempted (browser pass ended early)"]})
    out["session"] = dict(_SESSION)
    return out


def _selftest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # @tulsaybr only: @imvalpal is the owner's personal feed and is never a YBR source.
    out = _collect({"ybr_ig": ["tulsaybr"]})
    posts = out.get("ybr_ig", [])
    print(f"ybr_ig posts: {len(posts)}")
    for p_ in posts[:8]:
        print(" ", p_["posted_on"], p_["caption"][:90].replace("\n", " "))
    return 0 if posts else 1


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
