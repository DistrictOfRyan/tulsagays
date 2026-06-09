"""
One-time login into the dedicated TulsaGays FB automation profile.

Opens REAL Google Chrome (not Playwright's Chromium, which Facebook blocks at
login) pointed at a dedicated user-data-dir. William logs into Facebook once with
his personal account (the one that manages the Tulsa Gays page). After that, the
weekly group blast drives this profile headless via launch_persistent_context —
FB trusts real Chrome and the login persists for months, with the daily keepalive
keeping it warm. THIS is the one manual step, and it should only ever happen once
(plus the rare re-login if FB force-logs-out).

Usage: python tools/fb_profile_login.py
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "fb_auto_profile"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def main():
    chrome = next((c for c in CHROME_CANDIDATES if Path(c).exists()), None)
    if not chrome:
        print("Chrome not found in standard locations."); return 1
    PROFILE.mkdir(parents=True, exist_ok=True)
    # Separate --user-data-dir => its own Chrome instance, independent of the
    # user's normal Chrome (no profile-lock conflict).
    subprocess.Popen([
        chrome,
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.facebook.com/login",
    ])
    print("Opened a dedicated Chrome window for TulsaGays automation.")
    print("1. Log into Facebook with the account that manages the Tulsa Gays page.")
    print("2. (Optional) Switch to 'using Facebook as Tulsa Gays' — the blast also does this each run.")
    print("3. Close that Chrome window. The login is saved to the dedicated profile.")
    print(f"Profile dir: {PROFILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
