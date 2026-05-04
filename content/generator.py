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
- Sassy and opinionated. You have thoughts. You share them.
- Okay to start sentences with "and" or "but" or "like"
- Mix short punchy lines with longer conversational ones
- Use emojis but dont go overboard -- 4-7 total per post max
- Include 1-2 moments of genuine enthusiasm or a light read ("we LOVE this one", "no excuses this time", "your couch will survive without you")
- Occasionally drop a Tulsa-specific reference (Brookside, the Gathering Place, Cherry Street, 11th & Lewis, Philbrook, etc)
- Swear lightly if it fits the vibe (hell yeah, damn, etc) but keep it IG-friendly
- Convince people to go. Tell them what to do when they get there. Be specific.

WORDS/PHRASES YOU MUST NEVER USE (these are AI tells):
- delve, landscape, tapestry, vibrant, foster, holistic, synergy, leverage
- "I'd be happy to", "certainly", "absolutely", "it's worth noting"
- "in conclusion", "furthermore", "however" at the start of sentences
- "bustling", "myriad", "plethora", "nestled", "embark", "comprehensive", "paramount"
- "safe space", "don't miss out", "something for everyone"
- Never use the word "community" more than once per post
- No em dashes

HOMO HOTEL HAPPY HOUR RULES:
- This event is ALWAYS listed first, always gets the most hype
- Describe it with genuine excitement each time but vary the wording every week
- Its the signature event -- treat it like the main character it is

FORMAT RULES:
- First line is the hook -- short, punchy, makes people stop mid-scroll
- Then Homo Hotel Happy Hour callout with real enthusiasm
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
    """Use Claude to generate event-specific descriptions for every event.

    Processes all events in batches of 20. Only enriches events that are
    missing a description or have scraper-artifact text. Preserves good
    existing descriptions. Falls back to rule-based if API is unavailable.
    """
    if not events:
        return events

    if not config.ANTHROPIC_API_KEY:
        print("[generator] No API key — using rule-based enrichment")
        return _rule_based_enrich_all(events)

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    BATCH = 20

    # Only enrich events that need it
    needs_enrichment = [
        (i, e) for i, e in enumerate(events)
        if not (e.get("description") or "").strip()
        or len((e.get("description") or "").strip()) < 60
        or _is_scraper_artifact((e.get("description") or ""))
    ]

    print(f"[generator] Enriching {len(needs_enrichment)} of {len(events)} events via Claude API")

    for batch_start in range(0, len(needs_enrichment), BATCH):
        batch = needs_enrichment[batch_start:batch_start + BATCH]
        event_lines = []
        for j, (orig_idx, e) in enumerate(batch):
            name = e.get("name", "Unknown")
            venue = (e.get("venue") or "").split(",")[0].strip()  # business name only
            date = e.get("date", "")
            time = e.get("time", "")
            existing = (e.get("description") or "").strip()
            line = f"{j+1}. {name}"
            if venue:
                line += f" @ {venue}"
            if date or time:
                line += f" ({date} {time})".strip()
            if existing and len(existing) > 20 and not _is_scraper_artifact(existing):
                line += f" — hint: {existing[:120]}"
            event_lines.append(line)

        prompt = (
            "For each event below, write a 1-2 sentence description (under 180 chars) "
            "that tells someone what this specific event IS, why a gay introvert should drag "
            "themselves there, and what to do to have the best time. Be specific to THIS event. "
            "Sassy and warm, like a friend who has opinions and wants you to go. No em dashes. "
            "No 'safe space', 'vibrant', 'don't miss out', or other AI tells.\n\n"
            "Events:\n" + "\n".join(event_lines) +
            "\n\nReply with ONLY a numbered list. Format: 1. [description]"
        )

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=(
                    "You write short event descriptions for TulsaGays.com. Voice: Joan Crawford "
                    "at a queer community mixer. Sardonic, warm, opinionated, always on the reader's "
                    "side. You are convincing an introverted gay person to leave the house. Be specific "
                    "to the actual event. Never use em dashes. Never write fragmented sentence bursts "
                    "like 'No scripts. No judgment. No fuss.' Write connected prose instead."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            response = message.content[0].text.strip()
            for line in response.split("\n"):
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue
                try:
                    dot_idx = line.index(".")
                    num = int(line[:dot_idx]) - 1
                    desc = line[dot_idx + 1:].strip()
                    if 0 <= num < len(batch):
                        orig_idx = batch[num][0]
                        events[orig_idx]["description"] = desc
                except (ValueError, IndexError):
                    continue
            print(f"[generator] Batch {batch_start//BATCH + 1} done ({len(batch)} events)")
        except Exception as e:
            print(f"[generator] Batch enrichment failed: {e} — applying rule-based to this batch")
            for _, ev in batch:
                if not (ev.get("description") or "").strip():
                    ev["description"] = _rule_based_enrich(ev)

    return events


def _rule_based_enrich(event: dict) -> str:
    """Generate a sassy, action-oriented pitch that makes people want to go."""
    name = (event.get("name") or "").lower()
    venue = (event.get("venue") or "").strip()
    time  = (event.get("time") or "").strip()
    src   = (event.get("source") or "").lower()
    existing = (event.get("description") or "").strip()

    _scraper_artifacts = [
        "tulsa events lists", "ticket options may be available",
        "verified providers", "events.tulsa.okstate.edu",
        "did you know that **", "this event is sold out this is not an official",
    ]
    if existing and len(existing) > 80 and not any(a in existing.lower() for a in _scraper_artifacts):
        return existing  # already has a good description

    at_venue = f" at {venue}" if venue else ""
    at_time  = f" at {time}" if time else ""

    if any(k in name for k in ["dragnificent", "drag show", "drag night", "drag brunch", "drag queen", "drag king", "drag performer"]):
        return ("Put the phone in your pocket, get yourself to the front, and tip the queens properly. "
                "You are going to lose your mind in the best possible way and you will spend the whole drive home "
                "wishing you had done this weeks ago.")

    if any(k in name for k in ["cabaret", "comc", "chorus", "chorale", "council oak"]):
        return ("Dress up, get there early, and sit close enough to see faces during the big moments. "
                "This is a real ensemble that pours everything into every performance, and the energy in that "
                "room is unlike most things available to you on a Tuesday in Tulsa.")

    if "happy hour" in name or "homo hotel" in name:
        return ("Do not go and stand in the corner looking at your phone. Walk up to someone whose "
                "outfit you genuinely like, tell them so, and start a conversation from there. "
                "You will leave with at least two new people you actually want to see again.")

    if "brunch" in name or "boozy brunch" in name:
        return ("Dress like you made an effort. Order the thing you normally talk yourself out of. "
                "Talk to the table next to you because brunch with this crowd is a full social event "
                "and you will regret it if you spend it looking at your phone.")

    if any(k in name for k in ["craft", "crochet", "knit", "stitch", "maker", "queer craft"]):
        return (f"You do not need to know what you're doing. Show up{at_venue} with your hands and "
                "your personality and let the rest figure itself out. You will leave with something "
                "you made and probably someone new you actually like.")

    if any(k in name for k in ["karaoke"]):
        return ("Get up there and sing something you are slightly embarrassed to admit you love this much. "
                "Nobody is judging you and you will feel genuinely great afterward. The person who goes "
                "first always has the most fun. Be that person.")

    if any(k in name for k in ["trivia", "quiz"]):
        return ("Make a team with strangers, name it something that gets a reaction from the host, "
                "and talk trash between rounds. This is a room full of people who would genuinely "
                "enjoy meeting you if you stopped overthinking the approach.")

    if any(k in name for k in ["comedy", "comedian", "loony bin", "standup", "stand-up"]) or "comedy" in venue.lower():
        return ("Sit close to the front because it is always a better show from there, laugh out loud "
                "when it's actually funny, and talk to whoever's next to you during the break. "
                "Live comedy in a small room hits differently and there is no good reason not to go.")

    if any(k in name for k in ["rave", "broadway rave", "dance", "dj ", "w/dj", "latin night", "dance party"]):
        return ("Wear something you can actually move in because you will be dancing whether you planned "
                "to or not. Get on the floor within the first 20 minutes and do not leave before midnight. "
                "Your self-consciousness can wait in the car.")

    if any(k in name for k in ["tulsa eagle", "yellow brick", "majestic"]) or src in ("bars", "nightlife"):
        return (f"Get there{at_time}, order something, and start a conversation with whoever is next to you "
                "at the bar. Queer nightlife only stays worth having when people actually show up to it.")

    if any(k in name for k in ["market", "art market", "art show", "art fair", "gallery"]):
        return ("Bring cash and plan to spend a little more than you think you will. Talk to the artists "
                "because most of them genuinely want to tell you about their work. "
                "This is better than anything you'd find scrolling at home for the same amount of time.")

    if any(k in name for k in ["concert", "live music", "music night", "performance"]):
        return ("Arrive before it starts, find a spot worth holding, and put your phone away for at least "
                "the first three songs. Live music in Tulsa is genuinely underrated and you are going to "
                "feel something if you let yourself be actually present for it.")

    if any(k in name for k in ["support group", "healing", "chronic", "wellness"]):
        return ("You do not have to have it together before you walk in. That is the entire point of the "
                "group. Show up, listen, share when you're ready, and remember that you are not as alone "
                "in this as it has been feeling lately.")

    if any(k in name for k in ["all souls", "unitarian", "church", "spiritual", "meditation"]):
        return ("One of the largest UU congregations in the country and one of the most genuinely affirming "
                "spaces in Tulsa. Walk in exactly as you are. You will feel the difference immediately.")

    if "bowling" in name:
        return ("Show up even if you haven't bowled in years, because nobody is judging your form and "
                "the worse you bowl the better your lane-mates feel about theirs. "
                "Everyone there is just glad you made it out.")

    if any(k in name for k in ["canasta", "card", "game night", "board game", "dungeons", "d&d", "dragons"]):
        return ("Step away from the screen and use your brain for something that requires other actual "
                "humans. Sit next to a stranger, learn whatever's being played, and talk trash appropriately. "
                "This is a genuinely good time and the bar for entry is just showing up.")

    if "okeq" in src or "equality center" in (venue or "").lower():
        return (f"OKEQ's space{at_venue} is where Tulsa's queer community actually gathers and does the "
                "work. Walk in. Say hello to someone. Things get measurably better when you show up.")

    return ("Put this on your calendar and actually go this time. "
            "The people in that room are your people, and the only way you find that out is by walking "
            "through the door.")


_SCRAPER_ARTIFACTS = [
    "tulsa events lists", "ticket options may be available",
    "verified providers", "events.tulsa.okstate.edu",
    "did you know that **", "this event is sold out this is not an official",
]


def _is_scraper_artifact(desc: str) -> bool:
    d = desc.lower()
    return any(a in d for a in _SCRAPER_ARTIFACTS)


def _rule_based_enrich_all(events: list[dict]) -> list[dict]:
    """Apply rule-based enrichment to all events missing good or sassy descriptions."""
    for ev in events:
        existing = (ev.get("description") or "").strip()
        if not existing or len(existing) < 60 or _is_scraper_artifact(existing):
            ev["description"] = _rule_based_enrich(ev)
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
