"""
ig_login_api.py - @tulsagays login via the Instagram private API (instagrapi).

No browser, so no web captcha loop. You enter the @tulsagays username + password and,
if Instagram asks, one verification code. It saves a device+session file to
~/.credentials/ig_settings_tulsagays.json. After this, engagement + the Studio 66
scraper run on their own.

IMPORTANT (fixed 2026-06-03): this script now REUSES the device fingerprint stored in
the existing session file instead of generating a new random device on every login.
Instagram's challenge/checkpoint system is device-based: a brand-new device fingerprint
each login looks like a new suspicious device, which (a) triggers the challenge wall and
(b) makes the session die within hours. Logging in on a device Instagram has already
seen avoids most challenges and makes the session stick.

If you still hit a challenge ("Was this you?" / checkpoint): open the Instagram app on
your phone logged in as @tulsagays, approve the login alert, then re-run this script.

Run at your terminal:
    python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_api.py
Re-run only if a run later reports the session expired.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"


def main() -> int:
    try:
        from instagrapi import Client
        from instagrapi.exceptions import TwoFactorRequired, LoginRequired
    except ImportError:
        print("instagrapi not installed. Run: python -m pip install instagrapi")
        return 1

    user = (input("Instagram username [tulsagays]: ").strip() or "tulsagays").lstrip("@")
    pw = getpass.getpass("Instagram password (hidden): ")
    if not pw:
        print("No password entered. Aborting.")
        return 1

    cl = Client()
    cl.delay_range = [1, 3]  # human-like pacing between requests (instagrapi recommended)
    # If IG throws an email/SMS challenge, prompt for the code.
    cl.challenge_code_handler = lambda username, choice: input(
        f"Enter the verification code Instagram sent via {choice}: ").strip()

    # Reuse the saved device fingerprint so Instagram sees a known device, not a new
    # one. This is the single biggest factor in avoiding the challenge loop and in
    # keeping the session alive longer.
    old_uuids = None
    old_device = None
    if SETTINGS_FILE.exists():
        try:
            cl.load_settings(str(SETTINGS_FILE))
            settings = cl.get_settings()
            old_uuids = settings.get("uuids")
            old_device = settings.get("device_settings")
            print("Reusing the saved device fingerprint from a previous login "
                  "(fewer challenges, longer-lived session).")
        except Exception:
            old_uuids = None

    print("\nLogging in via the private API (no browser)...")
    try:
        try:
            cl.login(user, pw)
        except TwoFactorRequired:
            code = input("Enter your 2FA code (authenticator app or SMS): ").strip()
            cl.login(user, pw, verification_code=code)
    except Exception as e:
        msg = str(e)
        print(f"\n[FAIL] login error: {type(e).__name__}: {msg[:200]}")
        if "challenge" in msg.lower() or "ChallengeUnknownStep" in type(e).__name__ + msg:
            print(
                "\nThis is Instagram's checkpoint wall. instagrapi can't auto-clear this\n"
                "newer challenge type. To clear it:\n"
                "  1. Open the Instagram app on your phone logged in as @tulsagays.\n"
                "  2. Approve the 'Was this you? / We noticed a new login' alert (tap Yes).\n"
                "  3. Re-run this script. Because it now reuses the saved device, IG should\n"
                "     recognize it and let you in without challenging again.\n"
            )
        else:
            print("If it mentions a code/checkpoint, re-run and enter the code IG sends.")
        return 1

    # Validate the session. If the auth is stale but we have a known device, reset the
    # auth state while KEEPING the device uuids and try once more (canonical instagrapi
    # resilience pattern).
    try:
        cl.get_timeline_feed()
    except LoginRequired:
        if old_uuids:
            print("Auth was stale; retrying on the same device (keeping uuids)...")
            cl.set_settings({})
            cl.set_uuids(old_uuids)
            if old_device:
                cl.set_device(old_device)
            try:
                cl.login(user, pw)
                cl.get_timeline_feed()
            except Exception as e:
                print(f"[FAIL] retry on saved device failed: {type(e).__name__}: {str(e)[:160]}")
                return 1
        else:
            print("[FAIL] session did not validate and no saved device to reuse.")
            return 1
    except Exception as e:
        print(f"[FAIL] could not validate session: {type(e).__name__}: {str(e)[:160]}")
        return 1

    try:
        me = cl.account_info()
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(SETTINGS_FILE))
        print(f"\n[OK] Logged in as @{me.username}. Session saved -> {SETTINGS_FILE}")
        print("Engagement + Studio 66 scraper are now wired. Tell Claude 'IG login done' "
              "to run a live check.")
        return 0
    except Exception as e:
        print(f"[FAIL] logged in but could not verify/save: {type(e).__name__}: {str(e)[:160]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
