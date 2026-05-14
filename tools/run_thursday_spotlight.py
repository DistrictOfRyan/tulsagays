"""Thursday 12pm CT: pick the highest-flamingo venue or event that hasn't been
spotlighted recently, write a short blog article, deploy to tulsagays.com/blog/,
and post the matching spotlight image to FB + IG.

Image-only on social. Never falls back to text. Skips silently if no eligible
spotlight subject is available this week.

Usage:
  python tools/run_thursday_spotlight.py
  python tools/run_thursday_spotlight.py --dry-run
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from content.image_maker import make_engagement_slide  # noqa: E402
from tools.social_lib import (  # noqa: E402
    load_meta_config,
    log_engagement_event,
    post_facebook_photo,
    post_instagram_photo,
    public_url_for,
    wait_for_public_url,
)

GAY_BAR_VENUES = {
    "club majestic": "Club Majestic",
    "majestic tulsa": "Club Majestic",
    "tulsa eagle": "Tulsa Eagle",
    "yellow brick road": "Yellow Brick Road",
    "the vanguard": "The Vanguard",
    "pump bar": "Pump Bar",
}
SUPER_GAY_KW = (
    "drag ",
    "hhhh",
    "homo hotel",
    "queer ",
    "pride ",
    "twisted arts",
    "lesbian",
    "sapphic",
    "dragnificent",
)
NO_REPEAT_WEEKS = 16


def _venue_canonical(venue_raw: str) -> str | None:
    v = (venue_raw or "").strip().lower()
    for needle, canonical in GAY_BAR_VENUES.items():
        if needle in v:
            return canonical
    return None


def _subject_key(e: dict) -> str | None:
    canonical = _venue_canonical(e.get("venue", "") or "")
    if canonical:
        return f"venue::{canonical.lower()}"
    name = (e.get("name", "") or "").strip().lower()
    if any(k in name for k in SUPER_GAY_KW):
        return f"event::{name[:40]}"
    return None


def _score(e: dict) -> int:
    if _venue_canonical(e.get("venue", "") or ""):
        return 5
    name = (e.get("name", "") or "").lower()
    if any(k in name for k in SUPER_GAY_KW):
        return 5
    return 3


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:60] or f"spotlight-{datetime.now().strftime('%Y%m%d')}"


def _load_spotlight_log() -> list[dict]:
    path = ROOT / "data" / "blog" / "spotlight_log.json"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_spotlight_log(rows: list[dict]) -> Path:
    path = ROOT / "data" / "blog" / "spotlight_log.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    return path


def _featured_event_for(subject_key: str, events: list[dict]) -> dict:
    candidates = [e for e in events if _subject_key(e) == subject_key]
    candidates.sort(key=lambda e: e.get("date", ""))
    return candidates[0] if candidates else {}


def _related_events_for(subject_key: str, events: list[dict], max_n: int = 4) -> list[dict]:
    rows = [e for e in events if _subject_key(e) == subject_key]
    rows.sort(key=lambda e: (e.get("date", ""), e.get("time", "") or ""))
    return rows[:max_n]


def _article_html(title: str, slug: str, hero_p: str, sections: list[tuple[str, str]]) -> str:
    """Minimal valid HTML article that matches existing /blog/ structure."""
    canonical = f"https://www.tulsagays.com/blog/{slug}.html"
    title_e = html.escape(title, quote=True)
    sections_html = "\n".join(
        f"<h2>{html.escape(h)}</h2>\n<p>{html.escape(b)}</p>" for h, b in sections
    )
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>{title_e} - Tulsa Gays Blog</title>
<meta content="{title_e}: this week's queer Tulsa spotlight on tulsagays.com." name="description"/>
<meta content="index, follow" name="robots"/>
<meta content="{title_e}" property="og:title"/>
<meta content="This week's queer Tulsa spotlight." property="og:description"/>
<meta content="article" property="og:type"/>
<meta content="{canonical}" property="og:url"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="{title_e}" name="twitter:title"/>
<link href="{canonical}" rel="canonical"/>
<link href="../style.css" rel="stylesheet"/>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": {json.dumps(title)},
  "datePublished": "{today}",
  "author": {{"@type": "Organization", "name": "Tulsa Gays"}},
  "publisher": {{"@type": "Organization", "name": "Tulsa Gays"}},
  "mainEntityOfPage": "{canonical}"
}}
</script>
</head>
<body>
<main class="container">
<h1>{title_e}</h1>
<p class="post-meta"><span class="post-date">{today}</span></p>
<div class="post-body">
<p>{html.escape(hero_p)}</p>
{sections_html}
<p><a href="https://www.tulsagays.com/">See the rest of this week's queer Tulsa events.</a></p>
</div>
</main>
</body>
</html>
"""


def _prepend_index_card(title: str, slug: str) -> bool:
    """Prepend a simple card link to docs/blog/index.html. Returns True if changed."""
    index_path = ROOT / "docs" / "blog" / "index.html"
    if not index_path.exists():
        return False
    html_text = index_path.read_text(encoding="utf-8")
    new_card = (
        f'\n<article class="blog-card"><a href="{slug}.html">'
        f"<h2>{html.escape(title)}</h2></a></article>\n"
    )
    marker = "<!-- BLOG_CARDS -->"
    if marker in html_text:
        new_text = html_text.replace(marker, marker + new_card, 1)
    else:
        new_text = re.sub(
            r"(<main[^>]*>)", r"\1" + new_card, html_text, count=1, flags=re.IGNORECASE
        )
        if new_text == html_text:
            return False
    index_path.write_text(new_text, encoding="utf-8")
    return True


def _compose_article(subject_key: str, featured: dict, related: list[dict]) -> tuple[str, str, list]:
    canonical_venue = _venue_canonical(featured.get("venue", "") or "")
    is_venue = subject_key.startswith("venue::")

    if is_venue:
        title = f"Spotlight: {canonical_venue}"
        hero = (
            f"This week's queer Tulsa spotlight is {canonical_venue}. "
            "It is one of the gay bars that anchors the Tulsa scene, "
            "and there is more than one reason to make the trip this week."
        )
        sections: list[tuple[str, str]] = []
        if related:
            lines = "; ".join(
                f"{e.get('name','event')} on {e.get('date','')} {e.get('time','') or ''}".strip()
                for e in related
            )
            sections.append(("What is happening this week", lines))
        sections.append(
            (
                "Why we are featuring it",
                f"{canonical_venue} keeps showing up in our weekly scrape and the queer "
                "community keeps showing up at the door. That is the only kind of endorsement "
                "we care about.",
            )
        )
        sections.append(
            (
                "Plan your visit",
                "Bring a friend, leave the apologies at home, and grab a drink. "
                "Full week of events at tulsagays.com.",
            )
        )
        return title, _slugify(title), sections

    name = featured.get("name", "queer Tulsa event")
    title = f"Spotlight: {name}"
    venue = featured.get("venue", "")
    when = f"{featured.get('date','')} {featured.get('time','') or ''}".strip()
    hero = (
        f"This week's queer Tulsa spotlight is {name}. "
        f"Happening {when}{' at ' + venue if venue else ''}."
    )
    sections = [
        (
            "What to expect",
            featured.get("description")
            or "If you have not been to one of these, this is your week to go.",
        ),
        (
            "Why we are featuring it",
            "Drag, queer performance, and identity-affirming nights do not get featured by "
            "accident. They get featured because they are why we built this site.",
        ),
        (
            "Plan your visit",
            "Round up a friend. Show up early enough to actually see the show. "
            "Full week of events at tulsagays.com.",
        ),
    ]
    return title, _slugify(title), sections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    week_key = config.current_week_key()
    events_path = Path(config.EVENTS_DIR) / f"{week_key}_all.json"
    if not events_path.exists():
        print(f"No events file at {events_path}; silent skip.")
        return 0
    with events_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    events = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        events = []

    spotlight_log = _load_spotlight_log()
    recent_keys = {row.get("subject_key") for row in spotlight_log[-NO_REPEAT_WEEKS:]}

    candidates: list[tuple[int, dict, str]] = []
    seen_subject_keys: set[str] = set()
    for e in events:
        k = _subject_key(e)
        if not k or k in recent_keys or k in seen_subject_keys:
            continue
        seen_subject_keys.add(k)
        candidates.append((_score(e), e, k))

    if not candidates:
        print("No eligible spotlight subject this week; silent skip.")
        return 0

    candidates.sort(key=lambda t: t[0], reverse=True)
    _, _, subject_key = candidates[0]
    featured = _featured_event_for(subject_key, events)
    related = _related_events_for(subject_key, events)
    print(f"subject_key={subject_key}  featured={featured.get('name')}")

    title, slug, sections = _compose_article(subject_key, featured, related)
    hero = sections.pop(0)[1] if sections and sections[0][0].lower().startswith("hero") else (
        f"This week's queer Tulsa spotlight: {title.removeprefix('Spotlight: ')}."
    )

    blog_dir = ROOT / "docs" / "blog"
    blog_path = blog_dir / f"{slug}.html"
    blog_path.parent.mkdir(parents=True, exist_ok=True)
    blog_path.write_text(_article_html(title, slug, hero, sections), encoding="utf-8")
    index_changed = _prepend_index_card(title, slug)
    print(f"blog written: {blog_path.relative_to(ROOT)}  index_changed={index_changed}")

    out_rel = Path("docs") / "posts" / week_key
    out_abs = ROOT / out_rel
    out_abs.mkdir(parents=True, exist_ok=True)
    img_name = f"thursday-spotlight-{slug}.png"
    img_path = out_abs / img_name
    img = make_engagement_slide(
        headline=title.replace("Spotlight: ", ""),
        body=(featured.get("description") or hero)[:280],
        post_type="spotlight",
        subhead="This week's queer Tulsa spotlight",
    )
    img.save(img_path, "PNG", optimize=True)
    if img_path.stat().st_size < 30_000:
        raise RuntimeError("Generated spotlight image too small; aborting.")
    public_img_url = public_url_for(str(out_rel / img_name))
    public_blog_url = f"https://www.tulsagays.com/blog/{slug}.html"
    print(f"public_img_url={public_img_url}\npublic_blog_url={public_blog_url}")

    caption = (
        f"This week's spotlight: {title.replace('Spotlight: ', '')}.\n\n"
        f"Read the full story → {public_blog_url}\n\n"
        "#TulsaGays #QueerTulsa #LGBTQTulsa"
    )

    fb_result = {"id": "skipped"}
    ig_result = {"id": "skipped"}

    if args.dry_run:
        print("DRY RUN: skipping git push and social posts")
    else:
        import subprocess

        to_add = [str(blog_path.relative_to(ROOT)), str(out_rel / img_name)]
        if index_changed:
            to_add.append("docs/blog/index.html")
        subprocess.run(["git", "add", *to_add], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"tulsagays-thursday-spotlight: {slug}"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

        wait_for_public_url(public_img_url)
        wait_for_public_url(public_blog_url)

        cfg = load_meta_config()
        fb_result = post_facebook_photo(cfg, public_img_url, caption)
        print(f"facebook_post_id={fb_result.get('id')}")
        try:
            ig_result = post_instagram_photo(cfg, public_img_url, caption)
            print(f"instagram_post_id={ig_result.get('id')}")
        except RuntimeError as e:
            print(f"WARN: IG post failed (keeping FB): {e}")
            ig_result = {"id": "failed", "error": str(e)}

        spotlight_log.append(
            {
                "week": week_key,
                "fired_at": datetime.now().isoformat(timespec="seconds"),
                "subject_key": subject_key,
                "slug": slug,
                "title": title,
            }
        )
        _save_spotlight_log(spotlight_log)
        subprocess.run(["git", "add", "data/blog/spotlight_log.json"], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"tulsagays-thursday-spotlight: log {slug}"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

    log_engagement_event(
        week_key,
        {
            "task": "tulsagays-thursday-spotlight",
            "fired_at": datetime.now().isoformat(timespec="seconds"),
            "week": week_key,
            "subject_key": subject_key,
            "slug": slug,
            "title": title,
            "image_url": public_img_url,
            "blog_url": public_blog_url,
            "fb_post_id": fb_result.get("id"),
            "ig_post_id": ig_result.get("id"),
            "dry_run": args.dry_run,
        },
        ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
