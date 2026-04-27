"""
Generate rich, long, funny website descriptions for each event.
Writes 'website_description' field to the events JSON.
Different from 'slide_description' (slide stays short; website goes long).

Rules:
- 1-2 flamingo events: explain what the event IS, then make the gay case for going
- 3-5 flamingo events: vivid details + FOMO + community energy
- All: spicy gay puns/jokes, informative, fun to read
- Target: 4-8 sentences per event
"""
import json, os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import config

# ── Flamingo score logic (mirrors gen_website_html.py) ────────────────────────
_FIVE_FL = [
    'drag show', 'drag bingo', 'drag brunch', 'drag queen', 'drag king', 'drag race',
    'drag sing', 'drag along', 'drag perform', 'drag night',
    'pride show', 'pride party', 'pride dance', 'pride night', 'queer night',
    'gay night', 'lgbtq+ night', 'homo hotel', 'hhhh', 'rainbow night', 'twisted arts',
    'queer cabaret', 'dragnificent', 'lambda bowling',
    'queer support group', 'lgbtq support group', 'gender outreach support',
    'queer women', 'sapphic social', 'queer social', 'trans support group',
    'osu tulsa queer', 'pflag tulsa', 'queer support',
    'pflag', 'lambda unity',
    'bar crawl', 'pub crawl', 'pride crawl',
]
_GAY_BAR_VENUES = {
    'club majestic', 'tulsa eagle', 'yellow brick', 'majestic tulsa',
    '1330 e 3rd', '1338 e 3rd', 'the vanguard',
    'pump bar', '602 south lewis', '602 s. lewis', '602 s lewis',
}
_FOUR_VENUES = {
    'dvl', '302 south frankfort', '302 s. frankfort', '302 s frankfort', 'elote',
}
_FOUR_FL = [
    'lgbtq', 'lgbt', 'queer', 'lesbian', 'bisexual', 'sapphic',
    'transgender', 'nonbinary', 'non-binary', 'gender outreach',
    'equality center', 'okeq', 'pflag', 'rainbow pride', 'pride month',
    'sonic ray', 'council oak', 'hrc', 'gay bar', 'gay club',
    'queer collective', 'queer crafters', 'support group', 'trans support',
    'musical', 'the musical', 'pride', 'opera', 'broadway',
]
_LGBTQ_COMMUNITY_SOURCES = {"homo_hotel", "okeq", "recurring", "manual"}
_COMMUNITY_KW = [
    'support', 'group', 'meeting', 'collective', 'social', 'community',
    'bowling', 'yoga', 'meditation', 'sound bath', 'seniors', 'testing', 'coffee',
]
_TWO_FL = [
    'art', 'music', 'concert', 'gallery', 'theater', 'theatre', 'comedy',
    'poetry', 'film', 'cinema', 'festival', 'cabaret', 'dance', 'live music',
    'cultural', 'brunch', 'karaoke', 'trivia', 'open mic', 'rooftop',
    'bingo', 'scavenger', 'sketch', 'craft', 'workshop', 'coffee',
]

def flamingo_score(ev: dict) -> int:
    name   = ev.get('name', '').lower()
    venue  = ev.get('venue', '').lower()
    source = ev.get('source', '')
    content = f"{name} {venue}"
    if any(kw in content for kw in _FIVE_FL): return 5
    if any(bar in venue for bar in _GAY_BAR_VENUES): return 5
    if any(kw in content for kw in _FOUR_FL): return 4
    if any(v in venue for v in _FOUR_VENUES): return 4
    if source in ('homo_hotel', 'okeq'): return 4
    if source in _LGBTQ_COMMUNITY_SOURCES and any(kw in content for kw in _COMMUNITY_KW): return 3
    if any(kw in content for kw in _TWO_FL): return 2
    return 2  # 1 flamingo is reserved for truly exclusionary/corporate-only events


# ── Named event descriptions (keyword → description) ─────────────────────────
# Keys are lowercase substrings that must appear in the event name.
NAMED_DESCRIPTIONS = {
    "homo hotel happy hour": (
        "First Friday. The DoubleTree. The gays. Every month, Homo Hotel Happy Hour transforms a "
        "downtown hotel bar into the most welcoming room in Tulsa for two glorious hours. "
        "This month HHHH is raising money for Paws in Need Tulsa, which provides vet care, food, "
        "and support for pets in families facing hardship. Free admission, raffle tickets "
        "available, and nearly all proceeds go directly to Paws in Need. "
        "Show up at 6. Grab a drink (they're hotel-priced, bring your big-gay-night budget). "
        "Talk to strangers. Win a raffle prize. Feel genuinely good about your Friday night. "
        "No cover. No dress code. Just the most fabulous two hours Tulsa offers every month."
    ),
    "lambda bowling league": (
        "Monday night LGBTQ+ bowling at AMF Sheridan Lanes. The Lambda Bowling League is exactly "
        "what it sounds like: queer people being delightfully terrible at bowling together, "
        "wearing rented shoes with zero shame and maximum personality. "
        "Expect lane-to-lane trash talk, creative scorekeeping, gutter balls celebrated as art, "
        "and the kind of easy, low-stakes Monday night hang that actually gets you out of the house. "
        "No bowling experience required. In fact, the worse you are, the better the stories. "
        "Show up. Rent the shoes. Bowl terribly. Laugh genuinely. "
        "This is the Monday your couch has been keeping you from."
    ),
    "monday movie night": (
        "Free movie night at one of Tulsa's most beloved gay bars. Tonight it's a punk rock "
        "documentary, which means you'll walk in not knowing much about the Minutemen and "
        "walk out with a new favorite band and three strong opinions about the '80s underground. "
        "The bar is full of your people. The drinks are real. The movie is free. "
        "You were going to watch something alone on your couch anyway — "
        "watch it here, surrounded by humans who actually get it, and feel something. "
        "Doors open early. Show up when you feel like it."
    ),
    "dragnificent": (
        "Weekly drag at Club Majestic. If you haven't been to DRAGNIFICENT!, you have been "
        "making a recurring mistake and it stops tonight. "
        "Doors at 9, show at 10 — which means you have exactly one hour to pregame, "
        "find a spot close enough to the stage to make eye contact with a queen, "
        "and decide how many singles you're tipping. "
        "Expect full performances, charisma you can feel across the room, and at least one number "
        "that makes you realize drag is genuinely a high art form. "
        "Get there early for a good spot. Tip generously. Scream when you mean it. "
        "Club Majestic's DRAGNIFICENT is the Thursday-night anchor of Tulsa's queer nightlife."
    ),
    "gender outreach support group": (
        "Every week, the Dennis R. Neill Equality Center opens its doors for one of the most "
        "important gatherings in Tulsa's LGBTQ+ community: the Gender Outreach Support Group. "
        "This is a space specifically for people navigating gender identity, gender expression, "
        "trans experience, and nonbinary life. It's run by people who understand because they live it. "
        "No scripts. No explaining yourself from scratch. No having to justify your existence "
        "before someone will take you seriously. "
        "If you're questioning, transitioning, or just looking for a room full of people who get it, "
        "this is where you go. First-timers are welcome. Show up 30 minutes early if you can. "
        "You don't have to have it figured out to belong here."
    ),
    "osu tulsa queer support group": (
        "The OSU Tulsa Queer Support Group meets on campus for students, staff, and community "
        "members who want a space that actually sees them. "
        "This isn't a club meeting with an agenda — it's an open, low-pressure gathering where "
        "you can talk about what you're going through, listen to others, and just exist in a "
        "room full of people who understand without you having to explain the basics first. "
        "Open to OSU Tulsa students AND the broader community. "
        "If you're queer and in Tulsa and you've been feeling a little isolated, "
        "this room on Tuesday nights at 6 PM is for you. You don't have to be in crisis to come. "
        "Sometimes you just want to be around your people. That's enough."
    ),
    "queer crafters club": (
        "The Queer Crafters Club meets at the Equality Center and the whole point is exactly "
        "what it sounds like: queer people making things together. "
        "No crafting skills required. No judgment about your output. The project is incidental — "
        "the real reason to come is that you'll walk in with zero crafting skills and "
        "walk out with something you made, at least one new person you actually like, "
        "and a very defensible reason to tell people you 'had plans' on a Thursday evening. "
        "Bring whatever you're working on, or show up with nothing and borrow supplies. "
        "The vibe is relaxed, the company is excellent, and at least one person is going to "
        "make something inexplicably beautiful. Bring your weird self. That's the assignment."
    ),
    "equality business alliance": (
        "The Equality Business Alliance Networking Mixer is LGBTQ+ professionals doing the thing "
        "they do best: making real connections with people who get it. "
        "This is the opposite of the awkward corporate mixer where you stand by the cheese table "
        "wondering if anyone wants to hear about your job. "
        "The EBA crowd is warm, genuinely interesting, and here because they actually want community, "
        "not just business cards. The event is at the Dennis R. Neill Equality Center, which means "
        "you're networking in a space that already belongs to you. "
        "Drink something. Talk to someone. Leave with at least one contact you actually want to follow up with. "
        "LGBTQ+ professionals in Tulsa are building real things together. Come be part of it."
    ),
    "queer women's collective": (
        "The Queer Women's Collective May Meetup is happening at the Equality Center and "
        "if you're a queer woman or femme in Tulsa, there is genuinely no reason to skip this. "
        "First Friday of the month. The group rotates activities, always in a welcoming and "
        "inclusive space. Whether you're newly out, long-established in the community, or "
        "somewhere in between, this meetup is a low-pressure way to actually meet your people. "
        "No agenda, no dues, no requirements. Just show up as you are. "
        "You've been saying you'll go next time for three months. Tonight is next time."
    ),
    "pflag tulsa": (
        "PFLAG Tulsa's monthly meeting is one of the most important gatherings in the city "
        "for families, friends, and allies of LGBTQ+ people. "
        "If you have a queer kid, sibling, parent, or friend and you're trying to understand, "
        "support, and show up for them better — this room is where you start. "
        "PFLAG is not a support group for LGBTQ+ people (though you're welcome). "
        "It's specifically built for the people who love them and want to do right by them. "
        "The conversations are honest, the community is warm, and the information is practical. "
        "Meetings are monthly, free, and open to the public. Show up. Learn something. "
        "Be the family member everyone deserves."
    ),
    "lambda unity": (
        "Lambda Unity Group is an LGBTQ+ AA meeting at Fellowship Congregational Church. "
        "Recovery is hard enough without also having to explain yourself. "
        "This meeting is specifically for LGBTQ+ people in recovery, which means you walk in "
        "already understood. No need to code-switch, no need to sidestep the parts of your story "
        "that are uniquely queer, no need to feel like an asterisk in the room. "
        "If you're in recovery or considering it, this is one of the most affirming spaces "
        "Tulsa has to offer. Check the listing for time. Show up. You belong here."
    ),
    "drag bingo": (
        "Drag Bingo Fundraiser for Adonia at Oklahomans for Equality. "
        "You get a bingo card. A queen calls the numbers between show-stopping drag performances. "
        "Money goes to Adonia, an LGBTQ+ youth organization doing real work in Tulsa. "
        "This is the most fun you can have at a table in Tulsa on a Saturday night. "
        "The format is: drag number, bingo round, drag number, bingo round, repeat until "
        "you've screamed 'BINGO!' or lost your voice cheering for a performer, whichever comes first. "
        "Buy a card. Tip your queen generously. Scream when you win. "
        "You're having fun AND funding something that matters. That's a Saturday."
    ),
    "tulsa eagle leather night": (
        "Leather Night at the Tulsa Eagle with DJ Kudos. "
        "The Tulsa Eagle is Tulsa's leather and bear bar, and on Leather Night, the vibe is "
        "exactly what it should be: unapologetic, celebratory, and specifically designed for "
        "the part of the queer community that's been here the whole time. "
        "DJ Kudos keeps the energy right all night. Dress code is encouraged but not mandatory — "
        "come as you are, come leather up, come in your favorite vest. "
        "The Eagle crowd is one of the friendliest in the city once you walk through the door. "
        "This is the Tulsa bar experience that doesn't try to be anything other than exactly itself. "
        "Doors late. Energy good. Show up."
    ),
    "tulsa eagle bingo": (
        "Bingo at the Tulsa Eagle on a Saturday afternoon. "
        "Yes, you're playing bingo at a leather bar, and yes, it's one of the best Saturday "
        "afternoon activities in the city. The Eagle's bingo crowd mixes regulars, newcomers, "
        "curious first-timers, and people who will absolutely yell 'BINGO!' at the top of their lungs. "
        "Cards are cheap. Drinks are bar prices. The vibe is more festive than you'd expect "
        "from a 3 PM Saturday and less intimidating than you might think from the outside. "
        "It's a great way to get introduced to the Eagle scene in the most low-stakes possible setting. "
        "Come in, grab a card, and see what Tulsa's leather community is actually like when "
        "they're calling B-7 and gossiping between rounds."
    ),
    "kentuck derby": (
        "Kentucky Derby Watch Party and Derby Hat Contest at the Tulsa Eagle. "
        "The most extra afternoon of the sports calendar, held at one of Tulsa's most "
        "beloved gay bars, with a hat contest to make it properly fabulous. "
        "The Kentucky Derby has always had a devoted queer following, which makes complete sense "
        "given that it involves spectacular hats, dramatic pageantry, mint juleps, "
        "and an event that takes about two minutes but requires three weeks of outfit planning. "
        "Bring your most outrageous derby hat. Drink something with mint in it. "
        "Scream at a horse for 120 seconds. Win a prize for the hat. "
        "This is the Saturday afternoon you didn't know you needed."
    ),
    "sunday shenanigans": (
        "SUNDAY SHENANIGANS W/ SHANEL at the Tulsa Eagle. "
        "Shanel running Sunday nights means the music is going to be right, the crowd is going to "
        "be right, and you are going to have three very good hours before Monday finds you. "
        "This is the unofficial 'close out the weekend properly' event for Tulsa's queer nightlife scene. "
        "The Eagle on a Sunday with Shanel is relaxed enough to wind down from Saturday "
        "but alive enough to remind you the weekend isn't over yet. "
        "Show up around 6, stay as long as feels right, and stop checking your email until morning. "
        "You've earned a Sunday night out. This is the one."
    ),
    "sunday showdown": (
        "Open Talent Night at Club Majestic. Doors at 9, show at 11. "
        "This is unscripted, live, and completely unpredictable — which is exactly the point. "
        "Performers sign up, take the stage, and compete live for the crowd's approval. "
        "Some will be brilliant. Some will have bold choices that may or may not land. "
        "All of it is worth watching. "
        "Club Majestic's Sunday Showdown is the kind of queer nightlife that keeps you up past midnight "
        "because you can't leave when the next act might be the most interesting thing you see all month. "
        "Sleep is a Monday problem. Show up Sunday."
    ),
    "touchtunes friday": (
        "TOUCHTUNES FRIDAY at the Tulsa Eagle. "
        "This is the night where you and the bar collectively choose what happens next. "
        "TouchTunes is a jukebox app that lets anyone in the bar queue songs, which means "
        "Friday night at the Eagle becomes a live negotiation between who wants Robyn, "
        "who wants classic country, and who is going to spend actual money to push "
        "their song to the top of the queue. "
        "The result is usually chaotic and always perfect. The Eagle crowd curates instinctively well, "
        "and Fridays there have a loose, anything-goes energy that's hard to find anywhere else in Tulsa. "
        "Show up. Download the app. Fight for your song. It's a legitimately fun Friday."
    ),
    "shenanigans w/ shanel": (
        "SUNDAY SHENANIGANS W/ SHANEL at the Tulsa Eagle. "
        "Shanel running Sunday nights means the music is going to be right, the crowd is going to "
        "be right, and you are going to have three very good hours before Monday finds you. "
        "This is the unofficial 'close out the weekend properly' event for Tulsa's queer nightlife scene. "
        "The Eagle on a Sunday with Shanel is relaxed enough to wind down from Saturday "
        "but alive enough to remind you the weekend isn't over yet. "
        "Show up around 6, stay as long as feels right, and stop checking your email until morning. "
        "You've earned a Sunday night out. This is the one."
    ),
    "legendary midnight drags": (
        "Tulsa's Legendary Midnight Drags at Tulsa Raceway Park. "
        "These are not the drag you're thinking of. These are cars. Big engines. Green lights. "
        "Tulsa's outdoor street drag racing tradition happens monthly at the Raceway Park, "
        "and if you have never stood in a crowd while a car does something that should "
        "probably be illegal and the crowd collectively loses its mind, you've been missing out. "
        "The queer community has a long and underappreciated love of loud, fast, spectacular things — "
        "and this delivers on all three. Midnight start means you stay out past your usual limit. "
        "Bring closed-toe shoes and a friend who won't make you leave early. "
        "The queer case for going: you're fabulous AND you can appreciate horsepower. That's not a contradiction."
    ),
    "a people's museum": (
        "A People's Museum by AK/OK at Positive Space Tulsa. "
        "This is an international living archive of LGBTQ2S+ history told through hand-drawn portraits "
        "and the personal stories of the people in them. "
        "Artist and activist collective AK/OK has been traveling the world collecting these portraits — "
        "faces of queer elders, community organizers, people whose stories have never been in a textbook. "
        "The result is an exhibition that makes you feel seen in a way that very few art shows do. "
        "Walk in with ten minutes and you'll stay forty. "
        "This is the kind of art that makes you want to call your queer friends afterward and "
        "just say 'have you been?' Positive Space Tulsa is the right venue for it. "
        "Go this Saturday. Let it hit you."
    ),
    "brunch for the blossoms": (
        "Brunch at a local spot on Saturday morning. "
        "Brunch is the queerest meal in existence and this one is delivering on a Saturday. "
        "If you need a reason to get out of bed before noon on a weekend, 'brunch' is the only word "
        "that should appear in that sentence. "
        "Great food, good company, and the social lubricant of a morning drink in a relaxed setting. "
        "Show up, eat something excellent, and start your Saturday with actual human interaction "
        "instead of scrolling until 1 PM wondering where the day went."
    ),
    "pump bar": (
        "Pump Bar Birthday Party on Saturday. "
        "Pump Bar is a Tulsa LGBTQ+ institution on South Lewis, and a birthday party there "
        "is exactly the kind of community celebration that reminds you why Tulsa's gay bar scene matters. "
        "This is a neighborhood bar with history, personality, and a crowd that's been showing up "
        "for years. Come celebrate. The vibe is warm, the bar is full of regulars who will talk "
        "to you, and birthday energy is infectious. "
        "If you've never been to Pump Bar, a party is the perfect first visit."
    ),
    "muumuus": (
        "Muumuus & Margaritas. "
        "The dress code is a muumuu. The drink is a margarita. The vibe is exactly what it sounds like. "
        "This is the gay-coded social event the internet would have invented if the Tulsa queer "
        "community hadn't gotten there first. "
        "Put on something flowy, grab a drink, show up, and spend a few hours with people "
        "who understand that comfort and fabulousness are not opposites. "
        "You've been looking for a reason to wear that thing. Here it is."
    ),
    "gypsy": (
        "Gypsy the Musical at the Tulsa Performing Arts Center. "
        "'Everything's Coming Up Roses.' 'Let Me Entertain You.' 'Together Wherever We Go.' "
        "The Merman canon. The mother of all stage musicals. "
        "Gypsy is the story of Mama Rose, arguably the most fascinating and terrifying stage mom "
        "in American theater history, and it has been gay culture for 65 years for very good reason. "
        "If you love musical theater, this is one you see. The Tulsa Performing Arts Center is "
        "a beautiful venue and this is a legitimate production worth dressing up for. "
        "Buy a ticket. Sit close enough to see faces. Let the score do what it does to you. "
        "Warning: you will leave humming 'Everything's Coming Up Roses' for at least three days."
    ),
    "mahler": (
        "Mahler's Symphony No. 2, 'Resurrection' at the Tulsa Performing Arts Center. "
        "The Resurrection Symphony is 90 minutes of Mahler asking the biggest questions in the biggest room. "
        "It ends with a full choir and orchestra building to one of the most overwhelming finales "
        "in the orchestral canon — the kind of music that makes you feel something in your chest "
        "before your brain knows what's happening. "
        "The queer community has a long relationship with Mahler. The intensity, the drama, "
        "the emotional scale — it fits. "
        "If you've never heard a symphony orchestra live, this is a formidable way to start. "
        "If you have, you know what you're in for. "
        "Dress like you mean it. The music will do the rest."
    ),
    "robert randolph": (
        "Robert Randolph at Cain's Ballroom for CARNEY FEST '26. "
        "Robert Randolph plays sacred steel guitar in a way that makes the instrument sound like "
        "it was built specifically to be played this loud, this joyfully, and this hard. "
        "Cain's Ballroom has legendary acoustics and a wood floor you can feel in your feet. "
        "The combination of this artist in this room is the kind of live music experience "
        "that people describe for years afterward. "
        "Gay people have been at the front of the concert hall since concert halls existed, "
        "and this is the show worth fighting for a good spot at. "
        "You'll hear it in your chest for days. Go."
    ),
    "gillian welch": (
        "An Evening with Gillian Welch and David Rawlings at Guthrie Green. "
        "Gillian Welch is one of the most respected voices in American folk and Americana, "
        "full stop. This is a rare 'off the cuff' concert — stripped down, intimate, "
        "and at Guthrie Green, one of Tulsa's best outdoor venues. "
        "The queer folk music connection is not a coincidence. Welch has a following in the "
        "queer community because her music is about honesty, survival, and people living "
        "on the margins with grace. It hits different under an open sky. "
        "Bring a blanket if you have one. Arrive early for a good spot. "
        "This is the Wednesday night you'll talk about."
    ),
    "karaoke": (
        "Karaoke night. "
        "Karaoke is one of the most underrated queer spaces in any city. "
        "There is a reason gay bars have had karaoke nights forever — the combination of "
        "a microphone, a crowd of people who are rooting for you, and zero consequences "
        "for ambition is a genuinely freeing experience. "
        "You don't have to be good. You have to commit. That's the whole game. "
        "Pick the song that matters to you. Deliver it like you mean it. "
        "The crowd will meet you there. That's karaoke. That's why it works."
    ),
    "trivia": (
        "Trivia night. "
        "Trivia nights in Tulsa's bar scene are a reliable Wednesday or Thursday hang — "
        "you form a team, pick a name that's funnier than you planned, "
        "and spend two hours realizing how much random knowledge you've accumulated "
        "in extremely specific categories. "
        "The gay case for trivia: we disproportionately win pop culture, film, fashion, "
        "and Broadway rounds, and we have the vocabulary to make every team name a pun. "
        "Make a team with strangers or bring your crew. Name it something that gets a reaction. "
        "Buy a round when you win. This is what weeknight social life is supposed to look like."
    ),
    "first friday art crawl": (
        "First Friday Art Crawl in the Tulsa Arts District. "
        "Once a month, the galleries along Archer Street open their doors, put out wine, "
        "and let the city walk through and actually look at things. "
        "The art crawl pulls an artsy, inclusive, gay-friendly crowd that dresses up slightly, "
        "takes art seriously-ish, and treats the whole thing as a genuine neighborhood party "
        "with gallery stops between conversations. "
        "This month features two new exhibits. "
        "Walk slowly. Look at everything. Find something that surprises you. "
        "Talk to the artist if they're there. Buy something if you can. "
        "Then get dinner somewhere on Archer afterward and call it a perfect First Friday."
    ),
    "loony bin": (
        "Comedy show at the Loony Bin. "
        "The Loony Bin is Tulsa's established comedy club and they bring in touring acts regularly. "
        "Stand-up comedy is one of the great gay-night-out activities precisely because "
        "a good comedian and a room of strangers who all decide to laugh at the same moment "
        "is a weirdly communal, unexpectedly connective experience. "
        "Check who's headlining — comedians who play mid-size cities often work out material "
        "that hasn't been performed to death yet. "
        "Get there early enough to order something before the show. "
        "Sit close to the stage. It's always a better show from the front."
    ),
    "cindy kaza": (
        "Cindy Kaza at the Loony Bin Comedy Club. "
        "Cindy Kaza is a touring comedian playing Tulsa this week. "
        "Comedy shows at the Loony Bin are a reliable Thursday or Friday outing — "
        "the room is intimate, the drinks are bar prices, and a touring comedian usually "
        "has tighter material than a local open mic. "
        "Gay people, famously, have excellent taste in comedy. Use it. "
        "This is the kind of show you feel good about attending: support live comedy, "
        "support the club, and spend ninety minutes laughing in a room full of people. "
        "That's a better Friday than whatever you were considering instead."
    ),
    "drew dunn": (
        "Drew Dunn at the Loony Bin Comedy Club. "
        "Stand-up comedy on a Wednesday night at Tulsa's main comedy club. "
        "Drew Dunn is a touring act bringing new material to a mid-size market, "
        "which means you're often seeing stuff that's fresher than the Netflix special version. "
        "The queer community has always had a complicated and devoted relationship with comedy — "
        "we know when a bit lands and when it doesn't, and we make great audiences for comedians "
        "who actually have something to say. "
        "Wednesday nights are underrated for going out. The crowds are smaller, "
        "the energy is more focused, and you're not fighting for parking. "
        "Show up, drink something, laugh out loud, go home happy."
    ),
    "rooftop concert": (
        "Rooftop Concert Series at Soma Tulsa: Brut Hotel | Soma feat. BRANJAE. "
        "BRANJAE is a Tulsa musician with a following for a reason — the combination of "
        "a rooftop venue and an artist with actual stage presence is one of those "
        "Tuesday night experiences that punches well above its weekday weight. "
        "Soma is a creative, inclusive venue that draws an artsy crowd. "
        "The rooftop setting means sunset views, open air, and a concert that feels more "
        "intimate than the size of the space would suggest. "
        "Arrive before it starts. Find a good spot. Put your phone away long enough to "
        "actually hear the first song. "
        "Live music in Tulsa is genuinely underrated, and this is the kind of show "
        "that reminds you why you should go out on a Tuesday."
    ),
    "sunset cinema": (
        "Sunset Cinema Presents: 'We Jam Econo: The Story of the Minutemen' at Circle Cinema. "
        "The Minutemen were a San Pedro punk trio who made music that sounded like nothing else "
        "and influenced everyone who came after them. If you know them, you know why this is a must. "
        "If you don't, this documentary is the best possible introduction — "
        "it's a film about originality, community, friendship, and making art with what you have. "
        "Circle Cinema is Tulsa's beloved independent movie house, which means this is "
        "a free film at a great venue with an audience that cares. "
        "The queer underground music connection runs deep. Show up. "
        "Discover your new favorite band. Tell everyone about them."
    ),
    "queen bess": (
        "Queen Bess Centennial Aviation Arts Festival: 'The Flying Ace' Silent Film at Circle Cinema. "
        "Bessie Coleman was the first Black woman and first Native American to earn a pilot's license. "
        "She did it in 1921, in France, because no American flight school would accept her. "
        "Tulsa is honoring her centennial with a free silent film and live musical performance. "
        "This is the intersection of history, art, aviation, and the kind of story about a person "
        "who simply refused to be told no — which has always resonated in the queer community. "
        "Circle Cinema. Wednesday. Free. "
        "Bring someone who doesn't know the Bessie Coleman story yet. "
        "They'll leave wanting to know everything."
    ),
    "annie": (
        "Auditions for Annie the Musical. "
        "Yes, Annie. The red dress. The orphans. 'Tomorrow.' Sandy the dog. Daddy Warbucks. "
        "If you have ever, even once, belted 'It's a Hard Knock Life' into a hairbrush in private, "
        "this audition is for you and you know it. "
        "Musical theater auditions are where community theater meets genuine ambition, "
        "and the queer community's relationship with Annie specifically is documented and real. "
        "This is at 1301 S. Boston Avenue. You don't have to be a trained performer — "
        "community theater exists for people who love it, not just people who studied it. "
        "Show up. Sing your sixteen bars. Find out what you're made of. "
        "Miss Hannigan will not be played by you specifically, but let's not rule anything out."
    ),
    "networking": (
        "Networking mixer at Oklahoma Joe's BBQ. "
        "Networking events get a bad reputation and sometimes deserve it. "
        "The cure is showing up with a different goal: instead of collecting business cards, "
        "try to find two people you'd actually want to have lunch with again. "
        "Oklahoma Joe's BBQ is a relaxed setting with good food, which already beats "
        "the sad conference room networking events of the world. "
        "The queer case for professional networking: we're historically underrepresented "
        "in senior roles, and knowing the right people matters more than almost anything else. "
        "Go. Be interesting. Ask good questions. Eat something. "
        "If you walk out with one actual connection, it was worth it."
    ),
    "urban sketchers": (
        "Urban Sketchers Tulsa May Meet-up at Mother Road Market. "
        "Urban Sketchers is an international community of people who draw the world around them "
        "on location, in public, as it actually looks. "
        "Mother Road Market is an excellent place to do this — the indoor food hall setting "
        "gives you food, coffee, interesting faces, and enough variety that you'll never "
        "run out of things to draw. "
        "The queer case for Urban Sketchers: the arts are your people, and any group of people "
        "who carry sketchbooks into public spaces and draw strangers without judgment "
        "is self-selecting for interesting company. "
        "You don't have to be skilled. Sketching on location is about looking, not performing. "
        "Show up with a notebook. Leave with a Saturday memory."
    ),
    "tulsa indian club": (
        "Tulsa Indian Club Spring Festival: Native Arts & Crafts, Indian Tacos & More at Jenks Riverwalk. "
        "This is a genuine community cultural festival celebrating Native arts, food, and tradition "
        "along the Jenks Riverwalk. "
        "The Tulsa Indian Club has been running these events for decades, and the festival draws "
        "a mix of Native families, art collectors, and curious community members. "
        "The queer and Two-Spirit Indigenous community is a real and important part of this story — "
        "Two-Spirit identities predate colonial definitions of gender and sexuality, "
        "and Native cultural events are increasingly spaces of intersection. "
        "Come for the Indian tacos (which are legitimately excellent). "
        "Stay for the art. Learn something about the community that was here first."
    ),
    "craft & drafts": (
        "Craft & Drafts DIY Workshop at Cabin Boys Brewery. "
        "Make something with your hands while drinking a beer. "
        "This is the most honest description of an event that exists, and it works every time. "
        "Cabin Boys is a Tulsa brewery with a good reputation, and combining crafts with draft beer "
        "on a Sunday afternoon is genuinely the correct way to spend the end of a weekend. "
        "The queer community has always been over-represented in creative spaces, "
        "and a DIY workshop at a brewery is the perfect low-stakes way to try making something "
        "without any pressure to be good at it. "
        "Show up. Make a thing. Drink a beer. Tell people you 'did a craft' on Sunday. "
        "They'll ask to see it. Show them proudly."
    ),
    "ok so tulsa": (
        "Ok So Tulsa Grand Slam: 12th Tulsa's Best Storyteller Competition at Cain's Ballroom. "
        "True storytelling competitions are one of the best live events you can attend. "
        "Real people, real stories, five-minute time limit, and an audience that votes for the winner. "
        "The format rewards honesty, specificity, and the willingness to say the true thing out loud. "
        "Cain's Ballroom is a legendary venue. "
        "The queer community has always had extraordinary storytellers — "
        "we've had to be, because our stories weren't being told anywhere else. "
        "Come watch people compete to tell the truth in the most interesting way possible. "
        "It's a Saturday night show that will make you feel more human than most Saturday nights do."
    ),
    "all souls unitarian": (
        "All Souls Unitarian Sunday Services. "
        "All Souls Unitarian in Tulsa is one of the most LGBTQ-affirming congregations in the city — "
        "explicitly welcoming, radically inclusive, and deeply community-oriented. "
        "Sunday services run at 10:00 AM and 11:15 AM. "
        "Whether you're spiritual, questioning, agnostic-but-curious, or just looking for a "
        "community that doesn't require you to check your identity at the door, "
        "All Souls is worth showing up to. "
        "Many queer Tulsans have found genuine community here. "
        "Walk in knowing nothing. You'll be welcomed fully."
    ),
    "spiritual discussion": (
        "Spiritual Discussion: Reinvent Yourself Spiritually at Martin Regional Library. "
        "Sunday afternoon at the library: a discussion group about spirituality, reinvention, "
        "and questioning the frameworks you inherited. "
        "The queer journey and the spiritual journey have a lot in common — "
        "both often involve questioning what you were taught, figuring out what actually resonates, "
        "and building a relationship with something larger than yourself on your own terms. "
        "This is a free, open discussion. No particular tradition is required. "
        "Show up curious. Leave with something to think about."
    ),
    "antiracist support group": (
        "Tulsa Antiracist Support Group at Zarrow Library. "
        "This is a group of people committed to understanding and dismantling racism in their "
        "own lives and in their community, meeting regularly to hold each other accountable. "
        "The queer community and the antiracist movement have always been linked — "
        "because racism is a queer issue, because Black queer lives are LGBTQ+ lives, "
        "and because intersectionality isn't a theory, it's real people's actual experience. "
        "This group meets at the library. It's free. It's open. "
        "Show up if you're committed to doing the work."
    ),
    "happy hour": (
        "Happy Hour on the patio at 302 South Frankfort Avenue. "
        "It's happy hour. The drinks are cheaper than they'll be later and "
        "the crowd is better than it was at lunch. "
        "The gay case for Thursday/Friday happy hour: this is how you ease into the weekend "
        "without committing to a full night out. "
        "One drink becomes two. Two becomes 'let's get dinner.' Dinner becomes the best Friday "
        "you've had in a month. You know how this goes. Start at happy hour."
    ),
    "karaoke brunch": (
        "Karaoke Brunch at 302 South Frankfort Avenue. "
        "Brunch. Plus karaoke. On a Sunday. "
        "This is what peak civilization looks like, actually. "
        "The only thing better than belting 'Total Eclipse of the Heart' at midnight "
        "is doing it at 11 AM with eggs on the table and a bottomless mimosa in hand. "
        "The commitment to karaoke at brunch is an inherently queer act. "
        "You are too old to be self-conscious about this. Pick 'Barracuda.' Own it."
    ),
    "archer creatives": (
        "First Friday on Archer: Archer Creatives pop-up. "
        "The Tulsa Arts District on First Friday is the most walkable, social, "
        "gay-friendly thing you can do on a Friday evening in this city. "
        "Archer Creatives pops up with art, makers, and the general energy of people "
        "who make things and want you to see them. "
        "The crowd on Archer on First Friday is artsy, curious, and warm. "
        "Walk from gallery to gallery. Stop at a pop-up. Buy something from someone local. "
        "End the night somewhere on Archer with something good to eat. That's the move."
    ),
    "painters outing": (
        "Painters Outing with Twilight Exhibit in the Philbrook Garden. "
        "Philbrook Museum's garden on a Friday afternoon with an exhibit and painters working outdoors. "
        "This is a genuinely beautiful way to spend a First Friday afternoon before the evening events start. "
        "The queer community has always shown up for serious art in serious spaces, "
        "and Philbrook is one of Tulsa's great gifts — a real museum in a mansion and garden "
        "that punches well above its size. "
        "Bring a jacket if it might be cool. Stay longer than you planned. "
        "Then head to the Art Crawl afterward and call it a complete First Friday."
    ),
    "chris hardwick": (
        "Chris Hardwick at the Loony Bin Comedy Club. "
        "Chris Hardwick is a comedian and media personality best known for hosting 'Talking Dead' "
        "and @Midnight, and for being a fixture of the comedy nerd world. "
        "He does stand-up, and seeing someone with this profile at a mid-size comedy club means "
        "an intimate show with material that's being developed and refined in real time. "
        "The gay comedy audience is a good one — we tend to be sharp, quick, and genuinely appreciative "
        "of comedians who are doing real work. "
        "Show up, drink something, laugh. That's a Friday."
    ),
    "little big town": (
        "Little Big Town at The Cove at River Spirit Casino. "
        "Little Big Town is a country music group with a massive queer following, "
        "largely because Karen Fairchild and Kimberly Schlapman are style icons, "
        "their harmonies are objectively flawless, and 'Girl Crush' was a gay anthem before "
        "country radio finished being weird about it. "
        "River Spirit Casino's Cove venue is a solid mid-size concert room. "
        "If you're a country music fan in Tulsa's queer community, this is the show. "
        "Dress up slightly. Get there early. Let the harmonies wash over you."
    ),
    "circling": (
        "Authentic Relating Lab (Circling) at a private location. "
        "Circling is a structured practice of being fully present with another person — "
        "listening without agenda, reflecting without judgment, and actually making contact "
        "instead of performing conversation. "
        "It sounds more intense than it is, and it's usually more transformative than you expect. "
        "The queer community has a particular history with the difficulty of being truly seen, "
        "and a practice designed entirely around being witnessed with care is not incidentally relevant to that. "
        "First-timers are welcome. The facilitator guides everything. "
        "Show up open to it. That's all you need."
    ),
    "personal brand": (
        "Stop Blending In: Start Standing Out with a Magnetic Personal Brand. "
        "A personal branding workshop on Wednesday evening. "
        "The queer case for taking personal branding seriously: "
        "we've spent years performing for audiences who weren't interested. "
        "The skill of knowing who you are and being able to communicate it clearly is "
        "something many queer people have actually already developed — they just haven't monetized it. "
        "If your career needs a legible narrative, this workshop is the practical version of 'be yourself.' "
        "Show up. Do the exercises. Leave with something actionable."
    ),
    "shut up & write": (
        "Shut Up & Write! co-working session. "
        "The premise is simple and perfect: you show up, you don't talk, and you write. "
        "For writers who struggle with distraction (everyone) and accountability (most people), "
        "being in a room full of people who are also silently working is surprisingly effective. "
        "The queer community has always produced extraordinary writers — "
        "probably because having to narrate your own existence from scratch builds the muscle. "
        "If you have something you've been trying to write, this session gets words on the page. "
        "Show up. Write. Don't talk. Leave with progress."
    ),
    "loony bin karaoke": (
        "Karaoke at the Loony Bin. "
        "Comedy club karaoke is underrated. The room is set up for performance, the audience is "
        "already primed to be entertained, and the bar is stocked. "
        "The gay case: see above under karaoke. "
        "Pick something dramatic. Commit fully. This is the Tuesday you didn't expect."
    ),
    "frequency lounge": (
        "Karaoke Wednesdays at Frequency Lounge. "
        "Mid-week karaoke is a tradition for a reason: Wednesday is when you need it most. "
        "Frequency Lounge is a Tulsa bar with a following, and Wednesday karaoke there "
        "draws people who are genuinely committed to the bit. "
        "Pick something bold. Wednesday deserves it."
    ),
    "eerie abbey": (
        "Trivia Night at Eerie Abbey Ales Downtown. "
        "Eerie Abbey is a Tulsa craft brewery with solid beers and regular events. "
        "Trivia there draws a regular crowd that's been building teams for months, "
        "so come prepared to compete or come ready to join a team that needs a pop culture specialist. "
        "The gay team usually wins the entertainment rounds. Use that knowledge wisely."
    ),
}


def _find_description(ev: dict, score: int) -> str:
    """Return a rich website description. Check named registry first, then category fallbacks."""
    name = ev.get('name', '').lower()
    venue = ev.get('venue', '').lower()

    # Check named registry
    for key, desc in NAMED_DESCRIPTIONS.items():
        if key in name or key in venue:
            return desc

    # Category fallbacks based on keywords in name/venue
    cat_checks = [
        (['drag', 'dragnificent', 'cabaret'], _desc_drag),
        (['support group', 'support grp'], _desc_support),
        (['networking', 'mixer', 'connect'], _desc_networking),
        (['trivia'], _desc_trivia),
        (['karaoke'], _desc_karaoke),
        (['comedy', 'loony bin', 'comedian'], _desc_comedy),
        (['art crawl', 'gallery', 'exhibit', 'museum', 'art walk'], _desc_art),
        (['concert', 'live music', 'band', 'musician', 'singer', 'rooftop'], _desc_concert),
        (['brunch'], _desc_brunch),
        (['bowling'], _desc_bowling),
        (['bingo'], _desc_bingo),
        (['film', 'cinema', 'movie', 'documentary'], _desc_film),
        (['festival', 'fair', 'market'], _desc_festival),
        (['workshop', 'write', 'craft', 'sketch', 'draw'], _desc_workshop),
        (['happy hour', 'bar night', 'bar crawl'], _desc_bar),
    ]
    for keywords, fn in cat_checks:
        if any(kw in name or kw in venue for kw in keywords):
            return fn(ev, score)

    # Gay bar catch-all
    if any(bar in venue for bar in _GAY_BAR_VENUES):
        return _desc_gay_bar(ev, score)

    # Ultimate fallback
    return _desc_generic(ev, score)


def _gay_angle(ev_name: str) -> str:
    """Generate a 'gay case for going' sentence for 1-2 flamingo events."""
    return (
        "The gay case for going: the queer community has always shown up for events like this, "
        "because we know that the best rooms are the ones where curious, interesting people choose to be. "
        "Show up. You'll find your people there."
    )


def _desc_drag(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v}. "
        "Drag is Tulsa's most reliably spectacular live performance art, and this is your invitation "
        "to stop watching clips on your phone and be in the actual room. "
        "The lights, the music, the commitment of the performers — it hits completely differently live. "
        "Get close to the stage. Bring singles. Cheer loudly. Tip even louder. "
        "Drag shows in Tulsa are run by real artists doing real work, "
        "and showing up is how you support that."
    )


def _desc_support(ev, score):
    n = ev.get('name', '')
    return (
        f"{n}. "
        "Support groups exist because some things are easier to talk about with people who already get it. "
        "You don't need to be in crisis to show up — sometimes you just need a room where "
        "you're not the only one, and where you don't have to explain the basics before someone listens. "
        "First-timers are always welcome. The organizers have done this before. "
        "You belong here even if you're not sure yet."
    )


def _desc_networking(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v}. "
        "Networking events are only as useful as the people in the room and your willingness to talk to them. "
        "Set yourself a goal: find two people you'd genuinely want to have lunch with again. "
        "That's it. Two people. The rest is gravy. "
        + ("The queer case for professional networking: visibility in your industry is not optional. "
           "The people who get opportunities are usually the ones who are already known by the people "
           "giving them. This is how you get known. Show up, be yourself, ask good questions. " if score <= 2 else "")
        + "Come for the contacts. Stay because you met someone interesting."
    )


def _desc_trivia(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"Trivia Night at {v if v else 'a local bar'}. "
        "Form a team, name it something that makes at least one person at the bar laugh, "
        "and spend two hours finding out which categories you're embarrassingly good at "
        "and which ones reveal unsettling gaps in your general knowledge. "
        "The game: answer questions, drink between rounds, talk trash appropriately. "
        + ("Gay trivia teams statistically dominate pop culture, Broadway, film, fashion, and 'famous Julias' rounds. "
           "Use that advantage shamelessly. You've been training your whole life for this. " if score <= 2 else "")
        + "Make a team with strangers or bring your crew. "
        "Buy a round when you win. This is what weeknight social life is supposed to look like."
    )


def _desc_karaoke(ev, score):
    v = ev.get('venue', '')
    return (
        f"Karaoke at {v if v else 'a local bar'}. "
        "Karaoke is one of the most democratically joyful things a bar can offer. "
        "The rules are simple: pick the song that matters to you, get on the mic, commit completely. "
        "The crowd will meet you there if you mean it. "
        + ("The queer community has elevated karaoke to an art form precisely because we know how to "
           "take a moment seriously and make it into something. "
           "Pick 'Total Eclipse of the Heart.' Do it every time. Never explain yourself. " if score <= 2 else "")
        + "You don't have to be good. You have to be present. That's the whole game."
    )


def _desc_comedy(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local comedy club'}. "
        "Live stand-up comedy is one of the most underrated night-out options in any city. "
        "A good comedian in a room full of people who decide to laugh together is "
        "a surprisingly communal and human experience. "
        + ("Gay audiences are notoriously great comedy audiences — "
           "we recognize when something actually lands and we reward it generously. "
           "If this comedian earns it, they'll know it. " if score <= 2 else "")
        + "Get there early enough to order something before the show. Sit close to the stage. "
        "It's always a better show from the front."
    )


def _desc_art(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local gallery'}. "
        "Art openings and crawls are where Tulsa's creative community actually gathers, "
        "and the crowd skews curious, inclusive, and interesting. "
        "Walk slowly through the galleries. Look at everything longer than feels comfortable. "
        "If something stops you, figure out why. "
        + ("The queer community's relationship with visual art is long and documented — "
           "we've always been in the studios, the galleries, and the front row at openings. "
           "This is your crowd. Show up and find each other. " if score <= 2 else "")
        + "Buy something if you can. Talk to the artist if they're there. "
        "That's what First Fridays and art crawls are for."
    )


def _desc_concert(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local venue'}. "
        "Live music in Tulsa is better than it gets credit for, and this is the kind of show "
        "worth actually leaving the house for. "
        "The experience of being in a room when a performer is doing something real is "
        "fundamentally different from a streaming playlist, and you know it. "
        + ("Gay music fans have always been at the front of the room — "
           "we show up, we care, we remember the setlist. "
           "This artist deserves that kind of audience. Be that audience. " if score <= 2 else "")
        + "Arrive before the opener ends. Find a spot you can hold. "
        "Put your phone away for at least three songs. "
        "Let the room do what rooms do when music is working."
    )


def _desc_brunch(ev, score):
    v = ev.get('venue', '')
    return (
        f"Brunch at {v if v else 'a local spot'}. "
        "Brunch is technically a meal but functionally it's a social institution "
        "that the queer community has been perfecting for decades. "
        "The format: food that's a little indulgent, drinks that arrive before you're fully awake, "
        "and conversation that goes longer than you planned. "
        "There is no better start to a Saturday or Sunday than brunch with people you actually like. "
        "Show up hungry. Leave full and slightly warm. That's the whole plan."
    )


def _desc_bowling(ev, score):
    return (
        "Bowling night. "
        "The beauty of bowling is that it's genuinely more fun when you're bad at it. "
        "A spare is satisfying. A gutter ball followed by dramatic despair is a highlight. "
        "Bowling alleys are loud and bright and inherently social in a way that very few other "
        "activities are, and showing up with even two people makes it a good time. "
        + ("The queer bowling scene is real and it's welcoming. "
           "You don't have to know anything about bowling to belong here. " if score <= 2 else "")
        + "Rent the shoes. Bowl terribly. Have the best night."
    )


def _desc_bingo(ev, score):
    return (
        "Bingo night. "
        "Bingo is experiencing a fully justified renaissance as a queer bar event format, "
        "and for good reason: it's social, it's simple, it's exciting enough to hold the room, "
        "and it gives everyone a reason to scream. "
        "Cards are cheap. Drinks are bar prices. The joy of 'BINGO' is surprisingly genuine "
        "every single time regardless of how old you are. "
        "Show up. Get a card. Get in it."
    )


def _desc_film(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local cinema'}. "
        "Film screenings are a specific kind of shared experience that streaming has made rarer "
        "and therefore more valuable. Being in a room full of people seeing something together — "
        "especially a documentary — creates conversations that don't happen anywhere else. "
        + ("The queer case for film nights: independent cinema has always been a queer space, "
           "and the audience at screenings like this is exactly the crowd you want to be around. " if score <= 2 else "")
        + "Show up a few minutes early. Stay through the credits. Talk to someone on the way out."
    )


def _desc_festival(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local venue'}. "
        "Community festivals are exactly what Tulsa needs more of: "
        "reasons for different kinds of people to be in the same outdoor space at the same time. "
        "Walk slowly. Talk to vendors. Try the food. "
        + ("The queer community shows up for local festivals because we understand that "
           "visible community participation is how you build the city you actually want to live in. " if score <= 2 else "")
        + "Be present. Buy something local. Leave having learned something."
    )


def _desc_workshop(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local venue'}. "
        "Making something with your hands is one of the most reliably satisfying things a human can do. "
        "Workshops give you a prompt, a space, and other people working alongside you — "
        "which is usually all you need to actually finish something. "
        + ("Gay people, who are statistically over-represented in creative fields, "
           "occasionally need to be reminded that 'creative' doesn't require a portfolio. "
           "Show up. Make a thing. Judge it generously. " if score <= 2 else "")
        + "You'll leave with something and probably a few new acquaintances. That's the whole point."
    )


def _desc_bar(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local bar'}. "
        "Some nights are about the event. Some nights are about having somewhere to be. "
        "Happy hour is elegantly both: the drinks are cheaper than they'll be later, "
        "the crowd is loose and starting their night, "
        "and the barrier to showing up is low enough that you'll actually go. "
        "One drink becomes two. Two becomes dinner. That's a Friday well spent."
    )


def _desc_gay_bar(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at the bar. "
        "Gay bars are not just bars. They're the physical proof that we exist, "
        "that we've always existed, and that we deserve a room that belongs to us. "
        "Showing up to your local gay bar — even just for a drink on an unremarkable night — "
        "is participation in something that matters. "
        "The bartenders know the regulars. The regulars will talk to you. "
        "The music is usually better than you expect. Show up."
    )


def _desc_generic(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    base = (
        f"{n}{f' at {v}' if v else ''}. "
        "Getting out of the house and doing something intentional with your time "
        "is its own reward, and this is worth putting on your calendar. "
    )
    if score <= 2:
        base += (
            "The queer community has always shown up for things that are worth showing up for — "
            "and interesting rooms tend to contain interesting people. "
            "Go find out who's there. You might be surprised."
        )
    return base


# ── Main ──────────────────────────────────────────────────────────────────────

wk = config.current_week_key()
path = os.path.join('data', 'events', f'{wk}_all.json')

with open(path, encoding='utf-8') as f:
    raw = json.load(f)

events = raw if isinstance(raw, list) else raw.get('events', [])

updated = 0
for ev in events:
    score = flamingo_score(ev)
    desc = _find_description(ev, score)
    ev['website_description'] = desc
    updated += 1
    print(f"  [{score}🦩] {ev.get('name','')[:60]}")

if isinstance(raw, dict):
    raw['events'] = events
    save_obj = raw
else:
    save_obj = events

with open(path, 'w', encoding='utf-8') as f:
    json.dump(save_obj, f, ensure_ascii=False, indent=2)

print(f"\nWrote website_description to {updated} events -> {path}")
