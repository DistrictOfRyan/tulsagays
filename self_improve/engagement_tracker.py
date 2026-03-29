"""Track and analyze Instagram post engagement.

Logs posts, fetches engagement metrics from the Meta API,
analyzes trends, and generates weekly growth reports.
"""

import sys
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import requests
except ImportError:
    requests = None


ENGAGEMENT_LOG = os.path.join(config.DATA_DIR, "engagement_log.json")


def _load_log():
    """Load the engagement log."""
    if os.path.exists(ENGAGEMENT_LOG):
        with open(ENGAGEMENT_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts": [], "weekly_snapshots": []}


def _save_log(data):
    """Save the engagement log."""
    config.ensure_dirs()
    with open(ENGAGEMENT_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def log_post(post_id, post_type, events_featured, caption_style):
    """Log a new Instagram post for tracking.

    Args:
        post_id: Instagram media ID or internal identifier.
        post_type: One of 'carousel', 'reel', 'single_image', 'story'.
        events_featured: List of event names or categories featured.
        caption_style: Description of caption style, e.g. 'listicle', 'narrative'.
    """
    log = _load_log()

    post_entry = {
        "post_id": post_id,
        "post_type": post_type,
        "events_featured": events_featured,
        "caption_style": caption_style,
        "posted_at": datetime.now().isoformat(),
        "day_of_week": datetime.now().strftime("%A"),
        "hour": datetime.now().hour,
        "hashtags": [],
        "engagement": None,
    }

    log["posts"].append(post_entry)
    _save_log(log)
    print(f"[engagement] Logged post {post_id} ({post_type})")


def fetch_engagement(post_id, access_token=None):
    """Fetch engagement metrics for a post from the Meta Graph API.

    Args:
        post_id: Instagram media ID.
        access_token: Meta API access token. Defaults to config value.

    Returns:
        dict: Engagement metrics with keys: likes, comments, saves,
              reach, impressions. Returns None on failure.
    """
    if requests is None:
        print("[engagement] requests library not installed.")
        return None

    token = access_token or config.META_ACCESS_TOKEN
    if not token:
        print("[engagement] No Meta access token configured.")
        return None

    try:
        url = f"https://graph.facebook.com/v19.0/{post_id}/insights"
        params = {
            "metric": "impressions,reach,saved,likes,comments",
            "access_token": token,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        metrics = {}
        for item in data.get("data", []):
            name = item.get("name", "")
            values = item.get("values", [{}])
            metrics[name] = values[0].get("value", 0) if values else 0

        # Also fetch basic media fields for likes/comments counts
        media_url = f"https://graph.facebook.com/v19.0/{post_id}"
        media_params = {
            "fields": "like_count,comments_count",
            "access_token": token,
        }
        media_resp = requests.get(media_url, params=media_params, timeout=10)
        if media_resp.ok:
            media_data = media_resp.json()
            metrics["likes"] = media_data.get("like_count", metrics.get("likes", 0))
            metrics["comments"] = media_data.get("comments_count", metrics.get("comments", 0))

        engagement = {
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "saves": metrics.get("saved", 0),
            "reach": metrics.get("reach", 0),
            "impressions": metrics.get("impressions", 0),
            "fetched_at": datetime.now().isoformat(),
        }

        # Update the log entry
        log = _load_log()
        for post in log["posts"]:
            if post["post_id"] == post_id:
                post["engagement"] = engagement
                break
        _save_log(log)

        print(f"[engagement] Fetched metrics for {post_id}: "
              f"{engagement['likes']} likes, {engagement['comments']} comments, "
              f"{engagement['saves']} saves")

        return engagement

    except Exception as e:
        print(f"[engagement] Error fetching metrics for {post_id}: {e}")
        return None


def analyze_trends():
    """Analyze engagement data to find what's working.

    Returns:
        dict: Insights with keys:
            - top_categories: Categories with highest avg engagement
            - best_posting_times: Day/hour combos with best performance
            - top_hashtags: Hashtags correlated with high reach
            - best_post_types: Post formats ranked by engagement
            - avg_engagement_rate: Overall average engagement rate
    """
    log = _load_log()
    posts = [p for p in log["posts"] if p.get("engagement")]

    insights = {
        "top_categories": [],
        "best_posting_times": [],
        "top_hashtags": [],
        "best_post_types": [],
        "avg_engagement_rate": 0,
        "total_posts_analyzed": len(posts),
    }

    if not posts:
        print("[engagement] No posts with engagement data to analyze.")
        return insights

    # Analyze by category
    category_engagement = defaultdict(list)
    for post in posts:
        eng = post["engagement"]
        total_eng = eng.get("likes", 0) + eng.get("comments", 0) * 3 + eng.get("saves", 0) * 2
        for event_cat in post.get("events_featured", []):
            category_engagement[event_cat].append(total_eng)

    insights["top_categories"] = sorted(
        [
            {"category": cat, "avg_engagement": sum(vals) / len(vals), "count": len(vals)}
            for cat, vals in category_engagement.items()
        ],
        key=lambda x: x["avg_engagement"],
        reverse=True,
    )

    # Analyze by posting time
    time_engagement = defaultdict(list)
    for post in posts:
        eng = post["engagement"]
        total_eng = eng.get("likes", 0) + eng.get("comments", 0) * 3 + eng.get("saves", 0) * 2
        time_key = f"{post.get('day_of_week', 'Unknown')} {post.get('hour', 0)}:00"
        time_engagement[time_key].append(total_eng)

    insights["best_posting_times"] = sorted(
        [
            {"time": time_key, "avg_engagement": sum(vals) / len(vals), "count": len(vals)}
            for time_key, vals in time_engagement.items()
        ],
        key=lambda x: x["avg_engagement"],
        reverse=True,
    )[:5]

    # Analyze by post type
    type_engagement = defaultdict(list)
    for post in posts:
        eng = post["engagement"]
        total_eng = eng.get("likes", 0) + eng.get("comments", 0) * 3 + eng.get("saves", 0) * 2
        type_engagement[post.get("post_type", "unknown")].append(total_eng)

    insights["best_post_types"] = sorted(
        [
            {"type": ptype, "avg_engagement": sum(vals) / len(vals), "count": len(vals)}
            for ptype, vals in type_engagement.items()
        ],
        key=lambda x: x["avg_engagement"],
        reverse=True,
    )

    # Analyze hashtags
    hashtag_engagement = defaultdict(list)
    for post in posts:
        eng = post["engagement"]
        reach = eng.get("reach", 0)
        for tag in post.get("hashtags", []):
            hashtag_engagement[tag].append(reach)

    insights["top_hashtags"] = sorted(
        [
            {"hashtag": tag, "avg_reach": sum(vals) / len(vals), "count": len(vals)}
            for tag, vals in hashtag_engagement.items()
        ],
        key=lambda x: x["avg_reach"],
        reverse=True,
    )[:15]

    # Overall average engagement rate
    total_engagement = 0
    total_reach = 0
    for post in posts:
        eng = post["engagement"]
        total_engagement += eng.get("likes", 0) + eng.get("comments", 0) + eng.get("saves", 0)
        total_reach += eng.get("reach", 1)

    insights["avg_engagement_rate"] = (
        round(total_engagement / total_reach * 100, 2) if total_reach > 0 else 0
    )

    print(f"[engagement] Analyzed {len(posts)} posts. "
          f"Avg engagement rate: {insights['avg_engagement_rate']}%")

    return insights


def get_weekly_report():
    """Generate a text report of weekly growth metrics.

    Returns:
        str: Formatted report with follower growth, engagement stats,
             top performing content, and recommendations.
    """
    log = _load_log()
    posts = log["posts"]

    # Filter to last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    recent_posts = [
        p for p in posts
        if p.get("posted_at", "") >= week_ago
    ]

    recent_with_engagement = [p for p in recent_posts if p.get("engagement")]

    lines = [
        "=" * 50,
        f"  TULSA GAYS WEEKLY REPORT",
        f"  Generated: {datetime.now().strftime('%B %d, %Y')}",
        "=" * 50,
        "",
        f"Posts this week: {len(recent_posts)}",
        f"Posts with metrics: {len(recent_with_engagement)}",
        "",
    ]

    if recent_with_engagement:
        total_likes = sum(p["engagement"].get("likes", 0) for p in recent_with_engagement)
        total_comments = sum(p["engagement"].get("comments", 0) for p in recent_with_engagement)
        total_saves = sum(p["engagement"].get("saves", 0) for p in recent_with_engagement)
        total_reach = sum(p["engagement"].get("reach", 0) for p in recent_with_engagement)
        total_impressions = sum(p["engagement"].get("impressions", 0) for p in recent_with_engagement)

        lines.extend([
            "ENGAGEMENT SUMMARY",
            "-" * 30,
            f"  Total Likes:       {total_likes}",
            f"  Total Comments:    {total_comments}",
            f"  Total Saves:       {total_saves}",
            f"  Total Reach:       {total_reach}",
            f"  Total Impressions: {total_impressions}",
            "",
        ])

        # Best performing post
        best_post = max(
            recent_with_engagement,
            key=lambda p: (
                p["engagement"].get("likes", 0)
                + p["engagement"].get("comments", 0) * 3
                + p["engagement"].get("saves", 0) * 2
            ),
        )
        best_eng = best_post["engagement"]
        lines.extend([
            "TOP PERFORMING POST",
            "-" * 30,
            f"  ID: {best_post['post_id']}",
            f"  Type: {best_post['post_type']}",
            f"  Likes: {best_eng.get('likes', 0)} | "
            f"Comments: {best_eng.get('comments', 0)} | "
            f"Saves: {best_eng.get('saves', 0)}",
            f"  Events: {', '.join(best_post.get('events_featured', []))}",
            "",
        ])

    # Trend analysis
    insights = analyze_trends()
    if insights["top_categories"]:
        lines.extend([
            "TOP PERFORMING CATEGORIES",
            "-" * 30,
        ])
        for cat in insights["top_categories"][:3]:
            lines.append(f"  {cat['category']}: avg engagement {cat['avg_engagement']:.0f}")
        lines.append("")

    if insights["best_posting_times"]:
        lines.extend([
            "BEST POSTING TIMES",
            "-" * 30,
        ])
        for t in insights["best_posting_times"][:3]:
            lines.append(f"  {t['time']}: avg engagement {t['avg_engagement']:.0f}")
        lines.append("")

    # All-time stats
    all_with_engagement = [p for p in posts if p.get("engagement")]
    lines.extend([
        "ALL-TIME STATS",
        "-" * 30,
        f"  Total posts tracked: {len(posts)}",
        f"  Posts with metrics:  {len(all_with_engagement)}",
        f"  Avg engagement rate: {insights.get('avg_engagement_rate', 0)}%",
        "",
        "=" * 50,
    ])

    report = "\n".join(lines)
    print(report)
    return report


if __name__ == "__main__":
    print(get_weekly_report())
