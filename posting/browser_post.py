"""
Post to Instagram via browser automation using Claude's Chrome MCP tools.
This is the fallback/primary posting method when the Meta API isn't available.

Usage from Claude:
    1. Run: py main.py generate weekday  (generates carousel images + caption)
    2. Then ask Claude to: "post the weekday carousel to Instagram"
    3. Claude reads the post data, opens Instagram, and posts via browser

This file just documents the process and provides helper utilities.
The actual browser interaction happens through Claude's Chrome tools.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_latest_post_data(post_type="weekday"):
    """Get the most recent generated post data for browser posting."""
    week_key = config.current_week_key()
    post_file = os.path.join(config.DATA_DIR, "posts", week_key, f"{post_type}_post.json")

    if not os.path.exists(post_file):
        # Try to find any recent post
        posts_dir = os.path.join(config.DATA_DIR, "posts")
        if not os.path.exists(posts_dir):
            return None
        weeks = sorted(os.listdir(posts_dir), reverse=True)
        for week in weeks:
            pf = os.path.join(posts_dir, week, f"{post_type}_post.json")
            if os.path.exists(pf):
                post_file = pf
                break
        else:
            return None

    with open(post_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_carousel_images(post_type="weekday"):
    """Get paths to carousel images for the current week."""
    week_key = config.current_week_key()
    posts_dir = os.path.join(config.DATA_DIR, "posts", week_key)

    if not os.path.exists(posts_dir):
        return []

    images = sorted([
        os.path.join(posts_dir, f)
        for f in os.listdir(posts_dir)
        if f.startswith(f"{post_type}_") and f.endswith(".png")
    ])
    return images


def get_caption(post_type="weekday"):
    """Get the caption for the current week's post."""
    data = get_latest_post_data(post_type)
    if data:
        return data.get("caption", "")
    return ""


# Browser posting instructions for Claude:
POSTING_INSTRUCTIONS = """
To post a carousel to Instagram via browser:

1. Navigate to https://www.instagram.com/
2. Click the "+" (Create) button in the sidebar
3. Click "Select from computer" and upload all carousel images
4. Arrange slides in order (cover first, HHHH second, etc.)
5. Click "Next" to go to filters (skip filters)
6. Click "Next" to go to caption
7. Paste the generated caption
8. Click "Share" to publish

Image files are at: C:\\Users\\ryan\\OneDrive\\Desktop\\tulsagays\\data\\posts\\{week}\\
Caption is in: {week}_post.json
"""


if __name__ == "__main__":
    post_type = sys.argv[1] if len(sys.argv) > 1 else "weekday"
    data = get_latest_post_data(post_type)
    images = get_carousel_images(post_type)

    if data:
        print(f"Post type: {post_type}")
        print(f"Week: {data.get('week')}")
        print(f"Date range: {data.get('date_range')}")
        print(f"Caption length: {len(data.get('caption', ''))} chars")
        print(f"Images: {len(images)}")
        for img in images:
            print(f"  {img}")
        print(f"\nCaption preview:\n{data.get('caption', '')[:300]}...")
    else:
        print(f"No post data found for {post_type}. Run 'py main.py generate {post_type}' first.")
