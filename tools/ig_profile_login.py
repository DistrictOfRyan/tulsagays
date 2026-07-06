"""
One-time Instagram login into the dedicated TulsaGays automation profile.

Same pattern as fb_profile_login.py (real Chrome, dedicated user-data-dir) and
the SAME profile dir — one profile carries both the FB and IG web sessions.

Why this exists (2026-07-06): every API-side Instagram login is walled
(instagrapi -> bloks challenge; FB-OAuth mint -> dead-ends at /accounts/login),
and BOTH YBR accounts (@tulsaybr, @imvalpal) are personal accounts, so Meta App
Review / business_discovery can never read them. A normal WEB session in real
Chrome is the only path — and once it exists, scraper/instagram_web.py drives
this profile headless to read venue feeds via Instagram's own web API
(/api/v1/users/web_profile_info + /api/v1/feed/user), verified working
2026-07-06 from a logged-in session.

William logs in ONCE as @tulsagays (solving any checkpoint in the window), then
closes it. The login persists for months like the FB one.

Usage: python tools/ig_profile_login.py
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
    subprocess.Popen([
        chrome,
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.instagram.com/accounts/login/",
    ])
    print("Opened the dedicated TulsaGays automation Chrome at the Instagram login page.")
    print("1. Log in as @tulsagays (username tulsagays + its password).")
    print("2. Solve any 'suspicious login' checkpoint in the window if Instagram asks.")
    print("3. If asked 'Save your login info?' click Save.")
    print("4. Close that Chrome window. The session is saved to the dedicated profile.")
    print(f"Profile dir: {PROFILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
