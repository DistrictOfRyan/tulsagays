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
        expired = any(m in sample for m in LOGIN_MARKERS)

        if expired:
            print("SESSION EXPIRED -- Facebook is showing a login wall.")
            print("Re-run: python tools/fb_login.py")
            browser.close()
            sys.exit(1)

        # Session is valid -- save refreshed cookies
        context.storage_state(path=SESSION_FILE)
        print("Session valid. Cookies refreshed successfully.")
        browser.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
