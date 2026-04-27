"""One-time script to write unique sassy descriptions for slide-visible events."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config

week_key = config.current_week_key()
path = os.path.join(config.EVENTS_DIR, f"{week_key}_all.json")

with open(path, encoding="utf-8") as f:
    raw = json.load(f)

events = raw if isinstance(raw, list) else raw.get("events", raw)

DESCS = {
    "lambda bowling league": (
        "You're going to show up, rent ridiculous shoes, bowl terribly, and have the best "
        "Monday you've had in months. LGBTQ+ people being delightfully bad at bowling together "
        "is genuinely joyful. Stop texting from your couch and go."
    ),
    "monday movie night": (
        "Free punk rock documentary. Gay bar. Monday night. You were going to watch something "
        "alone anyway. Watch it here, with better people, and actually feel something."
    ),
    "sunset cinema presents": (
        "The Minutemen rewired what punk rock could be, and most people have no idea they "
        "existed. Circle Cinema is correcting that tonight under the open sky, for free. "
        "Show up. Discover your new favorite band."
    ),
    "gender outreach support group": (
        "Every week, people who actually get it sit in the same room at the Equality Center. "
        "If explaining your identity to strangers sounds exhausting, this is where you "
        "don't have to. First time? Show up 30 minutes early. You belong."
    ),
    "queen bess centennial aviation arts festival": (
        "Bessie Coleman was the first Black woman in the world to earn a pilot license and "
        "Tulsa is honoring her centennial with a free silent film and live performers. "
        "History, culture, community. It's free. There is literally no reason to stay home."
    ),
    "queer crafters club": (
        "You will walk in with zero crafting skills and walk out with something you made "
        "and at least one new person you actually like. The whole point is queer people "
        "making things together. Bring your weird self. That's the assignment."
    ),
    "robert randolph": (
        "Robert Randolph plays sacred steel guitar like the instrument begged to be played "
        "that way. Cain's Ballroom has floors you can feel and acoustics you won't forget. "
        "You'll hear this show in your chest for days. Go."
    ),
    "drag bingo fundraiser for adonia": (
        "You get a bingo card, a queen calls numbers between drag numbers, and all the money "
        "helps Adonia. This is the most fun you can have at a table in Tulsa on a Saturday. "
        "Buy a card. Tip your queen. Scream when you win."
    ),
    "legendary midnight drags": (
        "Cars line up. Lights go green. The crowd actually loses it. Tulsa's street drag "
        "racing tradition is loud, fast, and worth staying out past midnight for. "
        "Bring a friend. Wear closed-toe shoes. Leave your bedtime behind."
    ),
    "shenanigans w/ shanel": (
        "Shanel running Sunday at the Eagle means the music is right, the crowd is right, "
        "and at least one person is going to make you laugh out loud. You have three good "
        "hours before Monday finds you. Use them."
    ),
    "sunday showdown open talent night": (
        "Open stage at Club Majestic. Real performers competing live, unscripted. Some will "
        "be brilliant. Some will spectacularly wipe out. Both are worth showing up for. "
        "Doors 9, show 11. Sleep is a Monday problem."
    ),
    "equality business alliance networking mixer": (
        "LGBTQ+ professionals making real connections at the Equality Center. Not the awkward "
        "business card shuffle. Actual community. Come for the networking, stay because "
        "you met someone interesting."
    ),
    "okeq seniors": (
        "LGBTQ+ elders gathering weekly at the Equality Center for community, conversation, "
        "and connection. If you're a queer elder in Tulsa, you should absolutely be in this room."
    ),
    "hope testing (free hiv testing)": (
        "Free HIV testing at the Equality Center. No appointment needed. Walk in, get tested, "
        "know your status. OKEQ makes it easy because knowing matters."
    ),
    "osu tulsa queer support group": (
        "You don't have to have it all figured out to walk in. That's literally the whole point. "
        "Show up, listen, share when you're ready. You are not the only one going through it."
    ),
    "a people's museum by ak/ok": (
        "An international living archive of LGBTQ2S+ history told through hand-drawn portraits "
        "and personal stories. At Positive Space Tulsa. This is the kind of art that makes you "
        "feel seen. Walk in. Let it hit you."
    ),
    "dragnificent! drag show": (
        "Weekly drag at Club Majestic. Get to the front, tip the queens, and prepare to lose "
        "your mind in the best possible way. Thursday nights in Tulsa don't get better than this."
    ),
    "homo hotel happy hour (hhhh)": (
        "Tulsa's queerest happy hour is a First Friday tradition. The Homo Hotel opens its "
        "doors for community, conversation, and cocktails. Whether you're new to Tulsa or a "
        "longtime local, this is THE place to kick off your weekend with your LGBTQ+ family. "
        "No cover, just vibes."
    ),
    "queer women's collective": (
        "Queer women and femmes gathering at the Equality Center. First Friday of the month "
        "means this is the place to be tonight. Show up. Meet people. Stop saying you'll "
        "go next time."
    ),
}

fixed = 0
for e in events:
    name = (e.get("name") or "").lower()
    for key, desc in DESCS.items():
        if key in name:
            e["description"] = desc
            print(f"  Updated: {e['name']}")
            fixed += 1
            break

if isinstance(raw, dict):
    raw["events"] = events
    save_obj = raw
else:
    save_obj = events

with open(path, "w", encoding="utf-8") as f:
    json.dump(save_obj, f, ensure_ascii=False, indent=2)

print(f"\nTotal updated: {fixed}")
