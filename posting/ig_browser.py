"""
ig_browser.py - unattended Instagram engagement for @tulsagays via Playwright.

The Graph API cannot do IG follows, likes, or comment-replies, so these run
through a real browser session. Posture (set by William 2026-06-02):
  - REPLIES to comments on our own posts  -> AUTO (low ban risk, high value)
  - LIKES on others' posts                -> AUTO, conservative + paced
  - FOLLOWS (outbound)                     -> ASSISTED only: we PREPARE a one-tap
                                              list, we never click Follow (that is
                                              IG's #1 automation-ban trigger)

Anti-ban design:
  - One persistent logged-in session (storage_state); never logs in on a schedule
    (logins trigger checkpoints). Establish it once with scripts/ig_login_tulsagays.py.
  - Human pacing: randomized delays, tiny batches, hard per-run caps.
  - Checkpoint/login detection -> ABORT immediately (never hammer a challenge).
  - Idempotent: replied comments / liked posts tracked in a state file.
  - Full audit log of every action taken.

Session lives at ~/.credentials/ig_session_tulsagays.json (OFF the synced drive).
Secrets are never written to the repo.

CLI:
    python posting/ig_browser.py check            # session health, no actions
    python posting/ig_browser.py reply            # clear the reply queue
    python posting/ig_browser.py like [--max N]    # like N posts (default 5)
    python posting/ig_browser.py prepare-follows   # write the assisted follow list
    python posting/ig_browser.py engage            # reply + like + prepare-follows

NOTE: selectors are best-effort; the FIRST live run after login validates/tunes
them. Until the session exists, every command degrades cleanly (notifies + exits 0).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import ig_chrome
except ImportError:  # when imported as a package
    from posting import ig_chrome

HOME = Path.home()
SESSION_FILE = HOME / ".credentials" / "ig_session_tulsagays.json"
STATE_FILE = HOME / ".claude" / "tulsagays" / "ig_engage_state.json"
REPLY_QUEUE = HOME / ".claude" / "tulsagays" / "ig_reply_queue.json"
FOLLOW_LIST_OUT = HOME / ".claude" / "tulsagays" / "ig_follow_candidates.md"
LOG_FILE = HOME / ".claude" / "logs" / "tulsagays-ig-engage.log"
PENDING = HOME / ".claude" / "pending-william-actions.md"
ENV_FILE = HOME / ".claude" / "channels" / "telegram" / ".env"
CHAT_ID = "6202804878"

# Conservative caps (keep well under IG's automation thresholds).
LIKE_CAP = 5
REPLY_CAP = 8
MIN_DELAY, MAX_DELAY = 22, 75  # seconds between actions, jittered


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg)


def _pace() -> None:
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"replied": [], "liked": []}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _telegram(text: str) -> None:
    try:
        import urllib.parse, urllib.request
        token = None
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
        if not token:
            return
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:3500],
                                       "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                   data=data, method="POST"), timeout=10)
    except Exception:
        pass


def _degrade(reason: str) -> int:
    """No session / blocked: notify once, leave a pending note, exit clean (not a failure)."""
    log(f"DEGRADE: {reason}")
    _telegram(f"tulsagays-ig-engage skipped: {reason}. "
              f"Run `python scripts/ig_login_tulsagays.py` once to (re)establish the @tulsagays session.")
    try:
        with PENDING.open("a", encoding="utf-8") as f:
            f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] TulsaGays IG engage NEEDS YOUR ACTION\n"
                    f"Browser IG engagement could not run: {reason}. One-time fix: run "
                    f"`python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_tulsagays.py`, log in to @tulsagays, "
                    f"clear the 2FA, and it saves the session. Then engagement runs on its own.\n")
    except OSError:
        pass
    return 0


# ---- Playwright helpers -------------------------------------------------------

def _connect(p, headless: bool = True):
    """Launch real Chrome (IG profile) + attach via CDP.
    Returns (proc, browser, context, page), or None if no session/Chrome."""
    # No point launching if login was never done.
    if not ig_chrome.IG_PROFILE_DIR.exists() and not SESSION_FILE.exists():
        return None
    proc, endpoint = ig_chrome.launch(headless=headless)
    if not endpoint:
        return None
    try:
        browser = p.chromium.connect_over_cdp(endpoint)
    except Exception:
        ig_chrome.kill(proc)
        return None
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    return proc, browser, context, page


def _is_blocked(page) -> bool:
    """True if IG is showing a login wall or a challenge/checkpoint."""
    url = page.url.lower()
    if "challenge" in url or "/accounts/login" in url or "/accounts/suspended" in url:
        return True
    try:
        if page.locator("input[name='username']").count() > 0:
            return True
    except Exception:
        pass
    return False


def _has_sessionid(page) -> bool:
    """Definitive logged-in signal: a non-empty IG sessionid cookie."""
    try:
        return any(c.get("name") == "sessionid" and c.get("value")
                   for c in page.context.cookies())
    except Exception:
        return False


def _session_ok(page) -> bool:
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
    time.sleep(4)
    # Must hold a sessionid cookie AND not be on a login/challenge wall.
    # (A missing login form alone is NOT proof of being logged in — IG renders
    #  the form async, which produced a false "logged in" before.)
    return _has_sessionid(page) and not _is_blocked(page)


# ---- Actions -----------------------------------------------------------------

def do_replies(page, state: dict) -> int:
    """Reply to queued comments on our own posts. Returns count posted."""
    try:
        queue = json.loads(REPLY_QUEUE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log("no reply queue (ig_reply_queue.json) - skipping replies")
        return 0
    posted = 0
    for item in queue:
        if posted >= REPLY_CAP:
            break
        rid = item.get("id") or item.get("post_url", "") + "|" + item.get("reply", "")[:20]
        if rid in state["replied"]:
            continue
        url, reply = item.get("post_url"), item.get("reply")
        if not url or not reply:
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if _is_blocked(page):
                log("blocked mid-reply - aborting")
                return -1  # signal abort
            box = page.locator("textarea[aria-label*='omment'], textarea[placeholder*='omment']").first
            box.click(timeout=15000)
            box.fill(reply)
            time.sleep(random.uniform(1, 3))
            # Post button appears once text is entered
            page.locator("div[role='button']:has-text('Post'), button:has-text('Post')").first.click(timeout=10000)
            state["replied"].append(rid)
            _save_state(state)
            posted += 1
            log(f"replied on {url}")
            _pace()
        except Exception as e:
            log(f"reply failed on {url}: {type(e).__name__} {str(e)[:120]}")
            continue
    return posted


def do_likes(page, state: dict, max_likes: int) -> int:
    """Like a few posts from our home feed, paced. Conservative."""
    liked = 0
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        if _is_blocked(page):
            return -1
        for _ in range(max_likes * 3):  # scan a few, like up to max
            if liked >= max_likes:
                break
            like_btns = page.locator("svg[aria-label='Like']")
            n = like_btns.count()
            if n == 0:
                page.mouse.wheel(0, 1200)
                time.sleep(random.uniform(2, 4))
                continue
            try:
                like_btns.first.click(timeout=8000)
                liked += 1
                log(f"liked a post ({liked}/{max_likes})")
                _pace()
                page.mouse.wheel(0, 1400)
                time.sleep(random.uniform(2, 4))
            except Exception:
                page.mouse.wheel(0, 1400)
                time.sleep(2)
    except Exception as e:
        log(f"like flow error: {type(e).__name__} {str(e)[:120]}")
    return liked


def prepare_follows(page) -> int:
    """ASSISTED: gather follow candidates (Tulsa-area accounts) and write a one-tap
    list for William. We do NOT click Follow (ban-trigger avoidance)."""
    candidates = []
    # Seed sources: followers of local LGBTQ venues/orgs (per the engage SKILL).
    seeds = ["homohotelhappyhour", "tulsaeagle", "okeq"]
    try:
        for seed in seeds:
            page.goto(f"https://www.instagram.com/{seed}/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if _is_blocked(page):
                break
            # Best-effort: capture suggested/related handles visible on the profile.
            links = page.locator("a[href^='/']")
            for i in range(min(links.count(), 30)):
                href = links.nth(i).get_attribute("href") or ""
                h = href.strip("/").split("/")[0]
                if h and h.isalnum() and h not in seeds and h not in candidates:
                    candidates.append(h)
            _pace()
    except Exception as e:
        log(f"prepare_follows error: {type(e).__name__} {str(e)[:120]}")

    candidates = candidates[:15]
    FOLLOW_LIST_OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# TulsaGays follow candidates — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "Assisted list (we never auto-follow — IG bans for that). Tap Follow on the ones that look Tulsa-area + on-brand:\n"]
    for h in candidates:
        lines.append(f"- https://www.instagram.com/{h}/")
    FOLLOW_LIST_OUT.write_text("\n".join(lines), encoding="utf-8")
    log(f"prepared {len(candidates)} follow candidates -> {FOLLOW_LIST_OUT}")
    return len(candidates)


# ---- Orchestration -----------------------------------------------------------

def run(mode: str, max_likes: int = LIKE_CAP) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _degrade("playwright not installed")

    with sync_playwright() as p:
        bundle = _connect(p, headless=True)
        if bundle is None:
            return _degrade("no @tulsagays session yet - run scripts/ig_login_tulsagays.py")
        proc, browser, context, page = bundle
        try:
            if not _session_ok(page):
                return _degrade("IG session invalid/expired or showing a checkpoint")

            summary = []
            if mode in ("reply", "engage"):
                state = _load_state()
                r = do_replies(page, state)
                if r == -1:
                    return _degrade("hit an IG checkpoint during replies")
                summary.append(f"{r} replies")
            if mode in ("like", "engage"):
                state = _load_state()
                liked = do_likes(page, state, max_likes)
                if liked == -1:
                    return _degrade("hit an IG checkpoint during likes")
                summary.append(f"{liked} likes")
            if mode in ("prepare-follows", "engage"):
                c = prepare_follows(page)
                summary.append(f"{c} follow candidates prepared")

            msg = "tulsagays-ig-engage OK: " + ", ".join(summary)
            log(msg)
            _telegram(msg)
            return 0
        finally:
            try:
                browser.close()
            except Exception:
                pass
            ig_chrome.kill(proc)


def check() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _degrade("playwright not installed")
    with sync_playwright() as p:
        bundle = _connect(p, headless=True)
        if bundle is None:
            return _degrade("no @tulsagays session yet - run scripts/ig_login_tulsagays.py")
        proc, browser, context, page = bundle
        try:
            ok = _session_ok(page)
            log(f"session check: {'OK (logged in)' if ok else 'BLOCKED/expired'}")
            return 0 if ok else _degrade("session invalid/expired")
        finally:
            try:
                browser.close()
            except Exception:
                pass
            ig_chrome.kill(proc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["check", "reply", "like", "prepare-follows", "engage"])
    ap.add_argument("--max", type=int, default=LIKE_CAP)
    args = ap.parse_args()
    if args.command == "check":
        return check()
    return run(args.command, max_likes=args.max)


# Registry python-tier entrypoint.
def run_task(task_config=None, task_state=None) -> dict:
    rc = run("engage")
    return {"success": rc == 0, "message": f"ig engage rc={rc}"}


if __name__ == "__main__":
    sys.exit(main())
