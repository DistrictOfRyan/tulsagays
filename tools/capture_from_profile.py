"""
Capture the Facebook group session from William's real, logged-in Chrome profile
into data/fb_group_auth.json — no interactive login, no separate browser window.

Why: the headed-login capture didn't work for William (couldn't interact with the
browser the task opened), and Meta has no group API. His real Chrome (Profile 1)
is logged into FB as the Tulsa Gays page. This launches REAL Chrome (channel=
chrome) headless against a COPY of that profile so Chrome decrypts its own
app-bound cookies, confirms the FB session, and exports a storage_state the
headless group_blast + daily keepalive can reuse.

Usage: python tools/capture_from_profile.py [--profile "Profile 1"]
Exit 0 = session captured. Exit 1 = not logged in / failed.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "fb_group_auth.json"
USER_DATA = Path(r"C:\Users\willi\AppData\Local\Google\Chrome\User Data")

profile = "Profile 1"
if "--profile" in sys.argv:
    profile = sys.argv[sys.argv.index("--profile") + 1]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("playwright missing"); return 1

    src_profile = USER_DATA / profile
    src_localstate = USER_DATA / "Local State"
    if not src_profile.exists():
        print(f"profile not found: {src_profile}"); return 1

    tmp = Path(tempfile.mkdtemp(prefix="fbcap_"))
    try:
        # Build a minimal user-data-dir: Local State (holds the app-bound key) +
        # Default = copy of the target profile. Copy cookies/login files only.
        (tmp / "Default").mkdir(parents=True, exist_ok=True)
        if src_localstate.exists():
            shutil.copy2(src_localstate, tmp / "Local State")
        import subprocess
        def _force_copy(s: Path, d: Path):
            d.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(s, d)
                return True
            except Exception:
                # Chrome holds an exclusive lock on Cookies; robocopy /B (backup
                # mode) can read locked files.
                r = subprocess.run(
                    ["robocopy", str(s.parent), str(d.parent), s.name,
                     "/B", "/R:1", "/W:1", "/NJH", "/NJS", "/NP", "/NDL"],
                    capture_output=True, text=True)
                return d.exists()
        for rel in ["Network/Cookies", "Network/Network Persistent State",
                    "Preferences", "Secure Preferences", "Login Data"]:
            s = src_profile / rel
            d = tmp / "Default" / rel
            if s.exists():
                if not _force_copy(s, d):
                    print(f"  (could not copy {rel})")

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(tmp), channel="chrome", headless=True,
                args=["--no-first-run", "--no-default-browser-check"])
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            names = {c["name"] for c in ctx.cookies()}
            logged_in = "c_user" in names
            login_form = False
            try:
                login_form = pg.locator('input[name="email"]').count() > 0 and \
                    pg.locator('input[name="pass"]').count() > 0
            except Exception:
                pass
            if logged_in and not login_form:
                ctx.storage_state(path=str(AUTH_PATH))
                cu = [c["value"] for c in ctx.cookies() if c["name"] == "c_user"]
                print(f"CAPTURED: logged-in FB session saved to {AUTH_PATH} (c_user={cu})")
                ctx.close()
                return 0
            ctx.close()
            print(f"NOT logged in (c_user={'yes' if logged_in else 'no'}, login_form={login_form})")
            return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
