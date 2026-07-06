"""
De-duplicate + de-genericize event descriptions BEFORE slides render.

The 2026-06-08 carousel shipped with the same fallback line on 6 slides
("Put this on your calendar and actually go...") because the rule-based
generator gives same-category events identical copy when LLM enrichment fails.
This pass runs after enrichment, before generate-all, and GUARANTEES no two
posted events share a description — without depending on the (unreliable nested)
LLM. It rewrites each duplicate using the event's OWN specifics (name, venue,
time) plus a stable hash-indexed pick from on-voice opener/closer pools, so the
result is unique AND keeps the sassy-but-warm TulsaGays voice.

Idempotent. Operates on data/events/<week>_all.json. Run between
clean_event_data.py and `main.py generate-all`.
Usage: python tools/dedupe_descriptions.py [WEEK_KEY]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

# On-voice opener pool (RuPaul x Alicia Edwards x Dolly: sassy, warm, no em dash,
# never discouraging). Each is a *frame*; the event's own details get woven in.
# On-voice openers. MUST avoid every phrase in preflight_post.TEMPLATE_SIGNATURES
# (the old pool WAS those phrases, which the preflight then hard-blocked -> the
# pipeline contradicted itself and rule-based decks never passed). These are
# fresh, varied, signature-free frames; validated by --selftest. (Fixed 2026-06-29.)
# Rewritten 2026-07-06 (William: "write for an introvert and tell them WHY this
# event is good for them" — the old pool was name-plus-vibes with zero reason to
# go). Every frame gives a shy person a low-pressure entry plan: what the room
# feels like, where to stand, why showing up alone is fine. The retired frames
# are now TEMPLATE_SIGNATURES in preflight_post.py, so reusing them hard-blocks.
OPENERS = [
    "{name} is built for the quiet ones, honey: nobody checks if you came alone, and the people-watching does half the socializing for you.",
    "If crowds drain you, {name} is the gentle version: slip in, find the edge of the room, and let it come to you at your own speed.",
    "{name} asks nothing of you but showing up. No small talk quota, no dress code drama, just a room that's happier with you in it.",
    "Going solo to {name} is a power move, sugar. Claim a corner, settle in, and you'll be in a conversation before you decide to start one.",
    "{name} is the rare plan that costs no energy: come as you are, stay an hour, and leave whenever you want. That's the whole deal.",
    "Shy? Perfect. {name} runs on people who'd rather watch first and join in when it feels right, so you'll be in good company.",
    "Think of {name} as a starter social: low stakes, friendly room, easy exit if you need one. You probably won't use the exit.",
    "{name} is where you go to be around your people without performing for them. Soak it in, say hi to one person, call it a win.",
]
WHERE = [
    "It's happening{at_venue}{at_time}.",
    "Find it{at_venue}{at_time} and roll in like you own the place.",
    "Catch it{at_venue}{at_time}.",
    "{at_venue_cap}{at_time} is where you need to be.",
]
CLOSERS = [
    "Worst case you make a new friend, best case it becomes your new Thing.",
    "Bring someone or come solo and leave with three new numbers in your phone.",
    "Show up a little early, say hi to one stranger, and let the night do the rest.",
    "Put the phone away once you're there and actually be in the room.",
    "You belong in that room, so go claim your spot.",
    "Tulsa's queer community runs on people who show up. Be one of them.",
]


def _h(s, n):
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16) % n


def _details(e):
    venue = (e.get("venue") or "").split(",")[0].strip()
    time = (e.get("time") or "").strip()
    at_venue = f" at {venue}" if venue else ""
    at_venue_cap = f"{venue}" if venue else "It"
    at_time = f" on {e.get('date')}" if e.get("date") else ""
    if time:
        at_time += f" at {time}" if not at_time else f", {time}"
    return at_venue, at_venue_cap, at_time


def _unique_desc(e, salt, long=False):
    name = e.get("name", "this one")
    at_venue, at_venue_cap, at_time = _details(e)
    seed = f"{name}|{e.get('date','')}|{salt}"
    opener = OPENERS[_h(seed + "o", len(OPENERS))].format(name=name)
    if not long:
        # Short (slide) copy: include the where/when so the card says something
        # concrete about THIS event, as long as it still fits a slide (~200 chars).
        where = WHERE[_h(seed + "w", len(WHERE))].format(
            at_venue=at_venue, at_venue_cap=at_venue_cap, at_time=at_time).strip()
        combined = f"{opener} {where}".replace("  ", " ").strip()
        return combined if len(combined) <= 200 else opener
    where = WHERE[_h(seed + "w", len(WHERE))].format(
        at_venue=at_venue, at_venue_cap=at_venue_cap, at_time=at_time).strip()
    # Rung 3: prefer a venue-tailored "best-time" tip as the closer; fall back to
    # the generic encouraging closer pool only when no venue match.
    closer = ""
    try:
        from tools.venue_tips import tip_for as _tip
        closer = _tip(e)
    except Exception:
        closer = ""
    if not closer:
        closer = CLOSERS[_h(seed + "c", len(CLOSERS))]
    return f"{opener} {where} {closer}".replace("  ", " ").strip()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def dedupe(events):
    fixed = {"short": 0, "long": 0}
    for field, long in (("description", False), ("website_description", True)):
        seen = {}
        for e in events:
            key = _norm(e.get(field))
            if not key or len(key) < 25:
                continue
            if key in seen:
                # collision: rewrite THIS event's field uniquely, retry until distinct
                for salt in range(1, 25):
                    cand = _unique_desc(e, f"{field}{salt}", long=long)
                    if _norm(cand) not in seen:
                        e[field] = cand
                        seen[_norm(cand)] = e.get("name")
                        fixed["long" if long else "short"] += 1
                        break
            else:
                seen[key] = e.get("name")
    return fixed


def main():
    week = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else config.current_week_key()
    path = Path(config.DATA_DIR) / "events" / f"{week}_all.json"
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"no events file {path}"}))
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", [])
    fixed = dedupe(events)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "week": week, "rewritten": fixed}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
