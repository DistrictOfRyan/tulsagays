"""Inject sassy unique descriptions directly into the week's events JSON.
Run once per week after gen_website_descriptions.py falls back to templates.
Targets specific event names that would otherwise get identical category-fallback copy.
"""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import config

_DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]
_DATE_TO_DAY = {
    0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
    4: "friday", 5: "saturday", 6: "sunday",
}


def _event_day_name(ev: dict) -> str:
    """Return lowercase day-of-week for an event's date, or ''."""
    date_str = ev.get("date", "")
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return _DATE_TO_DAY[dt.weekday()]
    except (ValueError, KeyError):
        return ""


def validate_day_references(descriptions: dict, events: list) -> None:
    """
    Check every description in INJECTIONS for day-of-week mentions that
    don't match the actual event date.

    descriptions: the INJECTIONS dict  {key: (website_desc, slide_desc)}
    events:       list of event dicts loaded from the JSON
    """
    # Build map: normalised name substring -> actual day name
    name_to_day = {}
    for ev in events:
        name_lower = (ev.get("name") or "").lower()
        actual_day = _event_day_name(ev)
        if actual_day:
            name_to_day[name_lower] = actual_day

    found_any = False
    for key, descs in descriptions.items():
        # Find which event this injection targets
        actual_day = None
        for ev_name, day in name_to_day.items():
            if key in ev_name or ev_name in key:
                actual_day = day
                break
        if not actual_day:
            continue  # no event found this week — skip

        for desc_label, desc_text in zip(("website", "slide"), descs):
            if not desc_text:
                continue
            desc_lower = desc_text.lower()
            for day in _DAY_NAMES:
                if day in desc_lower and day != actual_day:
                    print(
                        f"  [WARNING] Day mismatch in '{key}' ({desc_label}): "
                        f"says '{day.capitalize()}' but event is on "
                        f"{actual_day.capitalize()}"
                    )
                    found_any = True
                    break

    if not found_any:
        print("  [OK] No day-of-week mismatches in injected descriptions.")

# ── Sassy unique descriptions keyed by lowercase substring of event name ──────
# Format: (website_description, slide_description)
# website = 4-6 sentences | slide = 2-3 sentences MAX

INJECTIONS = {
    "homo hotel happy hour": (
        "First Friday. The DoubleTree. The gays. Every month, Homo Hotel Happy Hour "
        "transforms a downtown hotel bar into the most welcoming room in Tulsa for two glorious hours. "
        "This month HHHH is raising money for Paws in Need Tulsa, vet care and food support for pets "
        "in families facing hardship. Free admission, raffle tickets, nearly all proceeds to Paws in Need. "
        "Show up at 6. Bring your big-gay-night budget. Talk to strangers. Win a raffle. "
        "No cover. No dress code. Just the most fabulous two hours Tulsa offers every month.",

        "First Friday. The DoubleTree. The gays, raising money for Paws in Need Tulsa. "
        "Free admission, raffle tickets, hotel-priced drinks. Show up at 6. "
        "This is the one you don't skip.",
    ),
    "66 days of fun: trivia": (
        "The WEL Bar is doing trivia and yes, that counts as getting out of the house. "
        "Sixty-six days of fun, and they chose trivia because they know exactly what they're doing. "
        "WEL Bar is LGBTQ-friendly, the crowd is good, and trivia nights there have an energy that "
        "rewards people who actually show up. Make a team. Name it something that makes the host snort. "
        "The gay team statistically wins pop culture every single time. Own it shamelessly.",

        "WEL Bar is doing trivia and the crowd is exactly who you think it is. "
        "Form a team, name it something outrageous, and remember: gay people disproportionately win "
        "pop culture rounds. Use that power. Buy a round when you win.",
    ),
    "trivia night": (
        "It's trivia night and yes, you DO know the answer to the Broadway category. "
        "You've been training for this your entire gay life without realizing it. "
        "Form a team with whoever's at the bar, name it something that makes people look over, "
        "and spend two hours finding out what you're embarrassingly good at. "
        "The drinks are bar prices. The competition is surprisingly real. Show up.",

        "Trivia night and you already know you're winning the pop culture round. "
        "The only question is whether you're brave enough to actually go. "
        "You are. Get there. Make a team. Win something.",
    ),
    "trivia thursday": (
        "Thursday trivia at 601 E 4th, and honestly, a competitive trivia round is the exact "
        "amount of social interaction a gay introvert needs on a Thursday night. "
        "Not too intense, just intense enough. You get a team, a drink, a reason to yell "
        "at someone who got the wrong answer, and a story for Friday. "
        "Show up with or without a team. The bar will sort you out.",

        "Thursday trivia and it's the low-commitment social event you've been looking for. "
        "Show up. Get a drink. Yell answers. Go home victorious or informed. "
        "Either way, better than your couch.",
    ),
    "friday karaoke at sutures": (
        "Sutures Bar has karaoke on Friday nights and you have been waiting for this specific "
        "excuse to finally sing 'Total Eclipse of the Heart' in front of strangers. "
        "Here it is. The bar is ready. The mic is live. The crowd is already rooting for you. "
        "Pick the song that lives in your chest. Deliver it completely. "
        "Gay karaoke energy is a specific and powerful force. Be that force on a Friday night.",

        "Friday karaoke at Sutures and it's time. The song you've been saving for the right moment "
        "has found its night. Pick it. Commit to it. The crowd will absolutely be there for you.",
    ),
    "gabbin with gabbi": (
        "Gabbi is hosting bingo and if you haven't seen her work, you've been missing the kind of "
        "entertainer who makes you feel personally chosen when she makes eye contact with your table. "
        "This is drag-hosted bingo, which means the bingo is technically the premise but the real "
        "product is Gabbi running the room. Get there early for a good seat. "
        "Bring cash for the bingo cards. Scream 'BINGO!' as loud as you physically can. "
        "That's not just encouraged, it's expected.",

        "Gabbi is hosting bingo and the room belongs to her the second she walks in. "
        "Bring cash for cards, arrive early, and practice your best 'BINGO!' scream in the car. "
        "This is the Tuesday you actually want.",
    ),
    "twisted arts drag bingo": (
        "Twisted Arts is running Drag Bingo and the name says everything you need to know. "
        "This isn't your grandmother's bingo. The numbers get called between performances "
        "that are legitimately spectacular, and every card is a front-row ticket to "
        "some of the best drag Tulsa has to offer. "
        "Get there before it sells out. Bring cash for bingo cards and extra for tips. "
        "The queens notice when you tip generously and they will absolutely acknowledge it. "
        "That's worth the price of the card alone.",

        "Twisted Arts Drag Bingo: the queens call the numbers AND perform between rounds. "
        "Bring cash for cards and tips, arrive early for a good table. "
        "This is the Saturday Tulsa drag scene that actually shows up.",
    ),
    "okeq senior": (
        "OKEQ's Senior Program at the Equality Center is one of Tulsa's most quietly important "
        "gatherings. LGBTQ+ seniors often have less visible community than younger folks, "
        "and this space exists specifically to fix that. If you're a senior or you know one "
        "who's been feeling isolated, this is exactly where to be. "
        "The Equality Center is warm, the organizers are experienced, "
        "and sometimes what you need is a room full of people who've been here longer "
        "than the rest of us and have stories worth hearing.",

        "OKEQ's senior gathering at the Equality Center is for the people who built this community "
        "before most of us were paying attention. Show up. Listen. Belong.",
    ),
    "affirming": (
        "AFFIRMING at the Equality Center is a recovery-focused space built for LGBTQ+ people. "
        "Walking into a recovery meeting where you don't have to explain or edit the queer parts "
        "of your story is a fundamentally different experience, and this space was built to give "
        "exactly that. You don't have to be in crisis to come. "
        "Sometimes you just want to be in a room where people actually understand. "
        "First-timers are welcomed. You belong here exactly as you are.",

        "AFFIRMING is recovery space built specifically for LGBTQ+ people. "
        "No explaining yourself, no code-switching, no editing your story before you tell it. "
        "Show up as you are. That's the whole point.",
    ),
    "positively grateful": (
        "Positively Grateful at the Equality Center is a support gathering for people navigating "
        "recovery and wellness in the LGBTQ+ community. "
        "The name says it: showing up, practicing gratitude, and doing it with people who "
        "understand your specific version of that journey. "
        "This is low-pressure, inclusive, and held in one of Tulsa's most affirming spaces. "
        "Walk in with whatever you're carrying. Walk out a little lighter.",

        "Positively Grateful meets at the Equality Center and it's exactly what it sounds like: "
        "people showing up, practicing gratitude, and being in community together. "
        "LGBTQ+ affirming. All welcome. Come as you are.",
    ),
    "okeq tulsa ttrpg": (
        "OKEQ is running a Tabletop RPG session at the Equality Center and this is the "
        "nerd-gay overlap event Tulsa didn't know it needed to put on a flyer. "
        "TTRPGs and queer spaces have overlapped for decades because both are fundamentally about "
        "building a world where you get to be exactly who you are, "
        "and the party has your back no matter what. "
        "New players welcome. Experienced players welcome. Just bring your character and your dice.",

        "OKEQ is running Tabletop RPGs at the Equality Center. "
        "Gay nerds, your world has arrived. New and experienced players welcome. "
        "Bring dice or borrow some. The party needs you.",
    ),
    "girl scout troop": (
        "Girl Scout Troop 7484 is meeting at the Equality Center. "
        "The Equality Center is an affirming space and this troop is here for it. "
        "If you have a scout-aged kid looking for an inclusive troop, this is worth knowing about.",

        "Girl Scout Troop 7484 meets at the Equality Center, one of Tulsa's most affirming spaces. "
        "Community showing up for the next generation.",
    ),
    "live music with barrett": (
        "Barrett, Alan, and Jacob are playing live at the Albatross and if you've been looking "
        "for a reason to try this spot, a live music night with three musicians sharing a stage "
        "is exactly that reason. "
        "It's a birthday show, which means the energy is already good before anyone plays a note. "
        "Show up. Order something. Let the music do what it does in a room full of people "
        "who actually showed up to listen.",

        "Birthday live music at the Albatross and the birthday energy makes every show better. "
        "Show up before it starts, find a good spot, and let the music justify your Tuesday.",
    ),
    "live music - ryan graham": (
        "Ryan Graham is playing live at 601 E 4th and this is the kind of Friday music night "
        "that turns into the best weekend you've had in a month. "
        "Live music in Tulsa's bar scene is genuinely underrated, and Friday nights at 601 "
        "draw a crowd that's there to have a good time rather than just kill time. "
        "Show up before he starts. Find a spot near the front. "
        "Let a Friday night remind you why you live in this city.",

        "Ryan Graham plays live Friday at 601 E 4th. "
        "Get there before he starts, find a spot you can hold, and let live music justify your Friday night. "
        "Tulsa has better live music than it gets credit for. This is evidence.",
    ),
    "live music - colt west": (
        "Colt West is playing live at 601 E 4th on Saturday and a live music night "
        "is always the right call when the alternative is sitting at home watching other people "
        "have fun on your phone. "
        "601 E 4th has a bar crowd that's there to actually have a night, not just check a box. "
        "Get there, order something, and let Saturday be a night with a story.",

        "Colt West plays live Saturday at 601 E 4th. "
        "Get out of the house. Get to the bar. Let Saturday be something worth talking about.",
    ),
    "lesbian attachment": (
        "The Lesbian Attachment and Communication Healing Intensive is the workshop that makes "
        "people send 'thank you for making me go to this' texts to the friend who dragged them. "
        "This is deep-work territory: attachment styles, communication patterns, and the specific "
        "ways queer relationships develop their own beautiful and complicated dynamics. "
        "If you've ever thought 'I wish I understood myself better in relationships,' "
        "this is the room for it. For lesbians and queer women. Come open. Leave changed.",

        "The Lesbian Attachment and Communication Healing Intensive is the workshop your "
        "therapist has been low-key suggesting for six months. "
        "Come open to it. Leave understanding yourself better. For lesbians and queer women.",
    ),
    "art gallery exhibition - carrie": (
        "Carrie Sheley's gallery exhibition is up and this is the kind of local art show "
        "that you walk into planning to spend ten minutes and leave an hour later having "
        "had two conversations you didn't expect and a new favorite piece you can't stop "
        "thinking about. "
        "Local exhibitions matter because local artists are your actual neighbors, "
        "making things in the same city you live in. "
        "Show up. Look slowly. Talk to Carrie if she's there. Buy something if you can.",

        "Carrie Sheley's gallery show is the kind of local art event you walk into for ten minutes "
        "and leave an hour later. Walk slowly. Look at everything. Talk to the artist if she's there.",
    ),
    "elote": (
        "Elote is one of Tulsa's most LGBTQ-friendly venues and when they host events, "
        "the crowd reflects that. Whatever's happening here, it's happening in a space "
        "that genuinely welcomes you. Show up hungry. The food is excellent "
        "and the company is reliably good.",

        "Elote is one of Tulsa's most queer-friendly spots and events there reflect it. "
        "Show up. The food is great and so is the crowd.",
    ),
    "drag sing along": (
        "Elote's Drag Sing Along is GAGA VS. MADONNA and yes, you have to pick a side. "
        "Two of the biggest queer music icons in history, one stage, one drag host, "
        "and a room full of people who have OPINIONS. "
        "Sing every lyric you know. Tip the performer who does your favorite song. "
        "And if you're a Gaga girl at a Madonna night or vice versa, "
        "you hold your head up high and you belt it anyway. "
        "This is camp. This is community. This is a Friday night at Elote.",

        "Elote's Drag Sing Along: GAGA VS. MADONNA. "
        "Pick a side, know your lyrics, and tip the performer who does your song. "
        "This is camp. Show up and participate fully.",
    ),
    "drag brunch": (
        "Drag Brunch at Elote is the meal format that the queer community invented and "
        "perfected over several decades. Bottomless mimosas. Drag performances between courses. "
        "A room full of people who showed up specifically to be fabulous on a weekend morning. "
        "Reserve a spot. Dress like you tried. Tip generously. "
        "This is exactly what Saturday and Sunday mornings are supposed to be for.",

        "Drag Brunch at Elote: performances between courses, mimosas flowing, "
        "room full of your people. Reserve a spot. Dress up. Tip generously. "
        "This is what weekends are for.",
    ),
    "inner circle drag show": (
        "Inner Circle Drag Show is bringing the full production and if you've been sleeping on "
        "Tulsa drag outside of the big venues, this is your wake-up call. "
        "Get a spot near the stage. Bring a mix of bills for tipping. "
        "The queens doing this work deserve a room that actually shows up for them. "
        "Be that room.",

        "Inner Circle Drag Show: full production, real performers, real stakes. "
        "Get a spot near the stage. Bring tip money. Show up for the queens doing the work.",
    ),
    "pride bar crawl": (
        "The Tulsa Pride Bar Crawl is the event where the entire queer community "
        "collectively takes over downtown and you just follow the energy. "
        "You will run into everyone you know and at least three people you've been meaning to text. "
        "Wear something that announces your presence. Start early. Pace yourself. "
        "This is the bar crawl where the route is less important than the crowd you're moving with. "
        "The best Pride bar crawl memory is always the unplanned part. Show up and let it happen.",

        "Tulsa Pride Bar Crawl: the whole queer community moving through downtown together. "
        "Wear something memorable, pace yourself, and remember that the best memories are "
        "always the unplanned parts. Show up. Follow the energy.",
    ),
    "black. queer. proud.": (
        "Black. Queer. Proud. is the intersection that built this movement and "
        "the community that deserves to take up space in Tulsa. "
        "This event is specifically for and centered on Black LGBTQ+ people in the city, "
        "and showing up is how you participate in the community you say you care about. "
        "Come to celebrate, connect, and be present with one of the most important communities "
        "in Tulsa's queer landscape.",

        "Black. Queer. Proud. is the community gathering that the city needs and that "
        "Black LGBTQ+ Tulsans deserve. Show up. Be present. This matters.",
    ),
    "transformation conference": (
        "The Transformation Conference brings together people navigating gender identity, "
        "transition, and queer community in a full conference format. "
        "Sessions, speakers, community connection, and the specific experience of being in "
        "a room where you don't have to explain anything before someone understands you. "
        "If this is your community, you already know why this matters. "
        "Register early. These conferences fill up. The people you'll meet here will become "
        "your people.",

        "The Transformation Conference is the full-day queer community gathering "
        "for people navigating gender and identity. Register early. "
        "The room you've been looking for is here.",
    ),
    "scavenger hunt": (
        "The Self-Care City Scavenger Hunt takes you through Tulsa on a mission, "
        "which is the most interesting way to spend time in this city that most people "
        "have never tried. "
        "Scavenger hunts are inherently social in the best way: "
        "you're competing but also exploring, moving but also talking. "
        "The gay case for a wellness scavenger hunt: "
        "we've spent years being told to take care of ourselves in other people's ways. "
        "This one is ours. Show up, team up, and actually enjoy the city you live in.",

        "Self-Care City Scavenger Hunt through Tulsa: exploration, competition, "
        "and the rare experience of actually enjoying this city on foot. "
        "Team up with a friend. Don't overthink it. Just go.",
    ),
}


# ── Main ──────────────────────────────────────────────────────────────────────

wk = config.current_week_key()
path = os.path.join('data', 'events', f'{wk}_all.json')

with open(path, encoding='utf-8') as f:
    raw = json.load(f)

events = raw if isinstance(raw, list) else raw.get('events', [])

injected = 0
for ev in events:
    name_lower = (ev.get('name') or '').lower()
    for key, (website_desc, slide_desc) in INJECTIONS.items():
        if key in name_lower:
            ev['website_description'] = website_desc
            ev['slide_description']   = slide_desc
            injected += 1
            print(f"  [injected] {ev.get('name','')[:60]}")
            break

if isinstance(raw, dict):
    raw['events'] = events
    save_obj = raw
else:
    save_obj = events

with open(path, 'w', encoding='utf-8') as f:
    json.dump(save_obj, f, ensure_ascii=False, indent=2)

print(f"\nInjected descriptions for {injected} events -> {path}")

# Validate that no description references the wrong day of the week
print("\nValidating day-of-week references in descriptions...")
validate_day_references(INJECTIONS, events)
