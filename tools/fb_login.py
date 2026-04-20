"""One-time Facebook login helper.

Launches a headed Chromium browser so you can log in to Facebook.
After you're logged in, press Enter here and the session is saved to
data/fb_session.json -- the Facebook events scraper reads from there.

Run this once (or whenever the saved session expires):
    python tools/fb_login.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SESSION_FILE = os.path.join(config.DATA_DIR, "fb_session.json")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    config.ensure_dirs()

    print("=" * 60)
    print("Facebook Login Helper -- Tulsa Gays Event Scraper")
    print("=" * 60)
    print()
    print("A browser will open. Log in to Facebook as the Tulsa Gays")
    print("account (or any account that can see LGBTQ Tulsa events).")
    print()
    print("Once you're logged in and your news feed is visible,")
    print("come back here and press Enter to save the session.")
    print()
    print(f"Session will be saved to: {SESSION_FILE}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.facebook.com/login")

        print("Browser opened. Log in to Facebook...")
        print()
        input("Press Enter once you're logged in and can see your news feed: ")

        context.storage_state(path=SESSION_FILE)
        print(f"\nSession saved to: {SESSION_FILE}")

        browser.close()

    print()
    print("Done! Run the scraper now:")
    print("    python tools/test_fb_events.py")
    print()
    print("The session stays valid until you change your Facebook password")
    print("or Facebook expires it. Re-run this script if you see login wall errors.")


if __name__ == "__main__":
    main()
