"""Self-driving Facebook GROUP blaster for the Tulsa Gays weekly carousel.

Posts the weekly group caption (tools.group_caption) into every group in the
curated registry (tools.fb_groups) AS the Tulsa Gays Page -- never a personal
account. Meta's Graph API can't post to groups (publish_to_groups deprecated
2024), so this drives the FB web UI via Playwright using a saved login.

WHY THIS IS SAFE (anonymity is the #1 rule):
  Before EVERY post, the script confirms the composer is acting as "Tulsa Gays".
  If it can't confirm, it SKIPS that group rather than risk a personal-account
  post. It also re-runs the page "Switch Now" step at startup.

One-time setup (on the machine that will run the blast):
    pip install playwright && playwright install chromium
    python -m posting.group_blast --setup        # headed login, saves auth

Weekly use:
    python -m posting.group_blast --dry-run       # plan + caption, no FB
    python -m posting.group_blast                  # live blast (headless)
    python -m posting.group_blast --headed         # live, visible (debug)
    python -m posting.group_blast --list           # dump joined groups

Outputs a ledger: data/posts/<week>/group_blast_results.json
Cooldown: a group posted within COOLDOWN_DAYS (from any prior ledger) is skipped.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.fb_groups import (  # noqa: E402
    FB_PAGE_URL, get_post_targets, get_group_url,
)
from tools.group_caption import build_group_caption, _current_week  # noqa: E402

AUTH_PATH = ROOT / "data" / "fb_group_auth.json"
COOLDOWN_DAYS = 5
PACE_SECONDS = 25          # gap between posts (spam-safety)
PAGE_NAME = "Tulsa Gays"


# ───────────────────────── auth / ledger helpers ──────────────────────────
def _ensure_pw():
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium")


def setup_auth():
    _ensure_pw()
    from playwright.sync_api import sync_playwright
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False)
        ctx = b.new_context()
        pg = ctx.new_page()
        pg.goto("https://www.facebook.com/")
        print("Log into Facebook as the account that manages the Tulsa Gays Page.")
        input("Press Enter once you're logged in: ")
        ctx.storage_state(path=str(AUTH_PATH))
        b.close()
    print(f"Saved auth -> {AUTH_PATH}")


def _recent_posts_by_group():
    """group_id -> latest ISO datetime we successfully posted (any prior ledger)."""
    seen = {}
    for ledger in (ROOT / "data" / "posts").glob("*/group_blast_results.json"):
        try:
            data = json.loads(ledger.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in data.get("results", []):
            if r.get("status") in ("live", "pending"):
                gid, ts = r.get("id"), r.get("at")
                if gid and ts and (gid not in seen or ts > seen[gid]):
                    seen[gid] = ts
    return seen


def _on_cooldown(group, recent, now):
    ts = recent.get(group["id"])
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return False
    return (now - last) < timedelta(days=COOLDOWN_DAYS)


# ───────────────────────── browser actions ────────────────────────────────
def _switch_to_page(page):
    """Make the session act as the Tulsa Gays Page. Returns True on success."""
    page.goto(FB_PAGE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # If a "Switch Now" / "Switch into ... Page" control exists, click it.
    for sel in ('div[role="button"]:has-text("Switch Now")',
                'a:has-text("Switch Now")',
                'div[aria-label*="Switch"]'):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=4000)
                page.wait_for_timeout(3000)
                break
        except Exception:
            continue
    # Confirm: the page body should reference acting as the page.
    try:
        body = page.inner_text("body", timeout=5000)
    except Exception:
        body = ""
    return ("now acting as" in body.lower()) or (PAGE_NAME.lower() in body.lower())


def _composer_is_page(page) -> bool:
    """True only if the open Create-post dialog is posting AS the Tulsa Gays Page."""
    try:
        dlg = page.locator('div[role="dialog"]').filter(has_text="Create post").first
        txt = dlg.inner_text(timeout=4000)
    except Exception:
        return False
    return PAGE_NAME.lower() in txt.lower()


def _post_to_group(page, group, caption):
    """Post caption to one group as the Page. Returns a result dict."""
    url = get_group_url(group)
    res = {"name": group["name"], "id": group["id"], "url": url}
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Open composer.
        opened = False
        for sel in ('div[role="button"]:has-text("Write something")',
                    'span:has-text("Write something")',
                    'div[role="button"]:has-text("Create post")'):
            try:
                page.locator(sel).first.click(timeout=4000)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            res["status"] = "error"; res["error"] = "composer not found"; return res

        page.wait_for_timeout(1500)

        # ANONYMITY GATE: must be acting as the Page.
        if not _composer_is_page(page):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            res["status"] = "skipped"; res["error"] = "not acting as Page (anonymity guard)"
            return res

        # Type caption.
        typed = False
        for sel in ('div[role="dialog"] [contenteditable="true"]',
                    '[role="textbox"][contenteditable="true"]'):
            try:
                box = page.locator(sel).first
                box.click(timeout=4000)
                box.type(caption, delay=8)
                typed = True
                break
            except Exception:
                continue
        if not typed:
            res["status"] = "error"; res["error"] = "textbox not found"; return res

        # Dismiss hashtag autocomplete so it doesn't eat the Post click.
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
        except Exception:
            pass

        # Let the tulsagays.com link card generate.
        page.wait_for_timeout(3500)

        # Submit.
        submitted = False
        for sel in ('div[role="dialog"] div[aria-label="Post"]',
                    'div[aria-label="Post"][role="button"]'):
            try:
                page.locator(sel).first.click(timeout=4000)
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            res["status"] = "error"; res["error"] = "Post button not found"; return res

        # Verify outcome.
        page.wait_for_timeout(5000)
        try:
            body = page.inner_text("body", timeout=5000).lower()
        except Exception:
            body = ""
        if "your post is pending" in body or "awaiting admin approval" in body:
            res["status"] = "pending"
        elif "tulsagays.com" in body or "comment as tulsa gays" in body:
            res["status"] = "live"
        else:
            res["status"] = "submitted"   # posted but couldn't confirm state
        return res
    except Exception as e:
        res["status"] = "error"; res["error"] = str(e)[:200]
        return res


# ───────────────────────── orchestration ──────────────────────────────────
def run(dry_run=False, headed=False, week=None):
    week = week or _current_week()
    caption = build_group_caption(week)
    targets = get_post_targets()
    now = datetime.now(timezone.utc)
    recent = _recent_posts_by_group()

    plan, skipped_cd = [], []
    for g in targets:
        (skipped_cd if _on_cooldown(g, recent, now) else plan).append(g)

    print(f"=== Tulsa Gays group blast :: {week} ===")
    print(f"caption: {len(caption)} chars | targets: {len(targets)} | "
          f"to post: {len(plan)} | on cooldown: {len(skipped_cd)}\n")
    for g in plan:
        print(f"  POST  [{g['type']:9}] {g['name']}")
    for g in skipped_cd:
        print(f"  SKIP  (cooldown) {g['name']}")

    if dry_run:
        print("\n--- caption preview ---")
        sys.stdout.buffer.write((caption + "\n").encode("utf-8", "replace"))
        return {"week": week, "dry_run": True, "planned": [g["name"] for g in plan]}

    _ensure_pw()
    from playwright.sync_api import sync_playwright
    if not AUTH_PATH.exists():
        raise SystemExit(f"No auth at {AUTH_PATH}. Run: python -m posting.group_blast --setup")

    results = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=not headed)
        ctx = b.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()

        # AUTH PRE-CHECK: detect an expired session up front and fail LOUDLY,
        # instead of silently erroring "composer not found" on all 17 groups
        # (which is exactly how the 2026-06-08 silent failure looked). Writes a
        # flag the Monday agent / keepalive read to alert William for re-auth.
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        _names = {c["name"] for c in ctx.cookies()}
        _login_form = False
        try:
            _login_form = page.locator('input[name="email"]').count() > 0
        except Exception:
            pass
        if "c_user" not in _names or _login_form:
            b.close()
            try:
                (ROOT / "data" / "GROUP_AUTH_DEAD.flag").write_text(
                    datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            except Exception:
                pass
            raise SystemExit(
                "AUTH_DEAD: Facebook group session is logged out — 0 groups posted. "
                "Re-auth (2 min): python tools/capture_group_auth.py")

        if not _switch_to_page(page):
            b.close()
            raise SystemExit("Could not confirm 'acting as Tulsa Gays Page'. "
                             "Aborting (anonymity guard). Re-run --setup if login expired.")
        print(f"\n[ok] acting as {PAGE_NAME}\n")

        for i, g in enumerate(plan):
            r = _post_to_group(page, g, caption)
            r["at"] = datetime.now(timezone.utc).isoformat()
            results.append(r)
            print(f"  [{r['status']:9}] {g['name']}"
                  + (f"  ({r.get('error')})" if r.get("error") else ""))
            if i < len(plan) - 1:
                time.sleep(PACE_SECONDS)   # spam-safe pacing
        b.close()

    out = {
        "week": week,
        "ran_at": now.isoformat(),
        "page": PAGE_NAME,
        "counts": {s: sum(1 for r in results if r["status"] == s)
                   for s in {r["status"] for r in results}},
        "skipped_cooldown": [g["name"] for g in skipped_cd],
        "results": results,
    }
    ledger = ROOT / "data" / "posts" / week / "group_blast_results.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nledger -> {ledger}")
    print(f"counts: {out['counts']}")
    return out


def list_joined(headed=False):
    """Discovery helper: dump the Page's joined groups (id :: name)."""
    _ensure_pw()
    from playwright.sync_api import sync_playwright
    if not AUTH_PATH.exists():
        raise SystemExit("Run --setup first.")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=not headed)
        ctx = b.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()
        _switch_to_page(page)
        page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        rows = page.eval_on_selector_all(
            'a[href*="/groups/"]',
            """els => {
                const seen=new Set(), out=[];
                for (const a of els){
                  const m=a.href.match(/groups\\/([^/?]+)/); if(!m) continue;
                  const id=m[1];
                  if(['joins','feed','discover','create','category'].includes(id)) continue;
                  const name=(a.textContent||'').trim().slice(0,50);
                  if(!name||name.length<3||seen.has(id)) continue;
                  seen.add(id); out.push(id+' :: '+name);
                }
                return out;
            }""")
        b.close()
    for r in rows:
        print(r)
    print(f"\n{len(rows)} groups")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--week")
    a = ap.parse_args()
    if a.setup:
        setup_auth()
    elif a.list:
        list_joined(headed=a.headed)
    else:
        run(dry_run=a.dry_run, headed=a.headed, week=a.week)
