"""Content optimization based on engagement data.

Uses historical engagement data to recommend hashtags, posting times,
content formats, and event featuring decisions.
"""

import sys
import os
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from self_improve.engagement_tracker import _load_log, analyze_trends


def get_optimal_hashtags(n=20):
    """Return the best performing hashtags based on past reach data.

    Combines analysis of past hashtag performance with the default
    hashtags from config, prioritizing those with proven reach.

    Args:
        n: Number of hashtags to return. Default 20.

    Returns:
        list[str]: Top n hashtags sorted by performance.
    """
    insights = analyze_trends()
    top_hashtags = insights.get("top_hashtags", [])

    # Start with proven performers
    result = [h["hashtag"] for h in top_hashtags if h.get("avg_reach", 0) > 0]

    # Fill remaining slots with defaults from config
    for tag in config.HASHTAGS:
        if tag not in result:
            result.append(tag)
        if len(result) >= n:
            break

    return result[:n]


def get_optimal_posting_time(post_type="weekday"):
    """Return the best posting time based on past engagement.

    Args:
        post_type: One of 'weekday' or 'weekend'. Determines which
                   config default to fall back on.

    Returns:
        dict: With keys 'day' (str), 'hour' (int), 'confidence' (str).
    """
    insights = analyze_trends()
    best_times = insights.get("best_posting_times", [])

    # Default times from config
    defaults = {
        "weekday": {
            "day": config.WEEKDAY_POST_DAY.capitalize(),
            "hour": config.WEEKDAY_POST_HOUR,
            "confidence": "default",
        },
        "weekend": {
            "day": config.WEEKEND_POST_DAY.capitalize(),
            "hour": config.WEEKEND_POST_HOUR,
            "confidence": "default",
        },
    }

    if not best_times:
        return defaults.get(post_type, defaults["weekday"])

    # Filter times relevant to the post type
    weekend_days = {"Saturday", "Sunday"}

    relevant_times = []
    for t in best_times:
        time_str = t.get("time", "")
        day_name = time_str.split(" ")[0] if " " in time_str else ""

        if post_type == "weekend" and day_name in weekend_days:
            relevant_times.append(t)
        elif post_type == "weekday" and day_name not in weekend_days:
            relevant_times.append(t)

    if not relevant_times:
        return defaults.get(post_type, defaults["weekday"])

    best = relevant_times[0]
    parts = best["time"].split(" ")
    day = parts[0] if parts else "Monday"
    hour_str = parts[1] if len(parts) > 1 else "9:00"
    hour = int(hour_str.split(":")[0])

    count = best.get("count", 0)
    if count >= 10:
        confidence = "high"
    elif count >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    return {"day": day, "hour": hour, "confidence": confidence}


def should_feature_bar_event(event):
    """Decide if a bar event is special enough to feature.

    Bar events (priority 3 in config) are only featured when they're
    special events, not regular nightly programming. This function
    uses past engagement with similar events to make the decision.

    Args:
        event: dict with keys like 'name', 'venue', 'description',
               'source' (matching a config.SOURCES key).

    Returns:
        bool: True if the event should be featured, False otherwise.
    """
    event_name = event.get("name", "").lower()
    event_desc = event.get("description", "").lower()

    # Always feature certain special event types
    special_keywords = [
        "drag show", "drag brunch", "pageant", "fundraiser",
        "benefit", "charity", "anniversary", "grand opening",
        "pride", "holiday", "special guest", "live music",
        "concert", "comedy", "contest", "competition",
        "theme night", "costume", "memorial", "celebration",
        "launch", "premiere", "debut",
    ]

    combined = f"{event_name} {event_desc}"
    for keyword in special_keywords:
        if keyword in combined:
            return True

    # Skip regular bar programming
    regular_keywords = [
        "happy hour", "daily special", "drink special",
        "open daily", "regular hours", "nightly",
    ]
    for keyword in regular_keywords:
        if keyword in combined:
            return False

    # Check past engagement with similar events at this venue
    log = _load_log()
    posts = [p for p in log["posts"] if p.get("engagement")]

    venue = event.get("venue", "").lower()
    venue_engagements = []

    for post in posts:
        for featured_event in post.get("events_featured", []):
            if venue and venue in featured_event.lower():
                eng = post["engagement"]
                total = (
                    eng.get("likes", 0)
                    + eng.get("comments", 0) * 3
                    + eng.get("saves", 0) * 2
                )
                venue_engagements.append(total)

    # If past similar events had good engagement, feature it
    if venue_engagements:
        avg_engagement = sum(venue_engagements) / len(venue_engagements)
        # Compare against overall average
        all_engagements = []
        for post in posts:
            eng = post["engagement"]
            total = (
                eng.get("likes", 0)
                + eng.get("comments", 0) * 3
                + eng.get("saves", 0) * 2
            )
            all_engagements.append(total)

        overall_avg = sum(all_engagements) / len(all_engagements) if all_engagements else 0
        if avg_engagement >= overall_avg * 0.8:
            return True

    # Default: don't feature regular bar events
    return False


def suggest_content_format():
    """Suggest the best content format based on past performance.

    Analyzes engagement data for carousels, reels, and single images
    to recommend the optimal format for the next post.

    Returns:
        dict: With keys:
            - format: Recommended format ('carousel', 'reel', 'single_image')
            - reason: Why this format is recommended
            - stats: Performance data for each format
    """
    insights = analyze_trends()
    type_data = insights.get("best_post_types", [])

    if not type_data:
        return {
            "format": "carousel",
            "reason": "Default recommendation: carousels work well for event listings because they can feature multiple events with swipeable cards.",
            "stats": {},
        }

    stats = {}
    for t in type_data:
        stats[t["type"]] = {
            "avg_engagement": t["avg_engagement"],
            "sample_size": t["count"],
        }

    best = type_data[0]
    best_format = best["type"]
    best_eng = best["avg_engagement"]

    # Build reason
    if best["count"] < 3:
        reason = (
            f"Early data suggests '{best_format}' performs well "
            f"(avg engagement: {best_eng:.0f}), but sample size is small "
            f"({best['count']} posts). Consider experimenting with other formats."
        )
    else:
        runner_up = type_data[1] if len(type_data) > 1 else None
        if runner_up:
            diff_pct = ((best_eng - runner_up["avg_engagement"]) / runner_up["avg_engagement"] * 100
                        if runner_up["avg_engagement"] > 0 else 0)
            reason = (
                f"'{best_format}' outperforms '{runner_up['type']}' by "
                f"{diff_pct:.0f}% on average engagement "
                f"(based on {best['count']} posts)."
            )
        else:
            reason = (
                f"'{best_format}' is the top performer with "
                f"avg engagement of {best_eng:.0f} "
                f"(based on {best['count']} posts)."
            )

    return {
        "format": best_format,
        "reason": reason,
        "stats": stats,
    }


if __name__ == "__main__":
    print("=== Content Optimization Report ===\n")

    print("OPTIMAL HASHTAGS:")
    hashtags = get_optimal_hashtags(20)
    print(f"  {' '.join(hashtags)}\n")

    print("OPTIMAL POSTING TIMES:")
    for ptype in ["weekday", "weekend"]:
        time_rec = get_optimal_posting_time(ptype)
        print(f"  {ptype}: {time_rec['day']} at {time_rec['hour']}:00 "
              f"(confidence: {time_rec['confidence']})")
    print()

    print("CONTENT FORMAT SUGGESTION:")
    format_rec = suggest_content_format()
    print(f"  Recommended: {format_rec['format']}")
    print(f"  Reason: {format_rec['reason']}")
    if format_rec["stats"]:
        print("  Stats:")
        for fmt, s in format_rec["stats"].items():
            print(f"    {fmt}: avg={s['avg_engagement']:.0f}, n={s['sample_size']}")
    print()
