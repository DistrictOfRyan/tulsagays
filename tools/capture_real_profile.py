"""
Capture FB session by launching REAL Chrome on the REAL profile (no copy).

The profile-COPY approach fails on Chrome 127+ app-bound cookie encryption. But
when Chrome is fully closed, launching the real Chrome binary (channel=chrome)
directly on the real user-data-dir + --profile-directory decrypts its own cookies
natively. Run ONLY while Chrome is closed. Captures storage_state ->
data/fb_group_auth.json. Closes cleanly so it doesn't hold the profile lock.

Usage: python tools/capture_real_profile.py [--profile-directory "Profile 1"]
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "fb_group_auth.json"
USER_DATA = r"C:\Users\willi\AppData\Local\Google\Chrome\User Data"

prof = "Profile 1"
if "--profile-directory" in sys.argv:
    prof = sys.argv[sys.argv.index("--profile-directory") + 1]


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=USER_DATA, channel="chrome", headless=True,
            timeout=150000,
            args=[f"--profile-directory={prof}", "--no-first-run",
                  "--no-default-browser-check", "--disable-extensions",
                  "--disable-background-networking", "--disable-sync",
                  "--disable-component-update"])
        try:
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            names = {c["name"] for c in ctx.cookies()}
            login_form = False
            try:
                login_form = pg.locator('input[name="pass"]').count() > 0
            except Exception:
                pass
            if "c_user" in names and not login_form:
                ctx.storage_state(path=str(AUTH_PATH))
                cu = [c["value"] for c in ctx.cookies() if c["name"] == "c_user"]
                print(f"CAPTURED FB session -> {AUTH_PATH} (c_user={cu})")
                return 0
            print(f"NOT logged in (c_user={'yes' if 'c_user' in names else 'no'}, login_form={login_form})")
            return 1
        finally:
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())
