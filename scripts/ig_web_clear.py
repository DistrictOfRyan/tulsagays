"""Open instagram.com in a headed browser so William can log in as @tulsagays and
clear an account-level security challenge that the private API (instagrapi) can't
resolve on its own (the bloks 'challenge_required' wall, 2026-06-19).

This does NOT save a session for the automation - the tulsagays pipeline logs in via
instagrapi separately (ig_login_api.py). The point of this is only to satisfy IG's
challenge in the official web UI: once the account passes a web verification, IG marks
it trusted and the subsequent instagrapi login (reusing the saved device) goes through.

Usage:
    python C:\\Users\\willi\\tulsagays\\scripts\\ig_web_clear.py
Then: log in as @tulsagays, complete any 'confirm it's you' / code step IG shows,
land on the home feed, close the window (or wait), and re-run ig_login_api.py.
"""
import time
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MAX_WAIT = 900  # 15 min


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.instagram.com/accounts/login/",
                  wait_until="domcontentloaded", timeout=60000)
        print("\n>>> instagram.com is open. Log in as @tulsagays.")
        print(">>> Complete any 'confirm it's you' / verification-code step IG shows.")
        print(">>> When you reach the home feed, this is done - close the window or wait.\n")
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            url = (page.url or "").lower()
            # Reached the authenticated app (not on a login/challenge URL)
            if ("instagram.com" in url and "/accounts/login" not in url
                    and "/challenge" not in url and "/two_factor" not in url):
                time.sleep(3)
                url2 = (page.url or "").lower()
                if "/accounts/login" not in url2 and "/challenge" not in url2:
                    print("DETECTED: you're past login/challenge on instagram.com. "
                          "Challenge should be cleared. Now re-run ig_login_api.py.")
                    break
            time.sleep(3)
        else:
            print("Window timed out. If you cleared the challenge, just re-run ig_login_api.py anyway.")
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
