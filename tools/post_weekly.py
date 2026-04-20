"""
Post the weekly carousel to Facebook and Instagram.

Usage:
    python tools/post_weekly.py              # post this week's slides
    python tools/post_weekly.py --dry-run    # validate only, no posting

Steps:
  1. Validate slides (all 9 present, >50KB each)
  2. Copy slides to docs/posts/{week-key}/ and git push for public URLs
  3. Post multi-image carousel to Facebook page (binary upload)
  4. Post carousel to Instagram (uses GitHub Pages public URLs)
  5. Save post IDs to meta_api_config.json and data/posts/{week}/post_results.json
"""

import json
import os
import sys
import shutil
import subprocess
import time
import requests
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config

DRY_RUN = "--dry-run" in sys.argv

# ── Load meta credentials ───────────────────────────────────────────────────
META_CFG_PATH = ROOT / "meta_api_config.json"

with open(META_CFG_PATH, encoding="utf-8") as f:
    meta_cfg = json.load(f)

PAGE_TOKEN = meta_cfg["page_access_token"]
PAGE_ID    = meta_cfg["page_id"]
IG_ID      = meta_cfg["instagram_business_account_id"]
API_BASE   = "https://graph.facebook.com/v25.0"

# ── Week and slide locations ────────────────────────────────────────────────
WEEK_KEY   = config.current_week_key()
SLIDES_DIR = ROOT / "data" / "posts" / WEEK_KEY
DOCS_DIR   = ROOT / "docs" / "posts" / WEEK_KEY

# GitHub Pages public URL base (www.tulsagays.com is the custom domain)
SITE_BASE  = f"https://www.tulsagays.com/posts/{WEEK_KEY}"

FB_BASE_CAPTION = (
    "THIS WEEK IN TULSA. Your daily LGBTQ+ community guide. "
    "Live music, drag shows, gatherings, events, and connection points all week. "
    "Swipe through for each day. Full listings at tulsagays.com. "
    "#TulsaGays #TulsaPride #QueerTulsa"
)

IG_BASE_CAPTION = (
    "THIS WEEK IN TULSA Your daily community guide. "
    "Swipe for each day of events, live music, drag shows, and connection. "
    "Full listings at tulsagays.com. "
    "#TulsaGays #LGBTQ #TulsaPride #QueerTulsa #Oklahoma"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_caption() -> str:
    """Read the generated caption from all_post.json if available."""
    post_json = SLIDES_DIR / "all_post.json"
    if post_json.exists():
        with open(post_json, encoding="utf-8") as f:
            data = json.load(f)
        cap = data.get("caption", "").strip()
        if cap and len(cap) > 50:
            return cap
    return FB_BASE_CAPTION


def get_slides() -> list[Path]:
    """Return sorted list of slide PNGs for this week."""
    if not SLIDES_DIR.exists():
        return []
    slides = sorted(SLIDES_DIR.glob("all__*.png"))
    return slides


def validate_slides(slides: list[Path]) -> None:
    if not slides:
        sys.exit(f"ERROR: No slides found in {SLIDES_DIR}.\n"
                 f"Run: python main.py generate-all")
    if len(slides) < 9:
        sys.exit(f"ERROR: Only {len(slides)} slides found (need 9).\n"
                 f"Run: python main.py generate-all")
    for s in slides:
        size = s.stat().st_size
        if size < 50 * 1024:
            sys.exit(f"ERROR: {s.name} is only {size // 1024}KB — likely corrupt or blank.\n"
                     f"Re-generate slides: python main.py generate-all")
    print(f"[OK] {len(slides)} slides validated ({WEEK_KEY})")


def host_slides_for_ig(slides: list[Path]) -> list[str]:
    """Copy slides to docs/posts/{week-key}/, push to git, return public URLs.

    The docs/ folder is served via GitHub Pages at www.tulsagays.com.
    Public URLs allow the Instagram Graph API to fetch the images.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for slide in slides:
        dest = DOCS_DIR / slide.name
        if not dest.exists() or dest.stat().st_mtime < slide.stat().st_mtime:
            shutil.copy2(slide, dest)

    print(f"[OK] Slides copied to docs/posts/{WEEK_KEY}/")

    # Git add + commit + push so GitHub Pages serves them
    rel_path = f"docs/posts/{WEEK_KEY}"
    cmds = [
        ["git", "add", rel_path],
        ["git", "commit", "-m", f"slides: publish {WEEK_KEY} carousel images"],
        ["git", "push", "origin", "main"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if cmd[1] == "push" and result.returncode != 0:
            print(f"WARN: git push failed: {result.stderr.strip()}")
            print("Continuing — URLs may already be live from a previous push.")
        elif cmd[1] == "commit" and "nothing to commit" in (result.stdout + result.stderr):
            print("[OK] Slides already committed — skipping commit.")
        elif result.returncode != 0 and cmd[1] != "commit":
            print(f"WARN: git {cmd[1]} failed: {result.stderr.strip()}")

    print("[OK] Slides pushed to GitHub. Waiting 50s for Pages to deploy...")
    if not DRY_RUN:
        time.sleep(50)

    public_urls = [f"{SITE_BASE}/{s.name}" for s in slides]

    # Spot-check first URL
    try:
        resp = requests.head(public_urls[0], timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            print(f"[OK] GitHub Pages live: {public_urls[0]}")
        else:
            print(f"WARN: {public_urls[0]} returned {resp.status_code} — Pages may still be building.")
            if not DRY_RUN:
                time.sleep(30)
    except Exception as e:
        print(f"WARN: Could not verify URL ({e}) — proceeding anyway.")

    return public_urls


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
    resp = requests.post(
        f"{API_BASE}/{PAGE_ID}/feed",
        data={"message": caption, "attached_media": attached, "access_token": PAGE_TOKEN},
        timeout=60,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"FB post failed: {data['error'].get('message')}")
    if "id" not in data:
        raise RuntimeError(f"FB post returned no ID: {data}")

    post_id = data["id"]
    print(f"[OK] Facebook post: https://www.facebook.com/{post_id}")
    return {"post_id": post_id, "photo_ids": photo_ids}


# ── Instagram ────────────────────────────────────────────────────────────────

def post_ig_carousel(public_urls: list[str], caption: str) -> str:
    """Post Instagram carousel using public image URLs. Returns IG post ID."""
    urls = public_urls[:10]  # IG max 10 images
    print(f"\n[IG] Creating {len(urls)} carousel item containers...")

    if DRY_RUN:
        print("     (dry run — skipping IG post)")
        return "dry_run_ig_id"

    child_ids = []
    for i, url in enumerate(urls, 1):
        print(f"     Item {i}/{len(urls)}", end=" ... ", flush=True)
        resp = requests.post(
            f"{API_BASE}/{IG_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": PAGE_TOKEN},
            timeout=120,
        )
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"IG container {i} failed: {data['error'].get('message')}")
        cid = data.get("id")
        if not cid:
            raise RuntimeError(f"IG container {i} returned no ID: {data}")
        child_ids.append(cid)
        print(f"ID {cid}")
        time.sleep(2)

    print("[IG] Creating carousel container...")
    resp = requests.post(
        f"{API_BASE}/{IG_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": PAGE_TOKEN,
        },
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

def save_results(fb_result: dict, ig_post_id: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")

    meta_cfg["last_post"] = {
        "date": today,
        "week_key": WEEK_KEY,
        "fb_post_id": fb_result["post_id"],
        "ig_post_id": ig_post_id,
        "photo_ids": fb_result["photo_ids"],
        "note": f"Weekly carousel {WEEK_KEY}. 9 slides.",
    }
    with open(META_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(meta_cfg, f, indent=2)

    results_path = SLIDES_DIR / "post_results.json"
    results = {
        "week": WEEK_KEY,
        "posted_at": datetime.now().isoformat(),
        "fb_post_id": fb_result["post_id"],
        "ig_post_id": ig_post_id,
        "photo_ids": fb_result["photo_ids"],
        "dry_run": DRY_RUN,
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {results_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"TULSA GAYS — POST WEEKLY CAROUSEL ({WEEK_KEY})")
    if DRY_RUN:
        print("  *** DRY RUN MODE — no actual posts will go out ***")
    print("=" * 60)

    # Step 1: Validate slides
    slides = get_slides()
    validate_slides(slides)

    # Step 2: Load caption
    caption = load_caption()
    print(f"[OK] Caption loaded ({len(caption)} chars)")

    # Step 3: Host slides on tulsagays.com for IG public URLs
    print("\n[HOSTING] Publishing slides to tulsagays.com...")
    public_urls = host_slides_for_ig(slides)

    # Step 4: Post to Facebook (binary upload, no external hosting needed)
    fb_result = post_fb_carousel(slides, caption)

    # Step 5: Post to Instagram (needs public URLs)
    try:
        ig_post_id = post_ig_carousel(public_urls, caption)
    except Exception as e:
        print(f"\n[WARN] Instagram post failed: {e}")
        print("       Facebook post is live. Report IG failure to William.")
        ig_post_id = f"FAILED: {e}"

    # Step 6: Save results
    save_results(fb_result, ig_post_id)

    # Summary
    print("\n" + "=" * 60)
    print("ALL DONE")
    print(f"  Week:      {WEEK_KEY}")
    print(f"  FB post:   {fb_result['post_id']}")
    print(f"  IG post:   {ig_post_id}")
    print(f"  Photos:    {len(fb_result['photo_ids'])} uploaded to FB")
    print("=" * 60)
    print("\nNEXT STEP: Share to FB groups via browser.")
    print("Groups to share to (copy the FB post link into each):")
    print("  1. Gay men of Tulsa   facebook.com/groups/161646500587551")
    print("  2. Okie Gays          facebook.com/groups/2612250565491228")
    print("  3. Tulsa LGBTQ+ Scene facebook.com/groups/715281449025002")
    print("  4. Gay Tulsa          facebook.com/groups/GayTulsa")
    print("  5. Tulsa's LGBT Night facebook.com/groups/220878821301627")
    print("  6. Things To Do Tulsa facebook.com/groups/InterestingThingsToDoInTulsa")
    print("  7. What's Up Tulsa    facebook.com/groups/WhatsHappeningTulsa")


if __name__ == "__main__":
    main()
