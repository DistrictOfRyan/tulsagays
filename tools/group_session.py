"""
Shared Facebook group-session helpers for the Tulsa Gays group blaster.

Meta has no API for posting to groups, so group_blast.py drives the FB web UI
with a saved browser session (data/fb_group_auth.json). That session silently
expires every ~week, which made the Monday group blast fail with "composer not
found" on all targets and forced a manual re-login.

This module makes the session durable:
  is_logged_in(state)  - headless check: does the saved session still resolve to
                         a logged-in FB account (c_user cookie + no login form)?
  refresh(state)       - headless: load the session, touch facebook.com, re-save
                         the (rotated) cookies. Run daily to keep FB from
                         expiring an idle session. Returns True if still logged
                         in (and re-saved), False if the session is dead.

Both are headless and safe to run from an automation shell.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "fb_group_auth.json"


def _check(page_ctx):
    """Return (logged_in: bool, detail: str) for an open context on facebook.com."""
    try:
        names = {c["name"] for c in page_ctx.cookies()}
    except Exception as e:
        return False, f"cookie read failed: {e}"
    if "c_user" not in names:
        return False, "no c_user cookie (logged out)"
    return True, "c_user present"


def is_logged_in(state_path=AUTH_PATH, timeout_s=45):
    """Headless: True if the saved session is still a logged-in FB account."""
    state_path = Path(state_path)
    if not state_path.exists():
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            ctx = b.new_context(storage_state=str(state_path))
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/", wait_until="domcontentloaded",
                    timeout=timeout_s * 1000)
            ok, _ = _check(ctx)
            # Double-check: a login form on the landing page means logged out.
            if ok:
                try:
                    if pg.locator('input[name="email"]').count() > 0 and \
                       pg.locator('input[name="pass"]').count() > 0:
                        ok = False
                except Exception:
                    pass
            return ok
        except Exception:
            return False
        finally:
            b.close()


def refresh(state_path=AUTH_PATH, timeout_s=45):
    """Headless: touch FB with the saved session and re-save rotated cookies.
    Returns True if still logged in (and re-saved), False if dead."""
    state_path = Path(state_path)
    if not state_path.exists():
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            ctx = b.new_context(storage_state=str(state_path))
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/", wait_until="domcontentloaded",
                    timeout=timeout_s * 1000)
            ok, _ = _check(ctx)
            if ok:
                # Visit one more authenticated surface so FB extends the session,
                # then persist the rotated cookies.
                try:
                    pg.goto("https://www.facebook.com/bookmarks/pages/",
                            wait_until="domcontentloaded", timeout=timeout_s * 1000)
                except Exception:
                    pass
                ctx.storage_state(path=str(state_path))
            return ok
        except Exception:
            return False
        finally:
            b.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "refresh":
        print("REFRESHED" if refresh() else "DEAD")
    else:
        print("LOGGED_IN" if is_logged_in() else "DEAD")
