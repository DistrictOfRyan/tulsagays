"""Generate this week's carousel slides (Apr 6-12, 2026).

EOTW: Sex & Violence — local drag/burlesque/wrestling show, Sat Apr 11.
Upcoming Featured Event: COMC Cabaret "Here Comes the Sun" — Apr 23.
HHHH was April 3 (last week, already passed).
"""
import sys, os
sys.path.insert(0, '.')
from content.image_maker import create_carousel, save_carousel

event_of_week = {
    "name": "Sex & Violence",
    "date": "2026-04-11",
    "time": "5:00 PM",
    "venue": "The Property Event Center, Tulsa",
    "description": "Drag. Burlesque. Pro wrestling. Tattoos, piercings, food, drinks. A full night of chaos, community, and celebration. This is the kind of Saturday Tulsa doesn't always let you have. Go.",
    "url": "https://www.eventbrite.com/e/sex-violence-tickets-1979239616974",
}

upcoming_featured = {
    "name": "COMC Cabaret: Here Comes the Sun",
    "date": "2026-04-23",
    "time": "7:00 PM",
    "venue": "Lynn Riggs Theater at the Equality Center",
    "hype": "The men of Council Oak Men's Chorale trade the risers for rhinestones — solos, duets, and show-stopping harmony wrapped in golden vibes. VIP 4-top tables with charcuterie, or general admission. Either way, bring applause and sunshine energy.",
    "url": "counciloak.org/concerts",
    "image_path": "assets/comc_cabaret_hcts.jpg",
}

events_by_day = {
    "Monday": [
        {"name": "Lambda Bowling League", "time": "7:00 - 9:00 PM", "venue": "AMF Sheridan Lanes, 3121 S Sheridan", "description": "Tulsa's most consistent queer gathering — years of Monday bowling, all skill levels, zero pretense. Gay bowling night every single Monday. You don't have to be good. You just have to show up.", "url": "facebook.com/groups/4177858394"},
        {"name": "Lambda Unity Group (LGBTQ+ AA)", "time": "8:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "Confidential, queer-affirming AA meeting every Monday at the Equality Center. Exists specifically because recovery looks different when you're navigating queer life. It's here every week.", "url": "okeq.org"},
        {"name": "Slaughter to Prevail at Tulsa Theater", "time": "6:30 PM", "venue": "Tulsa Theater, 105 W Reconciliation Way", "description": "Metal has always had a massive queer following — Slaughter to Prevail with Whitechapel and Attila at Tulsa Theater tonight. Wear black, protect your ears, arrive ready to scream something out of your body.", "url": "tulsatheater.com"},
        {"name": "Tulsa Eagle Monday Night", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Tulsa's leather and bear bar is open every day and Monday drink specials are worth showing up for. Low-key, welcoming, no attitude. The patio is the move.", "url": "facebook.com/TheTulsaEagle"},
        {"name": "Soundpony Bar", "time": "3:00 PM - 2:00 AM", "venue": "The Soundpony, 409 N Main St", "description": "Gay-friendly Arts District dive bar open nightly — check their calendar for Monday DJ sets or live music. Cheap drinks, good people, weird decor. Classic Tulsa.", "url": "thesoundpony.com"},
        {"name": "Arnie's Bar", "time": "12:00 PM - 2:00 AM", "venue": "Arnie's Bar, 318 E 2nd St", "description": "Gay-friendly dive bar one block from Club Majestic, open daily with drink specials. The kind of bar that doesn't need a theme night to be a good time.", "url": "arniesbar.com"},
        {"name": "OKEQ Health Clinic", "time": "Business hours — call to confirm", "venue": "Equality Center, 621 E 4th St", "description": "LGBTQ+ affirming healthcare, STI testing, and PrEP access at the Equality Center. Walk-ins welcome. This is what having queer-centered healthcare feels like.", "url": "okeq.org/programs"},
    ],
    "Tuesday": [
        {"name": "Trivia at American Solera", "time": "7:00 PM", "venue": "American Solera Brewery, Tulsa", "description": "Tuesday trivia at one of Tulsa's best craft breweries. Competitive crowd, good beer, teams up to 6. The kind of Tuesday that actually feels like something.", "url": "americansolera.com"},
        {"name": "Mamma Mia! (Broadway Tour)", "time": "7:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "A full Broadway touring company performing ABBA live on a Tulsa stage. Sequins encouraged, crying during Slipping Through My Fingers mandatory. Dress up, get there early for lobby drinks.", "url": "ticketmaster.com"},
        {"name": "OSU Tulsa Queer Support Group", "time": "6:00 PM", "venue": "OSU Tulsa, 700 N Greenwood", "description": "Free, open to all adults, no student ID. Real people having real conversations in a room that was built to feel safe — rarer in Tulsa than it should be. Show up as you are.", "url": "events.tulsa.okstate.edu"},
        {"name": "Karaoke Night at the Eagle", "time": "8:00 PM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "The Eagle's Tuesday karaoke crowd cheers louder when you're bad, which means the bar is zero and the fun is unlimited. Pick something you half-know and commit fully.", "url": "facebook.com/TheTulsaEagle"},
        {"name": "108 Contemporary: Shawn Smith", "time": "11:00 AM - 6:00 PM", "venue": "108 Contemporary, 108 E M.B. Brady St", "description": "Shawn Smith: Entangled Ecologies runs April 3-May 23 — immersive sculptural work at one of Tulsa's best contemporary craft galleries. Free admission. Brady Arts District, right where you want to be.", "url": "108contemporary.org"},
        {"name": "Woody Guthrie Center", "time": "10:00 AM - 5:00 PM", "venue": "102 E Reconciliation Way", "description": "The folk legend who told Dust Bowl refugees they belonged somewhere. Queer people have always claimed Woody. Tucked in the Arts District, worth an hour of your afternoon.", "url": "woodyguthriecenter.org"},
        {"name": "Trivia at American Solera", "time": "7:00 PM", "venue": "American Solera Brewery, Tulsa", "description": "Tuesday trivia at one of Tulsa's best craft breweries. Competitive crowd, good beer, teams up to 6. The kind of Tuesday that actually feels like something.", "url": "americansolera.com"},
        {"name": "PFLAG Tulsa Meeting", "time": "7:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "PFLAG Tulsa meets monthly — support, education, and advocacy for LGBTQ+ people and their families. Check tulsapflag.org to confirm this is the April date. If your family needs this, it's here.", "url": "tulsapflag.org"},
        {"name": "Soundpony Tuesday Night", "time": "3:00 PM - 2:00 AM", "venue": "The Soundpony, 409 N Main St", "description": "Gay-friendly Arts District bar with frequent Tuesday trivia or live music on the calendar. Cheap, cheerful, and steps from everything downtown.", "url": "thesoundpony.com"},
        {"name": "OKEQ Health Clinic", "time": "9:00 AM - 4:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "LGBTQ+ affirming healthcare by appointment — Blue Cross/Blue Shield accepted plus self-pay. STI testing, PrEP, primary care. Call 918-938-6537 or schedule online.", "url": "okeq.org/programs"},
        {"name": "OKEQ Seniors", "time": "10:00 AM - 12:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "LGBTQ+ elders program every Tuesday morning — advocacy, support, community, and a room full of queer adults who have survived everything and are still here. Free.", "url": "okeq.org"},
    ],
    "Wednesday": [
        {"name": "Stitched Up Heart at The Vanguard", "time": "Doors 7 PM, Show 8 PM", "venue": "The Vanguard, 222 N Main St", "description": "Rock band Stitched Up Heart performing live at The Vanguard in the Arts District tonight. Queer rock energy. Tickets from $44 — worth it for a midweek show in a venue this good.", "url": "thevanguardtulsa.com"},
        {"name": "Mamma Mia! (Broadway Tour)", "time": "7:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Midweek Broadway is the underrated move — slightly smaller crowd, same electric energy. ABBA, sequins, a mystery dad. Grab a drink in the PAC lobby and surrender completely.", "url": "tulsapac.com"},
        {"name": "Gender Support Group", "time": "7:00 - 8:30 PM", "venue": "Equality Center, 621 E 4th St", "description": "OKEQ's free weekly group for trans, nonbinary, and gender-questioning folks — confidential, peer-led, run by people who actually get it. No prep required, just show up.", "url": "okeq.org/transgender-support"},
        {"name": "Eagle Underwear Night", "time": "9:00 PM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Every Wednesday, pants are optional and confidence is the dress code. Open from 2 PM if you need time to warm up. The crowd gets good after dark.", "url": "facebook.com/TheTulsaEagle"},
        {"name": "Tulsa Botanic Garden: Bands & Blooms", "time": "10:00 AM", "venue": "Tulsa Botanic Garden, 3900 Tulsa Botanic Dr", "description": "Outdoor concerts in the middle of thousands of spring blooms — the Bands & Blooms series runs through April 16. Bring a blanket, bring someone, make a day of it.", "url": "tulsabotanic.org"},
        {"name": "Philbrook Museum", "time": "9:00 AM - 5:00 PM", "venue": "Philbrook Museum, 2727 S Rockford Rd", "description": "One of the most beautiful museum settings in the country — Renaissance villa, world-class collection, formal gardens. A queer afternoon in an objectively stunning space.", "url": "philbrook.org"},
        {"name": "108 Contemporary: Shawn Smith", "time": "11:00 AM - 6:00 PM", "venue": "108 Contemporary, 108 E M.B. Brady St", "description": "Entangled Ecologies continues — sculptural and fiber work by Shawn Smith through May 23. Free admission, Brady Arts District, 15 minutes in and you'll want to stay longer.", "url": "108contemporary.org"},
        {"name": "Welltown Themed Trivia", "time": "7:00 PM", "venue": "Welltown Brewing, Tulsa", "description": "Wednesday themed trivia nights at Welltown — past topics include Grey's Anatomy and The Office, so you know exactly who shows up. Competitive, fun, worth it.", "url": "welltownbrewing.com"},
        {"name": "Arnie's Bar Wednesday Night", "time": "12:00 PM - 2:00 AM", "venue": "Arnie's Bar, 318 E 2nd St", "description": "Gay-friendly downtown dive open daily with Wednesday drink specials. No theme night required. Just good bar energy in a building that knows what it is.", "url": "arniesbar.com"},
        {"name": "Gathering Place", "time": "6:00 AM - 11:00 PM", "venue": "2650 S John Williams Way", "description": "Tulsa's free world-class riverfront park. Kayak, walk, sit in the sun, be outdoors. Midweek is when the crowds are light and the space actually feels like yours.", "url": "gatheringplace.org"},
        {"name": "Name & Gender Correction Clinic", "time": "5:30 - 7:00 PM", "venue": "Rainbow Library, Equality Center, 621 E 4th St", "description": "Free legal help starting the name and gender correction process — attorney Joshua Payton walks you through it. If you've been putting this off, this is the night. No cost, no judgment.", "url": "okeq.org/event-calendar"},
        {"name": "Non-binary Support Group", "time": "7:00 - 8:30 PM", "venue": "Wellness Room, Equality Center", "description": "Part of OKEQ's Gender Support programming — specifically for non-binary folks, running concurrently with the other trans support groups. Free. First visit requires a brief interview with facilitators; arrive 30 min early.", "url": "okeq.org"},
        {"name": "Trans Men's Support Group", "time": "7:00 - 8:30 PM", "venue": "Glass Conference Room, Equality Center", "description": "Private support group for transgender men, every Wednesday at the Equality Center. Free. First visit requires a brief interview — call 918-743-4297 or arrive 30 minutes early.", "url": "okeq.org"},
        {"name": "Trans Women's Support Group", "time": "7:00 - 8:30 PM", "venue": "Equality Center, 621 E 4th St", "description": "Weekly support group for transgender women at OKEQ — free, confidential, affirming. First visit requires a brief interview with facilitators; call 918-743-4297 to connect before attending.", "url": "okeq.org"},
        {"name": "OKEQ Health Clinic", "time": "9:00 AM - 4:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "LGBTQ+ affirming healthcare by appointment — call 918-938-6537. Blue Cross/Blue Shield accepted plus self-pay. STI testing, PrEP, primary care from people who actually get it.", "url": "okeq.org/programs"},
    ],
    "Thursday": [
        {"name": "DRAGNIFICENT!", "time": "Doors 9 PM, Show 11 PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Hosted by Shanel Sterling, rotating queens, every Thursday without fail. $8 cover, 18+. If you're not here, what are you actually doing tonight. Get there before midnight for the best sets.", "url": "downtowntulsa.com/do/dragnificent-at-club-majestic-1"},
        {"name": "Green Country Bears Monthly Meetup", "time": "7:00 PM", "venue": "Restaurant varies — check greencountrybears.com", "description": "Second Thursday of the month — dinner, good company, zero pretense. Tulsa's bear community at its most relaxed. Show up hungry, check the website for this month's spot.", "url": "greencountrybears.com"},
        {"name": "GWAR at Cain's Ballroom", "time": "Doors 6:30 PM, Show 7:30 PM", "venue": "Cain's Ballroom, 423 N Main St", "description": "GWAR with Soulfly and King Parrot at the most storied venue in Tulsa. Chaotic, theatrical, completely unhinged and entirely intentional. Wear clothes you don't love. You will not be dry.", "url": "cainsballroom.com"},
        {"name": "Mamma Mia! (Thursday Night)", "time": "7:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Thursday night Broadway — catch Mamma Mia before the weekend crowds. If you're going to DRAGNIFICENT later, start here first and make the whole night a production.", "url": "tulsapac.com"},
        {"name": "Night Light Tulsa", "time": "6:30 - 9:00 PM", "venue": "200 N Maybelle Ave (under the bridge)", "description": "City Lights Foundation distributes hot meals, clothing, and essentials to Tulsa's unhoused community every Thursday in April. Volunteers and allies always welcome. Show up.", "url": "citylightsok.org"},
        {"name": "Philbrook Museum", "time": "9:00 AM - 5:00 PM", "venue": "Philbrook Museum, 2727 S Rockford Rd", "description": "World-class art collection in a Renaissance villa — open Thursday through Sunday. Spend an hour before your evening and remind yourself Tulsa has genuinely beautiful things in it.", "url": "philbrook.org"},
        {"name": "108 Contemporary: Shawn Smith", "time": "11:00 AM - 6:00 PM", "venue": "108 Contemporary, 108 E M.B. Brady St", "description": "Entangled Ecologies by Shawn Smith — sculptural work through May 23. Free. Brady Arts District. Perfect pre-show stop before DRAGNIFICENT or GWAR depending on your energy tonight.", "url": "108contemporary.org"},
        {"name": "Tulsa Botanic Garden: Bands & Blooms", "time": "10:00 AM", "venue": "Tulsa Botanic Garden, 3900 Tulsa Botanic Dr", "description": "Spring outdoor concert series runs through April 16. Thousands of blooms, live music, and Tulsa in the specific way it's good in April. Worth a morning or afternoon.", "url": "tulsabotanic.org"},
        {"name": "Queer Crafters Club", "time": "6:00 - 8:00 PM", "venue": "Gallery, Equality Center, 621 E 4th St", "description": "Bring your own craft — knitting, drawing, whatever you're working on — and spend two hours making things with queer people. Every Thursday in the Gallery at the Equality Center. Free.", "url": "okeq.org"},
        {"name": "Girl Scout Troop 7484", "time": "6:30 - 7:30 PM", "venue": "Wellness Room, Equality Center", "description": "Tulsa's queer-inclusive Girl Scout troop welcomes all girls, trans, and nonbinary youth every Thursday at 6:30 PM. Friendships, skills, and a community that actually sees you. Contact t.marler@cox.net.", "url": "okeq.org"},
        {"name": "OKEQ Health Clinic", "time": "9:00 AM - 12:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "Thursday morning LGBTQ+ health clinic hours — appointment required, call 918-938-6537. STI testing, PrEP, affirming primary care.", "url": "okeq.org/programs"},
    ],
    "Friday": [
        {"name": "Mamma Mia! Friday Night Show", "time": "8:00 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Friday night Broadway is the move — dress up, make a reservation first, walk in like you planned to feel something amazing tonight because you did. Tickets still available but Friday fills fast.", "url": "ticketmaster.com"},
        {"name": "Tulsa Oilers vs Idaho Steelheads", "time": "7:05 PM", "venue": "BOK Center, 200 S Denver Ave", "description": "PSO Pack the House Night with reversible bucket hat giveaway — and the queer community has fully claimed Oilers nights at BOK. Fast, fun, affordable. Get there early for the hat.", "url": "tulsaoilers.com"},
        {"name": "Girl Dinner at Inheritance Kitchen", "time": "6:00 - 10:00 PM", "venue": "Inheritance Kitchen, 108 S Detroit Ave", "description": "Plant-based, stunning food, perfect date-night energy — one of the most beautiful restaurants in Tulsa. Start here before the show or make it the whole evening. Make a reservation.", "url": "inheritancejuicery.com"},
        {"name": "Tulsa Botanic Garden: Bands & Blooms", "time": "10:00 AM", "venue": "Tulsa Botanic Garden, 3900 Tulsa Botanic Dr", "description": "Last Friday of the Bands & Blooms spring series — outdoor music among thousands of blooms. Perfect Friday afternoon before the evening starts. Bring someone.", "url": "tulsabotanic.org"},
        {"name": "Philbrook Museum", "time": "9:00 AM - 5:00 PM", "venue": "Philbrook Museum, 2727 S Rockford Rd", "description": "Take yourself to the Philbrook before the Friday night starts — art, gardens, a building that makes you feel like you're somewhere else entirely. Worth a Friday afternoon.", "url": "philbrook.org"},
        {"name": "Club Majestic Friday Night", "time": "9:00 PM - 2:00 AM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Tulsa's LGBTQ+ nightclub doing what it does on a Friday night. Check the calendar for DJ nights, themed events, and the kind of dancing you'll tell someone about Monday.", "url": "clubmajestictulsa.com"},
        {"name": "Tulsa Eagle Friday Night", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "The Eagle patio on a Friday night is one of Tulsa's consistently good gay experiences — low effort, high reward. Show up, grab a drink, see who you see.", "url": "facebook.com/TheTulsaEagle"},
        {"name": "Soundpony Friday Night", "time": "3:00 PM - 2:00 AM", "venue": "The Soundpony, 409 N Main St", "description": "Gay-friendly Arts District bar with frequent Friday live music. Check the calendar for tonight's lineup — it's almost always worth checking.", "url": "thesoundpony.com"},
        {"name": "Free Drop-In Therapy", "time": "9:00 AM - 5:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "No-cost drop-in therapy sessions with Tifany Oslin (she/her), a Licensed Master Social Worker — affirming, trauma-informed, no judgment. Call/text 918-205-4018 or just show up during open hours.", "url": "okeq.org"},
        {"name": "AFFIRMING (LGBTQ+ Youth, Ages 14-19)", "time": "6:00 - 7:00 PM", "venue": "Wellness Room, Equality Center", "description": "CBT-based program designed specifically for LGBTQ+ youth to manage stress and build wellbeing — developed in partnership with queer youth. Every Friday, free. Ages 14-19.", "url": "okeq.org"},
        {"name": "Positively Grateful", "time": "6:00 - 8:00 PM", "venue": "Event Center, Equality Center", "description": "HIV+ support group every Friday — potluck meals, wellness resources, community, and people who understand. All are welcome. The kind of Friday night that actually fills you up.", "url": "okeq.org"},
        {"name": "Community Care Providers Circle", "time": "11:00 AM - 12:30 PM", "venue": "Equality Center, 621 E 4th St", "description": "For therapists, social workers, organizers, teachers, clergy — anyone doing community care right now while also navigating their own oppression. Led by @yallschaplain. Come find your people.", "url": "okeq.org"},
        {"name": "OKEQ Health Clinic", "time": "1:00 - 4:00 PM", "venue": "Equality Center, 621 E 4th St", "description": "Friday afternoon LGBTQ+ health clinic — appointment required, call 918-938-6537. Affirming primary care, STI testing, PrEP. Insurance accepted plus self-pay.", "url": "okeq.org/programs"},
    ],
    "Saturday": [
        {"name": "Elote Drag Brunch: Drag Me to Church", "time": "11:00 AM + 1:30 PM", "venue": "Elote Cafe, 514 S Boston Ave", "description": "Elote's drag brunch sells out every second Saturday — queens preaching, food genuinely incredible, whoever you bring will thank you. Buy tickets on Eventbrite now because they are already going.", "url": "eventbrite.com"},
        {"name": "Sex & Violence", "time": "5:00 PM", "venue": "The Property Event Center", "description": "Drag, burlesque, pro wrestling, tattoos, piercings, food and drinks. The queer Saturday Tulsa doesn't always produce. Wear something bold, arrive ready, bring cash for the artists on site.", "url": "eventbrite.com/e/sex-violence-tickets-1979239616974"},
        {"name": "Mamma Mia! (Two Shows)", "time": "2:00 PM + 8:00 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Last Saturday for Mamma Mia in Tulsa — two shots, matinee or evening. Closes Sunday and ABBA doesn't come back on its own. Pick the evening show for the full night-out experience.", "url": "tulsapac.com"},
        {"name": "Tulsa Farmers' Market Season Opener", "time": "7:00 - 11:00 AM", "venue": "1 S Lewis Ave, Kendall Whittier", "description": "Spring 2026 season opens at the Kendall Whittier market — LGBTQ+ vendors, local produce, live music. Get there before 9 or the good stuff is gone and you're left with the $14 hot sauce.", "url": "tulsafarmersmarket.org"},
        {"name": "Philbrook Museum", "time": "9:00 AM - 5:00 PM", "venue": "Philbrook Museum, 2727 S Rockford Rd", "description": "Saturday at Philbrook is a full experience — villa, gardens, world-class collection, and a crowd that's actually there to look at things. Spend a Saturday morning here before everything else.", "url": "philbrook.org"},
        {"name": "108 Contemporary: Shawn Smith", "time": "11:00 AM - 6:00 PM", "venue": "108 Contemporary, 108 E M.B. Brady St", "description": "Saturday at 108 Contemporary means the Brady Arts District is alive and the gallery is at its best. Entangled Ecologies runs through May 23. Free admission, easy to pair with brunch.", "url": "108contemporary.org"},
        {"name": "Tulsa Botanic Garden: Bands & Blooms", "time": "10:00 AM", "venue": "Tulsa Botanic Garden, 3900 Tulsa Botanic Dr", "description": "Spring outdoor concerts through April 16 — Saturday at the Botanic Garden is exactly the right move before an afternoon full of drag, wrestling, and chaos.", "url": "tulsabotanic.org"},
        {"name": "Club Majestic Saturday Night", "time": "9:00 PM - 2:00 AM", "venue": "Club Majestic, 124 N Boston Ave", "description": "After everything else today — the brunch, the show, the wrestling — Club Majestic at midnight is the natural next step. Check the calendar for Saturday DJ and themed events.", "url": "clubmajestictulsa.com"},
        {"name": "Tulsa Eagle Saturday Night", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Saturday night at the Eagle is exactly what it sounds like — leather, bears, patio, good people. After Sex & Violence, head here and keep the night going.", "url": "facebook.com/TheTulsaEagle"},
    ],
    "Sunday": [
        {"name": "Sunday Showdown Open Talent Night", "time": "9:00 PM", "venue": "Club Majestic, 124 N Boston Ave", "description": "Open talent night at Club Majestic — perform or come watch, 18+, and the energy after midnight is the specific reason you shouldn't go home early on a Sunday in Tulsa.", "url": "clubmajestictulsa.com"},
        {"name": "All Souls Unitarian Services", "time": "10:00 AM + 11:15 AM", "venue": "All Souls, 2952 S Peoria Ave", "description": "Largest UU congregation in the US, queer-affirming since before it was a selling point. Walk in alone and walk out feeling like you belong somewhere in this city. Two services, show up when you can.", "url": "allsoulschurch.org"},
        {"name": "Mamma Mia! Final Shows", "time": "1:00 PM + 6:30 PM", "venue": "Chapman Music Hall, Tulsa PAC", "description": "Last day. ABBA leaves Tulsa tonight. If you haven't gone you already know what to do. The 6:30 PM show is the one for the full closing-night crowd energy.", "url": "ticketmaster.com"},
        {"name": "Philbrook Museum", "time": "12:00 PM - 5:00 PM", "venue": "Philbrook Museum, 2727 S Rockford Rd", "description": "Philbrook is open Sunday noon to 5 — a slower, quieter version of the best art museum in Tulsa. Sunday hours are perfect for an afternoon without an agenda.", "url": "philbrook.org"},
        {"name": "Gathering Place", "time": "6:00 AM - 11:00 PM", "venue": "2650 S John Williams Way", "description": "Free world-class riverfront park — Sunday at Gathering Place is Tulsa doing something genuinely right. Walk, kayak, sit on the grass, decompress from the week.", "url": "gatheringplace.org"},
        {"name": "108 Contemporary: Shawn Smith", "time": "12:00 PM - 5:00 PM", "venue": "108 Contemporary, 108 E M.B. Brady St", "description": "Sunday hours at 108 Contemporary (noon to 5) — Entangled Ecologies is worth a Sunday afternoon trip to the Brady Arts District before everything reopens tomorrow.", "url": "108contemporary.org"},
        {"name": "Tulsa Eagle Sunday", "time": "2:00 PM - 2:00 AM", "venue": "Tulsa Eagle, 1338 E 3rd St", "description": "Sunday funday at the Eagle is its own thing entirely — lower-key than Saturday but the patio is still the patio and the crowd still shows up. Wrap the week right.", "url": "facebook.com/TheTulsaEagle"},
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
    upcoming_event=upcoming_featured,
)

output = os.path.join("docs", "images", "weekly")
paths = save_carousel(slides, output)
print(f"Generated {len(paths)} slides:")
for p in paths:
    print(f"  {os.path.basename(p)}")
