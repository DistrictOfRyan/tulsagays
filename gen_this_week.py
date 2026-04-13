"""Generate this week's carousel slides (Apr 13-19, 2026).

EOTW: Orbit Arts Festival — FREE local arts day at TPAC, Sat Apr 18.
Upcoming Featured Event: COMC Cabaret "Here Comes the Sun" — Apr 23.
No Elote Drag Brunch this week (that's 2nd Saturday — was Apr 11).
"""
import sys, os
sys.path.insert(0, '.')
from content.image_maker import create_carousel, save_carousel

event_of_week = {
    "name": "Orbit Arts Festival",
    "date": "2026-04-18",
    "time": "10:00 AM - 5:00 PM",
    "venue": "Tulsa Performing Arts Center",
    "description": "40+ local artists, FREE, open to all. Live music, dance, theatre, spoken word, visual art, and interactive activities fill the TPAC lobbies and stages all day. This is Tulsa showing off what it's made of. No ticket needed. Just show up.",
    "url": "https://tulsapac.com/orbit-arts-festival",
}

upcoming_featured = {
    "name": "COMC Cabaret: Here Comes the Sun",
    "date": "2026-04-23",
    "time": "7:00 PM",
    "venue": "Lynn Riggs Theater at the Equality Center",
    "hype": "The men of Council Oak Men's Chorale trade the risers for rhinestones — solos, duets, and show-stopping harmony wrapped in golden vibes. VIP 4-top tables with charcuterie, or general admission. Either way, bring applause and sunshine energy.",
    "url": "https://counciloak.org/concerts",
    "image_path": "assets/comc_cabaret_hcts.jpg",
}

events_by_day = {
    "Monday": [
        # FEATURED: Lambda Bowling — most consistent queer Monday in Tulsa
        {"name": "Lambda Bowling League", "time": "7:00 - 9:00 PM", "venue": "AMF Sheridan Lanes, 3121 S Sheridan", "description": "Tulsa's most consistent queer gathering — years of Monday bowling, all skill levels, zero pretense. Gay bowling night every single Monday. You don't have to be good. You just have to show up.", "url": "https://www.facebook.com/groups/4177858394"},
        {"name": "Monday Night Jazz", "time": "8:00 - 11:00 PM", "venue": "Vintage Wine Bar, Tulsa", "description": "Live jazz on a Monday at one of Tulsa's most welcoming spots. Low-key, good drinks, warm crowd. A genuinely good reason to leave the house on a Monday.", "url": "https://www.downtowntulsa.com/do/monday-night-jazz"},
        {"name": "Tulsa Eagle Monday Night", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Tulsa's leather and bear bar on a Monday — drink specials, no attitude, patio is always the move. Low-key and welcoming every single day.", "url": "https://www.facebook.com/TheTulsaEagle"},
        {"name": "OKEQ Health Clinic", "time": "9:00 AM - 4:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "LGBTQ+ affirming healthcare, STI testing, and PrEP access at the Equality Center. Appointments required 24 hours in advance. This is what queer-centered healthcare feels like.", "url": "https://okeq.org/programs"},
    ],
    "Tuesday": [
        # FEATURED: Tulsa Drillers baseball — casual queer-friendly community outing
        {"name": "Tulsa Drillers vs Arkansas Travelers", "time": "12:00 PM", "venue": "ONEOK Field, Tulsa", "description": "Afternoon Double-A baseball at one of the best minor league ballparks in the country. Cheap seats, good food, the kind of midday Tuesday that beats sitting at your desk. Queer fans have always loved a Drillers game.", "url": "https://www.milb.com/tulsa"},
        {"name": "Tuesday Open Mic at Gypsy Coffee House", "time": "7:00 - 9:00 PM", "venue": "Gypsy Coffee House, Tulsa", "description": "One of the most genuinely welcoming stages in Tulsa — all genres, all levels, all ages. Come to perform or just come to listen. Queer artists have always had a home here.", "url": "https://www.downtowntulsa.com/do/tuesday-night-open-mic"},
        {"name": "Jazz Night at The Bend Mercantile", "time": "7:00 - 9:00 PM", "venue": "The Bend Mercantile, Tulsa", "description": "Live jazz in one of Tulsa's coolest intimate spaces. Good drinks, good vibes, great midweek energy. Bring a date or come solo — the crowd always makes space.", "url": "https://www.downtowntulsa.com/do/jazz-night-at-the-bend"},
        {"name": "Karaoke at the Eagle", "time": "8:00 PM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "The Eagle's Tuesday karaoke crowd cheers louder when you're bad, which means the bar is zero and the fun is unlimited. Pick something you half-know and commit fully.", "url": "https://www.facebook.com/TheTulsaEagle"},
    ],
    "Wednesday": [
        # FEATURED: Inspyral Circus Jam — free outdoor community event at Guthrie Green
        {"name": "Inspyral Circus Jam", "time": "6:30 - 8:30 PM", "venue": "Guthrie Green, Tulsa", "description": "Free, outdoors, weird in the best way. Flow arts, juggling, hoop spinning, aerial silks — skill share in a park with the whole city invited. The kind of Wednesday that reminds you Tulsa is genuinely interesting.", "url": "https://www.downtowntulsa.com/do/inspyral-circus-jam"},
        {"name": "Drew & Ellie Holcomb at Tulsa Theater", "time": "8:00 PM", "venue": "Tulsa Theater, 105 W Reconciliation Way", "description": "Drew and Ellie Holcomb bring the Never Gonna Let You Go Tour to Tulsa Theater, their gorgeous 20-year journey distilled into one night of folk-Americana warmth. Celebrating their Memory Bank album. One of the most intimate and beautiful rooms in town.", "url": "https://tulsatheater.com"},
        {"name": "Evan Honer: It's A Long Road Tour", "time": "7:30 PM", "venue": "Cain's Ballroom, 423 N Main St", "description": "Evan Honer brings the It's A Long Road Tour to the most storied ballroom in Oklahoma, with Timmy Skelly. All ages. Cain's on a Wednesday with a good touring artist is a reliable good night.", "url": "https://www.cainsballroom.com"},
        {"name": "Gender Support Group", "time": "7:00 - 8:30 PM", "venue": "Equality Center, 621 E 4th St", "description": "Support, education, and community for transgender and intersex individuals at the Equality Center. Specialized breakout sessions. Every Wednesday, free, affirming.", "url": "https://okeq.org/event-calendar"},
    ],
    "Thursday": [
        # FEATURED: DRAGNIFICENT! — every Thursday, no excuses
        {"name": "DRAGNIFICENT!", "time": "Doors 9 PM, Show 11 PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Hosted by Shanel Sterling, rotating queens, every single Thursday. $8 cover, 18+. Tulsa's most reliable drag night in the best LGBTQ+ venue downtown. Get there before midnight for the best sets.", "url": "https://downtowntulsa.com/do/dragnificent-at-club-majestic-1"},
        {"name": "Molly Tuttle at Cain's Ballroom", "time": "Doors 6:30, Show 7:30 PM", "venue": "Cain's Ballroom, 423 N Main St", "description": "Grammy-winning singer-songwriter and flat-picking guitar prodigy Molly Tuttle live at Cain's. Bluegrass with soul and serious chops. Start the night here, then walk down to Club Majestic after.", "url": "https://www.cainsballroom.com"},
        {"name": "A Dozen Loops — Opening Night", "time": "6:00 - 8:00 PM", "venue": "Woody Guthrie Folk Music Center", "description": "Member opening night for a new exhibition at the Woody Guthrie Center in the Arts District. Free, intimate, the kind of Thursday evening that Tulsa's creative community does really well.", "url": "https://www.downtowntulsa.com/do/a-dozen-loops--member-opening"},
        {"name": "Club Craft at Welltown Brewing", "time": "6:00 - 9:00 PM", "venue": "Welltown Brewing, Tulsa", "description": "Crafting meets craft beer — bring whatever you're working on, grab a pint, make things with people. The queer craft crowd always shows up. No skill required, just curiosity.", "url": "https://www.downtowntulsa.com/do/club-craft"},
    ],
    "Friday": [
        # FEATURED: Cosmic Chemistry — queer women's astrological matchmaking at YBR
        {"name": "Cosmic Chemistry: Queer Women's Matchmaking", "time": "8:00 - 11:30 PM", "venue": "YBR Pub, 2630 E 15th St", "description": "Opal & Onyx Co. brings astrological matchmaking to the sapphic community. Submit your birth date, meet up to 3 cosmic matches, DJ KATNIP spins while you flirt. YBR is one of the last dedicated lesbian bars in the US. 21+, $23.", "url": "https://www.eventbrite.com/e/cosmic-chemistry-a-queer-womens-astrological-matchmaking-experience-ybr-tickets-1985031022223"},
        {"name": "Tulsa Oilers vs Kansas City Mavericks", "time": "7:05 PM", "venue": "BOK Center, 200 S Denver Ave", "description": "ECHL hockey at BOK Center — the Oilers host KC in what's become a weekly queer community outing. Fast, fun, affordable. The gay section of BOK is real and it is glorious.", "url": "https://www.tulsaoilers.com"},
        {"name": "Club Majestic Friday Night", "time": "9:00 PM - 2:00 AM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Tulsa's LGBTQ+ nightclub doing what it does on a Friday. DJ sets, dancing, the whole thing. Check their calendar for any themed nights or special events.", "url": "https://www.clubmajestictulsa.com"},
        {"name": "Tulsa Eagle Friday Night", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "The Eagle patio on a Friday is one of Tulsa's most reliably good gay experiences. Low effort, high reward. Show up, grab a drink, see who you see.", "url": "https://www.facebook.com/TheTulsaEagle"},
    ],
    "Saturday": [
        # EOTW is always first on its day
        {"name": "Orbit Arts Festival", "time": "10:00 AM - 5:00 PM", "venue": "Tulsa PAC, 2nd Street Lobbies", "description": "FREE all-day arts festival with 40+ local artists. Live music, dance, theatre, spoken word, visual art, workshops, face painting, and activities for all ages. Avery Marshall, Rising Buffalo Dance Group, Talk of Tulsa Show Chorus, Tulsa Youth Symphony. No ticket needed.", "url": "https://tulsapac.com/orbit-arts-festival"},
        {"name": "Club Majestic Saturday Night", "time": "9:00 PM - 2:00 AM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Saturday night at Tulsa's flagship LGBTQ+ club. DJ sets, dancing, the community showing up for itself. Cap a big day at the festival with a big night downtown.", "url": "https://www.clubmajestictulsa.com"},
        {"name": "Wildin With Wallie — Aries Bash", "time": "10:00 PM", "venue": "Casa Roma Event Center, 747 N Utica Ave", "description": "DJ WallieMayne throws down an Aries birthday bash — dancing, vibes, good energy for Aries season going out right. 18+.", "url": "https://www.eventbrite.com/e/wildin-with-wallie-aries-bash-tickets-1986168330944"},
        {"name": "Tulsa Eagle Saturday", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "The Eagle on a Saturday is a full-day affair from afternoon patio drinks to late-night regulars inside. One of the best queer spaces in Oklahoma.", "url": "https://www.facebook.com/TheTulsaEagle"},
    ],
    "Sunday": [
        # FEATURED: Sunday Showdown — open talent night to close the week
        {"name": "Sunday Showdown Open Talent Night", "time": "9:00 PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Open talent night at Club Majestic — perform or come watch, 18+. Host Shanel Sterling with Scrappy Legacy and Londenn Davenport Raine spotlighting Tulsa's rising talent. Don't go home early on a Sunday.", "url": "https://www.clubmajestictulsa.com"},
        {"name": "Pulse & Paint: Brushes, Beats & Brews", "time": "3:00 PM", "venue": "Dead Armadillo Craft Brewing, Tulsa", "description": "Afternoon paint event with live music and craft beer at one of Tulsa's best local breweries. The kind of Sunday that actually feels restorative instead of just surviving until Monday.", "url": "https://www.eventbrite.com/e/pulse-paint-brushes-beats-and-brews-tickets-1986565531983"},
        {"name": "All Souls Unitarian Services", "time": "10:00 AM + 11:15 AM", "venue": "All Souls, 2952 S Peoria Ave", "description": "Largest UU congregation in the US, queer-affirming since before it was a selling point. Walk in alone and walk out feeling like you belong somewhere in this city.", "url": "https://allsoulschurch.org"},
        {"name": "Tulsa Eagle Sunday", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Sunday funday at the Eagle — lower-key than Saturday but the patio is still the patio. Wrap the week right.", "url": "https://www.facebook.com/TheTulsaEagle"},
    ],
}

events_by_category = {}

slides = create_carousel(
    events_by_category=events_by_category,
    post_type="weekday",
    date_range="April 13 - 19, 2026",
    events_by_day=events_by_day,
    featured_event=event_of_week,
    upcoming_event=upcoming_featured,
)

output = os.path.join("docs", "images", "weekly")
paths = save_carousel(slides, output)
print(f"Generated {len(paths)} slides:")
for p in paths:
    print(f"  {os.path.basename(p)}")
