"""
One-time Facebook login for the TulsaGays automation.

Opens real Google Chrome (plain chrome.exe, not a Playwright browser) on the
dedicated data/fb_auto_profile, at facebook.com/login. William logs in with the
account that manages the Tulsa Gays Page. The script then reads the live
session over the DevTools port, proves it in a separate headless browser, saves
it into data/fb_session.json (Facebook cookies only; the Instagram login in that
file is kept), closes the window, and runs the two-round restart test.

WHY (2026-10-22): this used to leave the login inside the persistent profile and
let the group blast reuse the profile. Chrome seals that profile's cookies with
DPAPI, and while DPAPI was broken (10/7-10/21) every Chrome exit dropped the
login, so this "one-time" step kept coming back. The jobs now read
data/fb_session.json (tools/group_session.py), which needs no DPAPI.
Root cause: ~/.claude/drafts/security/dpapi-2026-10-22.md

Usage: python tools/fb_profile_login.py [--wait MINUTES]
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
VAULT_SCRIPTS = Path.home() / ".claude" / "scripts"


def main():
    wait = 30
    if "--wait" in sys.argv:
        wait = int(sys.argv[sys.argv.index("--wait") + 1])
    sys.path.insert(0, str(VAULT_SCRIPTS))
    try:
        import storage_session
    except ImportError as e:
        print(f"Cannot load {VAULT_SCRIPTS / 'storage_session.py'}: {e}")
        return 2
    print("Log into Facebook in the Chrome window that opens (the account that manages the Tulsa Gays Page).")
    return storage_session.capture("tulsagays-fb", wait_min=wait)


if __name__ == "__main__":
    sys.exit(main())
