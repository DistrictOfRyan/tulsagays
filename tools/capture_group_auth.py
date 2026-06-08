"""
Non-blocking Facebook auth capture for the group blaster.

posting/group_blast.py --setup uses input("Press Enter...") which can't run from
a non-interactive shell. This opens a VISIBLE browser, navigates to Facebook,
and POLLS for the logged-in `c_user` cookie (no terminal keypress needed). Once
William logs in in the window, it saves the session to data/fb_group_auth.json
and exits. Safe to run from an automation shell because login is auto-detected.

Usage:  python tools/capture_group_auth.py [--timeout 360]
Exit 0 = fresh auth saved. Exit 1 = timed out (William didn't finish logging in).
"""
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "fb_group_auth.json"

TIMEOUT = 360
if "--timeout" in sys.argv:
    try:
        TIMEOUT = int(sys.argv[sys.argv.index("--timeout") + 1])
    except Exception:
        pass


def main():
    from playwright.sync_api import sync_playwright
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False)
        ctx = b.new_context()
        pg = ctx.new_page()
        pg.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        print(f"[capture] Browser open. Log into Facebook as the Tulsa Gays Page "
              f"manager. Waiting up to {TIMEOUT}s for login...", flush=True)
        deadline = time.time() + TIMEOUT
        saved = False
        while time.time() < deadline:
            try:
                names = {c["name"] for c in ctx.cookies()}
            except Exception:
                names = set()
            if "c_user" in names:
                # Logged in. Let the session settle, then capture.
                time.sleep(4)
                ctx.storage_state(path=str(AUTH_PATH))
                print(f"[capture] LOGGED IN — saved fresh auth to {AUTH_PATH}", flush=True)
                saved = True
                break
            time.sleep(3)
        b.close()
    if not saved:
        print("[capture] TIMEOUT — no login detected. Auth NOT saved.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
