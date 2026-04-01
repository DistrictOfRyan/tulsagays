"""Generate this week's carousel slides (Apr 1-6, 2026)."""
import sys, os
sys.path.insert(0, '.')
from content.image_maker import create_weekly_carousel, save_carousel

event_of_week = {
    "name": "Homo Hotel Happy Hour",
    "date": "Friday, April 4",
    "time": "6:00 - 8:00 PM",
    "venue": "wxyz bar, Aloft Tulsa Downtown",
    "description": "The best networking event in queer Tulsa, period. Drink specials, a gorgeous lobby bar, and every dollar supports local LGBTQ charities. If you only go to one thing this week, make it this.",
    "url": "meetup.com/homo-hotel-happy-hour",
}

daily_events = {
    "monday": ("March 31", [
        {"name": "Lambda Bowling League", "time": "7:00 - 9:00 PM", "venue": "AMF Sheridan Lanes", "description": "The most fun you can have on a Monday night. All skill levels welcome, nobody cares if you bowl a 60. It's about the people.", "url": "facebook.com/groups/4177858394"},
        {"name": "Smart Recovery (online)", "time": "6:30 PM", "venue": "Virtual", "description": "Evidence-based recovery support from the comfort of your home. No labels, no steps, just science and community. Free.", "url": "okeq.org/event-calendar"},
        {"name": "Plan Your Queer Week", "time": "Morning", "venue": "tulsagays.com", "description": "New events drop every Monday. Bookmark tulsagays.com and never miss what happens in your community.", "url": "tulsagays.com"},
    ]),
    "tuesday": ("April 1", [
        {"name": "OSU Tulsa Queer Support Group", "time": "6:00 PM", "venue": "OSU Tulsa Campus", "description": "Free, open to all adults. A safe weekly space to talk about what it means to be queer in Oklahoma right now.", "url": "events.tulsa.okstate.edu"},
        {"name": "Tulsa Artist Fellowship Studios", "time": "Afternoon", "venue": "Downtown Tulsa", "description": "Drop in and see what Tulsa artists are creating this week. Free, walkable, and always something unexpected on the walls.", "url": "tulsaartistfellowship.org"},
        {"name": "Gathering Place Evening Walk", "time": "5:00 - 7:00 PM", "venue": "Gathering Place", "description": "Tulsa's best park is gorgeous at sunset. Grab a friend, walk the trails, decompress. Free and inclusive.", "url": "gatheringplace.org"},
    ]),
    "wednesday": ("April 2", [
        {"name": "Queer Women's Collective", "time": "5:00 - 6:30 PM", "venue": "Equality Center", "description": "Low-key, no-pressure way to meet other LGBTQ+ women in Tulsa. Show up, grab a drink, make a friend. First Wednesdays only.", "url": "okeq.org/event-calendar"},
        {"name": "Tulsa Leather Community", "time": "6:30 - 8:30 PM", "venue": "Equality Center", "description": "Judgment-free education and connection for the leather community. Curious or experienced, safest room in Tulsa to ask questions.", "url": "okeq.org/event-calendar"},
        {"name": "Gender Support Group", "time": "7:00 - 8:30 PM", "venue": "Equality Center", "description": "Real talk with people who actually get it. Breakout sessions for trans and intersex folks navigating life in Oklahoma.", "url": "okeq.org/transgender-support"},
    ]),
    "thursday": ("April 3", [
        {"name": "Queer Crafters Club", "time": "6:00 - 8:00 PM", "venue": "Equality Center Gallery", "description": "Bring whatever you are working on and make stuff alongside other queer creatives. The gallery space is beautiful.", "url": "okeq.org/event-calendar"},
        {"name": "Relationships Outside the Box", "time": "7:00 - 8:00 PM", "venue": "Equality Center", "description": "A rare, honest space for people in non-traditional relationships. No judgment, just real conversation about how love works.", "url": "okeq.org/event-calendar"},
        {"name": "DRAGNIFICENT! at Club Majestic", "time": "Doors 9PM, Show 11PM", "venue": "124 N Boston Ave", "description": "Tulsa's legendary Thursday drag show hosted by Shanel Sterling. Local queens, visiting talent, and energy you can't get from Netflix.", "url": "downtowntulsa.com/do/dragnificent"},
    ]),
    "friday": ("April 4", [
        {"name": "Homo Hotel Happy Hour", "time": "6:00 - 8:00 PM", "venue": "Aloft Downtown", "description": "First Friday edition. The lobby bar fills up fast with the best crowd in Tulsa. Drink specials benefit LGBTQ charities.", "url": "meetup.com/homo-hotel-happy-hour"},
        {"name": "Anthony Corraro Gallery Opening", "time": "6:00 - 8:00 PM", "venue": "Equality Center", "description": "Portraits of real LGBTQ+ community members by a seriously talented artist. Free, beautiful, perfect First Friday stop.", "url": "okeq.org/event-calendar"},
        {"name": "First Friday Art Crawl", "time": "6:00 - 9:00 PM", "venue": "Downtown Arts District", "description": "Tulsa's best free night out. Dozens of galleries, live music everywhere, the whole Arts District comes alive. Bring a date.", "url": "thetulsaartsdistrict.org"},
    ]),
    "saturday": ("April 5 - Easter Eve", [
        {"name": "Eggstravaganza at Guthrie Green", "time": "10:00 AM - 12:00 PM", "venue": "111 E Reconciliation Way", "description": "Free Easter egg hunt downtown with music, food trucks, face painting, and prizes. Bring the whole crew. All ages.", "url": "downtowntulsa.com"},
        {"name": "Spring With the Bunny at Tulsa Zoo", "time": "9:00 AM - 12:00 PM", "venue": "Tulsa Zoo", "description": "Easter Bunny meet and greets, animal chats, and crafts. Free with zoo admission. Perfect morning out.", "url": "tulsazoo.org"},
        {"name": "PFLAG Tulsa", "time": "7:00 PM", "venue": "110 S Hartford Ave", "description": "For parents figuring out how to support their kid, or anyone who wants a room full of people who chose love over fear.", "url": "pflag.com/chapter/pflag-tulsa"},
    ]),
    "sunday": ("April 6 - Easter Sunday", [
        {"name": "All Souls Easter Service + Egg Hunt", "time": "10:00 AM + 11:15 AM", "venue": "2952 S Peoria Ave", "description": "The largest UU church in America. Easter service, then an egg hunt on the west playground at 11:15. Bring a basket. All welcome.", "url": "allsoulschurch.org/easter"},
        {"name": "Philbrook Art in Bloom", "time": "9:00 AM - 5:00 PM", "venue": "2727 S Rockford Rd", "description": "The museum and gardens are stunning on Easter. Special floral installations throughout. Dress up, bring a date, take pictures.", "url": "philbrook.org"},
        {"name": "Club Majestic Sunday Showcase", "time": "Evening", "venue": "124 N Boston Ave", "description": "Easter drag. Tulsa's emerging talent takes the stage hosted by Shanel Sterling. Big energy to close out the holiday.", "url": "facebook.com/clubmajestictulsa"},
    ]),
}

slides = create_weekly_carousel(event_of_week, daily_events, "March 31 - April 6, 2026")
output = os.path.join("docs", "images", "weekly")
paths = save_carousel(slides, output)
print(f"Generated {len(paths)} slides:")
for p in paths:
    print(f"  {os.path.basename(p)}")
