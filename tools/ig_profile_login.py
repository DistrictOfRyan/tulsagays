"""
One-time Instagram login for the TulsaGays web-session scraper.

scraper/instagram_web.py reads venue feeds through Instagram's own web API from
a logged-in session (every API-side login is walled, and both YBR accounts are
personal, so business_discovery can never read them). This opens a real Chrome
window at the Instagram login page; log in as the account the scraper should
read as (@tulsagays is the intent; on 2026-10-22 the saved session was
@districtofryan). The script saves the Instagram cookies into
data/fb_session.json (the Facebook login there is kept), proves them headless,
closes the window, and runs the two-round restart test.

WHY (2026-10-22): this used to leave the login inside data/fb_auto_profile.
Chrome seals that profile's cookies with DPAPI, and while DPAPI was broken
(10/7-10/21) every Chrome exit dropped them. data/fb_session.json needs no DPAPI.
Root cause: ~/.claude/drafts/security/dpapi-2026-10-22.md

Usage: python tools/ig_profile_login.py [--wait MINUTES]
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
    print("Log into Instagram in the Chrome window that opens; solve any checkpoint there.")
    return storage_session.capture("tulsagays-ig", wait_min=wait)


if __name__ == "__main__":
    sys.exit(main())
