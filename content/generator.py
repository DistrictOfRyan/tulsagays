"""
Generate Instagram post captions from scraped event data using Claude API.

Produces captions that read like a real local community member wrote them --
casual, warm, occasionally messy in a human way. Anti-AI-detection patterns
are baked into the system prompt so output never feels sterile or robotic.
"""

import sys
import os
import random
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from anthropic import Anthropic


# ── Category keywords for auto-classifying events ──────────────────────────

_COMMUNITY_KEYWORDS = [
    "okeq", "equality", "oklahomans for equality", "support group",
    "church", "unitarian", "all souls", "restoration", "affirming",
    "potluck", "volunteer", "meeting", "workshop", "youth",
]
_ARTS_KEYWORDS = [
    "twisted arts", "drag", "performance", "art", "gallery", "paint",
    "comedy", "open mic", "theater", "theatre", "improv", "cabaret",
    "burlesque", "poetry", "reading",
]
_NIGHTLIFE_KEYWORDS = [
    "eagle", "ybr", "yellow brick road", "majestic", "club", "dj",
    "dance night", "party",
]
_HOMO_HOTEL_KEYWORDS = [
    "homo hotel", "homo hotel happy hour",
]

# Formats to rotate between so posts don't all look the same
_POST_FORMATS = [
    "list",       # bullet-style event rundown
    "narrative",  # paragraph-style storytelling
    "hype",       # high-energy, lots of caps and excitement
    "chill",      # laid-back, conversational
]

# Hook lines to rotate through (Claude will pick/riff on these)
_HOOK_TEMPLATES = [
    "ok tulsa {post_type} plans are HERE",
    "your {post_type} just got a whole lot gayer",
    "so uhh who's free {date_range}??",
    "another week another slate of queer excellence",
    "tulsa gays rise up -- {post_type} edition",
    "we did the homework so you dont have to",
    "POV: you actually go out this {post_type}",
    "{post_type} vibes incoming",
    "who wants plans?? bc we got plans.",
    "bored? not anymore. {date_range} events below",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _classify_event(event: dict) -> str:
    """Return a category string for a single event."""
    name_lower = (event.get("name") or "").lower()
    desc_lower = (event.get("description") or "").lower()
    source_lower = (event.get("source") or "").lower()
    combined = f"{name_lower} {desc_lower} {source_lower}"

    if any(kw in combined for kw in _HOMO_HOTEL_KEYWORDS):
        return "featured"
    if any(kw in combined for kw in _ARTS_KEYWORDS):
        return "arts"
    if any(kw in combined for kw in _COMMUNITY_KEYWORDS):
        return "community"
    if any(kw in combined for kw in _NIGHTLIFE_KEYWORDS):
        return "nightlife"
    # Default to community for anything unclassified
    return "community"


def categorize_events(events: list[dict]) -> dict[str, list[dict]]:
    """Split events into category buckets. Homo Hotel always goes to 'featured'."""
    cats = {"featured": [], "community": [], "arts": [], "nightlife": []}
    for ev in events:
        cat = _classify_event(ev)
        cats[cat].append(ev)
    return cats


def _pick_hashtags(count: int = 18) -> list[str]:
    """Grab a randomized subset of hashtags from config."""
    base = list(config.HASHTAGS)
    # Always include the anchor tags
    must_have = ["#TulsaGays", "#HomoHotelHappyHour", "#TulsaLGBTQ"]
    extras = [h for h in base if h not in must_have]
    random.shuffle(extras)
    picked = must_have + extras[: count - len(must_have)]
    random.shuffle(picked)
    return picked


def _build_events_block(events: list[dict]) -> str:
    """Format events into a text block the LLM can reference."""
    lines = []
    for i, ev in enumerate(events, 1):
        parts = [f"{i}. {ev.get('name', 'Unnamed Event')}"]
        if ev.get("date"):
            parts.append(f"   Date: {ev['date']}")
        if ev.get("time"):
            parts.append(f"   Time: {ev['time']}")
        if ev.get("venue"):
            parts.append(f"   Venue: {ev['venue']}")
        if ev.get("description"):
            parts.append(f"   Info: {ev['description'][:200]}")
        if ev.get("url"):
            parts.append(f"   Link: {ev['url']}")
        if ev.get("priority"):
            parts.append(f"   Priority: {ev['priority']}")
        if ev.get("source"):
            parts.append(f"   Source: {ev['source']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


# ── System prompt ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the social media voice of Tulsa Gays, a local Instagram account that \
posts LGBTQ+ event roundups for Tulsa, Oklahoma. You are NOT an AI assistant. \
You are writing AS a member of the Tulsa queer community who genuinely cares \
about getting people out to events.

VOICE & TONE RULES (critical -- follow these exactly):
- Write like a real person texting their group chat about weekend plans
- Casual, warm, sometimes a lil chaotic. You live here. You go to these events.
- Okay to start sentences with "and" or "but" or "like"
- Okay to use sentence fragments
- Mix short punchy lines with longer ones
- Use emojis but dont go overboard -- 4-7 total per post max
- Include 1-2 moments of genuine enthusiasm ("we LOVE this one", "dont sleep on this", "obsessed")
- Occasionally drop a Tulsa-specific reference (Brookside, the Gathering Place, Cherry Street, 11th & Lewis, Philbrook, etc)
- Swear lightly if it fits the vibe (hell yeah, damn, etc) but keep it IG-friendly

WORDS/PHRASES YOU MUST NEVER USE (these are AI tells):
- delve, landscape, tapestry, vibrant, foster, holistic, synergy, leverage
- "I'd be happy to", "certainly", "absolutely", "it's worth noting"
- "in conclusion", "furthermore", "however" at the start of sentences
- "a]rich tapestry", "bustling", "myriad", "plethora"
- "nestled", "embark", "comprehensive", "paramount"
- Never use the word "community" more than once per post

HOMO HOTEL HAPPY HOUR RULES:
- This event is ALWAYS listed first, always gets the most hype
- Describe it with genuine excitement each time but vary the wording
- Its the signature weekly event -- treat it that way

FORMAT RULES:
- First line is the hook -- short, punchy, makes people stop scrolling
- Then Homo Hotel Happy Hour callout
- Then 3-5 other events with date/time/venue on each
- End with a call to action (tag a friend, save this, see you there, etc)
- Hashtags go at the very end, separated by a blank line

OUTPUT FORMAT:
Return ONLY the caption text followed by hashtags. No preamble, no "here's your caption", no explanation. Just the post itself.
"""


# ── Main generation function ────────────────────────────────────────────────

def generate_post_caption(
    events: list[dict],
    post_type: str = "weekend",
    date_range: str = "",
) -> dict:
    """
    Generate an Instagram caption from event data.

    Args:
        events: list of event dicts with keys:
            name, date, time, venue, description, url, priority, source
        post_type: "weekday" or "weekend"
        date_range: human-readable date range like "Mar 31 - Apr 3"

    Returns:
        dict with keys:
            caption (str) - the full post caption
            hashtags (list[str]) - hashtag list used
            category_events (dict) - events split by category
    """
    category_events = categorize_events(events)
    hashtags = _pick_hashtags()
    hashtag_str = " ".join(hashtags)

    # Pick a random format style for variety
    fmt = random.choice(_POST_FORMATS)
    hook_template = random.choice(_HOOK_TEMPLATES)
    hook_hint = hook_template.format(
        post_type=post_type,
        date_range=date_range or "this week",
    )

    events_text = _build_events_block(events)

    user_prompt = f"""\
Write an Instagram caption for the Tulsa Gays account.

Post type: {post_type}
Date range: {date_range or "this week"}
Style this week: {fmt}
Hook idea (riff on this, dont copy exactly): {hook_hint}

Here are the events to feature:

{events_text}

Use these hashtags at the end (include all of them, separated by spaces):
{hashtag_str}

Remember: Homo Hotel Happy Hour goes FIRST and gets the most love. Then pick \
the 3-5 most interesting other events. Dont just list everything -- curate it. \
Add personality. Make people actually want to go.
"""

    # Try the API call, fall back to template if it fails
    try:
        caption = _call_claude(user_prompt)
    except Exception as e:
        print(f"[generator] Claude API failed, using fallback: {e}")
        traceback.print_exc()
        caption = _fallback_caption(events, post_type, date_range, hashtag_str)

    return {
        "caption": caption,
        "hashtags": hashtags,
        "category_events": category_events,
    }


def _call_claude(user_prompt: str) -> str:
    """Send the prompt to Claude and return the caption text."""
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=1200,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )
    # Extract text from the response
    text = message.content[0].text.strip()
    return text


def enrich_event_descriptions(events: list[dict]) -> list[dict]:
    """Use Claude to generate exciting, brief descriptions for each event.

    Adds/replaces the 'description' field with a compelling 1-2 sentence pitch
    that tells people why they should go and what to expect.
    """
    if not events:
        return events

    # Build a batch prompt for efficiency (one API call for all events)
    event_lines = []
    for i, e in enumerate(events[:15]):  # cap at 15 to stay within token limits
        name = e.get("name", "Unknown")
        venue = e.get("venue", "")
        date = e.get("date", "")
        time = e.get("time", "")
        source = e.get("source", "")
        desc = e.get("description", "")
        event_lines.append(
            f"{i+1}. {name} | {venue} | {date} {time} | source: {source}"
            + (f" | existing desc: {desc[:100]}" if desc else "")
        )

    events_block = "\n".join(event_lines)
    prompt = f"""\
For each event below, write a brief exciting description (1-2 sentences max, under 80 characters ideal)
that would make someone want to go. Write like a local Tulsa queer person hyping their friends.
Be specific about what makes each one special or fun. Don't use generic filler.

Events:
{events_block}

Reply with ONLY a numbered list matching the input, one description per line.
Format: 1. [description]
"""

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=800,
            system="You write brief, exciting event descriptions for a Tulsa LGBTQ+ community Instagram account. Casual tone, like texting a friend. No AI-sounding words.",
            messages=[{"role": "user", "content": prompt}],
        )
        response = message.content[0].text.strip()

        # Parse numbered responses back into events
        for line in response.split("\n"):
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            try:
                dot_idx = line.index(".")
                num = int(line[:dot_idx]) - 1
                desc = line[dot_idx + 1:].strip()
                if 0 <= num < len(events):
                    events[num]["description"] = desc
            except (ValueError, IndexError):
                continue

    except Exception as e:
        print(f"[generator] Event enrichment failed, keeping existing descriptions: {e}")

    return events


# ── Fallback template (no API needed) ──────────────────────────────────────

def _fallback_caption(
    events: list[dict],
    post_type: str,
    date_range: str,
    hashtag_str: str,
) -> str:
    """Generate a basic caption when the API is unavailable."""
    lines = []

    # Hook
    hooks = [
        f"your {post_type} plans just got gayer",
        f"tulsa queer events for {date_range or 'this week'}",
        f"stuff to do {date_range or 'this week'} -- gay edition",
    ]
    lines.append(random.choice(hooks).upper())
    lines.append("")

    # Find Homo Hotel event or fake it
    hh_events = [e for e in events if "homo hotel" in (e.get("name") or "").lower()]
    if hh_events:
        hh = hh_events[0]
        lines.append(f"HOMO HOTEL HAPPY HOUR {hh.get('date', '')}")
        if hh.get("time"):
            lines.append(f"{hh['time']} @ {hh.get('venue', 'the usual spot')}")
        lines.append("you already know. be there.")
        lines.append("")
    else:
        lines.append("HOMO HOTEL HAPPY HOUR")
        lines.append("the weekly tradition continues. you already know.")
        lines.append("")

    # Other events (up to 5)
    others = [e for e in events if "homo hotel" not in (e.get("name") or "").lower()]
    for ev in others[:5]:
        name = ev.get("name", "Event")
        date = ev.get("date", "")
        time_ = ev.get("time", "")
        venue = ev.get("venue", "")
        detail = f"{name}"
        if date:
            detail += f" -- {date}"
        if time_:
            detail += f" @ {time_}"
        if venue:
            detail += f" ({venue})"
        lines.append(detail)

    lines.append("")
    ctas = [
        "tag someone who needs plans",
        "save this for later -- you'll thank us",
        "see yall out there",
        "drop a comment if youre going to any of these",
    ]
    lines.append(random.choice(ctas))

    lines.append("")
    lines.append(hashtag_str)

    return "\n".join(lines)


# ── Test harness ────────────────────────────────────────────────────────────

def _test():
    """Generate a sample caption with fake events for testing."""
    fake_events = [
        {
            "name": "Homo Hotel Happy Hour",
            "date": "Friday, Apr 4",
            "time": "5:00 PM - 8:00 PM",
            "venue": "The Homo Hotel",
            "description": "Weekly happy hour for the queer community. Cheap drinks, good vibes, great people.",
            "url": "https://example.com/hhhh",
            "priority": 1,
            "source": "homo_hotel",
        },
        {
            "name": "Queer Art Night",
            "date": "Thursday, Apr 3",
            "time": "7:00 PM",
            "venue": "Twisted Arts Tulsa",
            "description": "Open studio night with live painting and drag performances. BYOB.",
            "url": "https://twistedartstulsa.com/events",
            "priority": 1,
            "source": "twisted_arts",
        },
        {
            "name": "OKEQ Support Group",
            "date": "Wednesday, Apr 2",
            "time": "6:30 PM",
            "venue": "Dennis R. Neill Equality Center",
            "description": "Weekly peer support group. All are welcome. Confidential and affirming space.",
            "url": "https://okeq.org/events",
            "priority": 1,
            "source": "okeq",
        },
        {
            "name": "Drag Bingo Fundraiser",
            "date": "Saturday, Apr 5",
            "time": "8:00 PM",
            "venue": "Majestic Night Club",
            "description": "Drag bingo with prizes! Benefits local LGBTQ+ youth programs.",
            "url": "",
            "priority": 2,
            "source": "majestic",
        },
        {
            "name": "All Souls Potluck & Pride Planning",
            "date": "Sunday, Apr 6",
            "time": "12:00 PM",
            "venue": "All Souls Unitarian Church",
            "description": "Bring a dish, meet neighbors, help plan the upcoming pride season events.",
            "url": "https://allsoulschurch.org/events",
            "priority": 2,
            "source": "all_souls",
        },
        {
            "name": "Karaoke Night",
            "date": "Friday, Apr 4",
            "time": "9:00 PM",
            "venue": "Yellow Brick Road",
            "description": "Friday night karaoke. Song list is massive. No judgment zone.",
            "url": "",
            "priority": 3,
            "source": "ybr",
        },
    ]

    print("=" * 60)
    print("TESTING CAPTION GENERATOR")
    print("=" * 60)

    result = generate_post_caption(
        events=fake_events,
        post_type="weekend",
        date_range="Apr 2 - Apr 6",
    )

    print("\n--- CAPTION ---")
    print(result["caption"])

    print("\n--- HASHTAGS ---")
    print(", ".join(result["hashtags"]))

    print("\n--- CATEGORIES ---")
    for cat, evs in result["category_events"].items():
        names = [e["name"] for e in evs]
        print(f"  {cat}: {names}")

    print("\n" + "=" * 60)
    print("TESTING FALLBACK (simulating API failure)")
    print("=" * 60)

    fallback = _fallback_caption(
        fake_events, "weekend", "Apr 2 - Apr 6",
        " ".join(_pick_hashtags()),
    )
    print("\n--- FALLBACK CAPTION ---")
    print(fallback)


if __name__ == "__main__":
    _test()
