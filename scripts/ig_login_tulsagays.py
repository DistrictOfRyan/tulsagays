"""
ig_login_tulsagays.py - ONE-TIME @tulsagays Instagram login (two-phase, beats the
automated-browser captcha wall).

Instagram refuses to render its login reCAPTCHA in any automation-attached browser
(Playwright OR a Chrome started with --remote-debugging-port). So:

  Phase 1 (login): open a CLEAN real Chrome on a dedicated profile with NO debug
                   flags -> indistinguishable from a normal browser -> the captcha
                   renders and you log in normally. The session saves to the profile.
  Phase 2 (verify): after you close Chrome, relaunch that SAME (now logged-in)
                    profile headless WITH the debug port and attach via CDP just to
                    confirm the sessionid exists. No login happens, so no captcha.

Run at your terminal (NOT scheduled):
    python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_tulsagays.py
No password is stored by us; the session lives in the dedicated profile dir.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from posting import ig_chrome  # noqa: E402

SESSION_FILE = Path.home() / ".credentials" / "ig_session_tulsagays.json"


def _verify_and_save() -> bool:
    """Relaunch the profile headless + CDP, confirm sessionid, save storage_state."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed.")
        return False
    proc, endpoint = ig_chrome.launch(headless=True)
    if not endpoint:
        print("Could not relaunch Chrome for verification.")
        ig_chrome.kill(proc)
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)
            ok = any(c.get("name") == "sessionid" and c.get("value") for c in ctx.cookies())
            if ok:
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(SESSION_FILE))
            browser.close()
            return ok
    except Exception as e:
        print(f"verify error: {type(e).__name__}: {str(e)[:140]}")
        return False
    finally:
        ig_chrome.kill(proc)


def main() -> int:
    print("Opening a CLEAN Chrome (no automation flags) so the login captcha works...")
    proc = ig_chrome.launch_clean("https://www.instagram.com/accounts/login/")
    if proc is None:
        print(f"Could not start Chrome. Is chrome.exe at {ig_chrome.CHROME_EXE}?")
        return 1

    print("\n" + "=" * 70)
    print("A normal Chrome window opened. Log in to @tulsagays:")
    print("  - enter the @tulsagays username + password")
    print("  - solve any captcha (it will render now) and clear 2FA")
    print("  - get to your HOME FEED")
    print("  - if 'Save your login info?' appears, click Not now")
    print("THEN: fully CLOSE that Chrome window (so the session flushes to disk),")
    print("and come back here.")
    print("=" * 70)

    for attempt in range(4):
        try:
            input("\nAfter you've logged in AND closed the Chrome window, press Enter... ")
        except EOFError:
            print("No interactive stdin; run this in a real terminal.")
            return 1
        # make sure the clean chrome is fully closed, then verify via CDP
        ig_chrome.kill_existing()
        time.sleep(1)
        print("Verifying the saved session...")
        if _verify_and_save():
            print(f"\n[OK] Logged in! Session saved to the @tulsagays profile + {SESSION_FILE}.")
            print("Tell Claude 'finished the IG login' and it'll run a live check + first engage.")
            return 0
        print("[!] No logged-in session detected yet.")
        if attempt < 3:
            print("Re-opening a clean Chrome so you can finish logging in...")
            proc = ig_chrome.launch_clean("https://www.instagram.com/accounts/login/")
            if proc is None:
                return 1
    print("\nABORTED: never detected a logged-in session. Nothing saved. Re-run when ready.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
