"""
Post the weekly carousel to Facebook and Instagram.

Usage:
    python tools/post_weekly.py              # post this week's slides
    python tools/post_weekly.py --dry-run    # validate only: no posting, no git push
    python tools/post_weekly.py --ig-only    # recovery: Facebook is live, publish the same deck to IG only
    python tools/post_weekly.py --selftest-channels   # offline proof of the IG guard + PARTIAL reporting

Steps:
  1. Validate slides (all 9 present, >50KB each)
  2. Build an Instagram-safe JPEG of each slide (tools/ig_media_guard.py), copy
     slides + JPEGs to docs/posts/{week-key}/ and git push
  3. Post multi-image carousel to Facebook page (binary upload)
  4. Wait until every JPEG is publicly served byte-for-byte, then post the
     carousel to Instagram with only those verified URLs
  5. Save post IDs, per-channel status and the outcome (OK / PARTIAL / FAILED)
     to meta_api_config.json, post_ledger.json and post_results.json

Exit code: 0 = every attempted channel is live, 3 = PARTIAL (Facebook live,
Instagram failed, or the reverse), 1 = nothing went out.
"""

import json
import os
import re
import sys
import shutil
import subprocess
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config

DRY_RUN = "--dry-run" in sys.argv
IG_ONLY = "--ig-only" in sys.argv

# How long to wait for GitHub Pages to serve the pushed Instagram JPEGs before
# falling back to the commit-pinned raw.githubusercontent.com copy. W39's deploy
# took 8 minutes and W41's took 73; the old code waited a fixed 50 seconds.
IG_URL_WAIT_S = 240
_GUARD_FETCH = None          # test hook: fake HTTP for ig_media_guard
_TRACK_ENGAGEMENT = True     # test hook: selftest must not write engagement logs

# ── Load meta credentials ───────────────────────────────────────────────────
META_CFG_PATH = ROOT / "meta_api_config.json"

with open(META_CFG_PATH, encoding="utf-8") as f:
    meta_cfg = json.load(f)

PAGE_TOKEN = config.TULSAGAYS_PAGE_ACCESS_TOKEN
if not PAGE_TOKEN:
    raise SystemExit(
        "TulsaGays page token not found. config.py looked in env "
        "TULSAGAYS_PAGE_ACCESS_TOKEN, ./meta_api_config.json, and "
        "~/.claude/tulsagays/meta_api_config.json. Populate one of those."
    )
PAGE_ID    = meta_cfg["page_id"]
IG_ID      = meta_cfg["instagram_business_account_id"]
API_BASE   = "https://graph.facebook.com/v25.0"

# ── Week and slide locations ────────────────────────────────────────────────
WEEK_KEY   = config.current_week_key()
SLIDES_DIR = ROOT / "data" / "posts" / WEEK_KEY
DOCS_DIR   = ROOT / "docs" / "posts" / WEEK_KEY

# GitHub Pages public URL base. Host comes from config.SITE_URL (city-specific,
# NEVER_SYNC) so it always matches that city's docs/CNAME. Hardcoding the Tulsa
# host here is what gave LexingtonGays two canonical hosts: sync_from_tulsa.py
# rewrites "https://www.tulsagays.com" to "https://www.<domain>", which forced a
# www on a site whose CNAME is the bare domain. (2026-09-08)
SITE_HOST  = (getattr(config, "SITE_URL", "") or "").rstrip("/")
SITE_BASE  = f"{SITE_HOST}/posts/{WEEK_KEY}"

WEEK_OPENERS = [
    "Okay. We need to talk about what's happening in Tulsa this week.",
    "Your calendar needs clearing. At least one night. Actually all of them.",
    "Tulsa is doing the absolute most this week and we are completely here for it.",
    "Leave the house. We've given you zero reasons not to.",
    "This week in Tulsa? Fully undefeated. Here's what's on the agenda.",
    "If your week looks empty right now — fix that.",
    "We've got rhinestones, live music, drag, and community. Pick a night. Or all of them.",
    "This is your official sign to stop scrolling and start planning.",
]

EOTW_LEADS = [
    "This week's must-go:",
    "The event that needs to be on your calendar before anything else:",
    "Start with this one. Do not skip it:",
    "If you do one thing this week, make it this:",
    "The event of the week is not even a debate:",
    "We don't say 'don't miss it' lightly. This time we mean it:",
    "Clear the night. Here's why:",
    "This week's headliner:",
]

URGENCY_LINES = [
    lambda day, time, venue: f"{day} at {time}{f', {venue}' if venue else ''}. One night. An intimate room. You either go or you hear about it.",
    lambda day, time, venue: f"That's {day} at {time}{f' at {venue}' if venue else ''}. This doesn't happen every week. That's the whole point.",
    lambda day, time, venue: f"{day} night. {time}{f' at {venue}' if venue else ''}. You will not find anything like this anywhere else in Tulsa.",
    lambda day, time, venue: f"One night{f' — {day} at {time}' if day and time else ''}. An intimate space. The kind of evening you actually remember.",
    lambda day, time, venue: f"{day} at {time}{f', {venue}' if venue else ''}. The room is small. The energy is not. Go.",
    lambda day, time, venue: f"It's {day} at {time}{f' at {venue}' if venue else ''}. A room full of LGBTQIA+ joy and no reason to be anywhere else.",
    lambda day, time, venue: f"{day}. {time}{f'. {venue}' if venue else ''}. Be there or spend Friday hearing about it.",
    lambda day, time, venue: f"This is {day} at {time}{f' at {venue}' if venue else ''}. Intimate. Live. Unrepeatable. Go.",
]

FOMO_CLOSES = [
    "And that's just one night. The whole week is stacked — swipe through.",
    "Beyond that? Something happening every single day this week. Tap through.",
    "That's the headliner. The rest of the week keeps going — swipe to see it all.",
    "The week doesn't stop there. There's something on every single day.",
    "Clear that night first. Then swipe — the rest of the week is just as full.",
    "One night is not all you get. There's a whole week of this. Tap through.",
]

HASHTAGS = "#TulsaGays #TulsaLGBTQ #TulsaLGBTQIA #TulsaEvents #HomoHotelHappyHour #Tulsa #TulsaOklahoma #Oklahoma #VisitTulsa #OklahomaLGBTQ"

# Instagram location ID for "Tulsa, Oklahoma" on Facebook/Instagram.
# Adds a clickable location tag to every post — boosts local discovery.
# DISABLED: "213340757" was rejected by the API as invalid on 2026-05-25.
# To re-enable: GET graph.facebook.com/v25.0/search?type=place&q=Tulsa+Oklahoma&access_token={TOKEN}
# Find the correct numeric place ID and set it below.
IG_LOCATION_ID = ""  # disabled until valid ID is confirmed


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_eotw() -> dict | None:
    """Find the Event of the Week from this week's events JSON."""
    from eotw_selector import select_eotw

    events_file = ROOT / "data" / "events" / f"{WEEK_KEY}_all.json"
    if not events_file.exists():
        return None
    with open(events_file, encoding="utf-8") as f:
        data = json.load(f)
    events = data if isinstance(data, list) else data.get("events", [])

    today = datetime.now().date()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)

    def in_week(e):
        d = e.get("date", "")
        try:
            return week_monday <= datetime.strptime(d, "%Y-%m-%d").date() <= week_sunday
        except Exception:
            return False

    this_week = [e for e in events if in_week(e)]
    return select_eotw(this_week)


def _get_handle_line() -> str:
    """Return an '@mention' line for orgs whose events appear this week.

    Reads this week's events, looks up each source in config.SOURCE_IG_HANDLES,
    deduplicates, and returns a compact tag line (or '' if none are known).
    """
    handle_map = getattr(config, "SOURCE_IG_HANDLES", {})
    if not handle_map:
        return ""

    events_file = ROOT / "data" / "events" / f"{WEEK_KEY}_all.json"
    if not events_file.exists():
        return ""

    try:
        with open(events_file, encoding="utf-8") as f:
            data = json.load(f)
        events = data if isinstance(data, list) else data.get("events", [])
    except Exception:
        return ""

    seen_handles: list[str] = []
    seen_set: set[str] = set()
    for e in events:
        src = (e.get("source") or "").lower()
        handle = handle_map.get(src)
        if handle and handle not in seen_set:
            seen_handles.append(handle)
            seen_set.add(handle)

    if not seen_handles:
        return ""

    # Cap at 5 handles — more than that looks spammy
    return " ".join(seen_handles[:5])


def _format_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%A, %B ") + str(dt.day)
    except Exception:
        return date_str


def generate_caption() -> str:
    """Sassy, EOTW-focused caption. Sells the experience. Sounds like a person."""
    week_num = datetime.now().isocalendar()[1]
    eotw = _get_eotw()

    lines = [WEEK_OPENERS[week_num % len(WEEK_OPENERS)], ""]

    if eotw:
        name = eotw.get("name", "").strip()
        desc = eotw.get("description", "").strip()
        venue_full = eotw.get("venue", "").strip()
        venue = venue_full.split(",")[0].strip() if venue_full else ""
        date_str = eotw.get("date", "")
        time_str = eotw.get("time", "").strip()

        day_name = ""
        if date_str:
            try:
                day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
            except Exception:
                pass

        # Lead → event name → full description (the sell) → when/where + urgency
        lines.append(EOTW_LEADS[week_num % len(EOTW_LEADS)])
        lines.append("")
        lines.append(name)
        lines.append("")

        # Full description — use all of it, this is what sells it
        if desc:
            sentences = [s.strip() for s in desc.replace("\n", " ").split(".") if s.strip()]
            full_desc = ". ".join(sentences)
            if not full_desc.endswith("."):
                full_desc += "."
            lines.append(full_desc)
            lines.append("")

        # When/where + urgency — AFTER the pitch, as the call to act
        urgency_fn = URGENCY_LINES[week_num % len(URGENCY_LINES)]
        lines.append(urgency_fn(day_name, time_str, venue))
        lines.append("")

    lines.append(FOMO_CLOSES[week_num % len(FOMO_CLOSES)])
    lines.append("")
    lines.append("Hundreds of fabulous events every week in Tulsa. Full list at tulsagays.com")
    lines.append("New carousel every Monday. Follow @tulsagays so you don't miss it.")
    lines.append("")
    handle_line = _get_handle_line()
    if handle_line:
        lines.append(handle_line)
        lines.append("")
    lines.append(HASHTAGS)

    return "\n".join(lines)


def load_caption() -> str:
    """Return the post caption — custom from all_post.json, or dynamically generated."""
    post_json = SLIDES_DIR / "all_post.json"
    if post_json.exists():
        with open(post_json, encoding="utf-8") as f:
            data = json.load(f)
        cap = data.get("caption", "").strip()
        if cap and len(cap) > 100:
            return cap
    return generate_caption()


def get_slides() -> list[Path]:
    """Return sorted list of slide PNGs for this week.

    Supports both the legacy all__*.png naming and the current weekday__*.png
    / weekend__*.png naming conventions. Blank day slides (no events, mostly
    black, <30KB) are silently excluded — users don't need to swipe through
    empty slides. The CTA/outro slide is always included if present (it's
    always >=40KB due to text content).
    """
    if not SLIDES_DIR.exists():
        return []
    # Prefer weekday__*.png (current naming), fall back to all__*.png (legacy)
    all_slides = sorted(SLIDES_DIR.glob("weekday__*.png"))
    if not all_slides:
        all_slides = sorted(SLIDES_DIR.glob("all__*.png"))

    # Filter out intentionally blank day slides (mostly black canvas = tiny file)
    # Threshold: < 30KB indicates a "no events" placeholder, not a real slide.
    # Always keep the last slide (CTA/outro) regardless of size.
    MIN_CONTENT_BYTES = 30 * 1024
    slides = []
    for i, slide in enumerate(all_slides):
        is_last = (i == len(all_slides) - 1)
        size = slide.stat().st_size
        if size >= MIN_CONTENT_BYTES or is_last:
            slides.append(slide)
        else:
            print(f"[skip] {slide.name} ({size // 1024}KB) — blank day slide, excluded from carousel")
    return slides


def validate_slides(slides: list[Path]) -> None:
    if not slides:
        sys.exit(f"ERROR: No slides found in {SLIDES_DIR}.\n"
                 f"Run: python main.py generate-all")
    # Minimum 2 slides for a carousel (Instagram requires >=2).
    # Light weeks (Memorial Day, holiday weeks) may have fewer than 9 content slides
    # after blank day slides are filtered out — that is expected, not an error.
    if len(slides) < 2:
        sys.exit(f"ERROR: Only {len(slides)} slides found (need at least 2 for a carousel).\n"
                 f"Run: python main.py generate-all")
    for s in slides:
        size = s.stat().st_size
        if size < 15 * 1024:
            sys.exit(f"ERROR: {s.name} is only {size // 1024}KB — likely corrupt.\n"
                     f"Re-generate slides: python main.py generate-all")
    # PIXEL GATE (added 2026-06-20): every carousel slide must pass the graphic QA
    # gate (tofu/blank/resolution) before it can be hosted+posted. image_maker
    # routes emoji to the color font so slides are normally clean, but this is the
    # defense-in-depth backstop that makes a cheap/broken slide unpostable.
    try:
        from tools.preflight_image import preflight as _pf
    except Exception:
        from preflight_image import preflight as _pf  # when run from tools/
    bad = []
    for s in slides:
        v = _pf(str(s))
        if not v["ok"]:
            bad.append(f"{s.name}: {v['reason']}")
    if bad:
        sys.exit("ERROR: carousel slide(s) FAILED graphic QA — refusing to post:\n   "
                 + "\n   ".join(bad)
                 + "\n   Re-generate slides: python main.py generate-all")
    if len(slides) < 9:
        print(f"[NOTE] {len(slides)} slides (light week — some days had no events)")
    print(f"[OK] {len(slides)} slides validated + graphic-QA clean ({WEEK_KEY})")
    # APPROVAL ARTIFACT (added 2026-06-20): emit the visual contact sheet so the
    # review/approval request carries a single image of every graphic (green=pass,
    # red=blocked). Best-effort — never blocks posting.
    try:
        from tools.graphic_contact_sheet import build_sheet as _sheet
    except Exception:
        try:
            from graphic_contact_sheet import build_sheet as _sheet
        except Exception:
            _sheet = None
    if _sheet is not None:
        try:
            res = _sheet(str(SLIDES_DIR))
            if res.get("out"):
                print(f"[OK] approval contact sheet -> {res['out']} ({res['reason']})")
        except Exception as _e:
            print(f"[WARN] contact sheet skipped: {_e}")


def _guard():
    """tools/ig_media_guard.py, imported lazily so a broken import fails only
    the Instagram leg (reported PARTIAL), never the Facebook post. Always go
    through here so every caller shares one VERIFIED registry."""
    try:
        from tools import ig_media_guard as g
    except Exception:
        import ig_media_guard as g  # when run from tools/
    return g


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)


def _raw_base(sha: str) -> str:
    """raw.githubusercontent.com folder for this week's hosted files, pinned to
    the pushed commit: immutable, and live as soon as the push lands."""
    remote = (_git("remote", "get-url", "origin").stdout or "").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote)
    if not (m and sha):
        return ""
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{sha}/docs/posts/{WEEK_KEY}"


def stage_ig_assets(slides: list[Path]) -> dict:
    """Copy the slides to docs/posts/{week-key}/, write a validated
    Instagram-safe JPEG of each next to them, then commit + push that folder.

    Raises ig_media_guard.IGAssetError, naming every bad asset, before anything
    is pushed. Dry-run writes the local files but never commits or pushes (the
    old dry-run pushed the week's slides to the public site)."""
    g = _guard()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for slide in slides:
        dest = DOCS_DIR / slide.name
        if not dest.exists() or dest.stat().st_mtime < slide.stat().st_mtime:
            shutil.copy2(slide, dest)
    assets, bad = g.prepare_assets(slides, DOCS_DIR)
    if bad:
        raise g.IGAssetError(bad)
    for a in assets:
        how = f"converted {a.converted_from} to JPEG" if a.converted_from else "JPEG as-is"
        extra = f" ({'; '.join(a.notes)})" if a.notes else ""
        print(f"[IG-ASSET] {a.source.name} -> {a.name}: {a.width}x{a.height}, {a.size // 1024}KB, {how}{extra}")
    print(f"[OK] {len(assets)} slides + Instagram JPEGs in docs/posts/{WEEK_KEY}/")
    if DRY_RUN:
        print("[DRY RUN] not committing or pushing docs/posts; public URLs not checked")
        return {"assets": assets, "sha": "", "pushed": False}

    # Commit ONLY this week's folder, never whatever else is staged in the repo.
    rel_path = f"docs/posts/{WEEK_KEY}"
    _git("add", rel_path)
    c = _git("commit", "-m", f"slides: publish {WEEK_KEY} carousel images", "--", rel_path)
    if c.returncode != 0:
        out = (c.stdout + c.stderr).strip()
        if "nothing" in out or "no changes" in out:
            print("[OK] Slides already committed, skipping commit.")
        else:
            print(f"WARN: git commit failed: {out[:300]}")
    p = _git("push", "origin", "main")
    pushed = p.returncode == 0
    sha = (_git("rev-parse", "HEAD").stdout or "").strip()
    if pushed:
        print(f"[OK] docs/posts/{WEEK_KEY} pushed at {sha[:7]}")
    else:
        print(f"WARN: git push failed: {p.stderr.strip()[:300]}")
        print("      The URL check decides whether Instagram can be sent anything.")
    return {"assets": assets, "sha": sha, "pushed": pushed}


def resolve_ig_urls(staged: dict) -> list[str]:
    """Return one verified public URL per Instagram JPEG, or raise IGAssetError
    naming each asset that never became fetchable.

    Replaces a fixed 50s sleep plus a HEAD on slide 1 that carried on after a
    404. That is the W39/W41 failure: Instagram was handed www.tulsagays.com
    URLs while the GitHub Pages deploy was still running (8 and 73 minutes), so
    it downloaded the Pages 404 page and answered "Only photo or video can be
    accepted as media type"."""
    g = _guard()
    if DRY_RUN:
        return [f"{SITE_BASE}/{a.name}" for a in staged["assets"]]
    return g.resolve_public_urls(staged["assets"], SITE_BASE, _raw_base(staged.get("sha", "")),
                                 fetch=_GUARD_FETCH, budget_s=IG_URL_WAIT_S)


def host_slides_for_ig(slides: list[Path]) -> list[str]:
    """Stage + resolve in one call. tools/post_weekend.py uses this."""
    return resolve_ig_urls(stage_ig_assets(slides))


# ── Facebook ─────────────────────────────────────────────────────────────────

def fb_upload_photo_binary(slide_path: Path) -> str:
    """Upload a single slide to FB page as unpublished photo. Returns photo ID."""
    url = f"{API_BASE}/{PAGE_ID}/photos"
    with open(slide_path, "rb") as img:
        resp = requests.post(
            url,
            data={"published": "false", "access_token": PAGE_TOKEN},
            files={"source": (slide_path.name, img, "image/png")},
            timeout=120,
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"FB photo upload error: {data['error'].get('message')}")
    if "id" not in data:
        raise RuntimeError(f"FB photo upload returned no ID: {data}")
    return data["id"]


def post_fb_carousel(slides: list[Path], caption: str) -> dict:
    """Upload slides and create multi-image FB page post."""
    print(f"\n[FB] Uploading {len(slides)} photos...")
    photo_ids = []
    for i, slide in enumerate(slides, 1):
        print(f"     Slide {i}/{len(slides)}: {slide.name}", end=" ... ", flush=True)
        if DRY_RUN:
            print("(dry run)")
            photo_ids.append(f"dry_run_{i}")
            continue
        pid = fb_upload_photo_binary(slide)
        photo_ids.append(pid)
        print(f"ID {pid}")
        if i < len(slides):
            time.sleep(1.5)

    print(f"\n[FB] Creating post with {len(photo_ids)} attached photos...")
    if DRY_RUN:
        print("     (dry run — skipping post)")
        return {"post_id": "dry_run_post_id", "photo_ids": photo_ids}

    attached = json.dumps([{"media_fbid": pid} for pid in photo_ids])
    # The 9-photo attached_media /feed call intermittently returns FB's transient
    # "Please reduce the amount of data you're asking for, then retry your
    # request" (error code 1/2). Photos are already uploaded, so retry ONLY the
    # post-creation call with backoff — no duplicate uploads. FB returns the new
    # post id on success, so a retry after a true error cannot double-post.
    def _already_posted():
        """Did a 'failed' /feed attempt actually create the post? FB sometimes
        returns a transient error AFTER creating it (W30 2026-07-20: attempt 1
        'errored', the retry then failed 'Invalid parameter' because the photos
        were already consumed — but the post was LIVE). An unpublished photo's
        page_story_id is set the moment it's attached to a published post, so
        query the first photo instead of retrying blind."""
        try:
            r = requests.get(f"{API_BASE}/{photo_ids[0]}",
                             params={"fields": "page_story_id",
                                     "access_token": PAGE_TOKEN},
                             timeout=30).json()
            return r.get("page_story_id")
        except Exception:
            return None

    data = {}
    last_err = None
    for attempt, delay in enumerate((0, 8, 20, 40), start=1):
        if delay:
            story = _already_posted()
            if story:
                print(f"     [FB] attempt {attempt-1}'s 'error' was a false negative — post {story} is LIVE.")
                return {"post_id": story, "photo_ids": photo_ids}
            print(f"     [FB] transient error, retry {attempt-1} in {delay}s...")
            time.sleep(delay)
        resp = requests.post(
            f"{API_BASE}/{PAGE_ID}/feed",
            data={"message": caption, "attached_media": attached, "access_token": PAGE_TOKEN},
            timeout=60,
        )
        data = resp.json()
        if "id" in data:
            break
        last_err = data.get("error", {})
        code = last_err.get("code")
        # Retry only the known-transient codes; fail fast on real errors —
        # but never before checking whether the post actually landed.
        if code not in (1, 2) and "reduce the amount of data" not in (last_err.get("message") or "").lower():
            story = _already_posted()
            if story:
                print(f"     [FB] '{last_err.get('message')}' but post {story} is LIVE — treating as success.")
                return {"post_id": story, "photo_ids": photo_ids}
            raise RuntimeError(f"FB post failed: {last_err.get('message')}")
    if "id" not in data:
        raise RuntimeError(f"FB post failed after retries: {last_err}")

    post_id = data["id"]
    print(f"[OK] Facebook post: https://www.facebook.com/{post_id}")
    return {"post_id": post_id, "photo_ids": photo_ids}


# ── Instagram ────────────────────────────────────────────────────────────────

def _ig_fetch_error(err: dict) -> bool:
    """Instagram could not download/accept the image_url bytes (code 9004,
    subcode 2207052 "media could not be fetched", 2207003 download timeout)."""
    msg = (err.get("message") or "").lower()
    return (err.get("code") == 9004 or err.get("error_subcode") in (2207052, 2207003)
            or "media type" in msg or "download" in msg or "fetch" in msg)


def post_ig_carousel(public_urls: list[str], caption: str) -> str:
    """Post Instagram carousel using public image URLs. Returns IG post ID.

    Every URL must have been proven by ig_media_guard in this process, or pass
    a fresh check right here; an unproven URL is refused BEFORE the container
    call. A child container that Instagram could not fetch is retried (twice,
    30s apart) only while the URL still serves a valid image. Child and
    carousel containers are unpublished drafts, so a retry cannot double-post."""
    urls = public_urls[:10]  # IG max 10 images
    print(f"\n[IG] Creating {len(urls)} carousel item containers...")

    if DRY_RUN:
        print("     (dry run, skipping IG post)")
        return "dry_run_ig_id"

    g = _guard()
    child_ids = []
    for i, url in enumerate(urls, 1):
        if not g.is_verified(url):
            ok, why = g.check_url_for_ig(url, fetch=_GUARD_FETCH)
            if not ok:
                raise RuntimeError(f"IG item {i} refused before the container call ({url}): {why}")
        print(f"     Item {i}/{len(urls)}", end=" ... ", flush=True)
        data = {}
        for attempt in range(3):
            resp = requests.post(
                f"{API_BASE}/{IG_ID}/media",
                data={"image_url": url, "is_carousel_item": "true", "access_token": PAGE_TOKEN},
                timeout=120,
            )
            # Note: location_id is set on the carousel container, not individual items
            data = resp.json()
            err = data.get("error")
            if not err:
                break
            if attempt < 2 and _ig_fetch_error(err):
                ok, why = g.check_url_for_ig(url, fetch=_GUARD_FETCH)
                if not ok:
                    raise RuntimeError(f"IG container {i} failed: {err.get('message')} "
                                       f"(the URL now fails too: {why})")
                print(f"(IG could not fetch it: {err.get('message')}; the URL serves a valid "
                      f"image, retrying in 30s)", end=" ... ", flush=True)
                time.sleep(30)
                continue
            raise RuntimeError(f"IG container {i} failed: {err.get('message')} "
                               f"(code {err.get('code')}, subcode {err.get('error_subcode')}, url {url})")
        cid = data.get("id")
        if not cid:
            raise RuntimeError(f"IG container {i} returned no ID: {data}")
        child_ids.append(cid)
        print(f"ID {cid}")
        time.sleep(2)

    print("[IG] Creating carousel container...")
    carousel_params = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": PAGE_TOKEN,
    }
    if IG_LOCATION_ID:
        carousel_params["location_id"] = IG_LOCATION_ID
        print(f"     Location tag: {IG_LOCATION_ID}")
    resp = requests.post(
        f"{API_BASE}/{IG_ID}/media",
        data=carousel_params,
        timeout=60,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"IG carousel container failed: {data['error'].get('message')}")
    carousel_id = data.get("id")
    if not carousel_id:
        raise RuntimeError(f"IG carousel container returned no ID: {data}")

    print(f"     Carousel ID: {carousel_id}")
    time.sleep(3)

    print("[IG] Publishing carousel...")
    resp = requests.post(
        f"{API_BASE}/{IG_ID}/media_publish",
        data={"creation_id": carousel_id, "access_token": PAGE_TOKEN},
        timeout=60,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"IG publish failed: {data['error'].get('message')}")
    ig_post_id = data.get("id")
    if not ig_post_id:
        raise RuntimeError(f"IG publish returned no ID: {data}")

    print(f"[OK] Instagram post: https://www.instagram.com/p/{ig_post_id}/")
    return ig_post_id


# ── Save results ─────────────────────────────────────────────────────────────

def channel_outcome(channels: dict) -> str:
    """OK only when EVERY attempted channel delivered. One live and one failed
    is PARTIAL, never 'verified' (W39 and W41 were logged 'posted + verified'
    with Instagram dead)."""
    if not channels:
        return "FAILED"
    good = [k for k, v in channels.items() if v.get("status") in ("ok", "dry_run")]
    if len(good) == len(channels):
        return "OK"
    return "PARTIAL" if good else "FAILED"


def outcome_exit_code(outcome: str) -> int:
    return {"OK": 0, "PARTIAL": 3}.get(outcome, 1)


def save_results(fb_result: dict, ig_post_id: str, channels: dict | None = None,
                 outcome: str | None = None) -> None:
    today = datetime.now().strftime("%Y-%m-%d")

    if not DRY_RUN:
        # A dry run used to overwrite last_post and the week's REAL
        # post_results.json with dry_run ids. It now writes its own file.
        meta_cfg["last_post"] = {
            "date": today,
            "week_key": WEEK_KEY,
            "fb_post_id": fb_result["post_id"],
            "ig_post_id": ig_post_id,
            "photo_ids": fb_result["photo_ids"],
            "outcome": outcome,
            "note": f"Weekly carousel {WEEK_KEY}. 9 slides.",
        }
        with open(META_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(meta_cfg, f, indent=2)

    results_path = SLIDES_DIR / ("post_results_dryrun.json" if DRY_RUN else "post_results.json")
    results = {
        "week": WEEK_KEY,
        "posted_at": datetime.now().isoformat(),
        "fb_post_id": fb_result["post_id"],
        "ig_post_id": ig_post_id,
        "photo_ids": fb_result["photo_ids"],
        "outcome": outcome,
        "channels": channels or {},
        "dry_run": DRY_RUN,
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {results_path}")

    # Log the post for engagement tracking. The fetch_engagement() call
    # requires a valid Meta token — it will silently skip if the token is
    # expired. Re-run engagement_tracker.fetch_engagement(ig_post_id) after
    # refreshing the page token to backfill this week's numbers.
    if _TRACK_ENGAGEMENT and not DRY_RUN and not ig_post_id.startswith("FAILED"):
        try:
            sys.path.insert(0, str(ROOT))
            from self_improve.engagement_tracker import log_post, fetch_engagement
            events_file = ROOT / "data" / "events" / f"{WEEK_KEY}_all.json"
            events_count = 0
            if events_file.exists():
                with open(events_file, encoding="utf-8") as ef:
                    edata = json.load(ef)
                events_count = edata.get("total_events", 0) if isinstance(edata, dict) else len(edata)
            log_post(
                post_id=ig_post_id,
                post_type="carousel",
                events_featured=events_count,
                caption_style="eotw_hype",
            )
            print(f"[engagement] Post logged: {ig_post_id}")
            # Attempt an immediate metrics fetch — will silently fail if token expired
            metrics = fetch_engagement(ig_post_id)
            if metrics:
                print(f"[engagement] Live metrics: reach={metrics.get('reach',0)}, "
                      f"impressions={metrics.get('impressions',0)}, saves={metrics.get('saves',0)}")
            else:
                print("[engagement] Metrics fetch skipped (token likely expired). "
                      "Refresh page_access_token and re-run: "
                      "python -c \"from self_improve.engagement_tracker import fetch_engagement; "
                      f"fetch_engagement('{ig_post_id}')\"")
        except Exception as _e:
            print(f"[engagement] Tracking skipped: {_e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"TULSA GAYS — POST WEEKLY CAROUSEL ({WEEK_KEY})")
    if DRY_RUN:
        print("  *** DRY RUN MODE — no actual posts will go out ***")
    print("=" * 60)

    # Step 0: Hard approval gate — slides must be reviewed before posting
    approval_path = SLIDES_DIR / "approval_status.json"
    if not DRY_RUN:
        if not approval_path.exists():
            print(
                f"\n[STOP] No approval_status.json found at {approval_path}\n"
                f"       William has not reviewed this week's content.\n"
                f"       Run the Sunday approval task, or create approval_status.json with approved=true.\n"
                f"       Post ABORTED."
            )
            sys.exit(1)
        with open(approval_path, encoding="utf-8") as _f:
            _approval = json.load(_f)
        if not _approval.get("approved"):
            print(
                f"\n[STOP] approval_status.json exists but approved={_approval.get('approved')}.\n"
                f"       William has not approved this week's content.\n"
                f"       Post ABORTED."
            )
            sys.exit(1)
        print(f"[OK] Content approved ({_approval.get('approved_at', 'timestamp unknown')})")

    # Step 0.5: Hard PREFLIGHT gate — verify events, text fit, descriptions,
    # links. Blocks posting on any error. Runs even in dry-run (report only).
    try:
        from tools.preflight_post import run as _preflight_run
    except Exception:
        try:
            import preflight_post as _pf  # when run from tools/
            _preflight_run = _pf.run
        except Exception:
            _preflight_run = None
    if _preflight_run is not None:
        _pf_ok = _preflight_run(WEEK_KEY)
        if not _pf_ok and not DRY_RUN:
            print(
                "\n[STOP] Pre-post preflight FAILED — see the blocking errors above\n"
                "       and preflight_status.json. Post ABORTED."
            )
            sys.exit(1)
        if not _pf_ok and DRY_RUN:
            print("[DRY RUN] Preflight failed — a real post would be BLOCKED here.")
    else:
        print("[WARN] preflight_post unavailable — skipping verification (NOT recommended)")

    # Step 1: Validate slides
    slides = get_slides()
    validate_slides(slides)

    # Step 2: Load caption (strip any leaked harness/internal markers — these
    # must NEVER reach a public post; preflight also hard-blocks them).
    caption = load_caption()
    import re as _re
    caption = _re.split(r'\s*(?:SUPERVISOR_TASK_COMPLETE|SUPERVISOR:|TASK_COMPLETE)\b.*$',
                        caption, flags=_re.S)[0].rstrip()
    print(f"[OK] Caption loaded ({len(caption)} chars)")

    # Step 2.5: DUPLICATE-POST GUARD (2026-09-15). W38 went out TWICE on the
    # Page and on Instagram (4:02/4:19 PM FB, 4:04/4:20 PM IG): post_results.json
    # was written only at the very end, so a run that died after publishing left
    # no trace and the rerun published again. Now every publish is recorded the
    # moment it succeeds, and a rerun for a week that already has a live post is
    # refused. After a deliberate retraction, pass --repost.
    ledger_path = SLIDES_DIR / "post_ledger.json"
    live = _live_ids(ledger_path, SLIDES_DIR / "post_results.json")
    existing_fb = None
    if IG_ONLY and not DRY_RUN:
        # RECOVERY: the Page post is live and only Instagram failed. Publishes the
        # same deck + caption to Instagram and never touches Facebook. Whether a
        # late Instagram post is worth it is a human call; this is the tool for it.
        if live.get("ig_post_id"):
            print(f"\n[STOP] {WEEK_KEY} Instagram is already live ({live['ig_post_id']}). Nothing to recover.")
            sys.exit(1)
        if not live.get("fb_post_id"):
            print(f"\n[STOP] --ig-only recovers a week whose Facebook post is live; {WEEK_KEY} has none.\n"
                  f"       Run without --ig-only to post both channels.")
            sys.exit(1)
        existing_fb = {"post_id": live["fb_post_id"], "photo_ids": live.get("photo_ids") or []}
    elif not DRY_RUN and "--repost" not in sys.argv:
        prior = [f"{k}={v}" for k, v in live.items() if k.endswith("_post_id")]
        if prior:
            print(f"\n[STOP] {WEEK_KEY} already has live post(s): {', '.join(prior)}\n"
                  f"       Posting again would duplicate the carousel. If those posts were\n"
                  f"       retracted on purpose, rename the ledgers and re-run with --repost.\n"
                  f"       If only Instagram failed, use --ig-only.")
            sys.exit(1)

    result = publish(slides, caption, ledger_path, existing_fb=existing_fb)
    sys.exit(outcome_exit_code(result["outcome"]))


def _live_ids(*paths: Path) -> dict:
    """Post ids that are really live, from the ledger and post_results.json.
    A 'FAILED: ...' or dry-run value is not live."""
    live: dict = {}
    for p in paths:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("dry_run"):
            continue
        for k in ("fb_post_id", "ig_post_id"):
            v = str(d.get(k) or "")
            if v and v != "None" and not v.startswith(("FAILED", "dry_run")):
                live.setdefault(k, v)
        if d.get("photo_ids") and "photo_ids" not in live:
            live["photo_ids"] = d["photo_ids"]
    return live


def publish(slides: list[Path], caption: str, ledger_path: Path,
            existing_fb: dict | None = None) -> dict:
    """Stage IG assets, post Facebook (unless existing_fb), post Instagram,
    record every channel, and return {"outcome", "channels", ...}.

    outcome is OK only when every attempted channel delivered; a Facebook post
    with a dead Instagram leg is PARTIAL with the failing channel named."""

    def _record(key: str, value) -> None:
        if DRY_RUN:
            return
        try:
            cur = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"week": WEEK_KEY}
        except Exception:
            cur = {"week": WEEK_KEY}
        cur[key] = value
        cur[f"{key}_at"] = datetime.now().isoformat()
        ledger_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")

    channels: dict = {}

    # Step 3: build + validate the Instagram JPEGs and push them FIRST, so the
    # GitHub Pages deploy runs while Facebook uploads. A bad asset fails only
    # the Instagram leg, and fails it before any Instagram call.
    staged, ig_error = None, ""
    print("\n[HOSTING] Validating Instagram assets and publishing them to tulsagays.com...")
    try:
        staged = stage_ig_assets(slides)
    except Exception as e:
        ig_error = f"assets refused before any Instagram call: {e}"
        print(f"\n[FAIL] {ig_error}")

    # Step 4: Facebook (binary upload, no external hosting needed). A Facebook
    # failure raises: nothing is live, and the caller reports a failed run.
    if existing_fb:
        fb_result = existing_fb
        print(f"\n[FB] skipped (--ig-only); the live Page post is {fb_result['post_id']}")
        channels["facebook"] = {"status": "ok", "id": fb_result["post_id"],
                                "note": "already live, not re-posted (--ig-only)"}
    else:
        fb_result = post_fb_carousel(slides, caption)
        _record("fb_post_id", fb_result.get("post_id"))
        _record("photo_ids", fb_result.get("photo_ids"))
        channels["facebook"] = {"status": "dry_run" if DRY_RUN else "ok", "id": fb_result.get("post_id")}

    # Step 5: Instagram, only with URLs ig_media_guard proved serve the bytes.
    if ig_error:
        ig_post_id = f"FAILED: {ig_error}"
    else:
        try:
            public_urls = resolve_ig_urls(staged)
            ig_post_id = post_ig_carousel(public_urls, caption)
        except Exception as e:
            print(f"\n[FAIL] Instagram post failed: {e}")
            ig_post_id = f"FAILED: {e}"
    if ig_post_id.startswith("FAILED"):
        channels["instagram"] = {"status": "failed", "error": ig_post_id[len("FAILED: "):]}
    else:
        channels["instagram"] = {"status": "dry_run" if DRY_RUN else "ok", "id": ig_post_id}
    _record("ig_post_id", ig_post_id)

    outcome = channel_outcome(channels)
    _record("channels", channels)
    _record("outcome", outcome)

    # Step 6: Save results
    save_results(fb_result, ig_post_id, channels, outcome)

    # Summary
    print("\n" + "=" * 60)
    print("ALL DONE: every attempted channel is live" if outcome == "OK" else
          f"{outcome}: NOT every channel delivered")
    print(f"  Week:      {WEEK_KEY}")
    print(f"  FB post:   {fb_result['post_id']}")
    print(f"  IG post:   {ig_post_id}")
    print(f"  Photos:    {len(fb_result['photo_ids'])} on the FB post"
          + (" (untouched, --ig-only)" if existing_fb else " uploaded"))
    print("=" * 60)
    _print_group_steps()
    print("\n" + _outcome_line(outcome, channels))
    return {"outcome": outcome, "channels": channels, "fb_result": fb_result, "ig_post_id": ig_post_id}


def _outcome_line(outcome: str, channels: dict) -> str:
    parts = []
    for k, v in channels.items():
        if v.get("status") in ("ok", "dry_run"):
            parts.append(f"{k} live ({v.get('id')})" if v.get("status") == "ok" else f"{k} dry-run")
        else:
            parts.append(f"{k} FAILED: {v.get('error', 'unknown')}")
    line = f"OUTCOME {outcome} {WEEK_KEY}: " + "; ".join(parts)
    if outcome == "PARTIAL" and channels.get("instagram", {}).get("status") == "failed":
        line += ("\n  Instagram was NOT retried automatically. To publish this same deck to "
                 "Instagram only: python tools/post_weekly.py --ig-only")
    return line


def _print_group_steps() -> None:
    print("\nNEXT STEP: Upload all 9 slides directly to each FB group (browser).")
    print("Switch to Tulsa Gays page identity first. Then for each group:")
    print("  - Open group, Create post, attach all 9 images in order, add sassy EOTW caption, post.")
    print("Groups (11 total):")
    print("  1.  Gay men of Tulsa          groups/161646500587551")
    print("  2.  Okie Gays                 groups/2612250565491228")
    print("  3.  Tulsa LGBTQ+ Scene        groups/715281449025002")
    print("  4.  Gay Tulsa                 groups/GayTulsa")
    print("  5.  Tulsa's LGBT Nightlife    groups/220878821301627")
    print("  6.  Black Queer Tulsa         groups/436526440885847")
    print("  7.  Oklahoma Lesbian Friends  groups/649753022551343")
    print("  8.  Oklahoma House of Drag    groups/418182474119895")
    print("  9.  Interesting Things Tulsa  groups/InterestingThingsToDoInTulsa")
    print("  10. What's Up Tulsa?          groups/WhatsHappeningTulsa")
    print("  11. Tulsa Events              groups/114530202225051")


# ── Selftest (offline: fake Graph API, fake GitHub, temp dirs) ───────────────

def _selftest_channels() -> int:
    """Replays the W41 failure through publish() with no network: GitHub Pages
    answers 404 text/html, so Instagram must never be called and the run must
    read PARTIAL naming instagram. Then proves the healthy path, a bad asset,
    and --ig-only recovery."""
    global SLIDES_DIR, DOCS_DIR, META_CFG_PATH, DRY_RUN, IG_URL_WAIT_S, _GUARD_FETCH, _TRACK_ENGAGEMENT
    import tempfile
    from PIL import Image

    g = _guard()
    saved = (SLIDES_DIR, DOCS_DIR, META_CFG_PATH, DRY_RUN, IG_URL_WAIT_S, _GUARD_FETCH,
             _TRACK_ENGAGEMENT, dict(meta_cfg))
    real = (subprocess.run, requests.post, requests.get, requests.request, time.sleep)
    checks, failed = 0, []

    def check(cond, msg):
        nonlocal checks
        checks += 1
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failed.append(msg)

    graph: list[tuple[str, dict]] = []

    class _J:
        def __init__(self, d):
            self._d = d

        def json(self):
            return self._d

    def fake_post(url, data=None, files=None, timeout=None, **kw):
        data = dict(data or {})
        graph.append((url, data))
        if url.endswith(f"/{PAGE_ID}/photos"):
            return _J({"id": f"photo{len(graph)}"})
        if url.endswith(f"/{PAGE_ID}/feed"):
            return _J({"id": f"{PAGE_ID}_selftestpost"})
        if url.endswith(f"/{IG_ID}/media"):
            if data.get("is_carousel_item"):
                return _J({"id": f"child{len(graph)}"})
            return _J({"id": "carousel1"})
        if url.endswith(f"/{IG_ID}/media_publish"):
            return _J({"id": "ig_selftest_media"})
        return _J({"error": {"message": f"unexpected call {url}"}})

    def no_network(*a, **k):
        raise AssertionError(f"selftest tried the real network: {a[:2]}")

    def fake_git(cmd, cwd=None, capture_output=None, text=None, **kw):
        out = ""
        if cmd[:2] == ["git", "rev-parse"]:
            out = "48a2045" + "0" * 33
        elif cmd[:3] == ["git", "remote", "get-url"]:
            out = "https://github.com/DistrictOfRyan/tulsagays.git"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    gh404 = g.GITHUB_404
    tmp = Path(tempfile.mkdtemp(prefix="post_weekly_selftest_"))
    try:
        subprocess.run, requests.post, requests.get, requests.request = fake_git, fake_post, no_network, no_network
        time.sleep = lambda s: None
        _TRACK_ENGAGEMENT = False
        DRY_RUN = False
        IG_URL_WAIT_S = 0
        META_CFG_PATH = tmp / "meta_api_config.json"
        src_week = ROOT / "data" / "posts" / "2026-W41"

        def fresh(tag):
            d = tmp / tag
            (d / "data").mkdir(parents=True)
            slides = []
            for i in (1, 2, 3):
                real_slide = src_week / f"all__0{i}.png"
                p = d / "data" / f"all__0{i}.png"
                if real_slide.exists():
                    shutil.copy2(real_slide, p)
                else:
                    Image.new("RGB", (1080, 1080), (40, 10, 60)).save(p)
                slides.append(p)
            return d / "data", d / "docs", slides

        print("[A] W41 replay: Pages serves its 404 page (text/html) and the raw copy is not there either")

        def all_404(method, url):
            return g._Resp(404, "text/html; charset=utf-8", gh404)

        SLIDES_DIR, DOCS_DIR, slides = fresh("a")
        _GUARD_FETCH = all_404
        graph.clear()
        r = publish(slides, "selftest caption", SLIDES_DIR / "post_ledger.json")
        ig_calls = [u for u, _ in graph if f"/{IG_ID}/" in u]
        check(ig_calls == [], f"no Instagram container call was made ({len(ig_calls)} calls)")
        check(r["outcome"] == "PARTIAL", f"outcome is PARTIAL, not verified (got {r['outcome']})")
        check(r["channels"]["facebook"]["status"] == "ok", "facebook recorded live")
        ig_err = r["channels"]["instagram"].get("error", "")
        check(r["channels"]["instagram"]["status"] == "failed" and "404" in ig_err and "all__01.ig.jpg" in ig_err,
              f"instagram named as the failing channel with the asset + reason: {ig_err[:110]}")
        led = json.loads((SLIDES_DIR / "post_ledger.json").read_text(encoding="utf-8"))
        res = json.loads((SLIDES_DIR / "post_results.json").read_text(encoding="utf-8"))
        check(led.get("outcome") == "PARTIAL" and res.get("outcome") == "PARTIAL"
              and res["channels"]["instagram"]["status"] == "failed",
              "ledger and post_results.json both carry PARTIAL + per-channel status")
        check(outcome_exit_code(r["outcome"]) == 3, "PARTIAL exits 3, not 0")

        print("[B] healthy week: Pages serves the bytes")
        SLIDES_DIR, DOCS_DIR, slides = fresh("b")

        def pages_live(method, url):
            name = url.split("?")[0].rsplit("/", 1)[1]
            return g._Resp(200, "image/jpeg", (DOCS_DIR / name).read_bytes())

        _GUARD_FETCH = pages_live
        graph.clear()
        r = publish(slides, "selftest caption", SLIDES_DIR / "post_ledger.json")
        child_urls = [d.get("image_url") for u, d in graph if u.endswith(f"/{IG_ID}/media") and d.get("is_carousel_item")]
        check(r["outcome"] == "OK" and r["ig_post_id"] == "ig_selftest_media", f"outcome OK with the IG id (got {r['outcome']})")
        check(len(child_urls) == 3 and all(g.is_verified(u) and "?v=" in u for u in child_urls),
              "every IG child container got a URL the guard verified")
        check(all(".ig.jpg" in u for u in child_urls), "Instagram gets the JPEGs, Facebook keeps the PNG upload")
        check(outcome_exit_code(r["outcome"]) == 0, "OK exits 0")

        print("[C] a slide that is not an image: Instagram refused before any call, Facebook unaffected")
        SLIDES_DIR, DOCS_DIR, slides = fresh("c")
        slides[1].write_bytes(gh404)
        graph.clear()
        r = publish(slides, "selftest caption", SLIDES_DIR / "post_ledger.json")
        check(not [u for u, _ in graph if f"/{IG_ID}/" in u], "no Instagram call with a bad asset in the deck")
        check(r["outcome"] == "PARTIAL" and "all__02.png" in r["channels"]["instagram"]["error"]
              and "HTML" in r["channels"]["instagram"]["error"], "the bad asset and why are named")

        print("[D] --ig-only recovery: Facebook already live, Instagram failed")
        SLIDES_DIR, DOCS_DIR, slides = fresh("d")
        ledger = SLIDES_DIR / "post_ledger.json"
        ledger.write_text(json.dumps({"week": WEEK_KEY, "fb_post_id": f"{PAGE_ID}_existing",
                                      "photo_ids": ["p1", "p2", "p3"],
                                      "ig_post_id": "FAILED: IG container 1 failed: Only photo or video can be accepted as media type."}),
                          encoding="utf-8")
        live = _live_ids(ledger)
        check(live.get("fb_post_id") == f"{PAGE_ID}_existing" and "ig_post_id" not in live,
              "a FAILED Instagram id is not counted as live")
        _GUARD_FETCH = pages_live
        graph.clear()
        r = publish(slides, "selftest caption", ledger,
                    existing_fb={"post_id": live["fb_post_id"], "photo_ids": live["photo_ids"]})
        check(not [u for u, _ in graph if f"/{PAGE_ID}/" in u], "no Facebook call in --ig-only")
        check(r["outcome"] == "OK" and r["channels"]["facebook"]["id"] == f"{PAGE_ID}_existing",
              "Instagram posted, Facebook id preserved, outcome OK")

        print("[E] post_ig_carousel refuses a URL nobody verified")
        _GUARD_FETCH = all_404
        graph.clear()
        try:
            post_ig_carousel(["https://www.tulsagays.com/posts/2026-W99/all__01.png"], "x")
            check(False, "an unverified dead URL must raise")
        except RuntimeError as e:
            check("refused before the container call" in str(e) and not graph, f"refused: {str(e)[:100]}")
    finally:
        subprocess.run, requests.post, requests.get, requests.request, time.sleep = real
        (SLIDES_DIR, DOCS_DIR, META_CFG_PATH, DRY_RUN, IG_URL_WAIT_S, _GUARD_FETCH,
         _TRACK_ENGAGEMENT, mc) = saved
        meta_cfg.clear()
        meta_cfg.update(mc)
        shutil.rmtree(tmp, ignore_errors=True)

    if failed:
        print(f"SELFTEST FAIL: {len(failed)} of {checks} checks failed")
        return 1
    print(f"SELFTEST PASS ({checks} checks)")
    return 0


if __name__ == "__main__":
    if "--selftest-channels" in sys.argv:
        sys.exit(_selftest_channels())
    main()
