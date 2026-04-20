"""Save Facebook session for the event scraper.

Two modes:
  --cdp    Try to connect to a running Chrome via CDP (launch Chrome first,
           log in, then run this). Requires Chrome opened with:
           chrome.exe --remote-debugging-port=9222

  (default) Opens a fresh Playwright Chromium browser for manual login.
           Safest, always works.

Usage:
    python tools/fb_save_session.py           # fresh Playwright browser
    python tools/fb_save_session.py --cdp     # connect to running Chrome
"""

import os
import sys
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SESSION_FILE = os.path.join(config.DATA_DIR, "fb_session.json")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\willi\AppData\Local\Google\Chrome\Application\chrome.exe",
]


def save_via_playwright():
    """Open a fresh Playwright browser for manual Facebook login."""
    from playwright.sync_api import sync_playwright
    config.ensure_dirs()

    print("=" * 60)
    print("Facebook Login -- Tulsa Gays Event Scraper")
    print("=" * 60)
    print()
    print("A browser window will open. Log in to Facebook as the")
    print("account you use to see Tulsa LGBTQ events.")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--start-maximized"],
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

        input("\nLog in to Facebook, then press Enter here: ")

        # Verify we're actually logged in
        current_url = page.url
        html = page.content()
        if "log in" in html[:2000].lower() and "loginbutton" in html[:2000].lower():
            print("WARNING: Doesn't look like login completed. Try again.")
        else:
            context.storage_state(path=SESSION_FILE)
            print(f"\nSession saved to: {SESSION_FILE}")
            print("Run: python tools/test_fb_events.py --next")

        browser.close()


def save_via_cdp():
    """Connect to a running Chrome via CDP and extract the session."""
    import time
    from playwright.sync_api import sync_playwright
    config.ensure_dirs()

    print("=" * 60)
    print("Connect to running Chrome via CDP")
    print("=" * 60)
    print()

    # Try to find Chrome
    chrome_path = None
    for path in CHROME_PATHS:
        if os.path.exists(path):
            chrome_path = path
            break

    if not chrome_path:
        print("ERROR: Chrome not found. Using Playwright browser instead.")
        save_via_playwright()
        return

    print(f"Chrome found: {chrome_path}")
    print()
    print("Launching Chrome with remote debugging...")
    print("This opens a SEPARATE Chrome window -- your existing Chrome stays open.")
    print()

    cdp_port = 9222
    proc = subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "https://www.facebook.com/login",
    ])

    print("Chrome opened. Log in to Facebook in the new window.")
    input("Press Enter once you're logged in: ")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
            contexts = browser.contexts
            if not contexts:
                print("ERROR: No browser contexts found.")
                proc.terminate()
                return

            context = contexts[0]
            context.storage_state(path=SESSION_FILE)
            print(f"\nSession saved to: {SESSION_FILE}")
            print("Run: python tools/test_fb_events.py --next")
            browser.close()
        except Exception as e:
            print(f"CDP connection failed: {e}")
            print("Falling back to manual Playwright login...")
            proc.terminate()
            save_via_playwright()
            return

    proc.terminate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", action="store_true", help="Connect to running Chrome via CDP")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    if args.cdp:
        save_via_cdp()
    else:
        save_via_playwright()
