"""Delete a TulsaGays Instagram post through the signed-in browser profile.

Why this exists (2026-09-15): the Instagram Graph API has no DELETE for media
(`DELETE /{ig-media-id}` answers `(#10) Insufficient permissions`), so when a
published carousel is WRONG (W38 shipped a 2025 Fringe Festival as Event of the
Week) the only path is the web UI. This drives the same persistent real-Chrome
profile the FB group blast uses (`data/fb_auto_profile`, logged into Instagram
via Facebook) and clicks "More options" -> "Delete" -> "Delete".

Usage:
    python posting/ig_retract.py --permalink https://www.instagram.com/p/<code>/ --week 2026-W38
    python posting/ig_retract.py --permalink ... --headed      # watch it

Evidence: screenshots + a JSON entry appended to data/posts/<week>/retraction_log.json.
Exit 0 only when Instagram no longer serves the post (page says it is unavailable).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROFILE_DIR = ROOT / "data" / "fb_auto_profile"


def _shot(page, post_dir: Path, tag: str) -> str:
    post_dir.mkdir(parents=True, exist_ok=True)
    p = post_dir / f"_ig_retract_{tag}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
    except Exception:
        pass
    return str(p)


def _body(page) -> str:
    try:
        return page.inner_text("body", timeout=6000)
    except Exception:
        return ""


def _logged_out(page) -> bool:
    """Instagram's logged-out post view shows a 'Log In' + 'Sign Up' header."""
    try:
        hdr = page.locator('a[href*="/accounts/login/"]:has-text("Log In"), a[href*="/accounts/login/"]:has-text("Log in")')
        if hdr.count() and hdr.first.is_visible():
            return True
    except Exception:
        pass
    b = _body(page)[:2500].lower()
    return ("log in" in b and "sign up" in b)


def _current_username(page) -> str:
    """Username of the signed-in account, read from Instagram's own web API."""
    try:
        r = page.evaluate("""async () => {
            const r = await fetch('/api/v1/accounts/current_user/?edit=true',
                {credentials:'include', headers:{'x-ig-app-id':'936619743392459'}});
            if (!r.ok) return 'HTTP ' + r.status;
            const j = await r.json(); return (j.user && j.user.username) || '';
        }""")
        return str(r or "")
    except Exception as e:
        return f"ERR {e}"


def _login_via_facebook(page, post_dir: Path):
    """Click Instagram's 'Log in with Facebook' and ride the already-live
    Facebook session through. Returns (ok, why)."""
    try:
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)
        _shot(page, post_dir, "sso_01_login_page")
        clicked = False
        for sel in ('button:has-text("Log in with Facebook")',
                    'a:has-text("Log in with Facebook")',
                    'div[role="button"]:has-text("Log in with Facebook")',
                    'span:has-text("Log in with Facebook")'):
            try:
                loc = page.locator(sel).first
                if loc.count():
                    loc.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            return False, "no 'Log in with Facebook' control"
        page.wait_for_timeout(5000)
        _shot(page, post_dir, "sso_02_after_click")
        # Facebook may ask "Continue as <name>?"
        for _ in range(3):
            if "facebook.com" in page.url:
                for sel in ('div[role="button"]:has-text("Continue as")',
                            'button:has-text("Continue as")',
                            'div[aria-label^="Continue as"]',
                            'button[name="__CONFIRM__"]'):
                    try:
                        loc = page.locator(sel).first
                        if loc.count() and loc.is_visible():
                            loc.click(timeout=5000)
                            break
                    except Exception:
                        continue
                page.wait_for_timeout(5000)
            else:
                break
        _shot(page, post_dir, "sso_03_after_continue")
        # Instagram "Save your login info?" / "Turn on notifications" -> Not now
        for _ in range(2):
            for txt in ("Not now", "Not Now"):
                try:
                    b = page.get_by_role("button", name=txt).first
                    if b.count() and b.is_visible():
                        b.click(timeout=3000)
                        page.wait_for_timeout(1500)
                except Exception:
                    pass
        page.wait_for_timeout(2000)
        _shot(page, post_dir, "sso_04_done")
        who = _current_username(page)
        return (bool(who) and not who.startswith(("HTTP", "ERR"))), f"user={who} url={page.url[:80]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _gone(page) -> bool:
    b = _body(page).lower()
    return ("isn't available" in b or "isn’t available" in b
            or "page not found" in b or "link you followed may be broken" in b)


def retract(permalink: str, week: str, headed: bool = False) -> dict:
    from playwright.sync_api import sync_playwright

    post_dir = ROOT / "data" / "posts" / week
    res = {"permalink": permalink, "at": datetime.now(timezone.utc).isoformat(),
           "steps": [], "shots": []}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="chrome", headless=not headed,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport={"width": 1280, "height": 900},
            locale="en-US", timezone_id="America/Chicago")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto(permalink, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            res["shots"].append(_shot(page, post_dir, "01_open"))
            if _logged_out(page):
                # The profile's Instagram cookies were not an authenticated
                # session (2026-09-15: 62 cookies, still the logged-out view).
                # Its Facebook session IS live, so use Instagram's own
                # "Log in with Facebook" SSO: no password, no 2FA.
                res["steps"].append("logged out of Instagram; trying Facebook SSO")
                ok, why = _login_via_facebook(page, post_dir)
                res["steps"].append(f"facebook sso: ok={ok} {why}")
                if not ok:
                    res["ok"] = False
                    return res
                page.goto(permalink, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                res["shots"].append(_shot(page, post_dir, "01b_after_sso"))
                if _logged_out(page):
                    res["steps"].append("still logged out after SSO")
                    res["ok"] = False
                    return res
            who = _current_username(page)
            res["steps"].append(f"acting as @{who}")
            if who and who.lower() != "tulsagays":
                res["steps"].append("WRONG ACCOUNT - refusing to touch anything")
                res["ok"] = False
                return res
            page.goto(permalink, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            body = _body(page)
            if _gone(page):
                res["steps"].append("post already unavailable before we acted")
                res["ok"] = True
                return res

            # Dismiss "Turn on notifications" style dialogs if present.
            for txt in ("Not Now", "Not now", "Cancel"):
                try:
                    b = page.get_by_role("button", name=txt).first
                    if b.count() and b.is_visible():
                        b.click(timeout=2000)
                        page.wait_for_timeout(800)
                except Exception:
                    pass

            # Open the post's "More options" menu (the ... button in the header).
            opened = False
            for sel in ('article svg[aria-label="More options"]',
                        'svg[aria-label="More options"]',
                        'div[role="button"]:has(svg[aria-label="More options"])'):
                try:
                    loc = page.locator(sel).first
                    loc.scroll_into_view_if_needed(timeout=3000)
                    loc.click(timeout=4000)
                    opened = True
                    break
                except Exception:
                    continue
            page.wait_for_timeout(1500)
            res["shots"].append(_shot(page, post_dir, "02_menu"))
            if not opened:
                res["steps"].append("could not open More options menu")
                res["ok"] = False
                return res

            # Click "Delete" in the options sheet.
            clicked = False
            for sel in ('div[role="dialog"] button:has-text("Delete")',
                        'button:has-text("Delete")',
                        'div[role="dialog"] div[role="button"]:has-text("Delete")'):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.click(timeout=4000)
                        clicked = True
                        break
                except Exception:
                    continue
            page.wait_for_timeout(1500)
            res["shots"].append(_shot(page, post_dir, "03_confirm"))
            if not clicked:
                res["steps"].append("no Delete entry in options menu (not our post, or UI changed)")
                res["ok"] = False
                return res

            # Confirm the "Delete post?" dialog.
            confirmed = False
            for sel in ('div[role="dialog"] button:has-text("Delete")',
                        'button:has-text("Delete")'):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.click(timeout=4000)
                        confirmed = True
                        break
                except Exception:
                    continue
            res["steps"].append(f"confirm clicked={confirmed}")
            page.wait_for_timeout(4000)
            res["shots"].append(_shot(page, post_dir, "04_after"))

            # Verify: reload the permalink; Instagram must now say unavailable.
            page.goto(permalink, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)
            res["shots"].append(_shot(page, post_dir, "05_verify"))
            gone = _gone(page)
            res["steps"].append(f"verify reload: gone={gone}")
            res["ok"] = bool(gone)
            return res
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--permalink", required=True)
    ap.add_argument("--week", required=True)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    res = retract(a.permalink, a.week, headed=a.headed)
    log_path = ROOT / "data" / "posts" / a.week / "retraction_log.json"
    try:
        log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    except Exception:
        log = {}
    log.setdefault("ig_browser_retract", []).append(res)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
