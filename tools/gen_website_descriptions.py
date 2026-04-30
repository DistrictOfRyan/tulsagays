"""
Generate rich, persuasive website descriptions for each event.
Writes 'website_description' field to the events JSON.

Voice: Joan Crawford at a queer community mixer. Theatrical, imperious, sardonic,
withering but warm, always on the reader's side even when reading them. The goal
is to convince a shy introverted gay person to actually get off the couch, and to
tell them exactly what to do so they have the best possible time.

Rules:
- Full flowing paragraphs. No fragmented sentence bursts.
- Voice present throughout every paragraph, not just the opener and closer.
- Keep all the detail: practical specifics, arrival tips, costs, phone numbers.
- Make the gay case for going even at 1-2 flamingo events.
- No em dashes. No AI sentence fragments like "No scripts. No judgment. No fuss."
- Target: 3-4 paragraphs for website, 2-3 sentences for slide.
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
    'gabbin with gabbi', 'pride nation entertainment', 'brad lee',
    'lesbian attachment',
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
_THREE_FL = [
    'first friday art crawl', 'art crawl',
    'ballet', 'symphony', 'orchestra', 'choir', 'chorale', 'choral',
    'performing arts', 'theatre', 'theater', 'cabaret',
    'live performance', 'stage production', 'dance performance',
    'recital', 'repertory', 'philharmonic',
    'all souls',
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
    if any(kw in content for kw in _THREE_FL): return 3
    if any(kw in content for kw in _TWO_FL): return 2
    return 2  # 1 flamingo is reserved for truly exclusionary/corporate-only events


# ── Named event descriptions (keyword → description) ─────────────────────────
# Keys are lowercase substrings that must appear in the event name.
NAMED_DESCRIPTIONS = {
    "homo hotel happy hour": (
        "First Friday. The DoubleTree. The gays. Every month, Homo Hotel Happy Hour takes a "
        "downtown hotel bar and turns it into the most genuinely welcoming room in Tulsa for "
        "exactly two hours, and before you tell me you're tired or you don't know anyone who's "
        "going, I need you to understand that this event was specifically designed for the person "
        "who shows up knowing nobody and leaves knowing seven people by name. This month HHHH is "
        "raising money for Paws in Need Tulsa, which provides vet care, food, and support for pets "
        "belonging to families facing hardship, because apparently we are also saving animals while "
        "being fabulous, which is very on brand. "
        "Free admission. Raffle tickets available. Nearly all proceeds go directly to Paws in Need, "
        "so your presence is doing actual good in the world even if you spend the whole two hours "
        "working up the courage to approach someone with a great outfit. "
        "Show up at 6. Order something (the drinks are hotel-priced, which is your warning to bring "
        "the nice-night-out budget). Talk to whoever is standing next to you at the bar, because "
        "they showed up for the same reason you did. No cover. No dress code. Just the best two "
        "hours this city offers every first Friday of the month."
    ),
    "lambda bowling league": (
        "Monday night LGBTQ+ bowling at AMF Sheridan Lanes, and before you tell me bowling isn't "
        "your thing, I need you to know that it genuinely doesn't matter whether bowling is your "
        "thing, because the Lambda Bowling League is not actually about bowling. It is about queer "
        "people being in the same room on a Monday night, wearing rented shoes with zero shame and "
        "maximum personality, talking trash across lanes about gutter balls that everyone is going "
        "to pretend didn't happen. "
        "Expect lane-to-lane commentary, creative scoring interpretations, and the specific kind of "
        "easy Monday night hang that somehow always ends up being the night you tell people about "
        "afterward. No bowling experience required. In fact, the worse your game is, the better "
        "your stories are going to be. "
        "Show up. Rent the shoes. Bowl badly and own every frame of it. "
        "This is the Monday your couch has been keeping you away from."
    ),
    "monday movie night": (
        "Free movie night at one of Tulsa's most beloved gay bars. Tonight it's a punk rock "
        "documentary, which means you are going to walk in knowing approximately nothing about "
        "the Minutemen and walk out with a new favorite band and three strong opinions about the "
        "1980s underground music scene that you will be voicing to people for weeks. "
        "The bar is full of people who get it. The drinks are real. The movie costs you nothing. "
        "You were going to watch something on your couch alone tonight anyway, so watch it here, "
        "in a room full of actual humans who will be having the same experience right alongside "
        "you, which is a fundamentally different thing. "
        "Doors open early. Show up when you feel like it. Let yourself be surprised by what a "
        "good movie and a good bar can do to a Monday night."
    ),
    "dragnificent": (
        "Weekly drag at Club Majestic, and if you have never been to DRAGNIFICENT!, then you have "
        "been making a recurring error in judgment and tonight is when that ends. Doors at 9, show "
        "at 10, which gives you exactly one hour to get there, find a spot close enough to the "
        "stage to make real eye contact with a queen during a number, and figure out how many "
        "singles you're tipping (the answer is more than you currently think). "
        "Expect full performances with the kind of charisma you can feel from across the room, "
        "and at least one number that makes you genuinely reconsider whether drag is an art form, "
        "which it is, and this is the room that will prove it to you if you let it. "
        "Get there early for a good spot because the good spots go, tip generously because these "
        "performers are doing real work, and scream when you mean it because a room full of people "
        "who are giving it back to the stage is half of what makes the show what it is. "
        "Club Majestic's DRAGNIFICENT is the Thursday-night anchor of Tulsa's queer nightlife, "
        "and showing up is how you become part of that."
    ),
    "gender outreach support group": (
        "Every week at the Dennis R. Neill Equality Center, the Gender Outreach Support Group "
        "meets, and if you are trans, nonbinary, questioning, or anywhere in the wide and "
        "interesting territory of figuring out your gender, this room was built with you "
        "specifically in mind, not in the vague inspirational-poster way but in the literal sense "
        "that the people running it have lived this experience and know exactly what you walked "
        "in carrying before you say a word. "
        "You do not have to translate yourself before someone will listen. You do not have to "
        "start your story from the beginning every time. You do not have to have arrived at any "
        "particular conclusion before the room will take you seriously. "
        "First-timers are not just allowed, they are expected, and you should try to arrive about "
        "30 minutes early if you can manage it. You don't need to have it sorted out before you "
        "sit down. That is what the group is for, and the people there understand that completely."
    ),
    "osu tulsa queer support group": (
        "The OSU Tulsa Queer Support Group meets on campus on Tuesday evenings at 6 PM, open to "
        "OSU Tulsa students and the broader community, and it is not a club meeting with an agenda "
        "or a networking event or anything that requires preparation. It is an open gathering "
        "where you can talk about what you're going through, listen to others do the same, and "
        "exist in a room full of people who already understand without needing you to explain "
        "yourself from the ground up before they'll engage with you. "
        "If you're queer and in Tulsa and you've been feeling a little isolated, which is one of "
        "the most common and underreported experiences in this community, this room on Tuesday "
        "nights at the Neill Center was built for exactly that. You don't have to be in crisis "
        "to come. Sometimes you just need to be around your people, and that is a completely "
        "sufficient reason to show up."
    ),
    "queer crafters club": (
        "The Queer Crafters Club meets at the Equality Center and the whole premise is exactly "
        "what it says: queer people making things together. No crafting skills required, no "
        "judgment about what you produce, no pressure to arrive with a project or a plan. "
        "The crafting is technically the activity but it is actually the incidental part, because "
        "the real reason to come is that you will walk in with nothing in particular and walk out "
        "with something you made with your hands, at least one new person you actually like, and "
        "a thoroughly defensible reason to tell people you had plans on a Thursday evening. "
        "Bring something you're working on, or show up with nothing and borrow supplies. The vibe "
        "is relaxed, the company is genuinely good, and at least one person in the room is going "
        "to make something inexplicably beautiful. Bring yourself. That is the entire assignment."
    ),
    "equality business alliance": (
        "The Equality Business Alliance Networking Mixer is LGBTQ+ professionals doing the thing "
        "they do best, which is making real connections with people who already understand the "
        "context and don't need it explained. This is the opposite of the awkward corporate mixer "
        "where you stand near the food wondering if anyone wants to hear about your job title. "
        "The EBA crowd is warm, genuinely interesting, and present because they actually want "
        "connection, not just business cards from strangers they'll never follow up with. "
        "The event is at the Dennis R. Neill Equality Center, which means you're networking in "
        "a space that already belongs to you, and that changes the energy considerably. Order "
        "something. Talk to someone whose work sounds interesting. Ask what they're building. "
        "Leave with at least one contact you genuinely want to follow up with. LGBTQ+ "
        "professionals in Tulsa are building real things together and this is how you get to "
        "be part of that."
    ),
    "queer women's collective": (
        "The Queer Women's Collective meetup is at the Equality Center and if you are a queer "
        "woman or femme in Tulsa, I genuinely need you to stop finding reasons to skip this. "
        "The group rotates activities in a welcoming, inclusive space, and whether you're newly "
        "out, long-established in this community, or somewhere in the very large and interesting "
        "territory in between, this is a low-pressure way to actually meet your people without "
        "requiring very much from you at all. "
        "No agenda, no dues, no requirements. Just show up as you are. You have been telling "
        "yourself you'll go next time for several months now. This is next time, and it is "
        "happening regardless of whether you decide to be there."
    ),
    "pflag tulsa": (
        "PFLAG Tulsa's monthly meeting is one of the most important gatherings in this city for "
        "families, friends, and allies of LGBTQ+ people, and I want to be specific about who "
        "this is built for: it is for the people who love us and want to do right by us. This "
        "is not primarily a support group for LGBTQ+ people themselves, though you are welcome. "
        "It is specifically for the people who have a queer kid, sibling, parent, or friend and "
        "are genuinely trying to understand, support, and show up for them better. "
        "The conversations are honest, the group is warm, and the information is practical in "
        "the way that only comes from people who have actually lived through figuring this out. "
        "Meetings are monthly, free, and open to the public. Show up. Ask the questions you've "
        "been afraid to ask anywhere else. Be the family member that everyone deserves to have."
    ),
    "lambda unity": (
        "Lambda Unity Group is an LGBTQ+ AA meeting at Fellowship Congregational Church, and the "
        "thing that makes it specifically valuable is that you walk in already understood. Recovery "
        "is hard enough without also having to explain yourself before someone will fully engage "
        "with your story, and this meeting is specifically for LGBTQ+ people in recovery, which "
        "means you can talk about the parts of your experience that are uniquely queer without "
        "code-switching or softening the edges or feeling like a footnote in a room that wasn't "
        "quite built for you. "
        "If you are in recovery or considering it, this is one of the most affirming spaces Tulsa "
        "has to offer for that work. Check the listing for the current time. Show up. "
        "You belong here."
    ),
    "drag bingo": (
        "You get a bingo card. A queen calls the numbers between show-stopping drag performances. "
        "Money raised goes to Adonia, an LGBTQ+ youth organization doing real work in Tulsa. "
        "This is the most structurally perfect evening this city produces on a regular basis, "
        "and I mean that without any exaggeration: a format that is exciting enough to hold the "
        "room, performers who are genuinely committed to the work, and a fundraising purpose that "
        "means your Saturday night is also doing something meaningful in the world. "
        "The rhythm is drag number, bingo round, drag number, bingo round, and you repeat that "
        "until you have screamed BINGO or lost your voice cheering for someone's number, "
        "whichever comes first and both are honestly a win. "
        "Buy a card. Tip your queen generously because she is working. Scream when you win. "
        "You're having fun and funding something that matters, and that combination does not come "
        "around often enough."
    ),
    "tulsa eagle leather night": (
        "Leather Night at the Tulsa Eagle with DJ Kudos. The Tulsa Eagle is Tulsa's leather and "
        "bear bar, and on Leather Night the vibe is exactly what it should be: unapologetic, "
        "celebratory, and specifically designed for the part of the queer community that has been "
        "here building this scene the entire time. DJ Kudos keeps the energy right all night, "
        "which is not a small thing. "
        "There is a dress code that is strongly encouraged but not mandatory, so come leathered "
        "up, come in your best vest, come as you actually are, but come. The Eagle crowd is one "
        "of the friendliest in the city once you walk through the door, and the bar has a "
        "personality that is entirely its own and entirely worth experiencing. "
        "Doors are late. Energy is good. Show up."
    ),
    "tulsa eagle bingo": (
        "Bingo at the Tulsa Eagle on a Saturday afternoon, which sounds like it might be an "
        "unusual combination until you have actually done it, at which point you will understand "
        "completely why it works. The Eagle's bingo crowd mixes regulars, newcomers, curious "
        "first-timers, and people who will absolutely yell BINGO at full volume the instant it "
        "happens regardless of where they are in the bar. "
        "Cards are cheap. Drinks are bar prices. The energy is more festive than you might expect "
        "from a 3 PM Saturday and considerably less intimidating from the outside than it might "
        "look on paper. If you have never been to the Eagle, a Saturday afternoon bingo session "
        "is probably the single best low-stakes way to get introduced to the scene. "
        "Come in. Grab a card. Find out what Tulsa's leather community is actually like when "
        "they're calling B-7 and gossiping warmly between rounds."
    ),
    "kentuck derby": (
        "Kentucky Derby Watch Party and Derby Hat Contest at the Tulsa Eagle. The Kentucky Derby "
        "is the most extra two minutes in all of American sports, which means it has always had "
        "a devoted queer following, which makes complete sense when you consider that it involves "
        "spectacular hats, dramatic pageantry, mint juleps, and an event that takes 120 seconds "
        "but requires approximately three weeks of outfit planning to do properly. "
        "The Tulsa Eagle is the right venue for this. Bring your most outrageous derby hat "
        "because there is a contest and you should absolutely be in it. Drink something with "
        "mint in it. Scream at a horse for two minutes. Win a prize for the hat. "
        "This is the Saturday afternoon you didn't know you needed and will definitely be "
        "describing to people afterward."
    ),
    "sunday shenanigans": (
        "SUNDAY SHENANIGANS W/ SHANEL at the Tulsa Eagle, which is the unofficial close-out-the-"
        "weekend-properly event for Tulsa's queer nightlife scene and has been for long enough "
        "that it has its own regulars, its own energy, and its own particular version of a Sunday "
        "night that does not feel like the end of anything. "
        "Shanel running Sunday nights means the music is going to be right and the crowd is going "
        "to be right, which is honestly the full promise you need. The Eagle on a Sunday with "
        "Shanel is relaxed enough to genuinely wind down from Saturday but alive enough to remind "
        "you that the weekend is not over until you decide it is. "
        "Show up around 6. Stay as long as feels right. Stop checking your work email until "
        "morning because you have earned this evening and the inbox will survive."
    ),
    "sunday showdown": (
        "Open Talent Night at Club Majestic. Doors at 9, show at 11. This is unscripted, live, "
        "and completely unpredictable, which is exactly the point and also the reason you cannot "
        "leave early because the next act might be the most interesting thing you see all month. "
        "Performers sign up, take the stage, and compete live for the crowd's approval, which "
        "means some will be brilliant, some will make bold choices that land beautifully, and "
        "some will make bold choices that don't land at all, and all of it is genuinely worth "
        "watching because live performance carries real risk and that risk is what makes it feel "
        "like something actually happening rather than content. "
        "Club Majestic's Sunday Showdown is the kind of queer nightlife that keeps you up past "
        "midnight simply because you cannot bring yourself to leave before you see what comes "
        "next. Sleep is a Monday problem. Tonight is yours."
    ),
    "touchtunes friday": (
        "TOUCHTUNES FRIDAY at the Tulsa Eagle, which is the night where you and everyone else in "
        "the bar collectively decide what the evening sounds like. TouchTunes is a jukebox app "
        "that lets anyone in the bar queue songs, which means Friday night at the Eagle becomes "
        "a live negotiation between whoever wants Robyn, whoever wants classic country, and "
        "whoever is prepared to spend actual money to push their song to the top of the queue "
        "over everyone else's perfectly reasonable selection. "
        "The result is usually chaotic and almost always exactly right, because the Eagle crowd "
        "curates instinctively well on these nights and Fridays there have a loose, anything-goes "
        "energy that is genuinely hard to find anywhere else in this city. "
        "Show up. Download the app if you don't have it yet. Fight for your song. "
        "It's a legitimately good Friday."
    ),
    "shenanigans w/ shanel": (
        "SUNDAY SHENANIGANS W/ SHANEL at the Tulsa Eagle, which is the unofficial "
        "close-out-the-weekend-properly event for Tulsa's queer nightlife scene and has been "
        "for long enough that it has its own regulars, its own energy, and its own particular "
        "version of a Sunday night that does not feel like the end of anything. "
        "Shanel running Sunday nights means the music is going to be right and the crowd is "
        "going to be right, which is honestly the full promise you need. The Eagle on a Sunday "
        "with Shanel is relaxed enough to genuinely wind down from Saturday but alive enough "
        "to remind you that the weekend is not over until you decide it is. "
        "Show up around 6. Stay as long as feels right. Stop checking your email until morning "
        "because you have earned this."
    ),
    "legendary midnight drags": (
        "Tulsa's Legendary Midnight Drags at Tulsa Raceway Park, and yes, these are car drags, "
        "not the drag you were thinking of. Big engines. Green lights. Tulsa's outdoor street "
        "drag racing tradition happens monthly at the Raceway Park, and if you have never stood "
        "in a crowd while a car does something that probably shouldn't be legal and the crowd "
        "collectively loses its mind about it, you have been missing a specific kind of "
        "spectacular that is worth your time. "
        "The queer community has a long and underappreciated love of loud, fast, remarkable "
        "things, and this event delivers on all three simultaneously. The midnight start means "
        "you're staying out past your usual limit, which is honestly part of the point. "
        "Bring closed-toe shoes and a friend who won't try to make you leave before the night "
        "actually gets going. Being fabulous and appreciating horsepower are not in conflict. "
        "They never have been."
    ),
    "a people's museum": (
        "A People's Museum by AK/OK at Positive Space Tulsa. This is an international living "
        "archive of LGBTQ2S+ history told through hand-drawn portraits and the personal stories "
        "of the people in them, and it is the kind of exhibition that makes you feel genuinely "
        "seen in a way that most art shows never quite manage to accomplish. "
        "Artist and activist collective AK/OK has been traveling the world collecting these "
        "portraits, faces of queer elders and community organizers and people whose stories have "
        "never appeared in a textbook anywhere, and the result is something you need to "
        "experience in person to understand what it does to you. "
        "You will walk in thinking you have ten minutes and you will stay forty, and you will "
        "leave wanting to call your queer friends to ask if they've been yet. Positive Space "
        "Tulsa is exactly the right venue for this. Go this Saturday. Let it actually hit you."
    ),
    "brunch for the blossoms": (
        "Brunch on a Saturday morning, which is technically a meal but functionally a social "
        "institution that the queer community has been perfecting for decades and has no "
        "intention of surrendering. The format is food that's a little indulgent, drinks that "
        "arrive before you're fully awake, and conversation that reliably goes longer than you "
        "planned for when you left the house. "
        "There is no better start to a Saturday than brunch with people you actually like, and "
        "even brunch with people you're just meeting for the first time tends to work out because "
        "the format is forgiving and the table arrangement makes conversation mandatory. "
        "Show up hungry. Let yourself order the thing you normally wouldn't. "
        "Leave full and slightly warm. That's the whole plan and it works every time."
    ),
    "pump bar": (
        "Pump Bar on South Lewis is a Tulsa LGBTQ+ institution, and whatever the occasion is "
        "tonight, a party there is exactly the kind of community gathering that reminds you why "
        "Tulsa's gay bar scene matters and why showing up to your local bar is never actually "
        "a small thing. This is a neighborhood bar with real history, real personality, and a "
        "crowd that has been coming back for years because the room earns it. "
        "Come celebrate. The vibe is warm, the regulars will talk to you if you give them half "
        "a reason to, and the energy of a room full of people who are glad to be exactly where "
        "they are is contagious in the best possible way. "
        "If you've never been to Pump Bar, a party is the ideal first visit."
    ),
    "muumuus": (
        "Muumuus and Margaritas. The dress code is a muumuu. The drink is a margarita. "
        "The vibe is exactly what it sounds like, which is to say it is perfect. "
        "This is the gay-coded social event the internet would have invented if the Tulsa queer "
        "community hadn't gotten there first, and the premise requires no justification because "
        "the premise is a muumuu and a margarita and you already know whether you're in. "
        "Put on something flowy. Grab a drink. Show up. Spend a few hours with people who "
        "understand that comfort and fabulousness are not opposites and have never been. "
        "You have been looking for a reason to wear that thing. Here it is. No more excuses."
    ),
    "gypsy": (
        "Gypsy the Musical at the Tulsa Performing Arts Center. Everything's Coming Up Roses. "
        "Let Me Entertain You. Together Wherever We Go. This is the Merman canon, the mother "
        "of all American stage musicals, and it has been gay culture for 65 years for very good "
        "reason: it is the story of Mama Rose, arguably the most fascinating and terrifying "
        "stage mother in the history of American theater, and the score is objectively perfect "
        "from the overture to the final note. "
        "If you love musical theater, this is one you see, full stop, and the Tulsa Performing "
        "Arts Center is a beautiful venue that is worth dressing up for. Buy a ticket. Sit close "
        "enough to see faces during the big numbers. Let the score do what it does to you, "
        "which will be considerable and which you will not be able to stop. "
        "Fair warning: you will leave humming Everything's Coming Up Roses for at minimum three "
        "days and there is absolutely nothing to be done about that."
    ),
    "mahler": (
        "Mahler's Symphony No. 2, 'Resurrection,' at the Tulsa Performing Arts Center. The "
        "Resurrection Symphony is 90 minutes of Mahler asking the biggest possible questions in "
        "the biggest possible room, and it ends with a full choir and orchestra building to one "
        "of the most overwhelming finales in the entire orchestral canon, the kind of music that "
        "does something to your chest before your brain has had time to process what's happening. "
        "The queer community has a long and documented relationship with Mahler because the "
        "intensity, the drama, and the emotional scale are things that resonate on a cellular "
        "level for people who have had to feel things at full volume for their entire lives. "
        "If you have never heard a symphony orchestra live, this is a formidable place to start, "
        "and if you have, you already know exactly what you're walking into. Dress like you mean "
        "it. The music will handle everything else."
    ),
    "robert randolph": (
        "Robert Randolph at Cain's Ballroom for CARNEY FEST '26. Robert Randolph plays sacred "
        "steel guitar in a way that makes the instrument sound like it was specifically built to "
        "be played this loud, this joyfully, and this hard, and Cain's Ballroom has legendary "
        "acoustics and a wood floor you can feel resonating in your feet when the sound is right. "
        "The combination of this specific artist in this specific room is the kind of live music "
        "experience that people are still describing years after the fact. "
        "Gay music fans have been at the front of the concert hall since concert halls existed, "
        "and this is the show worth showing up early and fighting for a good spot at. "
        "You will feel it in your chest for days afterward. Go."
    ),
    "gillian welch": (
        "An Evening with Gillian Welch and David Rawlings at Guthrie Green. Gillian Welch is "
        "one of the most respected voices in American folk and Americana, full stop, and this "
        "is a rare off-the-cuff concert format, stripped down and intimate, at Guthrie Green, "
        "which is one of Tulsa's best outdoor venues for exactly this kind of show. "
        "The queer folk music connection to Welch is real and documented: her music is about "
        "honesty, survival, and people living at the margins with grace, and it hits differently "
        "under an open sky than it does anywhere else. "
        "Bring a blanket if there's any chance it gets cool in the evening. Arrive early enough "
        "to find a genuinely good spot. This is the Wednesday night you will still be talking "
        "about by the end of the week."
    ),
    "karaoke": (
        "Karaoke night, and before you tell me you can't sing I need you to understand that this "
        "is the least relevant information you could possibly offer, because karaoke has never "
        "once been about singing ability and it is not going to start tonight. It has always "
        "been about picking the song that has been living in your chest for years and getting up "
        "there and delivering it like you are closing a Broadway run, regardless of what your "
        "actual vocal range is doing at that particular moment. "
        "There is a reason gay bars have had karaoke nights since forever, and it is because the "
        "combination of a microphone, a crowd of people who are genuinely rooting for you, and "
        "zero consequences for ambition creates a specific kind of permission that is genuinely "
        "rare in adult life and worth finding whenever you can. "
        "Put your name in early because the list fills up. Pick something you would be slightly "
        "embarrassed to admit you love this much. That is always the right song. "
        "The crowd will meet you there if you mean it."
    ),
    "trivia": (
        "Trivia night, which is the most reliably good weeknight activity a bar can offer and "
        "I say that with complete conviction based on extensive personal research. You form a "
        "team, you give it a name that is funnier than you planned when you were doing it "
        "quickly, and you spend two hours discovering both how much random knowledge you have "
        "accumulated in extremely specific categories and how little you know about other things "
        "you thought you had a handle on. "
        "The gay case for trivia is entirely straightforward: we disproportionately dominate the "
        "pop culture, film, fashion, and Broadway rounds, we have the vocabulary to make every "
        "team name a pun, and we are genuinely excellent company during the rounds we don't know. "
        "Make a team with strangers or bring your crew. Name it something that gets a visible "
        "reaction from the host when they read it aloud. Buy a round when you win. "
        "This is what weeknight social life is supposed to look like."
    ),
    "first friday art crawl": (
        "First Friday Art Crawl in the Tulsa Arts District, which happens once a month and "
        "involves the galleries along Archer Street opening their doors, putting out wine, and "
        "letting the city walk through and actually look at things together in the same space "
        "at the same time. The crowd it pulls is artsy, inclusive, and gay-friendly in the way "
        "that Tulsa's arts community tends to be, and the whole evening functions as a genuine "
        "neighborhood party with gallery stops woven in between conversations. "
        "Walk slowly, because this is the event that rewards slowness and punishes people who "
        "rush through it. Look at everything for longer than feels strictly necessary. Find one "
        "piece that genuinely stops you and take the time to figure out why it did. Talk to "
        "the artist if they're present, because most of them want to talk to you. Buy something "
        "if you can, because buying local art is one of the better uses of discretionary income "
        "in this city. "
        "Then get dinner somewhere on Archer afterward and call it a complete First Friday, "
        "because that is exactly what it is."
    ),
    "loony bin": (
        "Comedy show at the Loony Bin. The Loony Bin is Tulsa's established comedy club and "
        "they bring in touring acts regularly, which matters because touring comedians who play "
        "mid-size cities are often working out material that hasn't been performed to death yet "
        "and hasn't gone through the Netflix special smoothing process, which means you get "
        "something rawer and more alive than the polished version you'd stream six months later. "
        "Stand-up comedy is one of the great gay-night-out activities because a good comedian "
        "and a room full of strangers who all decide to laugh at the same moment together is "
        "a weirdly communal and unexpectedly human experience that is genuinely hard to replicate. "
        "Get there early enough to order something before the show starts. Sit close to the "
        "stage, because it is always a better show from the front. That is the whole plan."
    ),
    "cindy kaza": (
        "Cindy Kaza at the Loony Bin Comedy Club. Cindy Kaza is a touring comedian playing "
        "Tulsa this week, and comedy shows at the Loony Bin are a reliable outing because the "
        "room is intimate, the drinks are bar prices, and a touring comedian generally has "
        "tighter and fresher material than you'd get at a local open mic. "
        "Gay people have excellent taste in comedy, famously, and the skill is knowing which "
        "rooms to use it in. This is one of those rooms. Show up, support live comedy and the "
        "club that hosts it, and spend ninety minutes actually laughing out loud in a room full "
        "of other people doing the same thing. "
        "That is a better Friday than whatever you were considering instead."
    ),
    "drew dunn": (
        "Drew Dunn at the Loony Bin Comedy Club. Stand-up comedy on a Wednesday night at "
        "Tulsa's main comedy club, and a touring act means material that is fresher than the "
        "Netflix special version because it is still being developed and refined in rooms "
        "exactly like this one. "
        "The queer community has always had a complicated and devoted relationship with comedy "
        "because we know when something actually lands and when it doesn't, and we make "
        "genuinely great audiences for comedians who have something real to say. "
        "Wednesday nights are underrated for going out: the crowds are smaller, the energy is "
        "more focused, and you are not fighting for parking. Show up. Drink something. "
        "Laugh out loud. Go home happy. The week gets easier after that."
    ),
    "rooftop concert": (
        "Rooftop Concert Series at Soma Tulsa: BRANJAE is a Tulsa musician with a following "
        "for a reason, and the combination of a rooftop venue and an artist with actual stage "
        "presence is one of those Tuesday night experiences that punches considerably above "
        "its weekday weight. "
        "Soma is a creative, inclusive venue that draws an artsy crowd, and the rooftop setting "
        "means sunset views, open air, and a concert that feels more intimate than the size of "
        "the space would suggest. Arrive before it starts, because the good spots are worth "
        "arriving early for. Find where you want to stand. Put your phone away long enough to "
        "actually hear the first song with your full attention. "
        "Live music in Tulsa is genuinely underrated, and this is exactly the kind of show "
        "that reminds you why you should go out on a Tuesday."
    ),
    "sunset cinema": (
        "Sunset Cinema Presents: 'We Jam Econo: The Story of the Minutemen' at Circle Cinema. "
        "The Minutemen were a San Pedro punk trio who made music that sounded like nothing else "
        "and influenced everyone who came after them, and if you know them you already know "
        "why this is a must. If you don't, this documentary is the best possible introduction "
        "because it is a film about originality, friendship, and making art with exactly what "
        "you have, which is a story the queer underground has been living for decades. "
        "Circle Cinema is Tulsa's beloved independent movie house, which means this is a free "
        "film at a great venue with an audience that genuinely cares about what it's watching. "
        "Show up. Discover your new favorite band. Tell everyone about them for the next month."
    ),
    "queen bess": (
        "Queen Bess Centennial Aviation Arts Festival: 'The Flying Ace' Silent Film at Circle "
        "Cinema. Bessie Coleman was the first Black woman and first Native American to earn a "
        "pilot's license. She did it in 1921, in France, because no American flight school "
        "would accept her. Tulsa is honoring her centennial with a free silent film and live "
        "musical performance. "
        "This is the intersection of history, art, aviation, and the kind of story about a "
        "person who simply refused to be told no, which has always resonated deeply in the "
        "queer community because we have always known what it costs to insist on existing. "
        "Circle Cinema. Free. Bring someone who doesn't know the Bessie Coleman story yet. "
        "They will leave wanting to know everything."
    ),
    "annie": (
        "Auditions for Annie the Musical. Yes, Annie. The red dress. The orphans. Tomorrow. "
        "Sandy the dog. Daddy Warbucks. If you have ever once, even privately, belted 'It's a "
        "Hard Knock Life' into a hairbrush when no one was watching, this audition is for you "
        "and somewhere deep down you already know it. "
        "Musical theater auditions are where community theater meets genuine ambition, and the "
        "queer community's specific and documented relationship with Annie is not an accident. "
        "The auditions are at 1301 S. Boston Avenue. You do not have to be a trained performer "
        "because community theater exists for people who love this, not just people who studied it. "
        "Show up. Sing your sixteen bars. Find out what you're made of. Miss Hannigan will not "
        "be played by you specifically, but let us not rule anything out definitively."
    ),
    "networking": (
        "Networking mixer at Oklahoma Joe's BBQ, and I know that networking events have a "
        "reputation and sometimes they earn it. The cure is showing up with a different goal: "
        "instead of trying to collect business cards, try to find two people you would actually "
        "want to have lunch with again in two weeks. That is the whole assignment. "
        "Oklahoma Joe's BBQ is a relaxed setting with genuinely good food, which already "
        "puts this ahead of the sad conference room networking events of the world on pure "
        "logistics. The queer case for professional networking is straightforward: we are "
        "historically underrepresented in senior roles and knowing the right people matters "
        "more than almost anything else in building a career. "
        "Go. Be interesting. Ask good questions. Eat something. If you walk out with one real "
        "connection, it was worth every minute."
    ),
    "urban sketchers": (
        "Urban Sketchers Tulsa meet-up at Mother Road Market. Urban Sketchers is an "
        "international community of people who draw the world around them on location, in "
        "public, as it actually looks right now. Mother Road Market is an excellent place "
        "to do this because the indoor food hall setting gives you food, coffee, interesting "
        "faces, and enough variety to sketch for hours without running out of subject matter. "
        "The queer case for Urban Sketchers is simple: any group of people who carry "
        "sketchbooks into public spaces and draw strangers without judgment is self-selecting "
        "for exactly the kind of interesting company we tend to find. You do not have to be "
        "skilled at drawing. Sketching on location is about looking closely at what's actually "
        "in front of you, not about performing. Show up with a notebook. "
        "Leave with a Saturday memory you made with your hands."
    ),
    "tulsa indian club": (
        "Tulsa Indian Club Spring Festival: Native Arts and Crafts, Indian Tacos and More at "
        "Jenks Riverwalk. This is a genuine community cultural festival celebrating Native "
        "arts, food, and tradition along the Jenks Riverwalk, run by an organization that "
        "has been doing this for decades and does it well. "
        "The queer and Two-Spirit Indigenous community is a real and important part of this "
        "story, because Two-Spirit identities predate colonial definitions of gender and "
        "sexuality by a very long time, and Native cultural events are increasingly spaces "
        "of meaningful intersection. Come for the Indian tacos, which are legitimately "
        "excellent and worth the trip on their own. Stay for the art. Leave having learned "
        "something about the community that was here first."
    ),
    "craft & drafts": (
        "Craft and Drafts DIY Workshop at Cabin Boys Brewery. Make something with your hands "
        "while drinking a beer. This is the most honest description of an event that exists, "
        "and it works every single time because the combination is simply correct. Cabin Boys "
        "is a Tulsa brewery with a good reputation, and combining crafts with draft beer on a "
        "Sunday afternoon is the proper way to close out a weekend. "
        "The queer community has always been over-represented in creative spaces, and a DIY "
        "workshop at a brewery is the ideal low-stakes way to try making something without "
        "any pressure whatsoever to be good at it. Show up. Make a thing. Drink a beer. "
        "Tell people on Monday that you 'did a craft' this weekend. They will ask to see it. "
        "Show them proudly."
    ),
    "ok so tulsa": (
        "Ok So Tulsa Grand Slam: Tulsa's Best Storyteller Competition at Cain's Ballroom. "
        "True storytelling competitions are one of the best live events you can attend in any "
        "city, and the format is simple and perfect: real people, real stories, five-minute "
        "time limit, and an audience that votes for the winner. No scripts, no safety net, "
        "just someone standing in front of people trying to tell the true thing as well as "
        "they can. "
        "Cain's Ballroom is a legendary venue. The queer community has always produced "
        "extraordinary storytellers because we have had to be, because our stories weren't "
        "being told anywhere else and we learned to tell them ourselves. "
        "Come watch people compete to say the true thing in the most interesting way possible. "
        "It's a Saturday night that will make you feel more human than most Saturday nights do."
    ),
    "all souls unitarian": (
        "All Souls Unitarian Sunday Services. All Souls in Tulsa is one of the most LGBTQ-"
        "affirming congregations in the city, explicitly welcoming and radically inclusive in "
        "the way that actually means something rather than just being a line somewhere in a "
        "mission statement. Services run at 10:00 AM and 11:15 AM. "
        "Whether you're spiritual, questioning, agnostic but curious, or simply looking for a "
        "community that does not require you to check your identity at the door before they "
        "will engage with you fully, All Souls is worth showing up to. Many queer Tulsans "
        "have found genuine long-term community here. "
        "Walk in knowing nothing. You will feel the difference from the moment you're inside."
    ),
    "spiritual discussion": (
        "Spiritual Discussion: Reinvent Yourself Spiritually at Martin Regional Library. "
        "Sunday afternoon at the library, a free discussion group about spirituality, "
        "reinvention, and questioning the frameworks you were handed when you were young. "
        "The queer journey and the spiritual journey have always had a great deal in common, "
        "because both frequently involve questioning what you were taught, figuring out what "
        "actually resonates when you hold it up to the light, and building a relationship "
        "with something larger than yourself entirely on your own terms. "
        "No particular tradition is required. Show up curious. Leave with something to sit "
        "with for the rest of the week."
    ),
    "antiracist support group": (
        "Tulsa Antiracist Support Group at Zarrow Library. This is a group of people committed "
        "to understanding and dismantling racism in their own lives and in their community, "
        "meeting regularly to hold each other accountable to doing that work rather than just "
        "thinking about it. "
        "The queer community and the antiracist movement have always been linked because racism "
        "is a queer issue, because Black queer lives are LGBTQ+ lives, and because "
        "intersectionality is not a theory you discuss in a seminar, it is real people's actual "
        "daily experience. This group meets at the library. It is free. It is open. Show up "
        "if you are committed to doing the work and not just feeling good about having opinions."
    ),
    "happy hour": (
        "Happy hour, and I know that happy hour sounds like a modest proposition until you "
        "understand how it actually plays out in practice. The drinks are cheaper than they "
        "will be later in the evening. The crowd is loose and early in their night and "
        "therefore at their most approachable. The barrier to showing up is low enough that "
        "you will actually do it, which is the most important variable in the entire equation "
        "of going out. "
        "One drink becomes two. Two becomes someone suggesting dinner somewhere nearby. "
        "Dinner becomes the kind of Friday night you are still talking about the following "
        "week. You know how this goes because you have been there before. "
        "Start at happy hour. Let the evening find itself from there."
    ),
    "karaoke brunch": (
        "Karaoke Brunch, which is brunch plus karaoke on a Sunday morning, and I want you to "
        "sit with that combination for a moment because it genuinely represents the apex of "
        "what civilization has produced. The only thing better than performing Total Eclipse "
        "of the Heart at midnight is doing it at 11 AM with eggs on the table, a bottomless "
        "mimosa in your hand, and absolutely no hangover yet to complicate your commitment. "
        "The willingness to do karaoke at brunch is an inherently queer act and a testament "
        "to a healthy relationship with self-consciousness (specifically: having abandoned it). "
        "Order the indulgent thing on the menu. Pick Barracuda. Own every single note of it "
        "with zero apology."
    ),
    "archer creatives": (
        "First Friday on Archer: Archer Creatives pop-up in the Tulsa Arts District. The arts "
        "district on First Friday is the most walkable, social, gay-friendly thing you can do "
        "on a Friday evening in this city, and Archer Creatives popping up means art, makers, "
        "and the general good energy of people who make things and genuinely want you to see "
        "what they've been working on. "
        "The crowd on Archer on First Friday is artsy, curious, and warm in the specific way "
        "that people who show up for things tend to be. Walk from gallery to gallery. Stop at "
        "the pop-up. Buy something from a local maker because it will mean something to them "
        "and you'll like looking at it. End the night somewhere on Archer with something good "
        "to eat. That is the move and it works every single time."
    ),
    "painters outing": (
        "Painters Outing with Twilight Exhibit in the Philbrook Garden. Philbrook Museum's "
        "garden on a Friday afternoon with an exhibit and painters working outdoors is a "
        "genuinely beautiful way to spend a First Friday afternoon before the evening events "
        "start, and it is the kind of thing you will be glad you did even though you almost "
        "didn't bother. "
        "Philbrook is one of Tulsa's great gifts, a real museum in a mansion and garden that "
        "punches well above its size and is worth your time whenever it opens its doors. "
        "Bring a jacket if it might be cool. Stay longer than you initially planned. "
        "Then head to the Art Crawl on Archer afterward and call it a complete and entirely "
        "successful First Friday."
    ),
    "chris hardwick": (
        "Chris Hardwick at the Loony Bin Comedy Club. Chris Hardwick is a comedian and media "
        "personality best known for hosting Talking Dead and @Midnight, and seeing someone "
        "with this profile at a mid-size comedy club means an intimate show with material that "
        "is being developed and refined in real time in front of a room that can actually "
        "affect how the jokes land going forward. "
        "The gay comedy audience is a good one, we tend to be sharp, quick, and genuinely "
        "appreciative of comedians who are doing real work rather than just running through "
        "the familiar material. If this comedian earns the room, they'll know it. "
        "Show up. Drink something. Laugh. That is a Friday."
    ),
    "little big town": (
        "Little Big Town at The Cove at River Spirit Casino. Little Big Town is a country "
        "music group with a massive queer following, largely because Karen Fairchild and "
        "Kimberly Schlapman are genuine style icons, their four-part harmonies are objectively "
        "flawless, and Girl Crush was a gay anthem before country radio finished being "
        "complicated about it. "
        "River Spirit Casino's Cove venue is a solid mid-size concert room with good sight "
        "lines throughout. If you are a country music fan in Tulsa's queer community, this "
        "is the show this season, full stop. Dress up slightly because this group deserves it. "
        "Get there early enough for a good spot. Let the harmonies do what they do."
    ),
    "circling": (
        "Authentic Relating Lab (Circling) at a private location. Circling is a structured "
        "practice of being fully present with another person, listening without agenda, "
        "reflecting without judgment, and actually making real contact instead of performing "
        "conversation the way we usually do in public. "
        "It sounds more intense than it is, and it is almost always more genuinely "
        "transformative than people expect going in. The queer community has a particular "
        "and well-documented history with the difficulty of being truly seen, and a practice "
        "designed entirely around being witnessed with care and attention is not incidentally "
        "relevant to that experience. "
        "First-timers are welcome and the facilitator guides everything. "
        "Show up open to it. That is genuinely all you need."
    ),
    "personal brand": (
        "Stop Blending In: Start Standing Out with a Magnetic Personal Brand. A personal "
        "branding workshop on Wednesday evening, and the queer case for taking personal "
        "branding seriously is actually straightforward: we have spent years learning to "
        "perform for audiences who weren't particularly interested in us, and the skill of "
        "knowing who you are and being able to communicate it clearly with confidence is "
        "something many queer people have actually already developed in the process of "
        "surviving that. "
        "What this workshop does is show you how to stop leaving that skill on the table "
        "and start using it where it can actually do you some good. If your career needs a "
        "clearer and more compelling narrative, this is the practical version of 'be yourself.' "
        "Show up. Do the exercises. Leave with something actionable."
    ),
    "shut up & write": (
        "Shut Up and Write co-working session. The premise is simple and genuinely excellent: "
        "you show up, you don't talk to anyone, and you write. For writers who struggle with "
        "distraction (everyone) and accountability (most people), being in a room full of "
        "other people who are also silently working is surprisingly effective because the "
        "social contract of the space keeps you at the page when you'd otherwise drift. "
        "The queer community has always produced extraordinary writers, probably because "
        "having to narrate your own existence from scratch before anyone else will do it "
        "for you builds the muscle in ways nothing else quite does. "
        "If you have something you've been trying to write, this session gets words on the "
        "page. Show up. Write. Don't talk. Leave with actual progress to show for it."
    ),
    "loony bin karaoke": (
        "Karaoke at the Loony Bin. Comedy club karaoke is underrated because the room is set "
        "up for performance, the audience arrived primed to be entertained, and the bar is "
        "properly stocked for the occasion. "
        "The gay case for karaoke at a comedy club specifically: you are in a room full of "
        "people who came out on a Tuesday night to be surprised by something, and you could "
        "be that thing. Pick something dramatic. Commit to it completely. "
        "This is the Tuesday night you did not see coming."
    ),
    "frequency lounge": (
        "Karaoke Wednesdays at Frequency Lounge. Mid-week karaoke is a tradition for a reason, "
        "which is that Wednesday is the night you need it most and the night you are most "
        "likely to talk yourself out of going. Do not talk yourself out of going. "
        "Frequency Lounge is a Tulsa bar with a following, and Wednesday karaoke there draws "
        "people who are genuinely committed to the bit, which makes the room better than your "
        "average Tuesday. Pick something bold. Wednesday deserves that from you."
    ),
    "eerie abbey": (
        "Trivia Night at Eerie Abbey Ales Downtown. Eerie Abbey is a Tulsa craft brewery with "
        "solid beers and regular events, and trivia there draws a regular crowd that has been "
        "building teams and competing for long enough that they know each other's weaknesses "
        "by category. "
        "Come prepared to compete, or come ready to join a team that needs someone who is "
        "very good at exactly the rounds you happen to be very good at. The gay team "
        "historically dominates the entertainment rounds. Use that knowledge wisely "
        "and without mercy."
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
    """Generate a 'gay case for going' paragraph for 1-2 flamingo events."""
    return (
        "The queer community has always shown up for the rooms worth being in, and the best "
        "rooms are rarely the ones that announce themselves as such in advance. Interesting "
        "spaces attract interesting people, and you are more likely to find your people in a "
        "place where curiosity and engagement are already the price of entry. "
        "Show up. See who's there. You might be pleasantly surprised by what a room can hold."
    )


def _desc_drag(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v}. Drag is Tulsa's most reliably spectacular live performance art, and this "
        "is your invitation to stop watching clips on your phone and actually be in the room "
        "where it's happening, which is a fundamentally different experience that no screen "
        "has ever fully managed to replicate. The lights, the music, the specific commitment "
        "of a performer who is giving you everything they have, it hits completely differently "
        "when you are standing there in front of it. "
        "Get close to the stage if you can. Bring singles because tipping your performers is "
        "not optional, it is the contract. Cheer loudly and mean it. "
        "Drag shows in Tulsa are run by real artists doing real work, and showing up and being "
        "present and putting money in their hands is how you support that work continuing."
    )


def _desc_support(ev, score):
    n = ev.get('name', '')
    return (
        f"{n}. Support groups exist because some things are simply easier to talk through "
        "with people who already understand the territory from the inside, not because they "
        "read about it somewhere but because they have lived it. You do not need to be in "
        "crisis to show up, and you do not need to have your story fully sorted out before "
        "you walk through the door. Sometimes you just need a room where you are not the "
        "only one, and where you do not have to explain the basics before someone will "
        "engage with what you're actually saying. "
        "First-timers are always welcome. The organizers know what they're doing. "
        "You belong here even if you are not yet entirely sure why."
    )


def _desc_networking(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "The queer case for professional networking is simple and documented: we are "
        "historically underrepresented in senior roles, and knowing the right people "
        "matters enormously. The people who get the opportunities are usually the ones "
        "who are already known by the people giving them. This is how you get known. " if score <= 2 else ""
    )
    return (
        f"{n} at {v}. Networking events are only as useful as the people in the room and "
        "your genuine willingness to talk to them, which means the goal is not to collect "
        "as many business cards as possible but to find two people you would actually want "
        "to have lunch with again in two weeks. That is the whole assignment, and it is "
        "achievable at almost any event if you approach it right. "
        + gay_line +
        "Go. Be genuinely interesting. Ask questions that show you were actually listening. "
        "Eat something. If you walk out with one real connection, it was worth every minute."
    )


def _desc_trivia(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "Gay trivia teams statistically dominate the pop culture, Broadway, film, and "
        "'famous Julias' rounds, and this is not something you should be modest about. "
        "Use that advantage shamelessly. You have been training your entire adult life "
        "for exactly this. " if score <= 2 else ""
    )
    return (
        f"Trivia Night at {v if v else 'a local bar'}. You form a team, you name it something "
        "that makes at least one person at the bar genuinely laugh when it's read aloud, and "
        "you spend two hours finding out which categories you are embarrassingly good at and "
        "which ones reveal unsettling gaps in your general knowledge that you did not "
        "previously know were there. "
        + gay_line +
        "Make a team with strangers if you came alone because it is genuinely more fun that "
        "way, or bring your crew and embarrass yourselves together. "
        "Buy a round when you win. This is what a good weeknight is supposed to look like."
    )


def _desc_karaoke(ev, score):
    v = ev.get('venue', '')
    gay_line = (
        "The queer community has elevated karaoke to an art form precisely because we "
        "understand intuitively what it means to take a moment seriously and make it into "
        "something, regardless of whether anyone asked us to. Pick Total Eclipse of the "
        "Heart. Do it every single time. Never explain yourself to anyone. " if score <= 2 else ""
    )
    return (
        f"Karaoke at {v if v else 'a local bar'}. Before you tell me you cannot sing I need "
        "you to understand that this is genuinely the least relevant information you could "
        "offer about karaoke, because it has never been about singing ability and it will "
        "not start being about that tonight. It is about picking the song that matters to "
        "you and getting up there and delivering it like you mean every word, regardless "
        "of what your vocal range is doing at that particular moment. "
        + gay_line +
        "You don't have to be good. You have to be present and committed. That is the "
        "whole game. The crowd will meet you there if you actually mean it."
    )


def _desc_comedy(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "Gay audiences are notoriously excellent comedy audiences because we recognize when "
        "something actually lands and we reward it generously and specifically, which is the "
        "kind of feedback a comedian actually learns from. If this comedian earns the room, "
        "they will know it. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local comedy club'}. Live stand-up comedy is one of the "
        "most consistently underrated night-out options in any city, largely because a good "
        "comedian in a room full of people who all decide to laugh at the same moment "
        "together is a weirdly communal and unexpectedly human experience that is genuinely "
        "hard to replicate through a screen. "
        + gay_line +
        "Get there early enough to order something before the show starts. Sit close to the "
        "stage because it is always a better show from the front and you deserve the better show."
    )


def _desc_art(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "The queer community's relationship with visual art is long and well-documented: "
        "we have always been in the studios, the galleries, and the front row at openings. "
        "This is your crowd. Show up and find each other. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local gallery'}. Art openings and crawls are where Tulsa's "
        "creative community actually gathers, and the crowd they pull skews curious, "
        "inclusive, and interesting in the specific way that people who show up for art "
        "tend to be. "
        "Walk slowly through the space. Look at everything for longer than feels strictly "
        "necessary. If something genuinely stops you, take the time to figure out why. "
        + gay_line +
        "Buy something if you can. Talk to the artist if they're there, because most of "
        "them genuinely want to talk to you. That is what these evenings are for."
    )


def _desc_concert(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "Gay music fans have always been at the front of the room because we show up, "
        "we care, and we remember the setlist. This artist deserves that kind of audience. "
        "Be that audience. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local venue'}. Live music in Tulsa is better than it gets "
        "credit for, and this is the kind of show worth actually leaving the house for. "
        "The experience of being in a room when a performer is doing something real is "
        "fundamentally different from a streaming playlist, and you already know this because "
        "you have felt it before in a room that was working. "
        + gay_line +
        "Arrive before the opener ends because openers are often worth it. Find a spot you "
        "can hold. Put your phone away for at least three songs. Let the room do what "
        "rooms do when music is actually working."
    )


def _desc_brunch(ev, score):
    v = ev.get('venue', '')
    return (
        f"Brunch at {v if v else 'a local spot'}. Brunch is technically a meal but "
        "functionally a social institution that the queer community has been perfecting "
        "for decades and has no intention of ceding to anyone. The format is food that's "
        "a little indulgent, drinks that arrive before you're fully awake, and conversation "
        "that reliably goes longer than you planned for when you sat down. "
        "There is no better start to a Saturday or Sunday than brunch with people you "
        "actually like, and even brunch with people you're just meeting tends to work out "
        "because the table arrangement makes conversation mandatory and the mimosas make "
        "it easier than usual. "
        "Show up hungry. Order the thing you'd normally talk yourself out of. "
        "Leave full and slightly warm. That is the entire plan and it works every time."
    )


def _desc_bowling(ev, score):
    gay_line = (
        "The queer bowling scene is real, it is welcoming, and you do not have to know "
        "anything about bowling to belong in it. " if score <= 2 else ""
    )
    return (
        "Bowling night. The beauty of bowling as a social activity is that it is genuinely "
        "more fun when you are bad at it, which removes the pressure entirely and replaces "
        "it with something better. A spare is satisfying. A gutter ball followed by "
        "theatrical despair is a highlight. Bowling alleys are loud and bright and "
        "inherently social in a way that very few other activities manage, and showing up "
        "with even two people makes it a genuinely good time. "
        + gay_line +
        "Rent the shoes. Bowl badly and commit to it. Have the best night."
    )


def _desc_bingo(ev, score):
    return (
        "Bingo night. Bingo is in the middle of a fully justified renaissance as a queer "
        "bar event format, and for good reason: it is social, it is simple, it is exciting "
        "enough to hold a room's attention, and it gives everyone a reason to scream "
        "something at full volume in public, which is an underrated pleasure. "
        "Cards are cheap. Drinks are bar prices. The genuine joy of yelling BINGO is "
        "surprisingly real every single time regardless of how old you are or how "
        "many times you have played before. "
        "Show up. Get a card. Get in it. That is the whole assignment."
    )


def _desc_film(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "Independent cinema has always been a queer space, and the audience at screenings "
        "like this is exactly the crowd worth being around. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local cinema'}. Film screenings are a specific kind of "
        "shared experience that streaming has made rarer and therefore considerably more "
        "valuable. Being in a room full of people seeing something together, especially a "
        "documentary, creates a particular kind of conversation afterward that simply does "
        "not happen anywhere else. "
        + gay_line +
        "Show up a few minutes early so you get a good seat. Stay through the credits. "
        "Talk to someone on the way out about what you just watched. "
        "That is what these evenings are for."
    )


def _desc_festival(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "The queer community shows up for local festivals because we understand that "
        "visible participation in the life of your city is how you build the version of "
        "it you actually want to live in. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local venue'}. Community festivals are exactly what "
        "Tulsa needs more of: reasons for different kinds of people to be in the same "
        "outdoor space at the same time, doing the same thing, which is looking at things "
        "and eating food and talking to strangers and being reminded that your city is "
        "more interesting than your usual route through it suggests. "
        + gay_line +
        "Walk slowly. Talk to vendors. Try the food from the booth you've never tried. "
        "Buy something local. Leave having learned at least one thing you didn't know."
    )


def _desc_workshop(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    gay_line = (
        "Gay people, who are statistically over-represented in creative fields, "
        "occasionally need the reminder that being creative does not require a portfolio "
        "or a finished body of work to show anyone. Show up. Make a thing. "
        "Judge it generously. " if score <= 2 else ""
    )
    return (
        f"{n} at {v if v else 'a local venue'}. Making something with your hands is one "
        "of the most reliably satisfying things a human can do, and workshops give you the "
        "thing that is hardest to manufacture on your own: a prompt, a space, and other "
        "people working alongside you, which is usually all the structure you actually need "
        "to finish something you've been putting off. "
        + gay_line +
        "You will leave with something you made and probably a few new acquaintances you "
        "did not have when you walked in. That is the whole point of coming."
    )


def _desc_bar(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'a local bar'}. Some nights are about the event and some "
        "nights are simply about having somewhere to be and a reason to be there, and "
        "happy hour is elegantly both of those things at once. The drinks are cheaper "
        "than they will be later. The crowd is loose and in the early part of their "
        "evening and therefore at their most open. The bar to showing up is low enough "
        "that you will actually do it, which is the variable that matters most. "
        "One drink becomes two. Two becomes someone suggesting dinner somewhere nearby. "
        "That is a Friday well spent, and you know it because you have been there before."
    )


def _desc_gay_bar(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    return (
        f"{n} at {v if v else 'the bar'}. Gay bars are not just bars. They are the "
        "physical proof that we exist, that we have always existed, and that we deserve "
        "a room that genuinely belongs to us without conditions or asterisks. Showing up "
        "to your local gay bar, even just for one drink on an otherwise unremarkable "
        "night, is participation in something that matters more than it might look like "
        "from the outside. "
        "The bartenders know the regulars. The regulars will talk to you if you give "
        "them any reason to. The music is usually better than you expect. "
        "Show up. The room is better when you're in it."
    )


def _desc_generic(ev, score):
    n = ev.get('name', '')
    v = ev.get('venue', '')
    base = (
        f"{n}{f' at {v}' if v else ''}. Getting out of the house and doing something "
        "intentional with your time is its own reward, and this is worth putting on "
        "your calendar and actually attending rather than saving and forgetting about. "
    )
    if score <= 2:
        base += (
            "The queer community has always shown up for things that are worth showing "
            "up for, and the best rooms are rarely the ones that announce themselves as "
            "such ahead of time. Interesting spaces attract interesting people. "
            "Go find out who's there."
        )
    return base


# ── Claude API description generator ─────────────────────────────────────────

def _generate_sassy_descriptions(ev: dict, score: int) -> tuple:
    """Call Claude to generate unique descriptions. Returns (website_desc, slide_desc).
    Falls back to template if API unavailable."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        name    = ev.get('name', '')
        venue   = ev.get('venue', '') or ''
        time    = ev.get('time', '') or ''
        date    = ev.get('date', '') or ''
        raw     = ev.get('description', '') or ''
        label   = {5: "Super Gay", 4: "Very Queer", 3: "LGBTQ-Friendly", 2: "Gay-Friendly", 1: "Mostly Straight"}.get(score, "Gay-Friendly")

        prompt = f"""You write event descriptions for Tulsa Gays, a website helping LGBTQ+ people in Tulsa, Oklahoma find things to do.

Your voice: Joan Crawford at a queer community mixer. Theatrical, imperious, sardonic, withering but warm, and always ultimately on the reader's side even when you're gently reading them. Think Alicia Edwards from Abbott Elementary: the perfectly delivered withering observation that is also the most helpful thing anyone has said. You are convincing a shy, introverted gay person to get off the couch, and you are going to tell them exactly what to do so they have the best possible time once they get there.

EVENT DETAILS:
Name: {name}
Venue: {venue}
Date/Time: {date} {time}
Gay Score: {score}/5 ({label})
Raw info: {raw[:400] if raw else 'none'}

Write TWO versions:

WEBSITE: 3-4 flowing paragraphs. Keep all the detail: what the event IS, the practical specifics (what time to arrive, what to bring, costs, phone numbers if applicable), exactly what to do to maximize fun, and why this specific gay introvert should care enough to leave the house. For low gay score (1-2), make the explicit case for why a queer person belongs there and will have a good time. For high score (4-5), lean into community energy, FOMO, and the specific things that make this the queer event it is. The voice must be present in every paragraph, not just the opener and closer. Every sentence earns the next one.

SLIDE: 2-3 sentences MAX. Same voice, compressed. Punchy opener that stops the scroll, then the essential information and reason to go.

CRITICAL RULES:
- Never use em dashes. Use commas or parentheses instead.
- No fragmented sentence bursts. Do not write "No scripts. No explaining yourself. No judgment." Instead write it as connected flowing prose: "You don't have to explain yourself from the beginning before someone will take you seriously."
- Thoughts must connect and flow. Each paragraph earns the next.
- Be specific to THIS event, not generic category filler.
- No hashtags.
- Don't start both versions with the event name.

Format EXACTLY as:
WEBSITE: [your text here]
SLIDE: [your text here]"""

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()

        website_desc = ""
        slide_desc   = ""
        if "WEBSITE:" in text and "SLIDE:" in text:
            parts        = text.split("SLIDE:", 1)
            website_desc = parts[0].replace("WEBSITE:", "").strip()
            slide_desc   = parts[1].strip()
        else:
            website_desc = text
            slide_desc   = text[:250].strip()

        return website_desc, slide_desc

    except Exception as e:
        print(f"    [API error: {e}] falling back to template")
        fallback = _find_description(ev, score)
        return fallback, fallback[:220].strip()


# ── Main ──────────────────────────────────────────────────────────────────────

wk = config.current_week_key()
path = os.path.join('data', 'events', f'{wk}_all.json')

with open(path, encoding='utf-8') as f:
    raw = json.load(f)

events = raw if isinstance(raw, list) else raw.get('events', [])

_GARBAGE_NAMES = {
    '(map)', 'stay connected!', 'our partners', 'event application',
    'event calendar', 'bruce goff event center',
}
def _is_garbage(ev):
    name = (ev.get('name') or '').strip()
    if not name or len(name) < 4:
        return True
    return name.lower() in _GARBAGE_NAMES
events = [e for e in events if not _is_garbage(e)]

updated = 0
for ev in events:
    score = flamingo_score(ev)
    website_desc, slide_desc = _generate_sassy_descriptions(ev, score)
    ev['website_description'] = website_desc
    ev['slide_description']   = slide_desc
    updated += 1
    print(f"  [{score}🦩] {ev.get('name','')[:55]}")

if isinstance(raw, dict):
    raw['events'] = events
    save_obj = raw
else:
    save_obj = events

with open(path, 'w', encoding='utf-8') as f:
    json.dump(save_obj, f, ensure_ascii=False, indent=2)

print(f"\nWrote website_description + slide_description to {updated} events -> {path}")
