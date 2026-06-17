# -*- coding: utf-8 -*-
"""One-shot builder for the 2026-W24 TulsaGays newsletter (Pride week).
Builds rich HTML (5 picks + business spotlight + community note), creates a Kit
broadcast, and ENFORCES the anonymity gate: only auto-sends if the default Kit
sending address ends with @tulsagays.com AND is verified. Otherwise DRAFT only.
"""
import json, sys, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KIT = json.loads((Path.home() / ".credentials" / "kit_config.json").read_text(encoding="utf-8"))
API = KIT.get("api_base", "https://api.kit.com/v4")
H = {"X-Kit-Api-Key": KIT["api_key"].strip(), "Accept": "application/json", "Content-Type": "application/json"}
PINK = "#e6007e"
CITY_TAG_ID = 20050806  # city-tulsa

subject = "Drag brunch, a Pride bar crawl, and a queer lit birthday. Your week, sorted."
preheader = "Five Pride-season picks through Sunday. Get off the couch, darling."

EVENTS = [
    {"name": "Queerlit Turns 2", "when": "Wednesday, 5:30 PM", "venue": "Heirloom Rustic Ales",
     "url": "https://www.tulsagays.com",
     "copy": "The little queer book night that could is turning two, and you are going to go celebrate it. Two years of gay readers, good beer, and a room that genuinely wants you there. Bring the friend who keeps swearing they will read more this year."},
    {"name": "DRAGNIFICENT! Drag Show", "when": "Thursday, Doors 9 PM / Show 10 PM", "venue": "Club Majestic",
     "url": "https://downtowntulsa.com/do/dragnificent-at-club-majestic-1",
     "copy": "Put the phone down and get to the front, because the queens at Majestic are not here for your half attention and neither am I. Tip generously, scream appropriately, and leave having forgotten whatever the week did to you."},
    {"name": "Dance Night with DJ Konnect", "when": "Friday night", "venue": "Club Majestic",
     "url": "https://www.tulsagays.com",
     "copy": "Friday, Majestic, DJ Konnect running the floor. The party's full name is doing plenty of heavy lifting on its own, so I will simply say: wear something you can move in, and do not make firm plans for Saturday morning."},
    {"name": "Elote Drag Brunch", "when": "Saturday, 11 AM and 1:30 PM (two seatings)", "venue": "Elote Cafe & Catering",
     "url": "https://www.eventbrite.com/o/elote-cafe-catering-17620608823",
     "copy": "Queso, queens, and two seatings because the people demanded it. Elote's drag brunch is the rare event worth leaving bed before noon on a weekend. Book ahead, darling, it fills up fast and you are not the only one who heard."},
    {"name": "Tulsa's Legendary Midnight Drags", "when": "Saturday night", "venue": "Tulsa Raceway Park",
     "url": "https://www.tulsagays.com",
     "copy": "No, not those drags. These ones have engines. Tulsa Raceway Park throws the strip open for the Legendary Midnight Drags, and it is a gloriously different way to spend a Saturday. Bring the friend who is forever threatening to buy a motorcycle."},
]

def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

p = []
p.append('<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;color:#222;line-height:1.6">')
p.append(f'<p style="font-size:13px;letter-spacing:.18em;text-transform:uppercase;color:{PINK};margin:0 0 4px">Tulsa Gays</p>')
p.append('<p style="font-size:18px"><strong>It is Pride season in Tulsa and the calendar has lost all restraint, which is exactly how we like it.</strong> Here are the five places you ought to be before Sunday.</p>')
p.append(f'<h3 style="color:{PINK};letter-spacing:.04em;margin-top:22px">THE SHORT LIST THIS WEEK</h3>')
for e in EVENTS:
    p.append(f'<div style="margin:16px 0;padding-bottom:14px;border-bottom:1px solid #eee">')
    p.append(f'<p style="margin:0"><strong style="font-size:16px">{esc(e["name"])}</strong><br>'
             f'<span style="color:#888;font-size:13px">{esc(e["when"])} &middot; {esc(e["venue"])}</span></p>')
    p.append(f'<p style="margin:6px 0 0;color:#333">{esc(e["copy"])}</p>')
    if e["url"].startswith("http") and "tulsagays.com" not in e["url"]:
        p.append(f'<a href="{esc(e["url"])}" style="color:{PINK};font-size:13px">Tickets / info &rarr;</a>')
    p.append('</div>')
p.append(f'<p style="margin:18px 0"><a href="https://www.tulsagays.com" style="background:{PINK};color:#fff;'
         f'padding:11px 20px;border-radius:6px;text-decoration:none;font-weight:bold">See everything at tulsagays.com &rarr;</a></p>')

# Business spotlight
p.append(f'<h3 style="color:{PINK};letter-spacing:.04em;margin-top:28px">LGBTQIA+ TULSA BUSINESS SPOTLIGHT</h3>')
p.append('<p style="margin:6px 0"><strong>Magic City Books</strong><br>'
         'Down in the Arts District sits Magic City Books, the independent shop that has quietly become one of the most '
         'reliably queer-welcoming rooms in town. Nonprofit, fiercely local, and never shy about putting LGBTQ+ authors '
         'on the table by the front door where you cannot miss them. Wander in any day and you walk out better company. '
         '<br><a href="https://www.magiccitybooks.com" style="color:%s;font-size:13px">221 E Archer St &middot; magiccitybooks.com &rarr;</a></p>' % PINK)

# Community note
p.append(f'<h3 style="color:{PINK};letter-spacing:.04em;margin-top:28px">A COMMUNITY NOTE</h3>')
p.append('<p style="margin:6px 0;color:#333">While the bars get loud this week, the Dennis R. Neill Equality Center is doing '
         'the quiet work that holds all of it up. Saturday at 1 they open <strong>Rainbow Harvest</strong>, a free farmers '
         'market: real produce, no cost, no judgment, just queer neighbors filling tote bags and sticking around to talk. '
         'Pride is the parade and the party, sure. It is also making sure the person next to you can eat. If you have a '
         'little extra this season, they could use it. If you have a little less, go take what you need. Both are the point.<br>'
         f'<a href="https://forms.gle/WXMVSfEJpav4Lg4p8" style="color:{PINK};font-size:13px">Pre-register for Rainbow Harvest &rarr;</a></p>')

p.append('<p style="margin-top:26px;font-weight:bold">Forward this to someone who needs to get out of the house.</p>')
p.append('<p style="color:#999;font-size:12px;margin-top:18px">'
         '<a href="https://www.tulsagays.com" style="color:#999">tulsagays.com</a> &middot; '
         '<a href="https://www.instagram.com/tulsagays" style="color:#999">Instagram</a> &middot; '
         '<a href="https://www.tulsagays.com/submit" style="color:#999">Submit an event</a><br>'
         'You are getting this because you wanted Tulsa\'s queer calendar in your inbox. Pace yourself, hydrate, look out for each other.</p>')
p.append('</div>')
html_body = "\n".join(p)

# --- ANONYMITY + DELIVERABILITY GATE ---
acct = requests.get(f"{API}/account", headers=H, timeout=30).json()
sending = (acct.get("account", {}) or {}).get("sending_addresses", []) or []
default_addr = next((a for a in sending if a.get("is_default")), (sending[0] if sending else {}))
sender_email = (default_addr.get("email_address") or "").lower()
sender_verified = bool(default_addr.get("is_verified"))
anonymous_sender = sender_email.endswith("@tulsagays.com")
can_send = anonymous_sender and sender_verified

payload = {
    "subject": subject,
    "preview_text": preheader,
    "content": html_body,
    "description": f"Tulsa Gays weekly newsletter {datetime.now().strftime('%Y-%m-%d')} (W24 Pride)",
    "public": True,
    "subscriber_filter": [{"all": [{"type": "tag", "ids": [CITY_TAG_ID], "operator": "is"}]}],
}
if can_send:
    payload["send_at"] = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

resp = requests.post(f"{API}/broadcasts", headers=H, json=payload, timeout=30)
print("Kit response:", resp.status_code)
if resp.status_code >= 300:
    print("BODY:", resp.text[:500])
    sys.exit(1)
b = resp.json().get("broadcast", {})
bid = b.get("id")
if can_send:
    print(f"SENT/SCHEDULED: id={bid} from={sender_email}")
else:
    reason = ("sender is not an @tulsagays.com address (anonymity)" if not anonymous_sender
              else "sending address not verified")
    print(f"DRAFT (NOT sent): id={bid} | reason: {reason} | sender: {sender_email or 'none'}")
print(f"EDIT/SEND IN KIT: https://app.kit.com/broadcasts/{bid}")
print(f"WORD_COUNT_APPROX: {len(' '.join([e['copy'] for e in EVENTS]).split()) + 120}")
