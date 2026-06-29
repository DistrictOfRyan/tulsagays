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


def _gate(image_paths) -> None:
    """HARD graphic gate (William 2026-06-21). Refuse to blast tofu / blank /
    broken slides into any group. Run ONCE up front: if the 9 slides are broken,
    abort the whole blast before touching a single group. Fail-CLOSED on a real
    block (raises); fail-OPEN if the gate tooling is unavailable."""
    if not image_paths:
        return
    try:
        from tools.preflight_image import gate_images
    except Exception:
        try:
            from preflight_image import gate_images
        except Exception as e:
            print(f"[gate] WARNING: image preflight unavailable ({e}) - blasting ungated")
            return
    gate_images([str(p) for p in image_paths])


# ───────────────────────── auth / ledger helpers ──────────────────────────
def _ensure_pw():
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium")


def setup_auth():
    # 2026-06-26: The old Playwright-Chromium login here was a TRAP. Google blocks
    # sign-in inside an automation-controlled browser at the verification step, so
    # this flow could NEVER complete (William re-ran it ~30 times, hours each, same
    # Google block every time). Worse: the blast uses the durable REAL-Chrome
    # persistent profile (data/fb_auto_profile) whenever it exists, and IGNORES the
    # storage_state this used to write - so even a "successful" --setup did nothing.
    # The ONLY method that works is logging into the dedicated profile with REAL
    # Chrome (Google trusts it; login persists for months). So --setup now just runs
    # tools/fb_profile_login.py. See memory: feedback_tulsagays_fb_group_reauth.
    import subprocess
    script = ROOT / "tools" / "fb_profile_login.py"
    print("[--setup] Using the REAL-Chrome profile login (the only method that works).")
    print("Playwright-Chromium login is disabled: Google blocks automation browsers.")
    return subprocess.call([sys.executable, str(script)])


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
def _acting_as_page(page) -> bool:
    """True if the session is currently acting as the Tulsa Gays Page. Checked on
    the HOME page, whose menu shows 'Professional dashboard'/'Meta Business Suite'
    + the page name ONLY when acting as a managed Page (verified 2026-06-23)."""
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        body = page.inner_text("body", timeout=8000).lower()
    except Exception:
        return False
    return (PAGE_NAME.lower() in body
            and ("professional dashboard" in body or "meta business suite" in body))


def _switch_to_page(page):
    """Make the session act as the Tulsa Gays Page via the ACCOUNT SWITCHER.

    2026-06-29 ROOT-CAUSE FIX: the old FB_PAGE_URL 'Switch Now' method silently
    failed and left the session acting as the HHHH page ('Tulsa's Homosexual Hotel
    Happy Hour, Inc.'), so EVERY group skipped on the per-group anonymity guard
    ('not acting as Page') and 0/17 landed for weeks. The account that owns this
    profile manages several pages (Tulsa Gays, HHHH, Lexington Gays...) and was
    defaulting to HHHH. The reliable switch is: open the avatar 'Select profile'
    panel and click the exact 'Tulsa Gays' row. Verified the group composer then
    posts AS 'Tulsa Gays'. The per-group _composer_is_page check stays the real
    guard.
    """
    def _do_switch():
        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            for sel in ('div[aria-label="Your profile"]', 'div[aria-label="Account"]'):
                try:
                    page.locator(sel).first.click(timeout=4000); break
                except Exception:
                    continue
            page.wait_for_timeout(2000)
            clicked = False
            try:
                loc = page.get_by_text(PAGE_NAME, exact=True).first
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=4000); clicked = True
            except Exception:
                for sel in (f'div[role="button"]:has-text("{PAGE_NAME}")',
                            f'a:has-text("{PAGE_NAME}")'):
                    try:
                        page.locator(sel).first.click(timeout=3000); clicked = True; break
                    except Exception:
                        continue
            page.wait_for_timeout(5000)
            # FB sometimes shows a "Switch to <Page>?" confirm.
            for sel in ('div[role="button"]:has-text("Switch")', 'span:has-text("Switch Now")'):
                try:
                    b = page.locator(sel).first
                    if b.count() and b.is_visible():
                        b.click(timeout=3000); page.wait_for_timeout(3000); break
                except Exception:
                    continue
            return clicked
        except Exception:
            return False

    # The account-switcher is authoritative — always run it (the persistent profile
    # tends to default back to HHHH). _acting_as_page can false-positive (the name
    # appears in the switcher preview), so we don't trust it to skip the switch.
    _do_switch()
    return _acting_as_page(page)


def _composer_is_page(page) -> bool:
    """True only if the open Create-post dialog is posting AS the Tulsa Gays Page."""
    try:
        dlg = page.locator('div[role="dialog"]').filter(has_text="Create post").first
        txt = dlg.inner_text(timeout=4000)
    except Exception:
        return False
    return PAGE_NAME.lower() in txt.lower()


def _post_to_group(page, group, image_paths):
    """Upload the weekly carousel GRAPHICS (the 9 slides) to one group AS the
    Tulsa Gays Page. GRAPHICS ONLY — never a text/caption post (William's hard
    rule, 2026-06-15). Every Playwright op is bounded so a single group can never
    silently wedge the whole run. Returns a result dict."""
    url = get_group_url(group)
    res = {"name": group["name"], "id": group["id"], "url": url}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        # Open composer. Groups vary in the entry label ("Write something",
        # "Discuss something", "Start a discussion", "Anonymous post"...) and the
        # entry can load off-screen, so scroll to top first. (2026-06-29: the bare
        # 3-selector list missed 2 groups with "composer not found".)
        _COMPOSER_OPENERS = (
            'div[role="button"]:has-text("Write something")',
            'span:has-text("Write something")',
            'div[role="button"]:has-text("Discuss something")',
            'span:has-text("Discuss something")',
            'div[role="button"]:has-text("Start a discussion")',
            'div[role="button"]:has-text("Create post")',
            'div[role="button"]:has-text("Anonymous post")',
        )
        try:
            page.keyboard.press("Home")
        except Exception:
            pass
        opened = False
        for sel in _COMPOSER_OPENERS:
            try:
                loc = page.locator(sel).first
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=4000)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            res["status"] = "error"; res["error"] = "composer not found"; return res
        page.wait_for_timeout(1500)

        # ANONYMITY GATE: must be acting as the Page, else SKIP (never expose Ryan).
        # Recovery: if the per-group navigation dropped the Page context, re-switch
        # to the Page once and reopen before giving up (transient identity loss).
        if not _composer_is_page(page):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            _switch_to_page(page)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
            except Exception:
                pass
            reopened = False
            for sel in _COMPOSER_OPENERS:
                try:
                    page.locator(sel).first.click(timeout=4000); reopened = True; break
                except Exception:
                    continue
            page.wait_for_timeout(1500)
            if not (reopened and _composer_is_page(page)):
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                res["status"] = "skipped"; res["error"] = "not acting as Page (anonymity guard)"
                return res

        # GRAPHICS ONLY: reveal the photo input (click Photo/video), then push the
        # 9 slide files onto the hidden <input type=file>. No caption is typed.
        for sel in ('div[aria-label="Photo/video"]',
                    'div[role="button"]:has-text("Photo/video")',
                    'div[aria-label*="Photo"][role="button"]'):
            try:
                page.locator(sel).first.click(timeout=4000)
                break
            except Exception:
                continue
        page.wait_for_timeout(1200)
        uploaded = False
        for sel in ('div[role="dialog"] input[type="file"][accept*="image"]',
                    'div[role="dialog"] input[type="file"]',
                    'input[type="file"][accept*="image"]',
                    'input[type="file"]'):
            try:
                page.locator(sel).first.set_input_files(image_paths, timeout=8000)
                uploaded = True
                break
            except Exception:
                continue
        if not uploaded:
            res["status"] = "error"; res["error"] = "photo input not found (graphics upload failed)"; return res

        # Wait (bounded) for the slide thumbnails to finish processing.
        try:
            page.wait_for_selector(
                'div[role="dialog"] img[src*="scontent"], div[role="dialog"] img[src^="blob:"]',
                timeout=25000)
        except Exception:
            pass
        page.wait_for_timeout(4000)

        # Submit the graphics-only post.
        submitted = False
        for sel in ('div[role="dialog"] div[aria-label="Post"]',
                    'div[aria-label="Post"][role="button"]'):
            try:
                page.locator(sel).first.click(timeout=5000)
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
        elif "comment as tulsa gays" in body:
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
    # GRAPHICS ONLY (William's hard rule, 2026-06-15): the group post is the 9
    # carousel slides, never a text/caption post. Validate they exist up front.
    post_dir = ROOT / "data" / "posts" / week
    image_paths = [str(post_dir / f"all__{i:02d}.png") for i in range(1, 10)]
    missing = [p for p in image_paths if not Path(p).exists()]
    if missing and not dry_run:
        raise SystemExit(f"GRAPHICS MISSING: {len(missing)}/9 slides not in {post_dir} "
                         f"— generate the carousel before blasting.")
    if not dry_run:
        _gate(image_paths)  # abort the whole blast if any slide is tofu/broken
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
    PROFILE_DIR = ROOT / "data" / "fb_auto_profile"
    use_profile = PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())
    if not use_profile and not AUTH_PATH.exists():
        raise SystemExit("No FB session. Set up the persistent profile once via "
                         "tools/fb_profile_login.py, or run --setup for a storage_state.")

    results = []
    with sync_playwright() as pw:
        if use_profile:
            # DURABLE PATH (2026-06-08): a dedicated, persistent REAL-Chrome profile
            # logged into FB once. FB trusts real Chrome and the login persists for
            # months; the daily keepalive keeps it warm. No expiring storage_state
            # snapshot, no app-bound-encryption capture problem. This is what makes
            # the weekly group blast run unattended without a manual re-login.
            ctx = pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel="chrome", headless=not headed,
                args=["--no-first-run", "--no-default-browser-check"])
            b = ctx  # ctx.close() tears the whole persistent context down
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
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
                "Re-auth (2 min): python tools/fb_profile_login.py  "
                "(REAL Chrome — Google trusts it; do NOT use capture_group_auth.py, "
                "its Chrome-for-Testing browser is blocked at Google login).")

        if not _switch_to_page(page):
            b.close()
            raise SystemExit("Could not confirm 'acting as Tulsa Gays Page'. "
                             "Aborting (anonymity guard). Re-run --setup if login expired.")
        print(f"\n[ok] acting as {PAGE_NAME}\n")

        # Bounded ops so a single group can never wedge the whole run (the
        # recurring silent 15-min hang). Plus a hard wall-clock cap on the loop.
        page.set_default_timeout(20000)
        page.set_default_navigation_timeout(35000)
        loop_deadline = time.monotonic() + 1200   # 20 min hard cap (fits all ~17 groups in one pass; still bounded so it can never silently hang)

        for i, g in enumerate(plan):
            if time.monotonic() > loop_deadline:
                print("  [aborted]  10-min wall-clock cap hit — stopping (no silent hang)")
                results.append({"name": g["name"], "id": g["id"], "status": "error",
                                "error": "run wall-clock cap hit before this group",
                                "at": datetime.now(timezone.utc).isoformat()})
                break
            r = _post_to_group(page, g, image_paths)
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
