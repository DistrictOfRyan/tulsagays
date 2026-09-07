"""Export the scraper/page session (data/fb_session.json) from the ALREADY
logged-in group-blast Chrome profile (data/fb_auto_profile).

Why this exists (2026-09-04): TulsaGays keeps two independent Facebook sessions
-- data/fb_auto_profile (persistent Chrome, group blast) and data/fb_session.json
(Playwright storage_state, event scraper + page posting). They expire separately,
so William was being asked to log in twice for what is one Facebook account. He
had already re-authed the profile; this derives the second store from it instead
of sending him back to a login screen.

Reads the profile READ-ONLY via a temp copy, so it never disturbs the group blast.

Usage: python tools/export_scraper_session_from_profile.py
Exit 0 = exported. Exit 1 = profile not logged in / failed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "fb_auto_profile"
OUT = ROOT / "data" / "fb_session.json"


def _force_copy(s: Path, d: Path) -> bool:
    d.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(s, d)
        return True
    except Exception:
        # Chrome takes an exclusive lock on Cookies; robocopy /B reads locked files.
        subprocess.run(
            ["robocopy", str(s.parent), str(d.parent), s.name,
             "/B", "/R:1", "/W:1", "/NJH", "/NJS", "/NP", "/NDL"],
            capture_output=True, text=True)
        return d.exists()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("playwright missing")
        return 1

    if not PROFILE.exists():
        print(f"profile not found: {PROFILE}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="fbexport_"))
    try:
        (tmp / "Default").mkdir(parents=True, exist_ok=True)
        ls = PROFILE / "Local State"
        if ls.exists():
            _force_copy(ls, tmp / "Local State")
        for rel in ["Network/Cookies", "Network/Network Persistent State",
                    "Preferences", "Secure Preferences", "Login Data"]:
            s = PROFILE / "Default" / rel
            if s.exists():
                if not _force_copy(s, tmp / "Default" / rel):
                    print(f"  (could not copy {rel})")

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(tmp), channel="chrome", headless=True,
                args=["--no-first-run", "--no-default-browser-check"])
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/",
                    wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            names = {c["name"] for c in ctx.cookies()}
            if "c_user" not in names:
                ctx.close()
                print("NOT logged in in the group profile (no c_user). "
                      "Re-run tools/fb_profile_login.py first.")
                return 1
            ctx.storage_state(path=str(OUT))
            cu = [c["value"] for c in ctx.cookies() if c["name"] == "c_user"]
            ctx.close()
            print(f"EXPORTED: {OUT} (c_user={cu})")
            return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
