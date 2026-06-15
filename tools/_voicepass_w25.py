"""One-off Step 2.1 voice pass for 2026-W25 featured events.
Writes Alicia Edwards x RuPaul x Dolly voice copy (why-to-go + best-time tip)
into data/events/2026-W25_all.json, then the caller re-renders with
TULSAGAYS_SKIP_ENRICH=1 so the enricher can't clobber it.
"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PATH = "data/events/2026-W25_all.json"

# (date, name-contains)  ->  dict of fields to set
COPY = [
 ("2026-06-15", "Corn-Husk Dolls", {
   "description": "Make a corn husk doll with your own two hands at Pratt Library. Free, quiet, and weirdly good for a noisy brain.",
   "website_description": "Pratt Library is hosting a hands-on session making traditional Native corn husk dolls, and it is the perfect low-pressure way to spend a Monday afternoon. Nobody is grading your craft skills, the whole point is sitting down and making something real for an hour. Get there a few minutes early so you can settle in and chat with whoever lands next to you. You walk out with a little doll you made and a calmer head than you came in with."}),
 ("2026-06-15", "Free Pool at Caz", {
   "description": "Cheap drinks and free pool at Caz's in the Arts District. Show up solo, rack a game, loosen up.",
   "website_description": "Caz's Pub runs an afternoon happy hour with free pool tables right in the Tulsa Arts District, which makes it an easy place to show up alone and still have something to do with your hands. Grab a drink, claim a table, and play the winner. Pool is the great icebreaker because you do not have to make small talk, you just have to chalk a cue. Go early in the window before it fills up and you will have the run of the place."}),
 ("2026-06-15", "Katherine Battenberg", {
   "description": "A free, intimate music hour with Katherine Battenberg at the Kishner Library. Lovely and low-key.",
   "website_description": "Katherine Battenberg brings live music and conversation to the Judy Z. Kishner Library for an easy hour you do not have to dress up for. It is the kind of small, warm program where you can just sit, listen, and let your shoulders drop. Sit toward the front so the room feels intimate instead of empty. Free, an hour, and a genuinely nice way to break up a Monday."}),
 ("2026-06-16", "SALT Yoga", {
   "description": "Free outdoor yoga on Guthrie Green at golden hour. Bring a mat, find some grass, stretch the day off.",
   "website_description": "SALT Yoga runs a free community class right on Guthrie Green, Tulsa's downtown front lawn, as the evening finally cools off. You do not need to be bendy or own cute leggings, you just need a towel and a willingness to look a little silly in public, which everyone else there is also doing. Stake out a spot toward the middle so you are wrapped in the group energy. It is free, it is outside, and an hour of stretching plus fresh air does more for your mood than another night on the couch."}),
 ("2026-06-16", "Starlight Concert Band", {
   "description": "The Starlight Concert Band plays under the evening sky. Show up for the music, stay for the goosebumps.",
   "website_description": "The Starlight Concert Band performs their Above and Below program, and live band music outdoors on a summer night is one of those simple pleasures that hits harder than you expect. Bring a chair or a blanket and get there before the downbeat so you are settled when it starts. Sit close enough to actually see the players, it turns the whole thing from background noise into a real event. A lovely, free excuse to be out among people without having to talk to a single one of them.",
   "venue": ""}),
 ("2026-06-16", "Bubble Stage Show", {
   "description": "Yes, a grown gay can love a bubble show. Dustin Reudelhuber's is pure delight, no notes.",
   "website_description": "Dustin Reudelhuber brings his bubble stage show to the library, and before you decide it is just for kids, remember that joy is joy and you are allowed to have some on a random Tuesday. It is genuinely impressive and genuinely silly in the best possible way. Sit a few rows back so you can see the big bubbles in their full glory. Free, about an hour, and a guaranteed mood lift."}),
 ("2026-06-17", "Balloon-Twisting", {
   "description": "Learn to twist balloons with Joe Coover at Charles Page Library. Free, silly, a party trick for life.",
   "website_description": "Joe Coover teaches the art of balloon twisting at the Charles Page Library, and this is one of those skills that sounds pointless right up until you become the person at every party who can make a dog out of a balloon. Show up ready to fail at it a few times and laugh about it. Grab a seat near someone so you can compare your lopsided creations. Free, easy, and you leave with a genuinely fun trick in your back pocket."}),
 ("2026-06-17", "All Thumbs Knitters", {
   "description": "Bring your yarn or bring nothing. All Thumbs Knitters teaches total beginners with zero judgment.",
   "website_description": "All Thumbs Knitters meets at the Collinsville Public Library, and the name tells you everything you need to know: nobody expects you to be good. Whether you knit, crochet, or just want someone patient to teach you, you sit in a circle of friendly people and make something while you talk. Bring a project if you have one, or show up empty-handed and someone will get you started. It is a warm, easy way to spend an afternoon making real connections instead of scrolling through fake ones."}),
 ("2026-06-17", "Velvet Chair Poetry", {
   "description": "Poetry night at Gypsy Coffeehouse, velvet chair and a latte. Listen, or read something of your own.",
   "website_description": "Velvet Chair Poetry Night at Gypsy Coffeehouse and Cyber Cafe is exactly the cozy, slightly bohemian evening it sounds like. You can come purely to listen, sink into a chair with a coffee, and let other people be brave on the mic. Or, if the spirit moves you, sign up and read something of your own, because the room at these things is always kind. Get there early enough to claim a comfortable seat and order before it gets busy. A genuinely soulful way to spend a Wednesday night."}),
 ("2026-06-18", "All Rise Happy Hour", {
   "description": "The Equality Center's All Rise Happy Hour is the easiest door into queer Tulsa. Walk in, say hi to one person.",
   "website_description": "All Rise Happy Hour at the Dennis R. Neill Equality Center is the gentlest on-ramp there is to the local LGBTQ community, built for exactly the person who feels weird walking into a bar alone. The whole point is meeting your people in a low-pressure, welcoming room. Do not lurk by the wall on your phone. Walk up to one person with a great outfit, tell them you like it, and let the conversation take it from there. You will leave with names, maybe numbers, and the feeling that this town is smaller and warmer than you thought."}),
 ("2026-06-18", "Queer Crafters", {
   "description": "Queer Crafters Club: bring a project or just your gay little hands. Beats another night alone, every time.",
   "website_description": "Queer Crafters Club at the Equality Center is a standing invitation to make something alongside other LGBTQ folks, no skill required. Knitting, drawing, gluing, whatever, the craft is really just an excuse to be in a room together. Bring whatever you are working on, or show up empty-handed and borrow supplies. Sit down next to someone new instead of next to the person you walked in with. It is the kind of easy, recurring thing that quietly turns strangers into your regular crowd."}),
 ("2026-06-18", "Board Meeting", {
   "description": "Want to know how queer Tulsa actually runs? OKEQ's board meeting is open. Show up and find your way in.",
   "website_description": "OKEQ's board meeting is open to the community, and sitting in on one is the fastest way to understand how the work that holds queer Tulsa together actually gets done. If you have ever thought you wanted to be more involved but had no idea where the door was, this is the door. Go a little early, introduce yourself to one person, and just listen the first time. You do not have to volunteer for a thing, but you will leave knowing exactly how to if you decide you want to."}),
 ("2026-06-19", "Empowerment Circle", {
   "description": "A virtual Pride empowerment circle you can join from the couch. Camera optional, community guaranteed.",
   "website_description": "This Pride Month LGBTQ+ Empowerment Circle happens online, which makes it the rare community event you can attend from the safety of your own living room. It is built for connection and encouragement, a space to feel a little less alone for an hour. Log in a couple minutes early so you are not the one fumbling with the mute button, and turn your camera on if you can, it makes the circle feel real. No pants required, and no real excuse not to."}),
 ("2026-06-19", "Benefit Drag Show", {
   "description": "A benefit drag show at the Tulsa Eagle where every tip does double duty. Bring singles and a loud mouth.",
   "website_description": "The Tulsa Eagle is hosting a benefit drag show, which means the queens are bringing it and the money goes somewhere good. This is about the most fun you can have while also doing a genuinely kind thing. Hit an ATM first so you have a stack of singles, because tipping is the entire love language here. Get there early for a spot near the stage, scream for the performers like they are your best friends, and you will leave absolutely buzzing."}),
 ("2026-06-19", "Juneteenth All-Ages Drag", {
   "description": "An all-ages Juneteenth drag show, equal parts celebration and performance. Cheer loud, tip what you can.",
   "website_description": "This Juneteenth All-Ages Drag Show pairs incredible performers with a celebration that actually means something, and the all-ages part means the joy is for everybody. Drag is at its best when the crowd brings the energy, so do not sit there stone-faced, clap and holler and make the queens feel like the stars they are. Bring cash to tip, get there early for a good sightline, and let yourself be fully delighted. A beautiful way to honor the day and have a great night doing it."}),
 ("2026-06-20", "COUNCIL OAK", {
   "name": "Council Oak Men's Chorale Concert",
   "description": "You haven't really heard Tulsa until you've heard its own gay men's chorus live. Dress up a little, get there early, sit close.",
   "website_description": "The Council Oak Men's Chorale is Tulsa's gay men's chorus, and hearing a roomful of voices like that in person is the kind of thing that gives you chills and maybe a few happy tears. This is the Event of the Week for a reason. Put on something you feel good in, get there early enough to grab a seat up close, and actually let yourself be moved instead of half-watching through a phone screen. You walk out lighter than you came in, and a little prouder of this community."}),
 ("2026-06-20", "Community Gathering hosted by Tulsa Flyer", {
   "description": "A Pride gathering building a real archive of queer Tulsa. Come add your piece to the record.",
   "website_description": "Hosted by the Tulsa Flyer and the Oklahoma Eagle, this Pride Month gathering is part celebration, part living archive, with resource sharing and a collective art project documenting queer Tulsa. Showing up is literally how you become part of the historical record here. Roll in around late morning when it kicks off, introduce yourself, and add your piece to the art project. It is meaningful, it is welcoming, and it is the good kind of Saturday that reminds you exactly who your people are."}),
 ("2026-06-20", "PRIDE DAY BINGO", {
   "description": "Pride Day Bingo with Brian B at the Eagle. Daytime, low-stakes, walk in solo and leave with friends.",
   "website_description": "Brian B hosts Pride Day Bingo at the Tulsa Eagle, and afternoon bingo is the perfect entry point if a packed nightclub feels like too much. The game gives you something to do with your hands and a built-in reason to talk to your neighbors. Show up at three, order a drink, grab a card, and start chatting with whoever is at the table next to you. Tulsa's nightlife runs on people actually showing up, and this is the friendliest possible place to start."}),
 ("2026-06-21", "Broadway Clubhouse - June Pride", {
   "never_feature": True}),  # duplicate of the monthly Broadway Clubhouse — keep off slides
 ("2026-06-21", "Broadway Clubhouse", {
   "description": "Tulsa's monthly queer sing-along in the Lynn Riggs Theater. Show tunes, a drink, your people. Come sing.",
   "website_description": "Broadway Clubhouse is the Equality Center's monthly queer sing-along, held in the Lynn Riggs Theater with Bill Nelson and Jason Sirios on piano. It is show tunes, libations, and a room full of musical theater gays belting their hearts out, which is about as joyful as a Sunday gets. Do not be shy about singing, that is the entire point and nobody is keeping score. Get there early for a good seat, grab a drink, and let yourself be loud. You leave with your cheeks sore from smiling."}),
 ("2026-06-15", "MONDAY MOVIE NIGHT", {
   "description": "Movie night at the Tulsa Eagle. Grab a drink, claim a stool, and watch something with the city's best gay bar crowd.",
   "website_description": "Monday Movie Night at the Tulsa Eagle is the most low-key way to spend an evening at the bar, no packed dance floor, no pressure, just a movie and the regulars who make the Eagle feel like somebody's living room. Go even if you go alone, because this crowd folds newcomers in fast. Get there a little before seven so you can grab a good seat and settle in with a drink. It is the gentlest possible excuse to start your week out of the house and around your people."}),
 ("2026-06-15", "David Sedaris", {
   "description": "David Sedaris. In Tulsa. Reading the dark, hilarious, deeply gay essays that made him famous. Do not miss this one.",
   "website_description": "David Sedaris, the patron saint of neurotic, hilarious, beautifully gay personal essays, is spending an evening at Magic City Books, and this is a genuine bucket-list night for anyone who has ever laughed out loud at one of his books. He reads, he riffs, he says the things out loud that you only think. Buy your ticket early because these sell out, get there in time to grab a signed copy, and sit close enough to catch every deadpan aside. You will leave quoting him for a week."}),
 ("2026-06-16", "Punch (Card) Party", {
   "description": "A crafty little after-work hour at the Collinsville Library making punch-card art. Free, easy, and quietly satisfying.",
   "website_description": "The Collinsville Public Library hosts a Punch Card Party, a relaxed evening of hands-on crafting that asks nothing of you except showing up. It is the kind of low-pressure maker hour where you sit down, make something with your hands, and fall into easy conversation with whoever is at the table. Go straight from work, you do not need to prep a thing. Grab a seat next to someone friendly and let an hour of making quiet your brain. Free and genuinely calming."}),
 ("2026-06-16", "Open Mic Night at Gypsy", {
   "description": "Open mic at Gypsy Coffeehouse: poets, musicians, brave souls, and a good latte. Come listen, or sign up and surprise yourself.",
   "website_description": "Open Mic Night at Gypsy Coffeehouse and Cyber Cafe in the Arts District is the cozy, come-as-you-are kind of evening where anyone can take the mic, music, poetry, a weird bit they have been working on. You can absolutely just come to listen, sink into a chair with a coffee, and cheer for people being brave. Or sign up, because the room at an open mic is the kindest audience you will ever find. Get there early to claim a comfortable seat and order before the rush."}),
 ("2026-06-17", "Film In Oklahoma", {
   "description": "Local film and cold beer at Cabin Boys Brewery. Watch Oklahoma-made movies with the people who actually made them.",
   "website_description": "Film In Oklahoma takes over Cabin Boys Brewery for an evening of locally made movies paired with very drinkable local beer, which is about as good a Wednesday gets. It is part screening, part hang, and the filmmakers are often right there to talk shop. Grab a beer first, find a seat with a clear view of the screen, and do not be shy about chatting with the crowd. A genuinely cool, low-key way to see Tulsa's creative scene up close."}),
 ("2026-06-17", "Open Mic Night", {
   "description": "Comedy open mic at Bricktown Comedy Club. Cheap laughs, brave amateurs, the occasional future star. Sit close and laugh loud.",
   "website_description": "Open Mic Night at the Bricktown Comedy Club is where Tulsa's comedians test new material, which means a wildly unpredictable night of big swings, a few bombs, and the occasional set that genuinely kills. That mix is the whole fun of live comedy. Sit a few rows back so you are not the heckle target, laugh loud at the ones that land, and buy a drink to keep the room warm. Low stakes, high reward, and a great solo night out."}),
 ("2026-06-21", "QWC PRIDE 2024", {
   "description": "The Queer Women's Collective Pride meetup at The Fur Shop. Walk in, find your people, and let the night go where it goes.",
   "website_description": "The QWC Pride Meetup gathers the Queer Women's Collective at The Fur Shop for exactly the kind of easy, welcoming hang that makes Pride feel personal instead of overwhelming. It is built for showing up alone and not staying that way for long. Do not hover by the door, walk up to one person and say hi, that is the entire trick. Get there earlier in the night while it is still easy to talk, grab a drink, and let the introductions snowball. You leave with new names in your phone."}),
 ("2026-06-21", "Karaoke Brunch", {
   "description": "Karaoke. At brunch. At the bar. Day-drink a little, sing something you have no business singing, and have the time of your life.",
   "website_description": "Karaoke Brunch at DVL is the gloriously chaotic combination of daytime drinking and belting show tunes that you did not know your Sunday needed. The daytime crowd is loose and forgiving, which makes it the perfect place to finally get up and sing. Have a drink or two first to shake the nerves, pick the song you secretly know every word to, and go for it. The person who sings first always has the most fun, so put your name in early and own it."}),
 ("2026-06-21", "Pride Week", {
   "description": "Pride Week is here. Don't try to do it all, just pick the one thing that scares you a little and go.",
   "website_description": "Pride Week is in full swing across Tulsa, and the beauty of it is the sheer range, from loud parties to quiet community moments. If the whole thing feels overwhelming, do not try to do everything. Pick the one event that makes you a little nervous in the good way and commit to just that. Bring a friend if you have one, or go alone and trust that you will not be alone for long. This is the week the city is most ready to welcome you, so let it."}),
]

def main():
    data = json.load(open(PATH, encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", data)
    applied = []
    for date, needle, fields in COPY:
        nl = needle.lower()
        hit = None
        for e in events:
            if e.get("date") == date and nl in (e.get("name") or "").lower():
                # prefer the first not-yet-touched match
                if id(e) not in [id(x) for x in applied]:
                    hit = e; break
        if not hit:
            print(f"  MISS: {date} ~ {needle}")
            continue
        for k, v in fields.items():
            hit[k] = v
        applied.append(hit)
        print(f"  set: {date} {needle[:32]:32} -> {list(fields.keys())}")
    out = events if isinstance(data, list) else {**data, "events": events}
    json.dump(out, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"applied {len(applied)} of {len(COPY)}")

main()
