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
import json
import time
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def get_date_range(post_type):
    """Get the date range string for the current week's post type."""
    today = datetime.now()
    # Find next Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0 and today.hour >= 12:
        days_until_monday = 7
    monday = today + timedelta(days=days_until_monday) if days_until_monday > 0 else today

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
    # Sort each day's events: timed events first (chronologically), untimed last
    def _time_sort_key(e):
        t = e.get("time", "") or ""
        return (1, "") if not t else (0, t)
    for day in days_of_week:
        events_by_day[day].sort(key=_time_sort_key)

    # Validate: warn if any day has zero events (expected for some days)
    days_with_events = [d for d in days_of_week if events_by_day[d]]
    print(f"\nEvents per day: { {d: len(events_by_day[d]) for d in days_of_week} }")
    if len(days_with_events) < 4:
        print(f"WARNING: Only {len(days_with_events)} days have events. "
              "Check scrapers — some sources may have failed.")

    # Generate carousel images
    print("\nGenerating carousel images...")
    try:
        from content.image_maker import create_carousel, save_carousel
        logo_path = config.LOGO_PATH if os.path.exists(config.LOGO_PATH) else None
        images = create_carousel(
            category_events, post_type, date_range, logo_path,
            events_by_day=events_by_day
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
