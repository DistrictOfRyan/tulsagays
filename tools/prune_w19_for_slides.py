"""One-shot script to prune the W19 events JSON down to the curated top 3 per day
plus EOTW (Tulsa Water Lantern Festival), with rewritten descriptions.

Run once before generate-all. Backup is at data/events/2026-W19_all.json.bak-full.
"""
import json
from datetime import datetime, timedelta

with open('data/events/2026-W19_all.json', encoding='utf-8') as f:
    data = json.load(f)
events_orig = data if isinstance(data, list) else data.get('events', [])

today = datetime.now().date()
mon = today - timedelta(days=today.weekday())
sun = mon + timedelta(days=6)

KEEP = {
    '2026-05-04': [
        ('Scrabble Palooza!',
         "Competitive Scrabble afternoon up in Skiatook starting at 1pm. Bring your best two-letter words and your trash talk. Worth the drive."),
        ('Hair Metal Karaoke @ The Max',
         "Hair metal karaoke at The Max on Elgin starting at 6pm. Sing Bon Jovi badly with strangers, leave with new friends. The good kind of Monday night."),
        ('Lambda Bowling League',
         "Tulsa's queer Monday tradition. AMF Sheridan Lanes, 7pm. Casual league bowling, low-pressure social. Show up even if you cannot bowl, especially if you cannot bowl."),
    ],
    '2026-05-05': [
        ('Cinco de Mayo Street Festival',
         "Cinco de Mayo block party at 514 S Boston starting at 4pm. Music, food, dancing in the street, the works. Tuesday is a vibe this week."),
        ('MICKY DOLENZ OF THE MONKEES: Legacy Concert Series & Recording Session',
         "Yes, that Micky Dolenz, the actual Monkees one, doing a legacy concert and recording at 304 S Trenton at 5:30pm. Rock and roll history in the room. Do not skip this."),
        ('Lukas Nelson live in concert!',
         "Lukas Nelson at Cain's Ballroom, 6:30pm. Willie's son is the real deal and Cain's is the venue. This one will sell out."),
    ],
    '2026-05-06': [
        ('Opening Day Wednesday Farmers Market',
         "Opening day for the Wednesday Farmers Market at 1 S Lewis, 8am. Fresh produce, local makers, the start of farmers market season. Bring a tote and a friend."),
        ('Mi Tea + R&B Open Mic',
         "Open mic night at Mi Tea with a live R&B band. Come perform, come listen, come sip tea and vibe. Tyra runs a warm room."),
        ('Open Mic @ New Story Brewing',
         "Wednesday open mic at New Story Brewing, 7pm. Try out the joke, the song, the poem. Beer is good either way."),
    ],
    '2026-05-07': [
        ('Auditions for Annie the Musical',
         "Open auditions for Annie at 1301 S Boston, 6pm. Sing 'Tomorrow' if you dare. Ensemble, leads, kids, all welcome. Tulsa community theater needs you."),
        ('Emily Main May Art Gallery Reception',
         "Emily Main's May art gallery reception at Circle Cinema, 6pm. New work, free wine, the kind of art crowd that actually talks to strangers."),
        ('Bands & Blooms',
         "Bands and Blooms at Tulsa Botanic Garden, 5pm. Live music in a garden in May. There is nothing wrong with this picture."),
    ],
    '2026-05-08': [
        ('Tulsa Chorale Chamber Singers',  # we'll match by prefix
         "Tulsa Chorale Chamber Singers perform 'For the Faithful Departed' at Saint John's Episcopal, 7pm. Choral music in a beautiful space. Quiet Friday night, very intentional."),
        ('NYU X Art 4orms: Art Therapy In Public Schools',
         "NYU and Art 4orms host a panel on Art Therapy in Public Schools at 112 N Boston, 6pm. Smart conversation about art education and access. Free."),
        ('The Freakout - Dance Party',
         "The Freakout dance party at The Starlite, 10pm. Late night, loud music, full dance floor. The Friday you actually wanted."),
    ],
    '2026-05-09': [
        ('Tulsa Water Lantern Festival',
         "EVENT OF THE WEEK. Tulsa Water Lantern Festival in Broken Arrow, 5:30pm. You decorate a lantern, light it, float it on the lake at sunset. It is gorgeous, it is family-friendly, and the photos do not lie. Tickets go fast."),
        ('The 32nd Annual Tulsa Festival of Kites',
         "32nd Annual Festival of Kites near 43rd & Garnett. Hundreds of kites in the sky, food trucks, kid energy without the kid responsibility. Bring sunscreen."),
        ('Tulsa Oddities & Curiosities Expo 2026',
         "Oddities and Curiosities Expo at Expo Square. Taxidermy, vintage medical, weird art, strange jewelry, and people-watching that pays for itself. The most us thing happening this weekend."),
    ],
    '2026-05-10': [
        ("Music and Mimosa's Mothers Day Brunch",
         "Music and Mimosas Mother's Day Brunch at 121 S Elgin, 7:30am. Live music, mimosas, and not having to cook for your mom. Reservation strongly suggested."),
        ("Mother's Day Brunch at The Chalkboard Tulsa",
         "Mother's Day Brunch at The Chalkboard, 1324 S Main, 11am. The Chalkboard does brunch right. Book it, do not just walk in."),
        ("Mother's Day Brunch at Duet with Margie and Tye!",
         "Mother's Day Brunch at Duet with Margie and Tye, noon. Live music, great food, the kind of brunch your mother will actually mention later. Reserve."),
    ],
}


def name_matches(event_name: str, target: str) -> bool:
    """Match exact or by clear prefix (handles smart-quote / encoding diffs)."""
    e = (event_name or '').strip()
    t = target.strip()
    if e == t:
        return True
    # Allow prefix match for the Tulsa Chorale event whose actual name has smart quotes
    if t == 'Tulsa Chorale Chamber Singers' and e.startswith('Tulsa Chorale Chamber Singers'):
        return True
    return False


in_week_keep = []
out_of_week = []

for e in events_orig:
    d = e.get('date', '')
    if not d:
        out_of_week.append(e)
        continue
    try:
        dt = datetime.strptime(d, '%Y-%m-%d').date()
    except ValueError:
        out_of_week.append(e)
        continue
    if not (mon <= dt <= sun):
        out_of_week.append(e)
        continue
    # In this week
    keep_for_day = KEEP.get(d, [])
    matched = False
    for target_name, desc in keep_for_day:
        if name_matches(e.get('name', ''), target_name):
            e['description'] = desc
            if target_name == 'Tulsa Water Lantern Festival':
                e['priority'] = 1
                e['source'] = 'manual'
            else:
                e['priority'] = 2
                if e.get('source') == 'recurring':
                    e['source'] = 'manual'
            in_week_keep.append(e)
            matched = True
            break
    # If not matched, drop from this-week (do NOT keep recurring/excluded)

# Verify coverage
print('=== Coverage check ===')
for date in sorted(KEEP.keys()):
    targets = [n for n, _ in KEEP[date]]
    found_names = [e.get('name', '') for e in in_week_keep if e.get('date') == date]
    print(f'  {datetime.strptime(date, "%Y-%m-%d").strftime("%A %m/%d")}: {len(found_names)}/3 targets')
    for t in targets:
        ok = any(name_matches(fn, t) for fn in found_names)
        print(f'    {"OK " if ok else "MISS"} {t}')

new_events = in_week_keep + out_of_week
if isinstance(data, list):
    new_data = new_events
else:
    data['events'] = new_events
    data['total_events'] = len(new_events)
    new_data = data

with open('data/events/2026-W19_all.json', 'w', encoding='utf-8') as f:
    json.dump(new_data, f, indent=2, ensure_ascii=False)

print(f'\nSaved: {len(in_week_keep)} in-week + {len(out_of_week)} out-of-week = {len(new_events)} total events.')
