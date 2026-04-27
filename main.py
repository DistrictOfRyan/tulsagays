"""
Tulsa Gays - Main Orchestrator
Coordinates scraping, content generation, image creation, posting, and blog updates.

Usage:
    py main.py scrape          # Run all scrapers
    py main.py generate        # Generate content for this week
    py main.py post-weekday    # Post weekday events
    py main.py post-weekend    # Post weekend events
    py main.py update-blog     # Update the blog with current events
    py main.py discover        # Discover new event sources
    py main.py report          # Generate engagement report
    py main.py full-run        # Run the complete weekly pipeline
    py main.py test            # Test run without posting
"""

import sys
import os
import re
import json
import time
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def get_date_range(post_type):
    """Get the date range string for the current week's post type."""
    today = datetime.now()
    # Always use the current week's Monday (Monday=0 in weekday())
    monday = today - timedelta(days=today.weekday())

    if post_type == "weekday":
        start = monday
        end = monday + timedelta(days=3)  # Mon-Thu
    elif post_type == "all":
        start = monday
        end = monday + timedelta(days=6)  # Mon-Sun
    else:
        start = monday + timedelta(days=4)  # Friday
        end = monday + timedelta(days=6)  # Sunday

    return f"{start.strftime('%b %d')} - {end.strftime('%b %d')}"


def cmd_scrape():
    """Run all event scrapers."""
    print("=" * 50)
    print("SCRAPING EVENTS")
    print("=" * 50)

    from scraper.runner import main as run_scrapers
    events = run_scrapers()
    print(f"\nTotal events found: {len(events) if events else 0}")
    return events


def cmd_generate(post_type="weekday"):
    """Generate content (caption + images) for a post."""
    print("=" * 50)
    print(f"GENERATING {post_type.upper()} CONTENT")
    print("=" * 50)

    config.ensure_dirs()
    week_key = config.current_week_key()

    # Load events for this post type
    events_file = os.path.join(config.EVENTS_DIR, f"{week_key}_{post_type}.json")
    if not os.path.exists(events_file):
        print(f"No events file found at {events_file}")
        print("Run 'py main.py scrape' first.")
        return None

    with open(events_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both formats: list of events or dict with 'events' key
    if isinstance(data, dict):
        events = data.get("events", [])
    else:
        events = data

    if not events:
        print("No events found for this period.")
        return None

    date_range = get_date_range(post_type)

    # Enrich events with exciting descriptions
    print("\nEnriching event descriptions...")
    try:
        from content.generator import enrich_event_descriptions
        events = enrich_event_descriptions(events)
        print(f"Enriched {len(events)} events with compelling descriptions")
        # Save enriched descriptions back to JSON so website and other tools use them
        with open(events_file, "w", encoding="utf-8") as _f:
            json.dump(events, _f, ensure_ascii=False, indent=2)
        print(f"Enriched descriptions saved to {events_file}")
    except Exception as e:
        print(f"Event enrichment skipped: {e}")

    # Generate caption
    print("\nGenerating caption...")
    try:
        from content.generator import generate_post_caption
        result = generate_post_caption(events, post_type, date_range)
        caption = result["caption"]
        category_events = result["category_events"]
        print(f"Caption generated ({len(caption)} chars)")
    except Exception as e:
        print(f"Caption generation failed: {e}")
        print("Using fallback template...")
        caption = _fallback_caption(events, post_type, date_range)
        category_events = _categorize_events(events)

    # Build events_by_day — only events within THIS week's Mon-Sun date range
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]
    events_by_day = {day: [] for day in days_of_week}
    no_date_events = []
    _today = datetime.now().date()
    _week_monday = _today - timedelta(days=_today.weekday())
    _week_sunday = _week_monday + timedelta(days=6)
    for ev in events:
        date_str = ev.get("date", "")
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                ev_date = dt.date()
                if not (_week_monday <= ev_date <= _week_sunday):
                    continue  # event is outside this week's range — skip
                day_name = dt.strftime("%A")
                if day_name in events_by_day:
                    events_by_day[day_name].append(ev)
            except ValueError:
                no_date_events.append(ev)
        else:
            no_date_events.append(ev)
    # Priority sort: LGBTQ non-bar non-recurring first, bars and non-LGBTQ last.
    # Within each tier, sort by actual time (AM/PM parsed correctly, untimed last).
    _BAR_VENUES = {"1338 e 3rd", "302 south frankfort", "302 s. frankfort",
                   "302 s frankfort", "124 n boston", "frequency lounge", "sutures bar"}
    _BAR_NAME_FRAGMENTS = {"touchtunes", "leather night", "shenanigans", "eagle bingo",
                           "derby watch party", "derby hat"}
    _LGBTQ_KEYWORDS = {
        "lgbtq", "queer", "gay", "lesbian", "trans", "drag", "pride",
        "bisexual", "nonbinary", "non-binary", "equality", "homo hotel",
        "hhhh", "two-spirit", "pflag", "okeq", "rainbow", "gender outreach",
        "lambda bowling", "lambda league",
    }
    # Known gay bars / LGBTQ venues — events here are LGBTQ even without keywords
    _LGBTQ_VENUES = {"dennis r. neill", "dennis r neill", "oklahomans for equality",
                     "positive space", "okeq",
                     "1338 e 3rd",        # Tulsa Eagle
                     "302 south frankfort", "302 s frankfort", "302 s. frankfort",  # DVL
                     "124 n boston",      # Club Majestic
                     }
    _LGBTQ_SOURCES = {"homo_hotel", "okeq", "community_groups"}
    _RECURRING_SOURCES = {"recurring"}
    _RECURRING_NAME_FRAGMENTS = {
        "bowling league", "support group", "lambda unity",
        "outreach group", "monthly meeting",
        "happy hour!",   # generic bar open-door entries (DVL, etc.) — not real events
        "touchtunes",    # weekly Eagle promo, every Friday
    }
    # These events should never appear in the top 3 — deprioritize to T6+
    _ALWAYS_DEPRIORITIZE = {
        "mix and mingle",     # straight networking, not a community event
        "aa meeting",         # valuable but not a highlight event
        "aa meetings",
        "book club - tulsa",  # org-specific book clubs (Tulsa SWE, etc.)
        "shut up & write",    # productivity meetup
        "raise your spiritual iq",  # generic self-help
    }
    # Cultural/entertainment events get a sub-tier boost so they float above
    # generic T5 events even when their start time is later
    _CULTURAL_KEYWORDS = {
        "concert", "symphony", "musical", "opera", "ballet",
        "film", "cinema", "silent film", "live music",
        "guthrie green", "cain's ballroom", "performing arts center",
    }

    def _parse_time_minutes(t):
        if not t:
            return 9999
        t = t.split("-")[0].split("–")[0].strip()
        for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
            try:
                dt_parsed = datetime.strptime(t, fmt)
                return dt_parsed.hour * 60 + dt_parsed.minute
            except ValueError:
                continue
        return 9999

    def _slide_priority(e):
        venue  = (e.get("venue") or "").lower()
        name   = (e.get("name") or "").lower()
        src    = (e.get("source") or "").lower()
        desc   = (e.get("description") or "").lower()
        combo  = f"{name} {desc} {venue} {src}"
        is_bar = (src == "bars"
                  or any(bv in venue for bv in _BAR_VENUES)
                  or any(bf in name  for bf in _BAR_NAME_FRAGMENTS))
        is_lgbtq = (any(kw in combo for kw in _LGBTQ_KEYWORDS)
                    or any(v in combo for v in _LGBTQ_VENUES)
                    or src in _LGBTQ_SOURCES)
        is_recurring = (src in _RECURRING_SOURCES
                        or any(kw in name for kw in _RECURRING_NAME_FRAGMENTS))
        is_deprioritized = any(kw in name for kw in _ALWAYS_DEPRIORITIZE)
        # Cultural events float above generic events at the same tier
        is_cultural = any(kw in combo for kw in _CULTURAL_KEYWORDS)
        sub_tier = 0 if is_cultural else 1
        minutes = _parse_time_minutes(e.get("time", ""))
        # Drag/performance shows at bars still rank high — they're worth featuring
        _PERFORMANCE_KEYWORDS = {"drag", "talent night", "open talent", "cabaret", "variety show"}
        is_drag_show = any(kw in combo for kw in _PERFORMANCE_KEYWORDS) and is_lgbtq
        if is_lgbtq and not is_bar and not is_recurring:
            tier = 1   # LGBTQ, non-bar, non-recurring — always show first
        elif is_drag_show and is_bar:
            tier = 2   # Drag/performance at a bar — worth featuring
        elif is_lgbtq and is_bar and not is_recurring:
            tier = 3   # LGBTQ bar, special one-off
        elif not is_lgbtq and not is_bar:
            tier = 4   # Non-LGBTQ cultural (concerts, art, film)
        elif is_lgbtq and not is_bar and is_recurring:
            tier = 5   # HARD RULE: recurring events (bowling, support groups) never lead a day
        elif is_lgbtq and is_bar:
            tier = 6   # Regular bar programming
        else:
            tier = 7   # Non-LGBTQ bar or generic catch-all
        # Deprioritized events never beat real events — sink to T6 minimum
        if is_deprioritized:
            tier = max(tier, 6)
        return (tier, sub_tier, minutes)

    for day in days_of_week:
        events_by_day[day].sort(key=_slide_priority)

    # Deduplicate: collapse same-day events with the same name (or HHHH variants)
    # into one record, merging the most complete venue/address/URL/description.
    def _dedup_day(ev_list):
        def _norm(s):
            return re.sub(r'\W+', ' ', (s or '').lower()).strip()

        def _has_address(venue):
            v = venue or ''
            return ',' in v or any(c.isdigit() for c in v)

        seen = {}   # key -> index in result
        result = []
        for ev in ev_list:
            name_norm = _norm(ev.get('name', ''))
            date = ev.get('date', '')
            # Collapse all HHHH variants to a single bucket
            if 'homo hotel' in name_norm or ('hhhh' in name_norm):
                key = ('__hhhh__', date)
            else:
                key = (name_norm[:40], date)

            if key not in seen:
                seen[key] = len(result)
                result.append(dict(ev))
            else:
                idx = seen[key]
                existing = result[idx]
                new_venue = ev.get('venue') or ''
                old_venue = existing.get('venue') or ''
                # Always prefer venue that has a street address (has comma or digit)
                if _has_address(new_venue) and not _has_address(old_venue):
                    existing['venue'] = new_venue
                elif _has_address(new_venue) and len(new_venue) > len(old_venue):
                    existing['venue'] = new_venue
                # Take longest/best description (keep sassy copy)
                if len(ev.get('description') or '') > len(existing.get('description') or ''):
                    existing['description'] = ev['description']
                # Take URL if missing
                if ev.get('url') and not existing.get('url'):
                    existing['url'] = ev['url']
        return result

    for day in days_of_week:
        before = len(events_by_day[day])
        events_by_day[day] = _dedup_day(events_by_day[day])
        after = len(events_by_day[day])
        if before != after:
            print(f"  [dedup] {day}: {before} -> {after} events (collapsed {before - after} duplicates)")

    # Validate: warn if any day has zero events (expected for some days)
    days_with_events = [d for d in days_of_week if events_by_day[d]]
    print(f"\nEvents per day: { {d: len(events_by_day[d]) for d in days_of_week} }")
    if len(days_with_events) < 4:
        print(f"WARNING: Only {len(days_with_events)} days have events. "
              "Check scrapers — some sources may have failed.")

    # Pre-select EOTW from deduplicated events_by_day so the cover uses
    # the merged record (correct venue/address) rather than raw category_events.
    _all_deduped = [e for d in days_of_week for e in events_by_day[d]]
    def _is_hh(e): return 'homo hotel' in (e.get('name') or '').lower() or (e.get('source') or '') == 'homo_hotel'
    def _is_co(e): return 'council oak' in ((e.get('name') or '') + (e.get('source') or '')).lower()
    def _is_qp(e):
        c = ' '.join([e.get('name',''), e.get('description',''), e.get('venue',''), e.get('source','')]).lower()
        return any(k in c for k in ['drag','cabaret','pride show','pride event','queer night','gay night','twisted arts'])
    def _is_rec(e):
        s = (e.get('source') or '').lower()
        n = (e.get('name') or '').lower()
        return s in {'recurring','aa_meetings','bars'} or any(k in n for k in ['bowling league','support group','outreach group'])
    _hh = [e for e in _all_deduped if _is_hh(e)]
    _co = [e for e in _all_deduped if _is_co(e)]
    _qp = [e for e in _all_deduped if _is_qp(e) and not _is_rec(e) and not _is_hh(e)]
    _sp = [e for e in _all_deduped if not _is_hh(e) and not _is_co(e) and not _is_qp(e) and not _is_rec(e)]
    _preselected_eotw = _hh[0] if _hh else (_co[0] if _co else (_qp[0] if _qp else (_sp[0] if _sp else None)))
    if _preselected_eotw:
        print(f"  [eotw] {_preselected_eotw.get('name')} @ {_preselected_eotw.get('venue')}")

    # Generate carousel images
    print("\nGenerating carousel images...")
    try:
        from content.image_maker import create_carousel, save_carousel
        logo_path = config.LOGO_PATH if os.path.exists(config.LOGO_PATH) else None
        images = create_carousel(
            category_events, post_type, date_range, logo_path,
            events_by_day=events_by_day,
            featured_event=_preselected_eotw,
        )
        output_dir = os.path.join(config.DATA_DIR, "posts", week_key)
        os.makedirs(output_dir, exist_ok=True)
        image_paths = save_carousel(images, output_dir, f"{post_type}_")
        print(f"Generated {len(image_paths)} carousel slides")
        # Sanity check: alert if any day slide appears blank (0 events)
        blank_days = [d for d in days_of_week if not events_by_day[d]]
        if blank_days:
            print(f"NOTE: Blank slides for days with no events: {', '.join(blank_days)}")
    except Exception as e:
        print(f"Image generation failed: {e}")
        image_paths = []

    # Save the post content
    post_data = {
        "week": week_key,
        "post_type": post_type,
        "date_range": date_range,
        "caption": caption,
        "image_paths": image_paths,
        "events_count": len(events),
        "generated_at": datetime.now().isoformat(),
    }

    post_file = os.path.join(config.DATA_DIR, "posts", week_key, f"{post_type}_post.json")
    os.makedirs(os.path.dirname(post_file), exist_ok=True)
    with open(post_file, "w") as f:
        json.dump(post_data, f, indent=2)

    print(f"\nPost content saved to {post_file}")
    print(f"\n--- CAPTION PREVIEW ---\n{caption[:500]}...")
    return post_data


def cmd_post(post_type):
    """Post to Instagram."""
    print("=" * 50)
    print(f"POSTING {post_type.upper()} TO INSTAGRAM")
    print("=" * 50)

    week_key = config.current_week_key()
    post_file = os.path.join(config.DATA_DIR, "posts", week_key, f"{post_type}_post.json")

    if not os.path.exists(post_file):
        print(f"No post content found. Run 'py main.py generate' first.")
        return False

    with open(post_file, "r") as f:
        post_data = json.load(f)

    if not config.META_ACCESS_TOKEN or not config.META_IG_USER_ID:
        print("ERROR: Meta API credentials not configured.")
        print("Set META_ACCESS_TOKEN and META_IG_USER_ID environment variables.")
        return False

    # Humanize: random delay before posting (1-5 minutes)
    delay = random.randint(60, 300)
    print(f"Humanization delay: waiting {delay} seconds...")
    time.sleep(delay)

    try:
        from posting.instagram import post_carousel, humanize_caption
        caption = humanize_caption(post_data["caption"])
        image_paths = post_data["image_paths"]

        if not image_paths:
            print("No images to post.")
            return False

        result = post_carousel(
            image_paths, caption,
            config.META_ACCESS_TOKEN, config.META_IG_USER_ID
        )
        print(f"Posted successfully! Media ID: {result.get('id', 'unknown')}")

        # Log the post
        from self_improve.engagement_tracker import log_post
        log_post(
            post_id=result.get("id", ""),
            post_type=post_type,
            events_featured=post_data["events_count"],
            caption_style="carousel",
        )
        return True
    except Exception as e:
        print(f"Posting failed: {e}")
        return False


def cmd_update_blog():
    """Update the blog with current events."""
    print("=" * 50)
    print("UPDATING BLOG")
    print("=" * 50)

    try:
        from blog.update_blog import update_blog
        update_blog()
        print("Blog updated successfully!")
    except Exception as e:
        print(f"Blog update failed: {e}")


def cmd_discover():
    """Discover new event sources."""
    print("=" * 50)
    print("DISCOVERING NEW SOURCES")
    print("=" * 50)

    try:
        from self_improve.source_discovery import discover_new_sources
        new_sources = discover_new_sources()
        if new_sources:
            print(f"\nFound {len(new_sources)} new potential sources:")
            for src in new_sources:
                print(f"  - {src}")
        else:
            print("No new sources found.")
    except Exception as e:
        print(f"Source discovery failed: {e}")


def cmd_report():
    """Generate engagement report."""
    print("=" * 50)
    print("ENGAGEMENT REPORT")
    print("=" * 50)

    try:
        from self_improve.engagement_tracker import get_weekly_report
        report = get_weekly_report()
        print(report)
    except Exception as e:
        print(f"Report generation failed: {e}")


def cmd_full_run():
    """Run the complete weekly pipeline."""
    print("*" * 60)
    print("  TULSA GAYS - FULL WEEKLY RUN")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("*" * 60)

    # Step 1: Scrape
    cmd_scrape()

    # Step 2: Generate weekday content
    cmd_generate("weekday")

    # Step 3: Generate weekend content
    cmd_generate("weekend")

    # Step 4: Update blog
    cmd_update_blog()

    # Step 5: Discover new sources
    cmd_discover()

    print("\n" + "=" * 60)
    print("FULL RUN COMPLETE")
    print("Posts are ready. Use 'py main.py post-weekday' or 'post-weekend' to publish.")
    print("=" * 60)


def cmd_test():
    """Test run - scrape and generate without posting."""
    print("*" * 60)
    print("  TULSA GAYS - TEST RUN (no posting)")
    print("*" * 60)

    cmd_scrape()
    cmd_generate("weekday")
    cmd_generate("weekend")
    print("\nTest run complete! Check data/posts/ for generated content.")


def _categorize_events(events):
    """Simple event categorization fallback."""
    categories = {"featured": [], "community": [], "arts": [], "nightlife": []}
    for event in events:
        source = event.get("source", "").lower()
        priority = event.get("priority", 3)
        if "homo_hotel" in source:
            categories["featured"].append(event)
        elif source in ("okeq", "all_souls", "church_restoration"):
            categories["community"].append(event)
        elif "twisted" in source:
            categories["arts"].append(event)
        elif priority <= 2:
            categories["community"].append(event)
        else:
            categories["nightlife"].append(event)
    return categories


def _fallback_caption(events, post_type, date_range):
    """Generate a simple caption without the API."""
    period = "this week" if post_type == "weekday" else "this weekend"
    lines = [f"Here's what's happening {period} in Tulsa! ({date_range})\n"]

    # Always lead with Homo Hotel
    homo = [e for e in events if "homo" in e.get("source", "").lower() or "homo" in e.get("name", "").lower()]
    if homo:
        h = homo[0]
        lines.append(f"HOMO HOTEL HAPPY HOUR")
        lines.append(f"{h.get('date', '')} | {h.get('time', '')}")
        lines.append(f"{h.get('venue', '')}")
        lines.append(f"{h.get('description', '')}\n")

    # Other events
    other = [e for e in events if e not in homo][:5]
    for event in other:
        lines.append(f"{event['name']}")
        lines.append(f"{event.get('date', '')} | {event.get('time', '')} @ {event.get('venue', '')}")
        if event.get("url"):
            lines.append(f"{event['url']}")
        lines.append("")

    # Hashtags
    hashtags = random.sample(config.HASHTAGS, min(15, len(config.HASHTAGS)))
    lines.append("\n" + " ".join(hashtags))

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower().replace("_", "-")
    commands = {
        "scrape": cmd_scrape,
        "generate": lambda: cmd_generate(sys.argv[2] if len(sys.argv) > 2 else "weekday"),
        "generate-all": lambda: cmd_generate("all"),
        "post-weekday": lambda: cmd_post("weekday"),
        "post-weekend": lambda: cmd_post("weekend"),
        "update-blog": cmd_update_blog,
        "discover": cmd_discover,
        "report": cmd_report,
        "full-run": cmd_full_run,
        "test": cmd_test,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
