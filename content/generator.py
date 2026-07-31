"""
Generate Instagram post captions from scraped event data using Claude API.

Produces captions that read like a real local community member wrote them --
casual, warm, occasionally messy in a human way. Anti-AI-detection patterns
are baked into the system prompt so output never feels sterile or robotic.
"""

import sys
import os
import random
import re
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
    "another week another slate of LGBTQIA+ excellence",
    "tulsa gays rise up -- {post_type} edition",
    "we did the homework so you dont have to",
    "POV: you actually go out this {post_type}",
    "{post_type} vibes incoming",
    "who wants plans?? bc we got plans.",
    "bored? not anymore. {date_range} events below",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

import re as _re_mod

# Relative-date leakage from Eventbrite / Google Events cards lands in the venue
# field ("in 5 days", "Tomorrow"). Interpolating it produced live copy reading
# "Summer Meltdown Half Marathon at in 5 days" on 85 site cards (2026-07-31).
# Treat a junk venue as NO venue, here at the source of the sentence.
_RELATIVE_DATE_VENUE_RE = _re_mod.compile(
    r'^(in\s+(a|an|\d+)\s+(day|days|hour|hours|week|weeks|month|months)'
    r'|today|tonight|tomorrow|yesterday|this\s+\w+|next\s+\w+|tba|tbd)$', _re_mod.I)


def _usable_venue(raw):
    """Venue string fit to drop into a sentence, or '' when it is scraper junk."""
    v = (raw or "").strip()
    if not v or _RELATIVE_DATE_VENUE_RE.match(v.rstrip('.!')):
        return ""
    return v


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


def _pick_hashtags(count: int = 10) -> list[str]:
    """Return a capped, randomized subset of hashtags from config.

    Always includes MUST_HAVE_HASHTAGS. Total capped at 10 — Instagram's
    algorithm now penalises posts with excessive hashtags.
    """
    base = list(config.HASHTAGS)
    must_have = getattr(config, "MUST_HAVE_HASHTAGS",
                        ["#TulsaGays", "#TulsaLGBTQ", "#HomoHotelHappyHour"])
    extras = [h for h in base if h not in must_have]
    random.shuffle(extras)
    cap = min(count, 10)
    picked = must_have + extras[: cap - len(must_have)]
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
You are writing AS a member of the Tulsa LGBTQIA+ community who genuinely cares \
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
- NEVER use em dashes. Not one. Use a comma, a period, or parentheses instead. This is a hard rule.

WORDS/PHRASES YOU MUST NEVER USE (these are AI tells):
- delve, landscape, tapestry, vibrant, foster, holistic, synergy, leverage
- "I'd be happy to", "certainly", "absolutely", "it's worth noting"
- "in conclusion", "furthermore", "however" at the start of sentences
- "a]rich tapestry", "bustling", "myriad", "plethora"
- "nestled", "embark", "comprehensive", "paramount"
- Never use the word "community" more than once per post

HOMO HOTEL HAPPY HOUR RULES (only when HHHH is in the event list provided):
- When HHHH appears in the events list, it goes first and gets the most hype
- Describe it with genuine excitement each time but vary the wording
- Its the signature monthly event -- treat it that way when present
- When HHHH is NOT in the events list (the user prompt will tell you), DO NOT
  mention it, do not tease it, do not reference "next month" or "coming up".
  Promote what's actually happening this week instead.

EVENT FIDELITY RULES (absolute, no exceptions):
- Only mention events from the list provided in the user prompt
- Never invent event names, dates, venues, or details
- Never pull events from memory of past weeks
- If the events list is short, write a shorter caption, do not pad with fictional events

FORMAT RULES:
- First line is the hook -- short, punchy, makes people stop scrolling
- Then the featured event (HHHH if present, otherwise the first event in the list)
- Then 3-5 other events with date/time/venue on each
- End with a call to action (tag a friend, save this, see you there, etc)
- Hashtags go at the very end, separated by a blank line

OUTPUT FORMAT:
Return ONLY the caption text followed by hashtags. No preamble, no "here's your caption", no explanation. Just the post itself.
"""


# ── Main generation function ────────────────────────────────────────────────

def _strip_em_dashes(text: str) -> str:
    """Hard belt-and-suspenders: William's #1 voice rule is NO em dashes, and the
    caption LLM occasionally slips one in. Ranges become 'to', prose dashes become
    commas. Runs on every caption before it can reach a post."""
    if not text:
        return text
    import re as _re
    text = _re.sub(r'(\w)\s*[–—]\s*(\d)', r'\1 to \2', text)  # "6pm – 9pm" -> "6pm to 9pm"
    text = text.replace(' — ', ', ').replace('—', ', ')       # em dash
    text = text.replace(' – ', ', ').replace('–', ', ')       # en dash
    return text


# Public alias so any generator/tool can import the canonical scrubber without
# reaching for a private name. Voice rule #1 (no em dashes) applies to ALL public
# copy, so every path that ships text to a human should call this on its output.
def strip_em_dashes(text: str) -> str:
    return _strip_em_dashes(text)


# LLM meta-chatter that occasionally leaks ahead of the real caption ("okay
# writing this one straight from the brief since everything needed ... is
# already fully specified in the prompt."). Never part of the post — drop
# leading paragraphs that talk ABOUT the task instead of TO the audience.
# Seen live 2026-07-22 in a W30 caption regen.
_PREAMBLE_MARKERS = (
    "the brief", "the prompt", "the instructions", "as requested",
    "here's the caption", "here is the caption", "here's your caption",
    "writing this one", "fully specified", "voice rules",
)


def _strip_llm_preamble(text: str) -> str:
    parts = (text or "").split("\n\n")
    while parts:
        first = parts[0].strip().lower()
        if first and any(m in first for m in _PREAMBLE_MARKERS) and len(first) < 300:
            parts.pop(0)
            continue
        break
    return "\n\n".join(parts).strip() or (text or "")


_REFUSAL_MARKERS = (
    "i cannot", "i can't", "i can not", "i'm unable", "i am unable",
    "i won't", "as an ai", "i'm sorry, but", "i am sorry, but",
    "i'm not able", "i am not able", "i must decline",
)


def _is_refusal(text: str) -> bool:
    """True if the model returned a refusal instead of copy. A refusal is the
    ultimate voice violation and must never be saved as a description."""
    low = (text or "").strip().lower()
    return any(low.startswith(m) or f" {m}" in low[:60] for m in _REFUSAL_MARKERS)


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
    # HARD FILTER: pass events through eotw_selector skip rules AND restrict
    # to the current Mon-Sun window before they reach the AI prompt. Without
    # this, banned events (Club Majestic, source=recurring like Lambda Bowling,
    # bowling leagues, support groups, health clinics, "open for business"
    # business-hours announcements) and events from FUTURE weeks (HHHH on
    # 2026-06-05 ending up in a W22 caption) end up in the post.
    # eotw_selector.py is the single source of truth for skip rules.
    from datetime import timedelta as _td
    _today = datetime.now().date()
    _week_monday = _today - _td(days=_today.weekday())
    _week_sunday = _week_monday + _td(days=6)

    def _in_current_week(e):
        d = e.get("date", "")
        if not d:
            return False  # undated events excluded — we cannot trust them in a caption
        try:
            ed = datetime.strptime(d, "%Y-%m-%d").date()
            return _week_monday <= ed <= _week_sunday
        except ValueError:
            return False

    try:
        from eotw_selector import _is_skip, _is_lgbtq
        date_in = [e for e in events if _in_current_week(e)]
        skip_filtered = [e for e in date_in if not _is_skip(e)]
        # Sort LGBTQ events first so they get into the AI's attention budget
        skip_filtered.sort(key=lambda e: (0 if _is_lgbtq(e) else 1))
        events_for_caption = skip_filtered
        # Check whether Homo Hotel Happy Hour is actually in this week's events
        # so we can tell the AI NOT to fabricate it when it isn't.
        hhhh_this_week = any(
            "homo hotel" in (e.get("name") or "").lower()
            for e in events_for_caption
        )
        print(f"[generator] Filtered {len(events)} -> {len(date_in)} in-week "
              f"-> {len(skip_filtered)} after skip rules. HHHH this week: "
              f"{hhhh_this_week}")
    except Exception as _e:
        print(f"[generator] WARNING: eotw_selector filter failed ({_e}); "
              f"falling back to raw in-week events. CAPTION REVIEW MANDATORY.")
        events_for_caption = [e for e in events if _in_current_week(e)]
        hhhh_this_week = any(
            "homo hotel" in (e.get("name") or "").lower()
            for e in events_for_caption
        )

    category_events = categorize_events(events_for_caption)
    hashtags = _pick_hashtags()
    hashtag_str = " ".join(hashtags)

    # Pick a random format style for variety
    fmt = random.choice(_POST_FORMATS)
    hook_template = random.choice(_HOOK_TEMPLATES)
    hook_hint = hook_template.format(
        post_type=post_type,
        date_range=date_range or "this week",
    )

    events_text = _build_events_block(events_for_caption)

    if hhhh_this_week:
        hhhh_instruction = (
            "Homo Hotel Happy Hour goes FIRST and gets the most love. Then pick "
            "the 3-5 most interesting other events from the list."
        )
    else:
        hhhh_instruction = (
            "Homo Hotel Happy Hour is NOT this week. DO NOT mention it, do not "
            "tease it, do not include it. Pick the 3-5 most interesting events "
            "from the list and feature those instead. The first event in the "
            "list is the highest-priority pick (it's already sorted)."
        )

    user_prompt = f"""\
Write an Instagram caption for the Tulsa Gays account.

Post type: {post_type}
Date range: {date_range or "this week"}
Style this week: {fmt}
Hook idea (riff on this, dont copy exactly): {hook_hint}

Here are the events to feature — ONLY mention events that appear in this list. \
Do NOT invent events, do NOT pull from memory of past weeks, do NOT reference \
events from other weeks even if you know about them:

{events_text}

Use these hashtags at the end (include all of them, separated by spaces):
{hashtag_str}

{hhhh_instruction} Don't just list everything -- curate it. Add personality. \
Make people actually want to go. If an event is not in the list above, do not \
mention it.
"""

    # Try the API call, fall back to template if it fails. Pass the
    # ALREADY-FILTERED events to the fallback too — without this, fallback
    # captions include banned events (Lambda Bowling, DRAGNIFICENT) and events
    # from future weeks (HHHH on a future date).
    try:
        caption = _call_claude(user_prompt)
    except Exception as e:
        print(f"[generator] Claude API failed, using fallback: {e}")
        traceback.print_exc()
        caption = _fallback_caption(
            events_for_caption, post_type, date_range, hashtag_str
        )

    caption = _strip_em_dashes(caption)
    caption = _strip_llm_preamble(caption)

    return {
        "caption": caption,
        "hashtags": hashtags,
        "category_events": category_events,
    }


# ── LLM health breadcrumb (gap G46) ──────────────────────────────────────
# A `claude -p` default-auth 401 once silently killed EVERY tulsagays CLI LLM
# layer at once: sanity_check, voice_pass, final_deck_review, description
# enrichment all just fell back to rule copy and NOBODY knew the LLM was dead.
# _call_claude_cli records a health breadcrumb on STATE CHANGE (not every call,
# to avoid churn) so `tools/llm_health.py` can turn a total-auth outage into a
# loud, detectable signal instead of a silent degrade. An individual prompt
# failing while auth still works is NOT an outage — only auth-class failures
# across ALL tokens flip the flag.
_LLM_HEALTH_FILE = _os_path_health = None  # resolved lazily to avoid import cost
_LLM_LAST_STATE = None  # None | "up" | "down"
_LLM_AUTH_SIGNATURES = ("401", "403", "authenticate", "authentication",
                        "credit balance", "unauthorized")


def _llm_health_path():
    import os as _o
    return _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))),
                        "data", "llm_health.json")


def _record_llm_health(ok: bool, detail: str = ""):
    """Persist LLM auth health on state change only. ok=True clears the alarm."""
    global _LLM_LAST_STATE
    state = "up" if ok else "down"
    if state == _LLM_LAST_STATE:
        return
    _LLM_LAST_STATE = state
    try:
        import json as _j, time as _t, os as _o
        p = _llm_health_path()
        _o.makedirs(_o.path.dirname(p), exist_ok=True)
        payload = {"auth_ok": ok, "ts": _t.strftime("%Y-%m-%d %H:%M:%S"),
                   "epoch": int(_t.time()), "detail": detail[:200]}
        with open(p, "w", encoding="utf-8") as f:
            _j.dump(payload, f, indent=1)
        if not ok:
            # loud stderr marker so a scheduled run's log flags it too
            print(f"[generator][LLM-DOWN] claude -p auth failing across all tokens: "
                  f"{detail[:120]} — LLM layers are degrading to rule-based copy",
                  file=__import__("sys").stderr)
    except Exception:
        pass


def _call_claude_cli(user_prompt: str, system_prompt: str = "", model: str = "sonnet",
                     timeout: int = 300) -> str:
    """Shell out to the local `claude -p` CLI for description generation.
    Uses the Claude Code subscription instead of the API (avoids double-billing).
    Returns empty string on failure so caller can fall back to rules.

    The CLI takes a single prompt via stdin. Pass system + user merged with
    a clear separator. Avoid leading bare "You are a ..." which trips the
    CLI's context-length pre-check.
    """
    import subprocess, shutil
    claude_bin = shutil.which("claude") or r"C:\Users\willi\.local\bin\claude"
    if not claude_bin:
        return ""
    if system_prompt:
        merged = f"<context>{system_prompt}</context>\n\n<request>\n{user_prompt}\n</request>"
    else:
        merged = user_prompt
    # Run from a neutral cwd. From inside the tulsagays/ project, `claude -p`
    # auto-loads project files and exceeds context. Use the user's home so it
    # starts with a minimal session.
    import os as _os
    neutral_cwd = _os.path.expanduser("~")

    # Sanity: if the CLI echoed a fixed-string error, treat as failure so the
    # caller falls back to rule-based copy. The CLI prints connection/API
    # failures to stdout (exit 0), so without this guard the error text gets
    # saved AS the caption. W26 (2026-06-23) shipped the literal string
    # "API Error: Unable to connect to API (FailedToOpenSocket)" as a caption
    # because the old guard only matched "error:", not "api error".
    _err_prefixes = (
        "prompt is too long", "error:", "rate limit", "api error",
        "execution error", "credit balance", "unable to connect",
        "overloaded", "internal server error", "failed to authenticate",
        "invalid authentication", "401", "403",
    )

    # Dual-token failover (same mechanism as instagram_orgs._claude_cli_complete
    # and the runner's claude-tier tasks): default auth first, then each stored
    # fleet token. Nested-session env vars (CLAUDE_CODE_*) make `claude -p`
    # 401 when invoked from inside a live Claude Code session — strip them.
    attempts = [None]
    try:
        _vals = {}
        with open(_os.path.join(_os.path.expanduser("~"), ".credentials",
                                "claude_tokens.env"), encoding="utf-8") as _tf:
            for _line in _tf:
                if "=" in _line and not _line.strip().startswith("#"):
                    _k, _v = _line.split("=", 1)
                    _vals[_k.strip()] = _v.strip()
        for _key in ("CLAUDE_TOKEN_PRIMARY", "CLAUDE_TOKEN_SECONDARY"):
            if _vals.get(_key):
                attempts.append(_vals[_key])
    except Exception:
        pass

    _last_fail = ""
    for tok in attempts:
        env = _os.environ.copy()
        for k in list(env):
            if k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "CLAUDE_EFFORT",
                                                     "CLAUDE_CHROME_PERMISSION_MODE"):
                env.pop(k, None)
        if tok:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
        try:
            # timeout default raised 120 -> 300 (2026-06-12): W23/W24 enrichment
            # batches timed out at 120s, fell back to rule-based templates, and
            # shipped 165 pool-filler descriptions to the website.
            r = subprocess.run(
                [claude_bin, "-p", "--model", model],
                input=merged,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                cwd=neutral_cwd,
                env=env,
            )
            out = (r.stdout or "").strip()
            if out and not out.lower().startswith(_err_prefixes):
                _record_llm_health(True)
                return out
            _last_fail = (out or r.stderr or "empty")
            print(f"[generator] claude CLI ({'stored-token' if tok else 'default-auth'}) "
                  f"failed: {_last_fail[:100]} — trying next auth")
        except Exception as e:
            _last_fail = str(e)
            print(f"[generator] claude CLI fallback failed: {e}")
    # Every auth path exhausted. If the last failure was auth-class (not a
    # one-off timeout / prompt-too-long), flip the loud health flag so the
    # silent LLM outage becomes detectable (gap G46).
    if any(sig in _last_fail.lower() for sig in _LLM_AUTH_SIGNATURES):
        _record_llm_health(False, _last_fail)
    return ""


def _call_claude(user_prompt: str) -> str:
    """Send the prompt to Claude and return the caption text.
    Prefers the local CLI (subscription credits) over the API (billable).
    Falls back to API only if CLI fails AND a key is configured.
    """
    cli_out = _call_claude_cli(user_prompt, _SYSTEM_PROMPT)
    if cli_out:
        return cli_out
    if not config.ANTHROPIC_API_KEY:
        return ""  # caller will use rule-based fallback
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text.strip()


_YBR_VENUE_SIGS = ("yellow brick", "ybr", "2630 e 15")
_YBR_INCLUSIVE_TAG = (
    "Yellow Brick Road is Tulsa's only lesbian bar and one of the last in the US, "
    "and everyone is welcome. The gay-guy crowd tends to skip it, but it's an "
    "inclusive home for the whole community."
)
# Signals that the description already conveys YBR's everyone-welcome nature, so
# we don't double up on the inclusive framing.
_YBR_INCLUSIVE_SIGNALS = ("everyone", "everybody", "inclusive", "whole community",
                          "all welcome", "welcome", "lesbian bar")


def _is_ybr_event(e: dict) -> bool:
    venue = (e.get("venue") or "").lower()
    name = (e.get("name") or "").lower()
    return any(sig in venue or sig in name for sig in _YBR_VENUE_SIGS)


def _apply_ybr_inclusive_note(events: list[dict]) -> list[dict]:
    """William 2026-06-21 + VENUE_FACTS.md: any YBR event must be framed as a
    welcoming spot for the WHOLE community (gay guys included), not just women.
    Deterministic post-pass so it applies no matter which enrichment path ran and
    never depends on the LLM remembering. Idempotent: skips events whose copy
    already conveys inclusivity."""
    for e in events or []:
        if not _is_ybr_event(e):
            continue
        for field in ("description", "website_description"):
            txt = (e.get(field) or "").strip()
            if not txt:
                continue
            if any(sig in txt.lower() for sig in _YBR_INCLUSIVE_SIGNALS):
                continue  # already inclusive — don't pile on
            e[field] = f"{txt} {_YBR_INCLUSIVE_TAG}".strip()
    return events


# ── Canonical voice prompt ──────────────────────────────────────────────────
# The one system prompt every LLM enrichment path uses, so the voice never drifts
# between the bulk enricher and the featured-only voice pass (tools/voice_pass.py).
VOICE_SYS_PROMPT = (
    "You write event descriptions for TulsaGays.com, an LGBTQ+ community events guide in "
    "Tulsa. Voice: RuPaul meets Alicia Edwards (Abbott Elementary) with a warm Dolly Parton "
    "heart. Sassy, fun, encouraging, a little theatrical, genuinely kind. You are talking to "
    "a gay introvert and your whole job is to lovingly get him off the couch and out the "
    "door, then make sure he has the best possible time once he's there. "
    "CRAFT (every time): open with a SPECIFIC sensory image of THIS event (a look, a "
    "sound, a moment), sprinkle drag-mother terms of endearment (honey, sugar, darling, "
    "baby), land one witty line, and close with a concrete BEST-TIME tip (when to arrive, "
    "where to stand, what to bring). Hand-written for that one event, never a template. "
    "NEVER waste a line on empty cheerleading: a bare 'make sure to go', 'you won't regret "
    "it', 'put it on your calendar', or 'these are your people' is FORBIDDEN. Every sentence "
    "must carry a specific, useful, or funny detail. "
    "HARD RULES: Never discourage, hedge, mock, or put down an event in ANY way — every "
    "event gets a genuine, warm reason to go. Never use em dashes. Never sound like AI or "
    "corporate copy. Banned phrases: 'vibrant community', 'safe space', 'don't miss out', "
    "'something for everyone', 'whether you're', 'make sure to go', 'actually go', "
    "'you will thank yourself', 'zero excuses'. Write like a real, funny, loving friend "
    "who happens to talk like Dolly hosting Drag Race. "
    "ANONYMITY: this account is anonymous. NEVER reveal or hint at who runs it. No real "
    "names, no 'I run this', no 'dm me', no personal signatures. Speak as the community, "
    "always 'you' (the reader), never 'I' (the operator)."
)


def _voice_batch_prompt(batch: list[dict]) -> str:
    """Build the S/L enrichment prompt for a small batch of events."""
    lines = []
    for j, e in enumerate(batch):
        name = e.get("name", "Unknown")
        venue = (e.get("venue") or "").split(",")[0].strip()
        date = e.get("date", "")
        time = e.get("time", "")
        existing = (e.get("description") or "").strip()
        line = f"{j+1}. {name}"
        if venue:
            line += f" @ {venue}"
        if date or time:
            line += f" ({date} {time})".strip()
        if existing and len(existing) > 20 and not _is_scraper_artifact(existing):
            line += f" -- hint: {existing[:120]}"
        lines.append(line)
    return (
        "For EACH event below, write TWO things:\n"
        "  (S) a SHORT slide pitch, 1 punchy sentence under 150 characters, that makes a "
        "shy gay introvert WANT to go. End on a high note (no trailing ellipsis).\n"
        "  (L) a LONG website description, 3 to 5 sentences: what the event IS, why it's "
        "worth leaving the house for, and ALWAYS end with a concrete 'how to have the best "
        "time' tip tailored to THIS event.\n\n"
        "Use any hint to be specific to the real event. Never invent a price or lineup.\n\n"
        "Events:\n" + "\n".join(lines) +
        "\n\nReply with ONLY this exact format, two lines per event, nothing else:\n"
        "1S. [short pitch]\n1L. [long description]\n2S. [short pitch]\n2L. [long description]"
    )


def _featured_rank(e: dict) -> int:
    """Lower sorts first. Spend the LLM budget on the copy people actually see:
    EOTW and explicitly queer, one-off events before the long tail."""
    name = (e.get("name") or "").lower()
    if e.get("is_eotw") or e.get("eotw"):
        return 0
    score = 5
    if e.get("lgbtq_relevant"):
        score -= 2
    if any(k in name for k in ("drag", "queer", "pride", "cabaret", "chorale", "happy hour")):
        score -= 2
    if (e.get("source") or "").lower() == "recurring":
        score += 2
    try:
        score -= int(e.get("priority") or 0)
    except (TypeError, ValueError):
        pass
    return max(0, score)


def voice_enrich(events: list[dict], budget_s: int = 240, batch: int = 6) -> dict:
    """LLM-rewrite the SHORT + LONG copy for the given (small) set of shown events
    in the canonical voice, featured/EOTW first, within a wall-clock budget. Any
    event the LLM can't reach falls back to rule-based copy so nothing ships empty.
    Marks each successfully processed event `voice_passed=True` so a later render
    with TULSAGAYS_SKIP_ENRICH keeps the copy. Returns a stats dict.

    This is the automatic version of the manual 'Step 2.1' voice pass: it runs on
    ONLY the featured/EOTW events (~20), so it fits the budget instead of stalling
    on all ~200 like the full enricher did.
    """
    import time as _time
    stats = {"total": len(events), "llm": 0, "rule": 0, "elapsed": 0.0}
    if not events:
        return stats
    order = sorted(range(len(events)), key=lambda i: _featured_rank(events[i]))
    start = _time.monotonic()
    use_cli = True
    i = 0
    while i < len(order):
        idxs = order[i:i + batch]
        i += batch
        batch_events = [events[k] for k in idxs]
        over_budget = (_time.monotonic() - start) > budget_s
        response = ""
        if use_cli and not over_budget:
            try:
                response = _call_claude_cli(_voice_batch_prompt(batch_events),
                                            VOICE_SYS_PROMPT, model="sonnet", timeout=300)
                if not response:
                    response = _call_claude_cli(_voice_batch_prompt(batch_events),
                                                VOICE_SYS_PROMPT, model="sonnet", timeout=300)
            except Exception as e:
                print(f"[voice_enrich] CLI batch failed: {e}")
                response = ""
        elif over_budget:
            print(f"[voice_enrich] budget {budget_s}s spent — rule-based for the rest")
            use_cli = False

        parsed = {}
        for line in (response or "").split("\n"):
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            try:
                dot = line.index(".")
                tag = line[:dot].strip()
                kind = tag[-1].upper() if tag and tag[-1].isalpha() else "S"
                num = int(tag.rstrip("SLsl")) - 1
                desc = line[dot + 1:].strip()
                if 0 <= num < len(batch_events) and desc:
                    parsed.setdefault(num, {})[kind] = desc
            except (ValueError, IndexError):
                continue

        for local, k in enumerate(idxs):
            got = parsed.get(local, {})
            # A refusal is never valid copy: drop it so the rule-based fallback runs.
            if _is_refusal(got.get("S")) or _is_refusal(got.get("L")):
                got = {}
            if got.get("S"):
                # Strip em dashes at the SOURCE so every downstream consumer
                # (slides, newsletter, website, feeds) inherits clean copy.
                events[k]["description"] = _strip_em_dashes(got["S"])
                if got.get("L"):
                    events[k]["website_description"] = _strip_em_dashes(got["L"])
                events[k]["voice_passed"] = True
                events[k]["voice_source"] = "llm"
                stats["llm"] += 1
            else:
                # Fallback: keep the deck shippable in the same voice.
                events[k]["description"] = _rule_based_enrich(events[k])
                events[k]["website_description"] = _rule_based_website_description(
                    events[k], events[k]["description"])
                events[k]["voice_passed"] = True  # don't let a later render re-template it
                events[k]["voice_source"] = "rule"
                stats["rule"] += 1
    stats["elapsed"] = round(_time.monotonic() - start, 1)
    return stats


def enrich_event_descriptions(events: list[dict]) -> list[dict]:
    """Public entrypoint: enrich, then guarantee YBR events carry the inclusive
    'everyone's welcome' framing on every return path."""
    return _apply_ybr_inclusive_note(_enrich_event_descriptions_impl(events))


def _enrich_event_descriptions_impl(events: list[dict]) -> list[dict]:
    """Use Claude to generate event-specific descriptions for every event.

    Processes all events in batches of 20. Only enriches events that are
    missing a description or have scraper-artifact text. Preserves good
    existing descriptions. Falls back to rule-based if API is unavailable.
    """
    if not events:
        return events

    import os, time as _time
    # RELIABILITY (2026-06-15): the nested `claude -p` enrichment hangs/stacks
    # (~300s per batch x ~21 batches => >1 hr) and silently blew past the Monday
    # post window. Two guards make weekly automation safe:
    #   1) TULSAGAYS_RULE_ENRICH=1 forces the fast, deterministic rule-based path
    #      (scheduled runs set this; the orchestrating agent rewrites only the
    #      featured/EOTW blurbs in-voice afterward, in-context, no nested CLI).
    #   2) TULSAGAYS_ENRICH_BUDGET_S caps total CLI wall-clock; once spent, every
    #      remaining batch uses rule-based so generation can never stall the post.
    # See feedback_headless_background_yield_trap + feedback_nested_claude_cli_prompt_size.
    if os.environ.get("TULSAGAYS_RULE_ENRICH", "").strip().lower() in ("1", "true", "yes"):
        print("[generator] TULSAGAYS_RULE_ENRICH set — fast rule-based enrichment (no nested claude CLI)")
        return _rule_based_enrich_all(events)
    _budget_s = int(os.environ.get("TULSAGAYS_ENRICH_BUDGET_S", "240"))
    _enrich_start = _time.monotonic()

    # Try claude CLI first (subscription, no double-billing). Use API only if CLI
    # unavailable AND a key is configured. Rule-based is the final fallback.
    import shutil
    use_cli = bool(shutil.which("claude")) or Path(r"C:\Users\willi\.local\bin\claude").exists()
    client = None
    if not use_cli and not config.ANTHROPIC_API_KEY:
        print("[generator] No claude CLI and no API key — using rule-based enrichment")
        return _rule_based_enrich_all(events)
    if use_cli:
        print("[generator] Enriching via claude CLI (subscription credits)")
    else:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    # Smaller batches = a partial CLI failure strands fewer events on rule-based
    # fallback (Rung 2 reliability). Was 20.
    BATCH = 10

    # Only enrich events that need it
    # Enrich when the long website copy is missing, the short copy is empty, or
    # the short copy is raw scraper junk. (A short-but-clean pitch alongside an
    # existing website_description is left alone — both fields are already good.)
    needs_enrichment = [
        (i, e) for i, e in enumerate(events)
        if not (e.get("website_description") or "").strip()
        or not (e.get("description") or "").strip()
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
            "For EACH event below, write TWO things:\n"
            "  (S) a SHORT slide pitch — 1 punchy sentence, under 150 characters, that makes a "
            "shy gay introvert WANT to go. End on a high note (no trailing ellipsis, no cut-off).\n"
            "  (L) a LONG website description — 3 to 5 sentences, full detail. Say what the event "
            "IS, why it's worth leaving the house for, and ALWAYS end with a concrete 'how to have "
            "the best time' tip tailored to THIS event type. Examples of tips: comedy show -> grab "
            "an edible beforehand; networking/mixer -> get there early and make yourself talk to "
            "just one or two people; concert -> show up for the opener and post up near the bar; "
            "drag show -> bring singles to tip the queens; gallery/art crawl -> start at the far "
            "end and work back so you beat the crowd.\n\n"
            "Use any hint provided to be specific to the real event. Never invent a price or a "
            "lineup you weren't given.\n\n"
            "Events:\n" + "\n".join(event_lines) +
            "\n\nReply with ONLY this exact format, two lines per event, nothing else:\n"
            "1S. [short pitch]\n1L. [long description]\n2S. [short pitch]\n2L. [long description]"
        )

        # RELIABILITY: once the flaky nested CLI has burned its wall-clock budget,
        # stop calling it — every remaining batch gets fast rule-based copy so slide
        # generation can never stall past the Monday post window.
        if use_cli and (_time.monotonic() - _enrich_start) > _budget_s:
            print(f"[generator] CLI enrichment budget ({_budget_s}s) exceeded — rule-based for remaining events")
            use_cli = False
        if not use_cli and client is None:
            for _, ev in batch:
                if not (ev.get("description") or "").strip() or _is_scraper_artifact(ev.get("description") or ""):
                    ev["description"] = _rule_based_enrich(ev)
            continue

        try:
            sys_prompt = VOICE_SYS_PROMPT
            if use_cli:
                # Route through `claude -p` subprocess — subscription credits.
                # Retry once on empty (nested CLI is flaky under concurrency).
                response = _call_claude_cli(prompt, sys_prompt, model="sonnet")
                if not response:
                    print("[generator] CLI empty, retrying batch once...")
                    response = _call_claude_cli(prompt, sys_prompt, model="sonnet")
                if not response:
                    raise RuntimeError("claude CLI returned empty output (after retry)")
            else:
                message = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=1200,
                    system=sys_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                response = message.content[0].text.strip()
            for line in response.split("\n"):
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue
                try:
                    dot_idx = line.index(".")
                    tag = line[:dot_idx].strip()          # e.g. "1S" or "1L"
                    kind = tag[-1].upper() if tag and tag[-1].isalpha() else "S"
                    num = int(tag.rstrip("SLsl")) - 1
                    desc = _strip_em_dashes(line[dot_idx + 1:].strip())
                    if 0 <= num < len(batch) and desc and not _is_refusal(desc):
                        orig_idx = batch[num][0]
                        if kind == "L":
                            events[orig_idx]["website_description"] = desc
                        else:
                            events[orig_idx]["description"] = desc
                except (ValueError, IndexError):
                    continue
            print(f"[generator] Batch {batch_start//BATCH + 1} done ({len(batch)} events)")
        except Exception as e:
            print(f"[generator] Batch enrichment failed: {e}")
            # Fallback chain: if the CLI failed but an API key is configured,
            # try the SDK before dropping to rule-based copy (keeps the voice).
            response = None
            if config.ANTHROPIC_API_KEY:
                try:
                    print("[generator] Retrying batch via Anthropic API (SITES key)")
                    _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
                    message = _client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=2000,
                        system=sys_prompt,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    response = message.content[0].text.strip()
                except Exception as e2:
                    print(f"[generator] API fallback also failed: {e2}")
                    response = None
            if response:
                for line in response.split("\n"):
                    line = line.strip()
                    if not line or not line[0].isdigit():
                        continue
                    try:
                        dot_idx = line.index(".")
                        tag = line[:dot_idx].strip()
                        kind = tag[-1].upper() if tag and tag[-1].isalpha() else "S"
                        num = int(tag.rstrip("SLsl")) - 1
                        desc = _strip_em_dashes(line[dot_idx + 1:].strip())
                        if 0 <= num < len(batch) and desc and not _is_refusal(desc):
                            orig_idx = batch[num][0]
                            if kind == "L":
                                events[orig_idx]["website_description"] = desc
                            else:
                                events[orig_idx]["description"] = desc
                    except (ValueError, IndexError):
                        continue
            else:
                print("[generator] Applying rule-based copy to this batch")
                for _, ev in batch:
                    if not (ev.get("description") or "").strip():
                        ev["description"] = _rule_based_enrich(ev)

    # FINAL GUARANTEE: no two events share a description. Rule-based copy gives
    # same-category events identical text (the 2026-06-08 repeat embarrassment);
    # this pass rewrites any duplicate uniquely + on-voice, regardless of which
    # enrichment path ran. Defensive: never let it break generation.
    try:
        from tools.dedupe_descriptions import dedupe as _dedupe
        _fixed = _dedupe(events)
        if _fixed.get("short") or _fixed.get("long"):
            print(f"[generator] de-duped repeated descriptions: {_fixed}")
    except Exception as _e:
        print(f"[generator] dedupe pass skipped: {_e}")

    return events


def _pick(seed: str, options: list[str]) -> str:
    """Deterministically pick one variant by a stable hash of the event name, so
    same-category events don't all read identically but a given event is stable run
    to run. (Math.random would break reproducibility; a name hash gives free variety.)"""
    if not options:
        return ""
    import hashlib
    h = int(hashlib.md5((seed or "x").encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


# RuPaul x Dolly Parton x Alicia Edwards voice bank. Each line: a specific sensory hook,
# real sass + Southern warmth, and a "best-time" tip baked in. NO generic "go!" filler,
# no "your people", no "put it on your calendar". Variants keep the feed from repeating.
_VOICE_BANK = {
    "drag": [
        "Honey, these queens did not beat that face for you to lurk in the back. "
        "Get to the rail, bring your singles, and tip like you mean it. Come early for the "
        "looks, stay late for when they stop being polite.",
        "Darling, this is the closest thing Tulsa has to church. Front row, fresh dollar "
        "bills, and a gasp ready in your throat. The opening number warms you up, but the "
        "late set is where the wigs and the inhibitions both come off.",
        "Sequins, spotlights, and a queen who will absolutely clock your outfit, sugar. Grab "
        "an aisle seat so you catch the death drops up close, and keep those ones folded and "
        "ready. The energy climbs all night, so pace your gasps.",
        "Baby, the lip sync is a contact sport and you are in the splash zone. Show up while "
        "the house lights are still up to snag a spot near the stage, then let a six-foot "
        "goddess in heels remind you why you left the house.",
        "This is where Tulsa keeps its glamour, honey. Big wigs, bigger personalities, and a "
        "crowd that hollers for every reveal. Come a touch early, tip early and often, and do "
        "not sit somewhere you would mind getting pulled onstage.",
        "Rhinestones catching the light, a host with a mouth on her, and numbers you will be "
        "quoting all week, darling. Post up near the runway, keep your drink in one hand and "
        "your tips in the other, and let the queens do the rest.",
    ],
    "brunch": [
        "Put on the outfit that makes you feel a little expensive and order the mimosa like "
        "it owes you money. This crowd treats brunch as a competitive sport of compliments, "
        "so grab a seat where you can talk to the table next to you. Arrive hungry and nosy.",
        "Eggs are optional, the gossip is mandatory, baby. Dress like you tried, tip your "
        "server like a Parton, and let the bottomless pours do the introductions. Roll in "
        "right at the start before the good tables go.",
        "Daytime drinking with a side of fabulous, sugar. The patio catches the morning sun "
        "and the whole room is dressed to be seen. Get there when the doors open so you land "
        "a table in the thick of it, not exiled to the corner.",
        "Carbs, cocktails, and a crowd that treats a Sunday like a runway, honey. Come with an "
        "appetite and a compliment ready for a stranger. Early birds get the good booth and "
        "the first round before the line wraps the block.",
        "The kind of brunch where the tea is hot and so is the coffee, darling. Sit near the "
        "action, order something that photographs well, and let the mimosas turn strangers "
        "into the table you never wanted to leave.",
    ],
    "dance": [
        "Wear something you can sweat through, sugar, because a chair is not in your future. "
        "Get on that floor in the first twenty minutes, before your nerves start negotiating, "
        "and do not you dare leave before the DJ's last song.",
        "This is your sign to move like nobody's filming, honey. The floor fills up by "
        "eleven, so get loose early and let the bass do your overthinking for you.",
        "Lights low, bass high, and a room full of people who came to lose it, darling. Stake "
        "out a spot near the speakers, hydrate like it is a personality trait, and stay for "
        "the set the DJ saves for the real ones.",
        "Baby, your hips have been waiting all week for this. Get there before the crowd peaks "
        "so you can actually find your groove, then dance until your feet file a complaint.",
        "A proper queer dance floor is cheaper than therapy and twice as fun, sugar. Show up "
        "an hour in when the room is warm but not packed, find your people by the light rig, "
        "and let the night take the wheel.",
    ],
    "bar": [
        "Pull up to the bar, order something with a little sparkle, and say hi to whoever's "
        "beside you like y'all go way back. Tulsa's queer nightlife runs on exactly that "
        "kind of nerve. Earlier is for real conversation, later is for delicious chaos.",
        "Belly up, tip your bartender like a tithe, and let the room do its thing, darling. "
        "Slow at first, electric by midnight. Go before you talk yourself into staying in.",
        "The good kind of dive where everybody eventually knows your drink, honey. Come early "
        "enough to actually hear the person next to you, grab a stool with a view of the door, "
        "and let the regulars fold you in.",
        "Neon, cheap-enough drinks, and a jukebox with excellent taste, sugar. Post up at the "
        "bar, buy a stranger's next round, and watch a quiet Tuesday turn into a story. "
        "Earlier for talking, later for trouble.",
        "This is where Tulsa's queer crowd unwinds and it shows, baby. Roll in before the rush "
        "for a real seat, tip well, and stay long enough to catch the moment the whole bar "
        "starts singing along.",
    ],
    "karaoke": [
        "Pick something gloriously embarrassing and commit to the bit, baby. Nobody in this "
        "room is judging, and the brave soul who signs up first always has the best night. "
        "Get your name on the list early so you go before the catalog fills up.",
        "The mic does not care if you can sing, honey, it cares if you mean it. Slide your "
        "slip in early, cheer loud for every nervous soul before you, and pick the song you "
        "belt in the car with the windows down.",
        "Somewhere between a talent show and a group hug, sugar. Sign up the second you walk "
        "in, order the drink that unlocks your range, and remember the crowd roots hardest "
        "for whoever commits the most.",
        "Darling, this is your Grammy moment and the academy is three drinks deep and adoring. "
        "Get your name down early, warm up in the bathroom mirror, and leave nothing on that "
        "little stage.",
    ],
    "trivia": [
        "Round up some strangers, name your team something that'll make the host blush, and "
        "play like there's rent on the line, honey. Show up fifteen minutes early to claim a "
        "good table and a fighting chance.",
        "You are smarter than you think and pettier than you admit, and both help here, sugar. "
        "Grab a table near the host so you hear every question, and bring the friend who "
        "somehow knows all the sports answers.",
        "Low stakes, high drama, free to lose your dignity, darling. Get there early to lock "
        "down a booth, order a round for the table, and let the tie-breaker bring out a side "
        "of you the group has never seen.",
        "The one weeknight where being a know-it-all pays off, baby. Show up before the first "
        "round to settle in, name the team something unrepeatable, and play like the gift card "
        "is a mortgage payment.",
    ],
    "comedy": [
        "Sit close enough to be in danger, laugh from your belly, and chat up the folks beside "
        "you at the break. Live comedy in a small room hits different, sugar. Get there early "
        "for the seats the comics actually look at.",
        "Grab a drink, sit a few rows back if you scare easy, and let a stranger with a mic "
        "ruin your composure, honey. The early crowd gets the tight seats and the best crowd "
        "work, so do not stroll in late.",
        "Nothing bonds a room like laughing at the same thing at the same time, darling. Come "
        "a little early, order before the show so you are not that clinking glass, and sit "
        "close enough to feel the punchlines land.",
        "The kind of night where your cheeks hurt in the good way, baby. Show up early for a "
        "seat with a clear sightline, tip your bartender, and be ready to be lovingly roasted "
        "if you take the front row.",
    ],
    "market": [
        "Bring cash and a little more willpower than usual, because the artists here are "
        "talented and you are weak, darling. Talk to the makers, ask about the work, and go "
        "early while the good pieces are still on the table.",
        "Local hands, weird and wonderful wares, and a crowd that browses like it is a sport, "
        "honey. Come early for first pick, chat up the vendor whose booth stops you, and bring "
        "a tote because you will not leave empty-handed.",
        "The good stuff sells fast and the makers love to talk shop, sugar. Get there near "
        "opening, wander the whole row before you commit, and tip your favorite artist with an "
        "actual sale, not just a compliment.",
        "A morning of one-of-a-kind finds and zero big-box energy, baby. Bring cash, bring a "
        "friend with opinions, and get there early while the tables are still full and the "
        "coffee line is short.",
    ],
    "music": [
        "Get there before the first note, find your spot, and let yourself feel something for "
        "once, honey. Tulsa's live music is criminally underrated. Early gets you close; close "
        "gets you a story.",
        "Show up for the opener nobody warned you would be that good, sugar. Post up near the "
        "bar for an easy refill and a clear view, and stay for the encore the die-hards are "
        "already screaming for.",
        "The room goes electric the second the band plugs in, darling. Come early enough to "
        "grab a spot with sightlines, tip the opener at the merch table, and let one great set "
        "reset your whole week.",
        "Live and loud and better in person, baby. Get there before doors close on the good "
        "spots, stand where the sound hits right, and let yourself be the person who sings "
        "every word without apology.",
    ],
    "default": [
        "This one's got your name on it, sugar. Walk in like you own a little piece of the "
        "place, because tonight you do. Show up near the start so you catch the good part "
        "before the crowd does.",
        "Consider this your formal invitation to leave the couch, darling. Roll in early, say "
        "yes to the first thing that sounds fun, and let the night surprise you.",
        "The kind of low-pressure good time that is easy to skip and easier to love, honey. "
        "Get there near the start, find one friendly face, and let the rest of the night build "
        "itself from there.",
        "Come as you are and a little earlier than you planned, baby. The best moments happen "
        "before the room fills up, so grab a good spot, order something you like, and settle "
        "in for a genuinely nice time.",
        "Small effort, real payoff, sugar. Show up near the top, park yourself somewhere you "
        "can people-watch and be watched, and let leaving the house feel like the easy win it "
        "is.",
    ],
}


def _rule_based_enrich(event: dict) -> str:
    """Generate a sassy, action-oriented pitch that makes people want to go."""
    name = (event.get("name") or "").lower()
    venue = _usable_venue(event.get("venue"))
    time  = (event.get("time") or "").strip()
    src   = (event.get("source") or "").lower()
    existing = (event.get("description") or "").strip()

    _scraper_artifacts = [
        "tulsa events lists", "ticket options may be available",
        "verified providers", "events.tulsa.okstate.edu",
        "did you know that **", "this event is sold out this is not an official",
    ]
    # Strip OKEQ-style metadata prefix. Two patterns to handle:
    #   "May 28, 2026 | 6:00 pm - 8:00 pm Dennis R. Neill Equality Center, 621 E 4th St, Tulsa, OK 74120, USA <real desc>"
    #   "May 29, 2026 | 6:00 pm - 8:00 pm <real desc starts with real description>"
    import re as _re
    if existing:
        # Step 1: strip leading "MMM DD, YYYY | TIME pm" header
        _date_pat = _re.compile(
            r'^[A-Za-z]+ \d{1,2}, \d{4}\s*\|\s*\d{1,2}:\d{2}\s*[ap]m'
            r'(?:\s*-\s*\d{1,2}:\d{2}\s*[ap]m)?\s+',
            _re.IGNORECASE,
        )
        cleaned = _date_pat.sub('', existing, count=1)
        # Step 2: if leading text looks like an address (ends in USA), strip it
        _addr_usa = _re.compile(r'^[^.!?]*?,?\s*USA\s+', _re.IGNORECASE)
        cleaned2 = _addr_usa.sub('', cleaned, count=1)
        if cleaned2 != cleaned:
            cleaned = cleaned2
        cleaned = cleaned.strip()
        if cleaned and cleaned != existing:
            existing = cleaned
            event['description'] = cleaned
    # OKEQ scraper descriptions are institutional copy-paste — force a William-voice
    # rewrite if the event matches one of the rules below. Other sources keep their
    # existing description if it's long enough.
    _FORCE_REWRITE_SRCS = {"okeq", "okeq_calendar"}
    _force_rewrite = src in _FORCE_REWRITE_SRCS
    if (existing and len(existing) > 80
            and not any(a in existing.lower() for a in _scraper_artifacts)
            and not _is_scraper_artifact(existing)   # also rejects raw HTML tags/entities
            and not _force_rewrite):
        return existing  # already has a good description

    at_venue = f" at {venue}" if venue else ""
    at_time  = f" at {time}" if time else ""

    if any(k in name for k in ["dragnificent", "drag show", "drag night", "drag brunch", "drag queen", "drag king", "drag performer"]):
        return _pick(name, _VOICE_BANK["drag"])

    # Anchor cultural event (Council Oak Men's Chorale slot) — config-driven
    _anchor = getattr(config, "ANCHOR_CULTURAL_EVENT", None) or {}
    _anchor_kws = [k.lower() for k in _anchor.get("name_keywords", [])]
    if any(k in name for k in ["cabaret", "chorus", "chorale"]) or any(kw in name for kw in _anchor_kws):
        return (f"Dress up. Get there early. Sit close. "
                "This is live performance from a real ensemble that pours everything into it, and the energy in that room is unlike anything else in Tulsa.")

    # Signature event (HHHH slot) — config-driven
    _sig = getattr(config, "SIGNATURE_EVENT", None) or {}
    _sig_kws = [k.lower() for k in _sig.get("name_keywords", [])]
    if "happy hour" in name or any(kw in name for kw in _sig_kws):
        return ("Do not go and stand in the corner on your phone. Go up to someone with a great outfit, compliment them, and start a conversation. "
                "You will leave with at least three new friends and a story worth telling.")

    if "brunch" in name or "boozy brunch" in name:
        return _pick(name, _VOICE_BANK["brunch"])

    if any(k in name for k in ["craft", "crochet", "knit", "stitch", "maker", "queer craft"]):
        return (f"You do not need to know what you're doing. Just show up{at_venue} with your hands and your personality. "
                "LGBTQIA+ people creating things together is magic, and you'll leave with something to show for it.")

    if any(k in name for k in ["karaoke"]):
        return _pick(name, _VOICE_BANK["karaoke"])

    if any(k in name for k in ["trivia", "quiz"]):
        return _pick(name, _VOICE_BANK["trivia"])

    if any(k in name for k in ["comedy", "comedian", "loony bin", "standup", "stand-up"]) or "comedy" in venue.lower():
        return _pick(name, _VOICE_BANK["comedy"])

    if any(k in name for k in ["rave", "broadway rave", "dance", "dj ", "w/dj", "latin night", "dance party"]):
        return _pick(name, _VOICE_BANK["dance"])

    # True gay bar match — config-driven (city's gay bar venue list)
    _true_bars = getattr(config, "TRUE_GAY_BAR_VENUES", set())
    _venue_lower = (venue or "").lower()
    if any(b in _venue_lower for b in _true_bars) or any(b in name for b in _true_bars) or src in ("bars", "nightlife"):
        return _pick(name, _VOICE_BANK["bar"])

    if any(k in name for k in ["market", "art market", "art show", "art fair", "gallery"]):
        return _pick(name, _VOICE_BANK["market"])

    if any(k in name for k in ["concert", "live music", "music night", "performance"]):
        return _pick(name, _VOICE_BANK["music"])

    if any(k in name for k in ["support group", "healing", "chronic", "wellness"]):
        return (f"You don't have to have it together to walk in. That's literally the whole point. "
                "Show up, listen, share if you're ready, and remember you are not the only one going through it.")

    # Affirming faith venues — generic prose, plus city-specific affirming venue keywords from config
    _affirming_kws = [k.lower() for k in getattr(config, "AFFIRMING_VENUE_KEYWORDS_CITY", [])]
    if (any(k in name for k in ["unitarian", "church", "spiritual", "meditation"])
            or any(kw in name for kw in _affirming_kws)):
        return (f"One of the most affirming spaces in Tulsa for LGBTQIA+ people of faith and skeptics alike. "
                "Walk in exactly as you are. You will feel it immediately.")

    if "bowling" in name:
        return ("LGBTQIA+ bowling leagues are pure community gold. Show up even if you haven't bowled in years. "
                "Nobody's judging your form. Everyone's glad you made it out.")

    if any(k in name for k in ["canasta", "card", "game night", "board game", "dungeons", "d&d", "dragons"]):
        return (f"Step away from the screen and use your brain for something that actually requires other people. "
                "Sit down next to a stranger, learn the rules, and talk trash. This is genuinely a great time.")

    # Mother Road Market — keep descriptions varied, not the same "summer-long festival" every day
    if "$5 wednesday" in name and "mother road" in (venue.lower() + name):
        return ("Five bucks for a midweek reset at Mother Road. Vendors, food trucks, live entertainment, "
                "and the kind of crowd that makes you remember Tulsa actually rules. Best five dollars you'll spend this week.")
    if "musical bikes" in name:
        return ("Tulsa's most casual cycling crew rolls through Mother Road for Musical Bikes Monday. "
                "Come on two wheels or just show up to watch. Either way, it's a vibe and a great way to start the week.")
    if "66 days of fun" in name or "66 days" in name:
        return ("Mother Road Market's summer-long festival keeps the patio busy with vendors, food, and Route 66 energy. "
                "Drop in for an hour, leave with a full belly and a story.")

    # Magic City Books — distinct vibe per event
    if "crime time" in name or ("magic city books" in (venue.lower() + name) and "crime" in name):
        return ("Mystery and thriller readers descend on Magic City Books for an evening of dark conversation. "
                "Bring your weirdest book recommendation, leave with three new ones. Indie bookstore energy at its best.")
    if "magic city books" in venue.lower():
        return ("Magic City Books is Tulsa's queer-friendly indie bookstore and they pour everything into their author events. "
                "Show up curious, leave with a signed copy and a new opinion.")

    # Shambhala meditation — varied, not boilerplate affirming
    if "shambhala" in venue.lower() or ("meditation" in name and "shambhala" in (venue.lower() + name)):
        return ("Shambhala is genuinely one of the most welcoming meditation spaces in Tulsa, full stop. "
                "No experience needed, no incense pressure, no weird vibes. Walk in, sit down, and let an hour of quiet do its work.")

    # Memorial Day / holiday runs — short, energetic
    if "memorial day" in name or ("run" in name and ("5k" in name or "1m" in name or "mile" in name)):
        return ("Lace up and get out before the cookouts start. A neighborhood run is the cheapest, fastest way to feel "
                "like you did something with your morning. All paces, all bodies, all welcome.")

    # NEFF Brewing / curated dinner events — specific food event vibe
    if "neff brewing" in venue.lower() or ("dinner" in name and "courses" in name):
        return ("A six-course tasting paired with NEFF's craft brews. Ticketed, intimate, and unlike anything else "
                "happening in Tulsa that night. If you've never done a curated tasting menu, this is the one.")

    # Guthrie Green / outdoor green-space events
    if "guthrie green" in venue.lower() and ("food truck" in name or "food trucks" in name):
        return ("Guthrie Green's Food Truck Wednesdays is the kind of casual midweek hang that doesn't need planning. "
                "Tacos, BBQ, bubble tea — pick a truck, grab a patch of grass, eat outside while you still can.")
    if "guthrie green" in venue.lower():
        return ("Guthrie Green is Tulsa's downtown front yard. Show up, find a spot, talk to whoever sits near you. "
                "Public space done right.")

    # Zoolightful / zoo events
    if "zoolightful" in name or ("zoo" in venue.lower() and "lantern" in name):
        return ("Tulsa Zoo after dark, lit up with hundreds of illuminated animal lanterns. Bring a date, "
                "bring your camera, bring patience for the lines. Worth every minute.")

    # Event-specific OKEQ rules — match BEFORE the generic OKEQ catch-all so
    # MOREcolor / AFFIRMING / Positively Grateful / Broadway Clubhouse / TTRPG
    # don't all share the same boilerplate description.
    if "morecolor" in name:
        return ("Allie Jensen Gallery transforms into one of Tulsa's best art receptions twice a year. "
                "Twenty regional artists, sculpture to felted wool, painting to beaded medallions. "
                "Show up early, talk to the artists, buy a piece if something speaks to you.")
    if "affirming" in name and "spaces" not in name:
        return ("AFFIRM is Cognitive Behavioral Therapy built specifically for LGBTQ+ youth. "
                "Free, weekly, in the Wellness Room at the Equality Center. "
                "If you know a young queer person who's struggling, this is the program.")
    if "positively grateful" in name:
        return ("HIV+ support runs on community, and this group has been holding it down every Friday for years. "
                "Potluck format, wellness check-ins, real friendships. Bring a dish, leave with a few new numbers in your phone.")
    if "broadway clubhouse" in name or "broadway club house" in name:
        return ("Tulsa's monthly queer sing-along in the Lynn Riggs Theater at the Equality Center. "
                "Bill Nelson and Jason Sirios on piano. Show tunes, libations, your people. "
                "Last Sunday of every month. Skip the streaming queue and come sing.")
    if "ttrpg" in name or "tabletop" in name:
        return ("OKEQ's tabletop crew runs the friendliest game night in town. "
                "Show up curious, get folded into a one-shot or a long campaign, walk out with a Discord invite. "
                "Snacks provided. No D&D experience required.")
    # Equality center / anchor LGBTQ+ org — config-driven (signature org source key + venue keyword)
    _sig_org_keys = {"okeq", "equality_center"} | {(_sig.get("source_key") or "").lower()} - {""}
    if src in _sig_org_keys or "equality center" in (venue or "").lower():
        return (f"This space{at_venue} is the heartbeat of Tulsa's LGBTQIA+ community. "
                "Walk in. Say hi to someone. Life genuinely gets better when you show up for your community.")

    return _pick(name, _VOICE_BANK["default"])


def _rule_based_website_description(event: dict, short: str) -> str:
    """Longer site copy in the same voice: the short pitch plus a concrete logistics
    beat (day / time / venue) so the website isn't templated filler. Distinct from the
    short slide line so the two fields never read identically."""
    import datetime as _dt
    venue = _usable_venue((event.get("venue") or "").split(",")[0])
    time = (event.get("time") or "").strip()
    date = (event.get("date") or "").strip()
    weekday = ""
    if date:
        try:
            weekday = _dt.datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        except ValueError:
            weekday = ""
    detail_bits = []
    if weekday:
        detail_bits.append(f"It's a {weekday} thing")
    if time:
        detail_bits.append(f"doors around {time}" if not detail_bits else f"around {time}")
    if venue:
        detail_bits.append(f"over at {venue}")
    detail = ", ".join(detail_bits).strip()
    closer = _pick((event.get("name") or "") + "L", [
        "Put on the look, bring a friend or bring your nerve, and let Tulsa show you a good time.",
        "Dress how it makes you feel, roll in a little early, and thank yourself later, sugar.",
        "Bring your whole personality. That's the only ticket this town really checks.",
    ])
    if detail:
        return f"{short} {detail[0].upper() + detail[1:]}. {closer}"
    return f"{short} {closer}"


_SCRAPER_ARTIFACTS = [
    "tulsa events lists", "ticket options may be available",
    "verified providers", "events.tulsa.okstate.edu",
    "did you know that **", "this event is sold out this is not an official",
]


_METADATA_PREFIX_PAT = re.compile(
    r'^[A-Za-z]+ \d{1,2}, \d{4}\s*\|\s*\d{1,2}:\d{2}\s*[ap]m',
    re.IGNORECASE,
)


def _is_scraper_artifact(desc: str) -> bool:
    d = desc.lower()
    if any(a in d for a in _SCRAPER_ARTIFACTS):
        return True
    # HTML tags / entities leaked from a scraper (e.g. a raw academic abstract
    # "&lt;p&gt;A major constraint...") are never our voice copy — treat as an
    # artifact so they get re-enriched into voice, not shipped raw to the site.
    if any(m in d for m in ("&lt;", "&gt;", "<p>", "<p ", "</p>", "<br", "&nbsp;", "&#")):
        return True
    # OKEQ-style "May 28, 2026 | 6:00 pm" metadata prefix counts as artifact
    if _METADATA_PREFIX_PAT.match(desc.strip()):
        return True
    return False


_FORCE_REWRITE_SOURCES = {"okeq", "okeq_calendar"}


def _rule_based_enrich_all(events: list[dict]) -> list[dict]:
    """Apply rule-based enrichment to all events missing good or sassy descriptions."""
    for ev in events:
        # Never re-template copy the LLM voice pass already wrote (tools/voice_pass.py).
        if ev.get("voice_passed"):
            continue
        existing = (ev.get("description") or "").strip()
        src = (ev.get("source") or "").lower()
        # Always re-enrich OKEQ events — their scraped descriptions are
        # institutional copy-paste that doesn't match the brand voice.
        if (not existing or len(existing) < 60 or _is_scraper_artifact(existing)
                or src in _FORCE_REWRITE_SOURCES):
            ev["description"] = _rule_based_enrich(ev)
        # Long site copy: fill it (in voice) whenever it's missing or is scraper junk,
        # so the website stops shipping templated filler (preflight blocks >40% filler).
        wd = (ev.get("website_description") or "").strip()
        if not wd or _is_scraper_artifact(wd) or src in _FORCE_REWRITE_SOURCES:
            ev["website_description"] = _rule_based_website_description(
                ev, ev.get("description", ""))
    # Guarantee uniqueness: the rule-based templates give same-category events
    # IDENTICAL copy (the 2026-06-08 repeat embarrassment — 21 cards shared one
    # line on the website). Dedupe before returning so every caller (website via
    # gen_website_html AND slide fallback) renders unique, on-voice blurbs.
    try:
        from tools.dedupe_descriptions import dedupe as _dedupe
        _dedupe(events)
    except Exception:
        pass
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
        f"tulsa lgbtqia+ events for {date_range or 'this week'}",
        f"stuff to do {date_range or 'this week'} -- gay edition",
    ]
    lines.append(random.choice(hooks).upper())
    lines.append("")

    # Find Homo Hotel event ONLY if it's actually in this week's filtered list.
    # Do NOT fabricate it when absent — that put W23's HHHH in the W22 caption.
    hh_events = [e for e in events if "homo hotel" in (e.get("name") or "").lower()]
    if hh_events:
        hh = hh_events[0]
        lines.append(f"HOMO HOTEL HAPPY HOUR {hh.get('date', '')}")
        if hh.get("time"):
            lines.append(f"{hh['time']} @ {hh.get('venue', 'the usual spot')}")
        lines.append("you already know. be there.")
        lines.append("")

    # Other events (up to 5) — events are already pre-sorted LGBTQ-first by
    # generate_post_caption(), so taking the top 5 gives us the most relevant.
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
            "description": "Weekly happy hour for the LGBTQIA+ community. Cheap drinks, good vibes, great people.",
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
