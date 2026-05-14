"""Post to a Facebook Group via Playwright (browser automation).

Meta's Graph API deprecated `publish_to_groups` in April 2024. There is
no programmatic path through the API for third-party apps to post to a
group anymore. This module gets around that by driving the regular
Facebook web UI through a headless Chromium controlled by Playwright,
the same way a human would.

Usage
-----
First-time setup on the machine that will run this:

    pip install playwright
    playwright install chromium

Then a one-time interactive login to capture an auth cookie:

    python -m posting.group_post --setup

A Chromium window will open. Log into Facebook as an account that has
permission to post in the HHHH group. After you're in and you can see
the group page, return to the terminal and press Enter. Auth state is
saved to data/fb_group_auth.json (gitignored via the existing data/ rule).

Once the auth state exists, post via:

    python -m posting.group_post "your caption text"
    python -m posting.group_post "your caption" path/to/img1.jpg path/to/img2.jpg

Configure HHHH_GROUP_URL in .env (full URL like
https://www.facebook.com/groups/123456789012345). The script only knows
which group to open because of that env var.

Notes
-----
- This is browser automation against a UI Meta can change at any time.
  If a future FB redesign breaks the selectors below, update them here.
- Keep the auth file off shared machines. Anyone with read access to
  data/fb_group_auth.json can post as that account until the session
  expires or you log out from FB.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config

AUTH_PATH = ROOT / "data" / "fb_group_auth.json"
GROUP_URL_ENV = "HHHH_GROUP_URL"


def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )


def setup_auth():
    """Open a headed browser so the user can log in once. Save state."""
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    group_url = os.environ.get(GROUP_URL_ENV, "https://www.facebook.com/")

    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(group_url)

        print("A browser window has opened.")
        print("Log into Facebook as the HHHH group poster account.")
        print("When you can see the group page (or your news feed), come back here and press Enter.")
        input("Press Enter when done: ")

        context.storage_state(path=str(AUTH_PATH))
        browser.close()
    print(f"Saved auth state to {AUTH_PATH}")


def post_to_group(message: str, image_paths=None):
    """Post a message (and optional images) to the configured FB group."""
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    group_url = os.environ.get(GROUP_URL_ENV, "")
    if not group_url:
        raise SystemExit(f"Set {GROUP_URL_ENV} in .env to the full group URL.")
    if not AUTH_PATH.exists():
        raise SystemExit(
            f"No saved auth at {AUTH_PATH}. Run with --setup first."
        )

    image_paths = [str(Path(p).resolve()) for p in (image_paths or [])]
    for p in image_paths:
        if not Path(p).exists():
            raise SystemExit(f"image not found: {p}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(AUTH_PATH))
        page = context.new_page()
        page.goto(group_url, wait_until="domcontentloaded")

        # Open the composer. Facebook's selectors change often; try a few.
        composer_selectors = [
            'div[role="button"]:has-text("Write something")',
            'div[role="button"]:has-text("Create post")',
            '[aria-label="Create a public post…"]',
        ]
        opened = False
        for sel in composer_selectors:
            try:
                page.locator(sel).first.click(timeout=4000)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            browser.close()
            raise SystemExit(
                "Could not find the post composer. The FB UI may have changed; "
                "update the selectors in posting/group_post.py."
            )

        # Type the caption into the textbox in the modal.
        text_selectors = [
            'div[role="dialog"] [contenteditable="true"]',
            '[role="textbox"][contenteditable="true"]',
        ]
        typed = False
        for sel in text_selectors:
            try:
                box = page.locator(sel).first
                box.click(timeout=4000)
                box.type(message, delay=20)
                typed = True
                break
            except Exception:
                continue
        if not typed:
            browser.close()
            raise SystemExit("Could not find the post text box.")

        # Attach images if any.
        for img in image_paths:
            try:
                page.set_input_files('input[type="file"]', img, timeout=4000)
                page.wait_for_timeout(1500)
            except Exception:
                browser.close()
                raise SystemExit(f"Could not attach image: {img}")

        # Submit.
        submit_selectors = [
            'div[role="dialog"] div[aria-label="Post"]',
            'div[aria-label="Post"][role="button"]',
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                page.locator(sel).first.click(timeout=4000)
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            browser.close()
            raise SystemExit("Could not find the Post submit button.")

        # Wait long enough for the dialog to close and the post to appear.
        page.wait_for_timeout(8000)
        browser.close()
    return {"ok": True, "group_url": group_url}


def _main():
    if "--setup" in sys.argv:
        setup_auth()
        return

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m posting.group_post --setup")
        print('  python -m posting.group_post "caption text" [image_path ...]')
        sys.exit(1)

    message = sys.argv[1]
    images = sys.argv[2:] or None
    result = post_to_group(message, image_paths=images)
    print(result)


if __name__ == "__main__":
    _main()
