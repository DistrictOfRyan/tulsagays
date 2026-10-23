"""
Shared Facebook/Instagram browser-session helpers for the Tulsa Gays automation.

Meta has no API for posting to groups, so group_blast.py drives the FB web UI
with a saved browser session. This module owns how every TulsaGays browser job
opens that session:

  open_context(pw)     - (browser, context): real Chrome, in-memory context,
                         loaded from STATE_PATH. Close with browser.close().
  save_state(ctx)      - write the rotated cookies back to STATE_PATH
                         (atomic; only the given domains are replaced).
  state_path()         - STATE_PATH if it holds a Facebook login, else None.
  is_logged_in()       - headless check: c_user + xs and no login form.
  refresh()            - headless: touch facebook.com, re-save the rotated
                         cookies. Run daily so FB never expires an idle session.

WHY STORAGE_STATE, NOT THE PERSISTENT PROFILE (2026-10-22): from the 10/7
Windows 26H2 restart until the 10/21 18:08 sign-in, DPAPI could not open this
Windows account's master keys, and Chrome seals its cookie key with DPAPI. So
data/fb_auto_profile kept the login only in memory and lost it on every Chrome
exit (its cookie DB held 0 rows on 10/22), which is the "logged out every week"
pattern. A storage_state is plain JSON loaded into an in-memory context, so it
never touches DPAPI. Write-up: ~/.claude/drafts/security/dpapi-2026-10-22.md.

STATE_PATH is the store the event scraper and page posting already kept alive:
William's FB account (/DistrictOfRyan, manages the Tulsa Gays Page) plus the
Instagram login the old profile carried. One login feeds every job; re-login
with `python tools/fb_profile_login.py`. data/* is gitignored.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "fb_session.json"
AUTH_PATH = STATE_PATH            # name kept for callers (group_auth_keepalive)
LEGACY_PROFILE_DIR = ROOT / "data" / "fb_auto_profile"   # capture window only now
FB_DOMAINS = ("facebook.com",)
IG_DOMAINS = ("instagram.com",)


def _ua(version):
    major = (version or "156").split(".")[0]
    return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36")


def _has_fb_login(path=STATE_PATH):
    try:
        names = {c["name"] for c in json.loads(Path(path).read_text(encoding="utf-8")).get("cookies", [])
                 if "facebook.com" in c.get("domain", "") and c.get("value")}
    except Exception:
        return False
    return {"c_user", "xs"} <= names


def state_path():
    """The store the group blast should use, or None when no Facebook login is saved."""
    return STATE_PATH if _has_fb_login(STATE_PATH) else None


def open_context(pw, headless=True, viewport=None, **context_kwargs):
    """Real Chrome (FB trusts it), in-memory context loaded from STATE_PATH.
    Returns (browser, context). browser.close() tears everything down."""
    args = ["--disable-blink-features=AutomationControlled"]
    try:
        b = pw.chromium.launch(channel="chrome", headless=headless, args=args)
    except Exception:
        b = pw.chromium.launch(headless=headless, args=args)
    kw = {"user_agent": _ua(b.version), "viewport": viewport or {"width": 1280, "height": 900},
          **context_kwargs}
    if STATE_PATH.exists():
        kw["storage_state"] = str(STATE_PATH)
    return b, b.new_context(**kw)


def _matches(domain, domains):
    d = (domain or "").lstrip(".").lower()
    return any(d == x or d.endswith("." + x) for x in domains)


def save_state(ctx, domains=FB_DOMAINS + IG_DOMAINS):
    """Atomically write the context's cookies for `domains` back into STATE_PATH,
    keeping every other domain the file holds."""
    new = ctx.storage_state()
    try:
        old = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        old = {"cookies": [], "origins": []}

    def host(o):
        return o.get("origin", "").split("://", 1)[-1].split("/", 1)[0]
    merged = {
        "cookies": [c for c in old.get("cookies", []) if not _matches(c.get("domain"), domains)]
                   + [c for c in new.get("cookies", []) if _matches(c.get("domain"), domains)],
        "origins": [o for o in old.get("origins", []) if not _matches(host(o), domains)]
                   + [o for o in new.get("origins", []) if _matches(host(o), domains)],
    }
    tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(merged), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def _check(page_ctx):
    """Return (logged_in: bool, detail: str) for an open context on facebook.com."""
    try:
        names = {c["name"] for c in page_ctx.cookies("https://www.facebook.com") if c.get("value")}
    except Exception as e:
        return False, f"cookie read failed: {e}"
    if not {"c_user", "xs"} <= names:
        return False, "no c_user/xs cookie (logged out)"
    return True, "c_user + xs present"


def _visit(timeout_s, keep_warm):
    if not state_path():
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    with sync_playwright() as pw:
        b, ctx = open_context(pw, headless=True)
        try:
            pg = ctx.new_page()
            pg.goto("https://www.facebook.com/", wait_until="domcontentloaded",
                    timeout=timeout_s * 1000)
            pg.wait_for_timeout(3000)
            ok, _ = _check(ctx)
            # A login form on the landing page means logged out, whatever the cookies say.
            if ok:
                try:
                    if pg.locator('input[name="email"]').count() > 0 and \
                       pg.locator('input[name="pass"]').count() > 0:
                        ok = False
                except Exception:
                    pass
            if ok and keep_warm:
                # Visit one more authenticated surface so FB extends the session.
                try:
                    pg.goto("https://www.facebook.com/bookmarks/pages/",
                            wait_until="domcontentloaded", timeout=timeout_s * 1000)
                except Exception:
                    pass
                # A failed write (another job holding the file for a moment) is not a
                # dead session; never let it turn a live login into a re-login ask.
                try:
                    save_state(ctx, FB_DOMAINS)
                except Exception as e:
                    print(f"[group_session] session live, re-save skipped: {type(e).__name__}: {e}")
            return ok
        except Exception:
            return False
        finally:
            b.close()


def is_logged_in(state_path_unused=None, timeout_s=45):
    """Headless: True if the saved session is still a logged-in FB account."""
    return _visit(timeout_s, keep_warm=False)


def refresh(state_path_unused=None, timeout_s=45):
    """Headless: touch FB to keep the session warm and re-save the rotated
    cookies. Returns True if logged in."""
    return _visit(timeout_s, keep_warm=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "refresh":
        print("REFRESHED" if refresh() else "DEAD")
    else:
        print("LOGGED_IN" if is_logged_in() else "DEAD")
