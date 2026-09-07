"""Check and refresh the saved Facebook session before Monday's scrape.

Run this Sunday night (or any time) to verify the session is still valid.
If valid: refreshes the saved cookies so the 90-day expiry resets.
If expired: exits with code 1 so the caller knows to alert William.

Usage:
    python tools/check_fb_session.py
Exit codes:
    0 -- session valid and refreshed
    1 -- session expired or missing (needs manual re-login)
    2 -- playwright not installed
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SESSION_FILE = os.path.join(config.DATA_DIR, "fb_session.json")

# --- SECOND STORE (added 2026-09-04) -------------------------------------
# TulsaGays has TWO independent Facebook sessions and this script historically
# only knew about one, so a green verdict here could co-exist with a completely
# dead group blast:
#   * fb_session.json  (Playwright storage_state) -- event SCRAPER + page posting
#   * data/fb_auto_profile (persistent Chrome profile) -- GROUP blast
#     (tools/group_session.py), re-authed with tools/fb_profile_login.py
# Root cause of gap G646's week: the group profile was logged out for weeks while
# this checker reported only on the storage_state half, and its remediation line
# sent the reader to fb_login.py, which does not touch the group profile at all.
PROFILE_COOKIES = os.path.join(
    config.DATA_DIR, "fb_auto_profile", "Default", "Network", "Cookies"
)


def check_group_profile():
    """Read the group-blast Chrome profile's cookie jar directly.

    Returns (ok: bool, detail: str). Never raises -- a store we cannot read is
    reported as unknown rather than silently passing.
    """
    import shutil
    import sqlite3
    import tempfile

    if not os.path.exists(PROFILE_COOKIES):
        return False, f"no cookie store at {PROFILE_COOKIES}"
    tmp = os.path.join(tempfile.gettempdir(), "tg_fb_profile_cookies.db")
    try:
        shutil.copy(PROFILE_COOKIES, tmp)
    except PermissionError:
        return False, ("cookie store is LOCKED -- Chrome is still running on this "
                       "profile. Cookies only flush on a clean exit, so close that "
                       "window before trusting any verdict here.")
    except Exception as exc:
        return False, f"could not read cookie store: {exc}"
    try:
        con = sqlite3.connect(tmp)
        names = {
            r[0] for r in con.execute(
                "select name from cookies where host_key like '%facebook%'"
            )
        }
        con.close()
    except Exception as exc:
        return False, f"could not query cookie store: {exc}"
    if "c_user" in names and "xs" in names:
        return True, "c_user + xs present"
    missing = [n for n in ("c_user", "xs") if n not in names]
    return False, f"missing {', '.join(missing)} -- re-run tools/fb_profile_login.py"


LOGIN_MARKERS = [
    'id="loginbutton"',
    'name="login"',
    "log in to facebook",
    "you must log in",
    '"loginform"',
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(2)

    group_ok, group_detail = check_group_profile()
    print(f"[group blast  ] data/fb_auto_profile: "
          f"{'OK' if group_ok else 'DEAD'} ({group_detail})")
    print("[scraper/page ] data/fb_session.json: checking...")

    if not os.path.exists(SESSION_FILE):
        print(f"ERROR: No session file at {SESSION_FILE}")
        print("Run tools/fb_login.py first.")
        sys.exit(1)

    print(f"Checking FB session: {SESSION_FILE}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            storage_state=SESSION_FILE,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            page.goto("https://www.facebook.com/", timeout=20000, wait_until="domcontentloaded")
            import time as _t
            _t.sleep(3)
            html = page.content()
        except Exception as e:
            print(f"ERROR: Could not load facebook.com: {e}")
            browser.close()
            sys.exit(1)

        sample = html[:5000].lower()
        marker_hit = any(m in sample for m in LOGIN_MARKERS)

        # AUTHORITATIVE CHECK (added 2026-09-04): the c_user cookie is Facebook's own
        # "you are logged in as this user ID" cookie. Its absence is definitive proof
        # of no active session, regardless of what the logged-out homepage's HTML
        # happens to contain. The 5 hardcoded LOGIN_MARKERS string-matched the *page*
        # and false-positived "valid" on a session that had already lost its c_user/xs
        # cookies (Facebook silently changed the logged-out markup so none of the 5
        # strings appeared). Found via a raw cookie audit that directly contradicted
        # this script's own "Session valid" verdict on 2026-09-04 -- see
        # blocker_evidence.py receipt tulsagays-fb-reauth.
        cookies = context.cookies()
        has_login_cookie = any(
            c.get("name") == "c_user" and ".facebook.com" in c.get("domain", "")
            for c in cookies
        )
        expired = marker_hit or not has_login_cookie

        if expired:
            reason = "Facebook showed a login wall" if marker_hit else "no c_user auth cookie present"
            print(f"SESSION EXPIRED (scraper/page store) -- {reason}.")
            print("Re-run: python tools/fb_login.py")
            if not group_ok:
                print("ALSO DEAD (group blast store): re-run "
                      "python tools/fb_profile_login.py")
            browser.close()
            sys.exit(1)

        # Session is valid -- save refreshed cookies
        context.storage_state(path=SESSION_FILE)
        print("Scraper/page session valid. Cookies refreshed successfully.")
        browser.close()
        if not group_ok:
            # Do NOT exit 0 here. A green scraper session with a dead group
            # profile is exactly the state that let the Monday group blast go
            # dark for weeks while this script reported success.
            print("OVERALL: FAIL -- group blast profile is dead "
                  "(re-run python tools/fb_profile_login.py)")
            sys.exit(1)
        print("OVERALL: PASS -- both Facebook stores are live.")
        sys.exit(0)


if __name__ == "__main__":
    main()
