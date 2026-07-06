"""
ig_login_via_fb.py - mint the @tulsagays instagrapi session WITHOUT a password.

Uses the dedicated real-Chrome profile (data/fb_auto_profile), which stays logged
into Facebook for the group blast. Instagram's "Log in with Facebook" rides that
session, so no IG password and usually no 2FA is needed. After login we verify the
account really is @tulsagays, lift the sessionid cookie, and build the instagrapi
session file (~/.credentials/ig_settings_tulsagays.json) that studio66.py,
instagram_orgs.py, and engagement all share.

Safety rails:
  - Headless, dedicated profile only (never William's daily Chrome).
  - HARD ABORT if the logged-in IG user is not @tulsagays (never saves a wrong
    account's session; logs out of IG in the profile before exiting).
  - Facebook session is never touched.

Run: python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_via_fb.py [--headed]
Exit 0 = session saved + validated. Non-zero = fall back to ig_login_api.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROFILE_DIR = Path(r"C:\Users\willi\tulsagays\data\fb_auto_profile")
SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"
SHOT_DIR = Path(r"C:\Users\willi\tulsagays\data\ig_login_shots")
EXPECTED_USER = "tulsagays"


def log(msg: str) -> None:
    print(f"[ig-via-fb] {msg}", flush=True)


def shot(page, name: str) -> None:
    try:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOT_DIR / f"{name}.png"))
    except Exception:
        pass


def get_ig_identity(context) -> tuple[str | None, str | None, str | None]:
    """Return (username, sessionid, ds_user_id) from the context cookies, best effort."""
    sessionid = ds_user_id = username = None
    for c in context.cookies("https://www.instagram.com"):
        if c["name"] == "sessionid":
            sessionid = c["value"]
        elif c["name"] == "ds_user_id":
            ds_user_id = c["value"]
        elif c["name"] == "ds_user":
            username = c["value"]
    return username, sessionid, ds_user_id


def main() -> int:
    headed = "--headed" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright not installed")
        return 1

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel="chrome", headless=not headed,
                viewport={"width": 1280, "height": 900},
            )
        except Exception as e:
            log(f"could not launch profile (Chrome already using it?): {e}")
            return 1

        page = context.new_page()
        try:
            page.goto("https://www.instagram.com/accounts/login/",
                      wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            shot(page, "01-login-page")

            # Cookie-consent dialog (EU-style) if present
            for label in ("Allow all cookies", "Accept all"):
                try:
                    page.get_by_role("button", name=label).click(timeout=2000)
                    page.wait_for_timeout(1500)
                    break
                except Exception:
                    pass

            # Already logged in? (redirected off /accounts/login/)
            _, sessionid, _ = get_ig_identity(context)
            if not sessionid:
                # Find the FB login entry point. IG renders it as a button or link.
                def find_fb_control():
                    for finder in (
                        lambda: page.get_by_role("button", name="Log in with Facebook"),
                        lambda: page.get_by_role("link", name="Log in with Facebook"),
                        lambda: page.get_by_text("Log in with Facebook", exact=False).first,
                        lambda: page.get_by_text("Continue with Facebook", exact=False).first,
                    ):
                        try:
                            el = finder()
                            el.wait_for(state="visible", timeout=3000)
                            return el
                        except Exception:
                            continue
                    return None

                el = find_fb_control()
                if el is None:
                    shot(page, "02-no-fb-button")
                    log("no 'Log in with Facebook' control found — see screenshots")
                    context.close()
                    return 2

                # IG's FB login opens EITHER a popup window OR navigates the same tab.
                # Try to catch a popup; if none, fall back to same-tab navigation.
                fb_page = None
                try:
                    with page.expect_popup(timeout=8000) as pop:
                        el.click()
                    fb_page = pop.value
                    log("Facebook OAuth opened in a popup window")
                except Exception:
                    log("no popup — assuming same-tab FB navigation")
                    fb_page = page
                page.wait_for_timeout(6000)

                # Resolve the OAuth dialog on whichever page is on facebook.com
                target = fb_page
                if "facebook.com" not in (target.url or ""):
                    for pg in context.pages:
                        if "facebook.com" in pg.url:
                            target = pg
                            break
                shot(target, "03-after-fb-click")
                log(f"oauth page url: {(target.url or '')[:90]}")

                # Facebook OAuth confirm: "Continue as <name>" / "Continue"
                confirmed = False
                for finder in (
                    lambda: target.get_by_role("button", name="Continue as").first,
                    lambda: target.get_by_role("button", name="Continue").first,
                    lambda: target.locator("[aria-label^='Continue']").first,
                    lambda: target.locator("div[role=button]:has-text('Continue')").first,
                ):
                    try:
                        finder().click(timeout=5000)
                        confirmed = True
                        log("clicked Continue on the Facebook dialog")
                        break
                    except Exception:
                        continue
                if not confirmed:
                    log(f"no Continue dialog (url {(target.url or '')[:70]}) — may have "
                        "auto-continued or already authorized")
                page.wait_for_timeout(8000)
                shot(page, "04-after-continue")

                # Possible interstitials: "Save your login info?" / "Sync your info"
                for label in ("Not now", "Not Now", "Skip"):
                    try:
                        page.get_by_role("button", name=label).click(timeout=2500)
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass
                shot(page, "05-final")

            username, sessionid, ds_user_id = get_ig_identity(context)
            log(f"identity: user={username} ds_user_id={ds_user_id} "
                f"sessionid={'yes' if sessionid else 'no'}")

            if not sessionid:
                log("no instagram sessionid after the flow — login did not complete")
                context.close()
                return 3

            # Verify the account. ds_user cookie is not always set; ask IG who we are.
            if not username:
                try:
                    resp = page.evaluate(
                        "() => fetch('/api/v1/accounts/current_user/?edit=true', "
                        "{headers:{'x-ig-app-id':'936619743392459'}})"
                        ".then(r=>r.json()).then(d=>d.user && d.user.username)"
                    )
                    username = resp
                    log(f"current_user says: {username}")
                except Exception as e:
                    log(f"could not confirm username in-page: {e}")

            if (username or "").lower() != EXPECTED_USER:
                log(f"ABORT: logged-in IG user is {username!r}, not @{EXPECTED_USER}. "
                    "Logging out of IG (FB untouched) and exiting without saving.")
                try:
                    page.goto("https://www.instagram.com/accounts/logout/", timeout=20000)
                except Exception:
                    pass
                context.close()
                return 4

            context.close()

        except Exception as e:
            shot(page, "99-error")
            log(f"browser flow error: {type(e).__name__}: {e}")
            try:
                context.close()
            except Exception:
                pass
            return 1

    # ── Mint the instagrapi session from the web sessionid ──────────────────
    log("building instagrapi session from sessionid...")
    try:
        from instagrapi import Client
    except ImportError:
        log("instagrapi not installed")
        return 1

    cl = Client()
    cl.delay_range = [1, 3]
    # Reuse a previously-known device fingerprint if one is on disk (fewer challenges)
    if SETTINGS_FILE.exists():
        try:
            cl.load_settings(str(SETTINGS_FILE))
        except Exception:
            pass
    try:
        cl.login_by_sessionid(sessionid)
        me = cl.account_info()
    except Exception as e:
        log(f"login_by_sessionid failed: {type(e).__name__}: {str(e)[:200]}")
        return 5
    if me.username.lower() != EXPECTED_USER:
        log(f"ABORT: instagrapi session is @{me.username}, not @{EXPECTED_USER} — not saving")
        return 4

    try:
        cl.get_timeline_feed()  # the same validation studio66.py uses
    except Exception as e:
        log(f"session did not validate: {type(e).__name__}: {str(e)[:160]}")
        return 5

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(str(SETTINGS_FILE))
    log(f"OK: @{me.username} session saved -> {SETTINGS_FILE}")
    return 0


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    log(f"done rc={rc} in {time.time() - t0:.0f}s")
    sys.exit(rc)
