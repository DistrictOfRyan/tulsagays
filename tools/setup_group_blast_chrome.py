"""
One-time setup: save Facebook login state for the group blaster
using a real Chrome window (not Playwright Chromium).

Usage:  python tools/setup_group_blast_chrome.py
"""
import subprocess, sys, time, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "fb_group_auth.json"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\willi\AppData\Local\Google\Chrome\Application\chrome.exe",
]

CDP_PORT = 9223   # 9222 may already be in use

def main():
    chrome = next((p for p in CHROME_PATHS if Path(p).exists()), None)
    if not chrome:
        sys.exit("Chrome not found — check CHROME_PATHS in this script.")

    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Opening Chrome for Facebook login...")
    print("(This is a separate window from your existing Chrome.)")
    proc = subprocess.Popen([
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "https://www.facebook.com/",
    ])

    print("\n1. Log into Facebook in the Chrome window that just opened.")
    print("2. Once you're logged in and see your feed, come back here.")
    input("Press Enter when you're logged in: ")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            ctx = browser.contexts[0] if browser.contexts else None
            if not ctx:
                sys.exit("No browser context found. Make sure Chrome opened.")
            ctx.storage_state(path=str(AUTH_PATH))
            print(f"\nSaved auth -> {AUTH_PATH}")
            print("Group blaster is now ready for hands-off Monday posting.")
            browser.close()
        except Exception as e:
            sys.exit(f"CDP connection failed: {e}\nMake sure Chrome opened on port {CDP_PORT}.")

    try:
        proc.terminate()
    except Exception:
        pass

if __name__ == "__main__":
    main()
