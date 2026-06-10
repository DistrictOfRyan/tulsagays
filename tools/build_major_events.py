"""Build data/major_tulsa_events.json from a compact, sourced spec.

Why a generator: many marquee Tulsa events run multiple days, and the event
schema has a single `date` field (runner Filter 3 keeps an event only in the
Mon-Sun week its date falls in). So a multi-day festival needs one entry PER
day to show across its run, and a multi-week display needs one entry per week.
Hand-writing dozens of near-identical entries is error-prone; this expands them
from one spec line. Re-run after confirming ESTIMATED dates:

    python tools/build_major_events.py

cadence:
  "daily"  -> one entry for each day from start..end (festivals, the fair)
  "weekly" -> one entry every 7 days start..end (long holiday light displays,
              multi-week exhibits) so the event shows once each active week
              without cluttering every single day
  "single" -> one entry on `start` (one-day events; ignores end)

confidence CONFIRMED/ESTIMATED is recorded in source_note so William knows
which dates to re-verify before they go live.
"""

import json
import os
from datetime import date, timedelta

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "major_tulsa_events.json")

# Each spec: name, start (YYYY-MM-DD), end, cadence, time, venue, url, priority,
# short (slide pitch), long (website copy), confidence, note.
SPEC = [
    # ── June 2026 ──────────────────────────────────────────────────────────
    {
        "name": "Saint Francis Tulsa Tough",
        "start": "2026-06-05", "end": "2026-06-07", "cadence": "daily",
        "time": "All day", "venue": "Downtown Tulsa & Riverside (Blue Dome, Tulsa Arts District, Cry Baby Hill)",
        "url": "https://www.tulsatough.com/", "priority": 2,
        "short": "Tulsa Tough takes over downtown for three days of pro-level criterium racing, group rides, and the gloriously costumed chaos of Cry Baby Hill.",
        "long": "Saint Francis Tulsa Tough is the city's biggest cycling weekend, three days of criterium races, Gran Fondo group rides, and street parties across Blue Dome, the Tulsa Arts District, and Riverside. Sunday's Cry Baby Hill is the wild, costumed, very-Tulsa heart of it, and the crowd skews festive and welcoming. You do not need a bike to belong here, just show up and cheer.",
        "confidence": "CONFIRMED", "note": "tulsatough.com 2026 schedule",
    },
    {
        "name": "Tulsa Juneteenth Festival",
        "start": "2026-06-20", "end": "2026-06-20", "cadence": "single",
        "time": "2:00 PM - 11:00 PM", "venue": "Historic Greenwood District, 500 N Greenwood Ave, Tulsa, OK 74120",
        "url": "https://www.tulsajuneteenth.org/", "priority": 2,
        "short": "Juneteenth on Black Wall Street brings national music acts, spoken word, and art to the heart of Greenwood for a free day-long celebration.",
        "long": "The Tulsa Juneteenth Festival fills the Historic Greenwood District, the heart of Black Wall Street, with national musical acts, open-mic spoken word, visual art, and cultural exhibitions. It is free, it is joyful, and it is one of the most meaningful gatherings on the Tulsa calendar.",
        "confidence": "CONFIRMED", "note": "tulsajuneteenth.org; main festival day (programming runs Jun 8-20)",
    },
    {
        "name": "Route 66 Birthday: Cars Movie Nights",
        "start": "2026-06-12", "end": "2026-06-12", "cadence": "single",
        "time": "Evening", "venue": "Philbrook Museum & Gathering Place, Tulsa",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "Celebrate the Mother Road's 100th with outdoor screenings of Cars at Philbrook and Gathering Place.",
        "long": "As part of the Route 66 Centennial, Tulsa marks the Mother Road's birthday with outdoor screenings of Cars, both at Philbrook's Films on the Lawn and at Gathering Place. Bring a blanket and settle in under the stars.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    {
        "name": "Reflections on Route 66: Starlight Concert Band",
        "start": "2026-06-23", "end": "2026-06-23", "cadence": "single",
        "time": "Evening", "venue": "Guthrie Green, 111 Reconciliation Way, Tulsa, OK 74103",
        "url": "https://www.guthriegreen.com/", "priority": 3,
        "short": "The Starlight Concert Band plays a Route 66 Centennial tribute on the lawn at Guthrie Green, free and easy.",
        "long": "The Starlight Concert Band brings a Route 66 Centennial tribute to Guthrie Green for a free evening on the lawn. Pack a picnic, grab a spot on the grass, and let the Mother Road nostalgia wash over you.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    {
        "name": "Route 66 Road Fest",
        "start": "2026-06-27", "end": "2026-06-28", "cadence": "daily",
        "time": "All day", "venue": "Expo Square, 4145 E 21st St, Tulsa, OK 74114",
        "url": "https://www.visittulsa.com/", "priority": 3,
        "short": "A big interactive Route 66 Centennial expo at Expo Square, journeying through 100 years of the Mother Road.",
        "long": "Route 66 Road Fest is a large interactive expo at Expo Square celebrating the Mother Road's centennial, with immersive exhibits, history, and Americana taking you across all 100 years of Route 66. Great for families and road-trip romantics alike.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    # ── July 2026 ──────────────────────────────────────────────────────────
    {
        "name": "Route 66 Festival: Tales of the Mother Road",
        "start": "2026-07-18", "end": "2026-07-18", "cadence": "single",
        "time": "All ages", "venue": "Gathering Place, 2650 S John Williams Way, Tulsa, OK 74114",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "Demonstrations, performances, and Mother Road storytelling for all ages at Gathering Place.",
        "long": "Route 66 Festival: Tales of the Mother Road brings demonstrations, performances, and living history to Gathering Place for a free all-ages Centennial celebration of the road that built Tulsa's reputation.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    {
        "name": "Films at the Museum: Mother Road 100 Years",
        "start": "2026-07-31", "end": "2026-07-31", "cadence": "single",
        "time": "Evening", "venue": "Philbrook Museum of Art, 2727 S Rockford Rd, Tulsa, OK 74114",
        "url": "https://philbrook.org/", "priority": 3,
        "short": "Philbrook screens Route 66 documentaries for the Mother Road's 100th.",
        "long": "Philbrook Museum of Art hosts a Route 66 Centennial documentary night, screening films on the Mother Road's 100-year story. A cool, cultured way to spend a summer evening.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    # ── August 2026 ────────────────────────────────────────────────────────
    {
        "name": "Urban Sketchers Route 66 Centennial Exhibit",
        "start": "2026-08-04", "end": "2026-08-25", "cadence": "weekly",
        "time": "Gallery hours", "venue": "TCC McKeon Center for Creativity, 909 S Boston Ave, Tulsa, OK 74119",
        "url": "https://www.tulsacc.edu/", "priority": 3,
        "short": "An Urban Sketchers exhibit capturing Route 66 at 100, on view through August at TCC's McKeon Center.",
        "long": "The Urban Sketchers Route 66 Centennial Exhibit fills TCC's McKeon Center for Creativity with on-location drawings of the Mother Road at 100. A quiet, lovely stop for anyone who loves art and Americana.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar; runs Aug 4-25",
    },
    {
        "name": "Art Crawl on 66 (Red Fork)",
        "start": "2026-08-14", "end": "2026-08-14", "cadence": "single",
        "time": "Evening", "venue": "Historic Red Fork District, Tulsa",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "The monthly Art Crawl lights up the historic Red Fork stretch of Route 66 with galleries, makers, and music.",
        "long": "Art Crawl on 66 turns the historic Red Fork District into a walkable evening of galleries, makers, and live music along Route 66. A laid-back, local night out on the Mother Road.",
        "confidence": "CONFIRMED", "note": "Recurring 2nd Friday; TulsaPeople R66 calendar",
    },
    # ── September 2026 ─────────────────────────────────────────────────────
    {
        "name": "Cox Movie Night: Toy Story 4",
        "start": "2026-09-11", "end": "2026-09-11", "cadence": "single",
        "time": "Evening", "venue": "Gathering Place, 2650 S John Williams Way, Tulsa, OK 74114",
        "url": "https://www.gatheringplace.org/", "priority": 3,
        "short": "Free outdoor screening of Toy Story 4 on the lawn at Gathering Place.",
        "long": "Cox Movie Night brings a free outdoor screening of Toy Story 4 to Gathering Place. Bring blankets, snacks, and the whole crew for a easy night under the stars.",
        "confidence": "CONFIRMED", "note": "TulsaPeople / Gathering Place calendar",
    },
    {
        "name": "Art Crawl on 66 (Red Fork)",
        "start": "2026-09-11", "end": "2026-09-11", "cadence": "single",
        "time": "Evening", "venue": "Historic Red Fork District, Tulsa",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "The monthly Art Crawl lights up the historic Red Fork stretch of Route 66 with galleries, makers, and music.",
        "long": "Art Crawl on 66 turns the historic Red Fork District into a walkable evening of galleries, makers, and live music along Route 66. A laid-back, local night out on the Mother Road.",
        "confidence": "CONFIRMED", "note": "Recurring 2nd Friday; TulsaPeople R66 calendar",
    },
    {
        "name": "Tulsa Greek Festival",
        "start": "2026-09-17", "end": "2026-09-19", "cadence": "daily",
        "time": "11:00 AM - 10:00 PM", "venue": "Holy Trinity Greek Orthodox Church, 1222 S Guthrie Ave, Tulsa, OK 74119",
        "url": "https://tulsagreekfestival.com/", "priority": 3,
        "short": "Three days of gyros, baklava, live music, and folk dancing at the 66th annual Tulsa Greek Festival.",
        "long": "The Tulsa Greek Festival serves up three days of authentic Greek food, gyros, souvlaki, baklava, hot loukoumades, plus live music, folk dancing, church tours, and a Greek marketplace. One of the tastiest weekends of the Tulsa year.",
        "confidence": "CONFIRMED", "note": "tulsagreekfestival.com; verify exact address on official site",
    },
    {
        "name": "Scotfest Oklahoma (Final Year)",
        "start": "2026-09-18", "end": "2026-09-20", "cadence": "daily",
        "time": "All day", "venue": "Broken Arrow Events Park, 21101 E 101st St, Broken Arrow, OK 74014",
        "url": "https://www.okscotfest.com/", "priority": 3,
        "short": "Highland games, Celtic music, and clan villages for Scotfest's farewell year after nearly five decades.",
        "long": "Scotfest Oklahoma brings Highland games, Celtic bands, whisky tastings, and clan villages to Broken Arrow, and 2026 is billed as the final Scotfest after 46 years. If you have ever meant to go, this is your last call to catch the kilts and caber tosses.",
        "confidence": "CONFIRMED", "note": "okscotfest.com; flagged as final year",
    },
    {
        "name": "Curator-Led Tour: Roadside Abstractions",
        "start": "2026-09-20", "end": "2026-09-20", "cadence": "single",
        "time": "Afternoon", "venue": "Philbrook Museum of Art, 2727 S Rockford Rd, Tulsa, OK 74114",
        "url": "https://philbrook.org/", "priority": 3,
        "short": "A curator walks you through Philbrook's Route 66-inspired Roadside Abstractions.",
        "long": "Philbrook offers a curator-led tour of Roadside Abstractions, an exhibit riffing on Route 66 and the American road. A smart, unhurried way to see the show through an expert's eyes.",
        "confidence": "CONFIRMED", "note": "TulsaPeople R66 centennial calendar",
    },
    # ── October 2026 ───────────────────────────────────────────────────────
    {
        "name": "Tulsa State Fair",
        "start": "2026-10-01", "end": "2026-10-11", "cadence": "daily",
        "time": "All day", "venue": "Expo Square, 4145 E 21st St, Tulsa, OK 74114",
        "url": "https://www.tulsastatefair.com/", "priority": 3,
        "short": "Eleven days of rides, livestock, concerts, and absurdly good fair food at Oklahoma's biggest fair.",
        "long": "The Tulsa State Fair is Oklahoma's largest annual fair, eleven days of midway rides, livestock shows, concerts, contests, and every fried food you can imagine at Expo Square. Bring your appetite and your stretchy pants.",
        "confidence": "CONFIRMED", "note": "tulsastatefair.com / exposquare.com",
    },
    {
        "name": "Art Crawl on 66 (Red Fork)",
        "start": "2026-10-09", "end": "2026-10-09", "cadence": "single",
        "time": "Evening", "venue": "Historic Red Fork District, Tulsa",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "The monthly Art Crawl lights up the historic Red Fork stretch of Route 66 with galleries, makers, and music.",
        "long": "Art Crawl on 66 turns the historic Red Fork District into a walkable evening of galleries, makers, and live music along Route 66. A laid-back, local night out on the Mother Road.",
        "confidence": "CONFIRMED", "note": "Recurring 2nd Friday; TulsaPeople R66 calendar",
    },
    {
        "name": "Zeeco Oktoberfest Tulsa",
        "start": "2026-10-22", "end": "2026-10-25", "cadence": "daily",
        "time": "Afternoon - late", "venue": "River West Festival Park, 2100 S Jackson Ave, Tulsa, OK 74107",
        "url": "https://tulsaoktoberfest.org/", "priority": 3,
        "short": "Beer tents, Glockenspiel, the Dachshund Dash, and polka on the river at one of the nation's top Oktoberfests.",
        "long": "Zeeco Oktoberfest Tulsa (formerly Linde Oktoberfest) is a nationally ranked Oktoberfest on the Arkansas River, German beer and food, the Glockenspiel, the beloved Dachshund Dash, and nonstop polka in the big tents at River West Festival Park. Prost.",
        "confidence": "CONFIRMED", "note": "tulsaoktoberfest.org; sponsor rebranded Linde -> Zeeco for 2026",
    },
    {
        "name": "Boo Ha Ha in Brookside",
        "start": "2026-10-24", "end": "2026-10-24", "cadence": "single",
        "time": "Evening", "venue": "Brookside District, S Peoria Ave, Tulsa",
        "url": "https://www.tulsaboohaha.com/", "priority": 3,
        "short": "Brookside's beloved Halloween parade and street party takes over Peoria Avenue.",
        "long": "Boo Ha Ha is Brookside's beloved Halloween parade and street party along South Peoria, costumes, floats, and a whole district in on the fun. A Tulsa autumn tradition worth dressing up for.",
        "confidence": "ESTIMATED", "note": "Date ESTIMATED (usually late-Oct Saturday; 2025 was Oct 25). Re-verify on tulsaboohaha.com when 2026 posts.",
    },
    # ── November 2026 ──────────────────────────────────────────────────────
    {
        "name": "Route 66 Tulsa Birthday Bash & Veterans Day Parade",
        "start": "2026-11-11", "end": "2026-11-11", "cadence": "single",
        "time": "All day into evening", "venue": "Downtown Tulsa, concert finale at Cain's Ballroom, 423 N Main St, Tulsa, OK 74103",
        "url": "https://otrd.travelok.com/oklahoma-announces-plans-for-route-66-centennial-celebration-in-2026/", "priority": 2,
        "short": "The marquee Route 66 Centennial finale: a downtown celebration and Veterans Day parade capped by a concert at Cain's Ballroom.",
        "long": "The Route 66 Tulsa Birthday Bash is the signature finale of the Mother Road's 100th, music and performances across downtown on Veterans Day, paired with the Veterans Day parade and a headline concert at the legendary Cain's Ballroom. If you catch one centennial event, make it this one.",
        "confidence": "CONFIRMED", "note": "OTRD/TravelOK + TulsaPeople; marquee dated centennial event",
    },
    {
        "name": "Art Crawl on 66 (Red Fork)",
        "start": "2026-11-13", "end": "2026-11-13", "cadence": "single",
        "time": "Evening", "venue": "Historic Red Fork District, Tulsa",
        "url": "https://www.tulsapeople.com/about-town/route-66-centennial-events-in-tulsa-and-surrounding-areas/article_098457f8-0335-496f-ba71-29c6b1ef0f72.html", "priority": 3,
        "short": "The monthly Art Crawl lights up the historic Red Fork stretch of Route 66 with galleries, makers, and music.",
        "long": "Art Crawl on 66 turns the historic Red Fork District into a walkable evening of galleries, makers, and live music along Route 66. A laid-back, local night out on the Mother Road.",
        "confidence": "CONFIRMED", "note": "Recurring 2nd Friday; TulsaPeople R66 calendar",
    },
    {
        "name": "Arvest Winterfest (Downtown Ice Skating)",
        "start": "2026-11-27", "end": "2026-12-31", "cadence": "weekly",
        "time": "Evenings", "venue": "Outside BOK Center, 200 S Denver Ave, Tulsa, OK 74103",
        "url": "https://www.arvestwinterfest.com/", "priority": 3,
        "short": "Downtown's outdoor ice rink, ice slides, and holiday glow return under the Tulsa skyline.",
        "long": "Arvest Winterfest brings outdoor ice skating, ice slides, and holiday cheer to downtown beside the BOK Center, running from the day after Thanksgiving into early January. Lace up under the skyline for the most festive night out in town.",
        "confidence": "ESTIMATED", "note": "Dates ESTIMATED (day after Thanksgiving -> early Jan). Re-verify on arvestwinterfest.com.",
    },
    {
        "name": "Philbrook Festival (Holiday Lights)",
        "start": "2026-11-27", "end": "2026-12-31", "cadence": "weekly",
        "time": "Select nights", "venue": "Philbrook Museum of Art, 2727 S Rockford Rd, Tulsa, OK 74114",
        "url": "https://philbrook.org/visit/fundraising/festival/", "priority": 3,
        "short": "Philbrook's gardens glow with holiday lights, music, s'mores, and Santa on select nights.",
        "long": "The Philbrook Festival turns the museum's gardens into a holiday wonderland of lights and music on select nights, with Santa visits, s'mores, hot cocoa, and the Lego Villa. One of the prettiest ways to do the holidays in Tulsa.",
        "confidence": "ESTIMATED", "note": "Dates ESTIMATED (Thanksgiving week -> early Jan, select nights). Re-verify the night list on philbrook.org.",
    },
    {
        "name": "Rhema Christmas Lights",
        "start": "2026-11-24", "end": "2026-12-31", "cadence": "weekly",
        "time": "5:30 PM - 11:30 PM", "venue": "Rhema Bible Church, 1025 W Kenosha St, Broken Arrow, OK 74012",
        "url": "https://www.rhemalights.org/", "priority": 3,
        "short": "Millions of synchronized lights, train rides, and cocoa light up 110 acres in Broken Arrow, free every night.",
        "long": "Rhema Christmas Lights blankets 110 acres in Broken Arrow with millions of synchronized LED lights set to music, plus train rides and holiday treats, free every night from late November through New Year's Day. A jaw-dropping, kid-pleasing holiday must.",
        "confidence": "ESTIMATED", "note": "Dates ESTIMATED (Tue before Thanksgiving -> Jan 1). Re-verify on rhemalights.org.",
    },
]


def _expand(spec):
    start = date.fromisoformat(spec["start"])
    end = date.fromisoformat(spec["end"])
    cadence = spec.get("cadence", "single")
    out = []
    if cadence == "single":
        days = [start]
    elif cadence == "daily":
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    elif cadence == "weekly":
        days, d = [], start
        while d <= end:
            days.append(d)
            d += timedelta(days=7)
    else:
        raise ValueError(f"bad cadence {cadence!r} for {spec['name']}")

    for d in days:
        out.append({
            "name": spec["name"],
            "date": d.isoformat(),
            "time": spec.get("time", ""),
            "venue": spec.get("venue", ""),
            "description": spec["short"],
            "website_description": spec["long"],
            "url": spec.get("url", ""),
            "priority": spec.get("priority", 3),
            "source_note": f"{spec.get('confidence','')}: {spec.get('note','')} | built {date(2026,6,5).isoformat()} via build_major_events.py",
        })
    return out


def main():
    events = []
    for spec in SPEC:
        events.extend(_expand(spec))
    events.sort(key=lambda e: (e["date"], e["name"]))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(events)} expanded entries from {len(SPEC)} specs -> {OUT_PATH}")
    by_conf = {}
    for spec in SPEC:
        by_conf[spec.get("confidence", "?")] = by_conf.get(spec.get("confidence", "?"), 0) + 1
    print("Specs by confidence:", by_conf)


if __name__ == "__main__":
    main()
