"""One-time Slack session login for the session-mode scraper.

Opens a VISIBLE browser to Slack. William logs into the Tulsa Remote workspace
(Google SSO, ~30s). The persistent Playwright profile then holds the session, and
slack_session_scraper.py reuses it headless every week — no app install, no admin.

Re-run this only when the weekly scraper reports code 2 (session expired), which
Slack does every few weeks. The session-health watcher pings William when that
happens, so this is a rare, deliberate step.

Usage:
  python scraper/slack_session_login.py
"""
import os
import sys
import time

PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".credentials", "slack_pw_profile")
TEAM_ID = "TF1E6FCR5"
# The WORKSPACE sign-in URL shows the SSO buttons (Sign in with Google) that
# TulsaRemote configured. The generic slack.com/signin hides them behind an
# email/workspace prompt, which is confusing (William, 2026-07-17).
SIGNIN_URL = "https://tulsaremote.slack.com/"

_CHECK = (
    "() => { try { const c = JSON.parse(localStorage.getItem('localConfig_v2'));"
    " return Object.values(c.teams||{}).some(t => t.token"
    " && t.token.startsWith('xoxc')); } catch(e){ return false; } }"
)


def main() -> int:
    os.makedirs(os.path.dirname(PROFILE_DIR), exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"playwright not installed: {e}\n  pip install playwright && python -m playwright install chromium")
        return 5

    print("=" * 64)
    print("  SLACK SESSION LOGIN (one time)")
    print("  A browser will open. Log into the TULSA REMOTE workspace.")
    print("  When you're in and see channels, come back here — it auto-detects.")
    print("=" * 64)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE_DIR, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # Workspace sign-in first (shows the Google SSO button directly).
            page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            page.goto("https://slack.com/signin")

        deadline = time.time() + 420  # 7 minutes to finish logging in
        ok = False
        while time.time() < deadline:
            try:
                if page.evaluate(_CHECK):
                    ok = True
                    break
            except Exception:
                pass
            time.sleep(3)

        if ok:
            page.wait_for_timeout(2500)  # let the token settle before we save
            print("\n✅ Logged in and session saved. The weekly scraper is now armed.")
            print(f"   Profile: {PROFILE_DIR}")
        else:
            print("\n⏱  Timed out waiting for login. Re-run and finish signing in faster.")
        ctx.close()
        return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
