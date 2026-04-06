"""Generate this week's carousel slides (Apr 6-12, 2026).

COMC gets Slide 2 (Event of the Week) per William's special instruction.
HHHH was April 3 (last week). This week: COMC rehearsal + spring concert promo.
"""
import sys, os
sys.path.insert(0, '.')
from content.image_maker import create_carousel, save_carousel

event_of_week = {
    "name": "Council Oak Men's Chorale",
    "date": "Monday, April 6 (Rehearsal) + Concert April 23",
    "time": "Rehearsal: 6:50 - 9:00 PM",
    "venue": "All Souls Unitarian, 2952 S Peoria Ave",
    "description": "Tulsa's gay men's chorus is gearing up for their spring concert 'Cabaret: Here Comes the Sun' on April 23. Monday rehearsals are open to new singers. Gay and affirming men of all experience levels welcome. This is community.",
    "url": "counciloak.org",
}

events_by_day = {
    "Monday": [
        {"name": "COMC Chorus Rehearsal", "time": "6:50 - 9:00 PM", "venue": "All Souls Unitarian, 2952 S Peoria", "description": "Tulsa's gay men's chorus rehearses every Monday. Spring concert April 23. New singers always welcome. Show up and find your people.", "url": "counciloak.org/get-involved"},
        {"name": "Lambda Bowling League", "time": "7:00 - 9:00 PM", "venue": "AMF Sheridan Lanes, 3121 S Sheridan", "description": "Tulsa's LGBTQ+ bowling league rolls every Monday. IGBO-affiliated. All skill levels. The most fun you can have on a Monday night. Show up at 7.", "url": "facebook.com/groups/4177858394"},
        {"name": "Yellow Brick Road Opens", "time": "6:00 PM", "venue": "YBR, 2630 E 15th St", "description": "One of the last lesbian bars in the country opens its doors Monday at 6 PM. Pool, darts, cheap drinks, good people. Start your week right.", "url": "facebook.com/YBRTulsa"},
    ],
    "Tuesday": [
        {"name": "OSU Tulsa Queer Support Group", "time": "6:00 PM", "venue": "OSU Tulsa Campus, 700 N Greenwood", "description": "Free, open to all adults every Tuesday at 6 PM. Real people talking about real stuff in a safe, welcoming space. You don't have to be a student.", "url": "events.tulsa.okstate.edu"},
        {"name": "Mamma Mia! (Broadway Tour)", "time": "7:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "ABBA on a Broadway stage in Tulsa. The touring production runs all week. This is the gay cultural event of the season. Book tickets now.", "url": "ticketmaster.com"},
        {"name": "Karaoke Night at the Eagle", "time": "Evening", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Every Tuesday at the Eagle. Sing your heart out on the patio. The worse you are, the louder they cheer. Open from 2 PM.", "url": "facebook.com/TheTulsaEagle"},
    ],
    "Wednesday": [
        {"name": "Queer Women's Collective", "time": "Evening", "venue": "Equality Center, 621 E 4th St", "description": "First Wednesday monthly. One of the best gatherings in Tulsa for queer women and femmes. Low-key, welcoming, genuinely fun. Come meet your people.", "url": "facebook.com/queerwomenscollectivetulsa"},
        {"name": "Gender Support Group", "time": "7:00 - 8:30 PM", "venue": "Equality Center, 621 E 4th St", "description": "Free weekly support for trans, nonbinary, and gender-questioning folks. Private, confidential, run by OKEQ. No judgment. Just people who get it.", "url": "okeq.org/transgender-support"},
        {"name": "Eagle Underwear Night", "time": "Evening", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Every Wednesday. Confidence required. Pants optional. Open from 2 PM if you need to warm up. The patio vibes are always right.", "url": "facebook.com/TheTulsaEagle"},
    ],
    "Thursday": [
        {"name": "DRAGNIFICENT!", "time": "Doors 9PM, Show 11PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Tulsa's weekly Thursday drag institution hosted by Shanel Sterling. Rotating performers who come to slay. 18+ ($8/$4 cover). Every Thursday. No excuses.", "url": "downtowntulsa.com/do/dragnificent-at-club-majestic-1"},
        {"name": "Relationships Outside the Box", "time": "7:00 - 8:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "First Thursday monthly. OKEQ's support group for people in non-traditional relationships. Polyamory, open, whatever your structure. Zero judgment.", "url": "okeq.org/okeq-events/relationships-outside-the-box"},
        {"name": "GWAR at Cain's Ballroom", "time": "7:30 PM", "venue": "Cain's Ballroom, 423 N Main St", "description": "GWAR's 'Gor Gor Strikes Back' tour with Soulfly and King Parrot. All ages. Theatrical, chaotic, unforgettable. Wear clothes you don't mind getting wet. $63+.", "url": "cainsballroom.com"},
    ],
    "Friday": [
        {"name": "Mamma Mia! Friday Night Show", "time": "8:00 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Friday night is the perfect time to catch Mamma Mia! on Broadway. ABBA, sequins, a wild story. This is the big night out of the week. Get tickets before they're gone.", "url": "ticketmaster.com"},
        {"name": "Girl Dinner at Inheritance Kitchen", "time": "6:00 - 10:00 PM", "venue": "Inheritance Kitchen, 108 S Detroit Ave", "description": "Friday night at one of Tulsa's most stunning plant-based restaurants. Beautiful food, beautiful space, perfect date night energy downtown.", "url": "inheritancejuicery.com"},
        {"name": "Tulsa Oilers vs Idaho Steelheads", "time": "7:05 PM", "venue": "BOK Center, 200 S Denver Ave", "description": "Professional hockey at BOK Center. Fast, fun, and affordable. The queer community loves Oilers nights. 7:05 PM puck drop.", "url": "tulsaoilers.com"},
    ],
    "Saturday": [
        {"name": "Elote Drag Brunch: Drag Me to Church", "time": "11:00 AM + 1:30 PM", "venue": "Elote Cafe, 514 S Boston Ave", "description": "The queens are ready to preach, pray, and slay. Two seatings. Glitter as gospel, brunch as blessing. Get tickets on Eventbrite NOW -- this sells out every time.", "url": "eventbrite.com"},
        {"name": "PFLAG Tulsa Monthly Meeting", "time": "7:00 PM", "venue": "110 S Hartford Ave", "description": "For parents, siblings, partners, and family of LGBTQ+ people. And for anyone who wants a room full of people who chose love. Free. First Saturday.", "url": "pflag.org/chapter/pflag-tulsa"},
        {"name": "Cherry Street Farmers Market", "time": "7:00 - 11:00 AM", "venue": "15th Street, Cherry Street District", "description": "Season opens! Fresh produce, local meats, artisan bread, plants, flowers, live music. Two city blocks of Tulsa goodness. Get there early.", "url": "tulsafarmersmarket.org"},
    ],
    "Sunday": [
        {"name": "All Souls Unitarian Services", "time": "10:00 AM + 11:15 AM", "venue": "All Souls, 2952 S Peoria Ave", "description": "The largest UU congregation in the US. LGBTQ+ affirming since forever. Sunday services at 10 and 11:15. First-timers welcomed warmly. Walk in as you are.", "url": "allsoulschurch.org"},
        {"name": "Sunday Showdown Open Talent Night", "time": "9:00 PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Close out your week on the most electric possible note. Open talent night at Club Majestic until midnight. Come watch, come perform. 18+.", "url": "clubmajestictulsa.com"},
        {"name": "Mamma Mia! Final Shows", "time": "1:00 PM + 6:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Last chance to see Mamma Mia! before it leaves Tulsa. Two shows Sunday. ABBA. Broadway. Your last shot. Don't let it slip away.", "url": "ticketmaster.com"},
    ],
}

# events_by_category kept for API compatibility (featured_event overrides HHHH logic)
events_by_category = {}

slides = create_carousel(
    events_by_category=events_by_category,
    post_type="weekday",
    date_range="April 6 - 12, 2026",
    events_by_day=events_by_day,
    featured_event=event_of_week,
)

output = os.path.join("docs", "images", "weekly")
paths = save_carousel(slides, output)
print(f"Generated {len(paths)} slides:")
for p in paths:
    print(f"  {os.path.basename(p)}")
