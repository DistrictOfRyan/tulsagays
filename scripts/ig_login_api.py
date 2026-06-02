"""
ig_login_api.py - ONE-TIME @tulsagays login via the Instagram private API (instagrapi).

No browser, so no captcha loop. You enter the @tulsagays username + password once
(password is hidden, never printed or logged) and, if Instagram asks, one verification
code from your phone/email. It saves a device+session file to
~/.credentials/ig_settings_tulsagays.json. After this, engagement runs 100% on its own.

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
        from instagrapi.exceptions import TwoFactorRequired
    except ImportError:
        print("instagrapi not installed. Run: python -m pip install instagrapi")
        return 1

    user = (input("Instagram username [tulsagays]: ").strip() or "tulsagays").lstrip("@")
    pw = getpass.getpass("Instagram password (hidden): ")
    if not pw:
        print("No password entered. Aborting.")
        return 1

    cl = Client()
    # If IG throws an email/SMS challenge, prompt for the code.
    cl.challenge_code_handler = lambda username, choice: input(
        f"Enter the verification code Instagram sent via {choice}: ").strip()

    print("\nLogging in via the private API (no browser)...")
    try:
        try:
            cl.login(user, pw)
        except TwoFactorRequired:
            code = input("Enter your 2FA code (authenticator app or SMS): ").strip()
            cl.login(user, pw, verification_code=code)
    except Exception as e:
        print(f"\n[FAIL] login error: {type(e).__name__}: {str(e)[:200]}")
        print("If it mentions a challenge/checkpoint, re-run and enter the code IG sends.")
        return 1

    try:
        me = cl.account_info()
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(SETTINGS_FILE))
        print(f"\n[OK] Logged in as @{me.username}. Session saved -> {SETTINGS_FILE}")
        print("Engagement is now 100% automated. Tell Claude 'IG login done' to run a live check + first engage.")
        return 0
    except Exception as e:
        print(f"[FAIL] logged in but could not verify/save: {type(e).__name__}: {str(e)[:160]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
