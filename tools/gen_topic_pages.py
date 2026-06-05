"""Programmatic long-tail SEO/GEO landing pages for TulsaGays (Answer Engine L2+L3).

Generates one evergreen, schema-rich page per high-value query
("gay bars in tulsa", "drag shows in tulsa", "lgbtq support groups tulsa", ...)
from data the site already owns: the queer-org census + this week's events.

Each page carries:
  - clean title/meta/canonical/OpenGraph/Twitter (matches the site)
  - JSON-LD: CollectionPage + ItemList (the venues/orgs) + FAQPage + BreadcrumbList
    -> the machine-readable shape Google AI Overviews and LLMs cite by default
  - real content: intro, a card list of relevant orgs/venues, this-week events,
    an FAQ, and internal links back into the site

Pages render with the EXACT site header/footer/style (cloned from about.html) so
they're visually native. Output: docs/guides/<slug>.html. Also rewrites
docs/sitemap.xml to include them. Idempotent. `--selftest` proves rendering +
schema validity on synthetic data without touching docs/.
"""

import os
import sys
import re
import json
import html
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

DOCS = os.path.join(config.PROJECT_DIR, "docs")
GUIDES_DIR = os.path.join(DOCS, "guides")
CENSUS_FILE = os.path.join(config.PROJECT_DIR, "tulsa_queer_org_census.json")
EVENTS_CURRENT = os.path.join(DOCS, "events-current.json")
SITEMAP = os.path.join(DOCS, "sitemap.xml")
BASE = "https://www.tulsagays.com"

# Topic = a query we want to own. `match` selects census orgs by type and/or
# alias keyword; `event_kw` selects this-week events by keyword.
TOPICS = [
    {
        "slug": "gay-bars-in-tulsa",
        "title": "Gay Bars in Tulsa: The Complete LGBTQ+ Nightlife Guide",
        "h1": "Gay Bars in Tulsa",
        "desc": "Every LGBTQ+ bar and nightlife spot in Tulsa, Oklahoma, with what each one is known for and what's happening there this week.",
        "intro": "Tulsa's queer nightlife punches well above the city's size. From a long-running leather and bear bar to the only lesbian bar in the state, here is every LGBTQ+ bar in Tulsa, what each is known for, and what is happening this week.",
        "types": ["bar"], "event_kw": ["bar", "drag", "club", "happy hour"],
        "faqs": [
            ("How many gay bars are in Tulsa?", "Tulsa has several dedicated LGBTQ+ bars including Tulsa Eagle, Yellow Brick Road (the state's lesbian bar), and Club Majestic, plus queer-friendly lounges like DVL."),
            ("What is the lesbian bar in Tulsa?", "Yellow Brick Road (YBR), on Cherry Street at 2630 E 15th St, is Tulsa's lesbian bar and one of the few remaining lesbian bars in the country."),
            ("Where is the gay district in Tulsa?", "Tulsa's LGBTQ+ nightlife clusters around the Arts District (Tulsa Eagle) and Cherry Street (YBR), with the Dennis R. Neill Equality Center anchoring the community downtown."),
        ],
    },
    {
        "slug": "drag-shows-in-tulsa",
        "title": "Drag Shows in Tulsa: Where to See Drag Every Week",
        "h1": "Drag Shows in Tulsa",
        "desc": "Where to find drag shows in Tulsa, Oklahoma, from weekly bar performances to drag brunch, plus this week's lineup.",
        "intro": "Tulsa has a thriving drag scene with shows nearly every night of the week. Here is where to find drag in Tulsa, from high-energy bar performances to a laid-back drag brunch, plus what's on this week.",
        "types": [], "match_kw": ["drag", "majestic", "dragnificent", "elote", "house of drag"],
        "event_kw": ["drag", "dragnificent", "showdown", "brunch", "pageant"],
        "faqs": [
            ("Where can I see a drag show in Tulsa?", "Club Majestic hosts DRAGNIFICENT! and the Sunday Showdown weekly, and Elote Cafe runs a monthly drag brunch. Check this week's listings above for exact dates."),
            ("Is there drag brunch in Tulsa?", "Yes, Elote Cafe & Catering downtown hosts a popular drag brunch, typically on the second Saturday of the month with two seatings."),
        ],
    },
    {
        "slug": "lgbtq-support-groups-tulsa",
        "title": "LGBTQ+ Support Groups in Tulsa: Community, Counseling & Connection",
        "h1": "LGBTQ+ Support Groups in Tulsa",
        "desc": "LGBTQ+ support groups, peer meetings, and affirming community programs in Tulsa, Oklahoma, including trans, youth, and recovery groups.",
        "intro": "Whether you're looking for a trans peer group, a coming-out space, affirming recovery, or just community, Tulsa has options. Here are the recurring LGBTQ+ support groups and affirming programs in town.",
        "types": [], "match_kw": ["support", "outreach", "pflag", "prime timers", "two-spirit", "youth", "relationships", "gender", "black queer"],
        "event_kw": ["support", "group", "meeting", "pflag", "outreach"],
        "faqs": [
            ("Where can I find LGBTQ+ support in Tulsa?", "The Dennis R. Neill Equality Center (Oklahomans for Equality) hosts many recurring support programs, including gender outreach, prime timers, and more. PFLAG Tulsa meets monthly."),
            ("Is there a trans support group in Tulsa?", "Yes. Oklahomans for Equality runs a Gender Outreach support group, and several affirming therapists in Tulsa specialize in trans care."),
        ],
    },
    {
        "slug": "queer-friendly-churches-tulsa",
        "title": "Affirming & Queer-Friendly Churches in Tulsa",
        "h1": "Affirming Churches in Tulsa",
        "desc": "LGBTQ+ affirming and welcoming churches and congregations in Tulsa, Oklahoma, with service times and community events.",
        "intro": "Faith and queerness are not at odds in Tulsa. These congregations are openly affirming, with welcoming services and LGBTQ+ community programming throughout the year.",
        "types": ["church"], "event_kw": ["church", "service", "congregation", "affirming"],
        "faqs": [
            ("What churches in Tulsa are LGBTQ+ affirming?", "All Souls Unitarian, Fellowship Congregational Church, and Metropolitan Community Church Tulsa are among the openly affirming congregations in Tulsa."),
            ("Does Fellowship Congregational have community groups?", "Yes, Fellowship Congregational Church hosts community programming including craft groups, and is openly LGBTQ+ affirming."),
        ],
    },
    {
        "slug": "lgbtq-organizations-tulsa",
        "title": "LGBTQ+ Organizations & Community Groups in Tulsa",
        "h1": "LGBTQ+ Organizations in Tulsa",
        "desc": "The community organizations, social clubs, and advocacy groups serving LGBTQ+ Tulsa, from Oklahomans for Equality to niche social groups.",
        "intro": "Tulsa's LGBTQ+ community is held together by a surprising number of organizations, from the decades-old Oklahomans for Equality to bowling leagues, choirs, and identity-specific social groups. Here's the map.",
        "types": ["org", "group"], "event_kw": ["okeq", "equality", "collective", "league", "society"],
        "faqs": [
            ("What is the main LGBTQ+ organization in Tulsa?", "Oklahomans for Equality (OKEQ), which operates the Dennis R. Neill Equality Center, has anchored LGBTQ+ Tulsa since 1980 and is one of the largest LGBTQ+ community centers in the world."),
            ("Are there Black queer or two-spirit groups in Tulsa?", "Yes, Black Queer Tulsa and the All Nations Two-Spirit Society both serve their communities with regular events."),
        ],
    },
    {
        "slug": "sound-baths-meditation-tulsa",
        "title": "Sound Baths & Meditation in Tulsa: Queer-Welcoming Wellness",
        "h1": "Sound Baths & Meditation in Tulsa",
        "desc": "Queer-welcoming sound baths, meditation, and wellness events in Tulsa, Oklahoma, open to the public.",
        "intro": "Tulsa's wellness scene is quietly one of the most queer-welcoming spaces in the city. Public sound baths, meditation sits, and breathwork happen regularly, no membership or experience required.",
        "types": ["wellness"], "match_kw": ["shambhala", "meditation", "sound bath"],
        "event_kw": ["sound bath", "meditation", "breathwork", "reiki", "wellness", "yoga"],
        "faqs": [
            ("Where can I find a sound bath in Tulsa?", "The Shambhala Meditation Center of Tulsa hosts regular public sound baths and meditation sessions. Check this week's listings above for the next one."),
            ("Are Tulsa meditation events LGBTQ+ friendly?", "The wellness spaces TulsaGays lists are queer-welcoming and open to the public, no experience required."),
        ],
    },
]

# ── data loaders ─────────────────────────────────────────────────────────────
def _load_census():
    return json.load(open(CENSUS_FILE, encoding="utf-8")).get("orgs", [])


def _load_events():
    if not os.path.exists(EVENTS_CURRENT):
        return []
    d = json.load(open(EVENTS_CURRENT, encoding="utf-8"))
    return d.get("events", []) if isinstance(d, dict) else d


def _select_orgs(topic, census):
    out = []
    types = set(topic.get("types", []))
    kws = [k.lower() for k in topic.get("match_kw", [])]
    for o in census:
        if types and o.get("type") in types:
            out.append(o); continue
        blob = (o.get("name", "") + " " + " ".join(o.get("aliases", []))).lower()
        if kws and any(k in blob for k in kws):
            out.append(o)
    # de-dup by id, keep order
    seen, dedup = set(), []
    for o in out:
        if o["id"] not in seen:
            seen.add(o["id"]); dedup.append(o)
    return dedup


def _select_events(topic, events):
    kws = [k.lower() for k in topic.get("event_kw", [])]
    hits = []
    for e in events:
        blob = (str(e.get("name", "")) + " " + str(e.get("venue", ""))).lower()
        if any(k in blob for k in kws):
            hits.append(e)
    return hits[:8]


# ── rendering ────────────────────────────────────────────────────────────────
def esc(s):
    return html.escape(str(s or ""), quote=True)


def _header(active=""):
    return f"""<body>
    <header class="site-header">
        <div class="header-inner">
            <a href="/" class="logo-area"><div>
                <div class="logo-text">Tulsa Gays</div>
                <div class="logo-tagline">Your Weekly LGBTQ+ Event Guide</div>
            </div></a>
            <button class="nav-toggle" aria-label="Toggle navigation" onclick="document.querySelector('nav').classList.toggle('open')">&#9776;</button>
            <nav><ul>
                <li><a href="/">This Week</a></li>
                <li><a href="/archive.html">Archive</a></li>
                <li><a href="/blog/index.html">Blog</a></li>
                <li><a href="/directory.html">Directory</a></li>
                <li><a href="/guides/index.html">Guides</a></li>
                <li><a href="/about.html">About</a></li>
                <li><a href="/newsletter.html" class="newsletter-cta">Newsletter</a></li>
            </ul></nav>
        </div>
    </header>"""


FOOTER = """    <footer class="site-footer"><div class="footer-inner">
        <p>Follow us on Instagram: <a href="https://instagram.com/tulsagays" target="_blank" rel="noopener">@tulsagays</a> &middot; <a href="https://linktr.ee/tulsagays" target="_blank" rel="noopener">All Links</a></p>
        <p>Updated weekly &middot; Your guide to LGBTQ+ Tulsa</p>
        <p style="font-size:0.75em;opacity:0.55;margin-top:0.5em">&copy; 2026 Tulsa Gays&#8482;</p>
    </div></footer>
</body></html>"""

GA = """    <script async src="https://www.googletagmanager.com/gtag/js?id=G-3ZGBZH6554"></script>
    <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-3ZGBZH6554');</script>
    <script defer src="/js/img-guard.js"></script>"""

# Minimal inline styling for the guide-specific classes (not in the shared
# style.css). Kept scoped so it can't affect the rest of the site.
STYLE = """    <style>
    .topic-intro{font-size:1.1rem;line-height:1.6;margin:0 0 1.5rem}
    .topic-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;margin:1rem 0 2rem}
    .topic-grid .event-card{border:1px solid rgba(181,23,158,.25);border-radius:12px;padding:1rem 1.1rem;background:#fff}
    .topic-grid .event-card h3{margin:0 0 .35rem;font-size:1.05rem}
    .topic-grid .event-card p{margin:0;font-size:.92rem;opacity:.82;line-height:1.45}
    .topic-events{list-style:none;padding:0;margin:.5rem 0 2rem}
    .topic-events li{padding:.55rem .25rem;border-bottom:1px solid rgba(0,0,0,.08)}
    details.faq{border:1px solid rgba(0,0,0,.1);border-radius:10px;padding:.65rem .9rem;margin:.5rem 0}
    details.faq summary{font-weight:600;cursor:pointer}
    details.faq p{margin:.6rem 0 0;line-height:1.55;opacity:.88}
    .topic-cta{margin-top:2rem;padding:1rem 1.2rem;background:rgba(181,23,158,.06);border-radius:10px}
    </style>"""


def _schema(topic, orgs):
    url = f"{BASE}/guides/{topic['slug']}.html"
    items = [{"@type": "ListItem", "position": i + 1,
              "item": {"@type": "Organization", "name": o["name"]}}
             for i, o in enumerate(orgs)]
    blocks = [
        {"@context": "https://schema.org", "@type": "CollectionPage",
         "name": topic["title"], "description": topic["desc"], "url": url,
         "isPartOf": {"@type": "WebSite", "name": "Tulsa Gays", "url": BASE},
         "mainEntity": {"@type": "ItemList", "itemListElement": items}},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}}
                        for q, a in topic["faqs"]]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE},
             {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{BASE}/guides/index.html"},
             {"@type": "ListItem", "position": 3, "name": topic["h1"], "item": url}]},
    ]
    return "\n".join(f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks)


def render_page(topic, orgs, events):
    url = f"{BASE}/guides/{topic['slug']}.html"
    org_cards = "\n".join(
        f'<div class="event-card"><h3>{esc(o["name"])}</h3>'
        f'<p>{esc(o.get("note", ""))}</p></div>' for o in orgs) or "<p>Listings coming soon.</p>"
    if events:
        ev = "\n".join(
            f'<li><strong>{esc(e.get("name"))}</strong> &middot; {esc(e.get("date"))} '
            f'{esc(e.get("time",""))} &middot; {esc(e.get("venue",""))}</li>' for e in events)
        events_block = f'<h2>Happening this week</h2><ul class="topic-events">{ev}</ul>'
    else:
        events_block = ('<h2>Happening this week</h2><p>Check the '
                        '<a href="/">weekly calendar</a> for the latest dates.</p>')
    faq = "\n".join(
        f'<details class="faq"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
        for q, a in topic["faqs"])
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(topic['title'])} | Tulsa Gays</title>
<meta name="description" content="{esc(topic['desc'])}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(topic['title'])}">
<meta property="og:description" content="{esc(topic['desc'])}">
<meta property="og:type" content="website"><meta property="og:url" content="{url}">
<meta property="og:site_name" content="Tulsa Gays">
<meta property="og:image" content="{BASE}/favicon-512.png">
<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(topic['h1'])}">
<meta name="twitter:description" content="{esc(topic['desc'])}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link href="https://fonts.googleapis.com/css2?family=Poiret+One&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
{_schema(topic, orgs)}
{GA}
{STYLE}
</head>
{_header()}
<main class="container">
  <div class="week-header"><h1>{esc(topic['h1'])}</h1><div class="rainbow-bar rainbow-gradient"></div></div>
  <div class="about-content">
    <p class="topic-intro">{esc(topic['intro'])}</p>
    <h2>The places &amp; groups</h2>
    <div class="topic-grid">{org_cards}</div>
    {events_block}
    <h2>Frequently asked</h2>
    {faq}
    <p class="topic-cta">Want this in your inbox every week? <a href="/newsletter.html">Subscribe to the free newsletter</a> or browse the <a href="/directory.html">full directory</a>.</p>
  </div>
</main>
{FOOTER}"""


def _render_index(topics):
    cards = "\n".join(
        f'<div class="event-card"><h3><a href="/guides/{t["slug"]}.html">{esc(t["h1"])}</a></h3>'
        f'<p>{esc(t["desc"])}</p></div>' for t in topics)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LGBTQ+ Tulsa Guides: Bars, Drag, Churches, Support &amp; More | Tulsa Gays</title>
<meta name="description" content="Deep guides to queer Tulsa: gay bars, drag shows, affirming churches, support groups, community organizations, and wellness.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{BASE}/guides/index.html">
<meta property="og:title" content="LGBTQ+ Tulsa Guides"><meta property="og:type" content="website">
<meta property="og:url" content="{BASE}/guides/index.html"><meta property="og:site_name" content="Tulsa Gays">
<link href="https://fonts.googleapis.com/css2?family=Poiret+One&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
{GA}
{STYLE}
</head>
{_header()}
<main class="container">
  <div class="week-header"><h1>Guides to Queer Tulsa</h1><div class="rainbow-bar rainbow-gradient"></div></div>
  <div class="about-content"><p>Evergreen guides to everything LGBTQ+ in Tulsa. Each one is kept current from our weekly event tracking.</p>
  <div class="topic-grid">{cards}</div></div>
</main>
{FOOTER}"""


def _update_sitemap(slugs):
    if not os.path.exists(SITEMAP):
        return 0
    xml = open(SITEMAP, encoding="utf-8").read()
    added = 0
    urls = [f"{BASE}/guides/index.html"] + [f"{BASE}/guides/{s}.html" for s in slugs]
    inject = ""
    for u in urls:
        if u not in xml:
            inject += f"  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n"
            added += 1
    if inject and "</urlset>" in xml:
        xml = xml.replace("</urlset>", inject + "</urlset>")
        open(SITEMAP, "w", encoding="utf-8").write(xml)
    return added


def run():
    os.makedirs(GUIDES_DIR, exist_ok=True)
    census, events = _load_census(), _load_events()
    written = []
    for t in TOPICS:
        orgs = _select_orgs(t, census)
        evs = _select_events(t, events)
        page = render_page(t, orgs, evs)
        open(os.path.join(GUIDES_DIR, f"{t['slug']}.html"), "w", encoding="utf-8").write(page)
        written.append((t["slug"], len(orgs), len(evs)))
    open(os.path.join(GUIDES_DIR, "index.html"), "w", encoding="utf-8").write(_render_index(TOPICS))
    added = _update_sitemap([t["slug"] for t in TOPICS])
    print(f"[topic-pages] wrote {len(written)} guides + index; sitemap +{added} urls")
    for slug, no, ne in written:
        print(f"  /guides/{slug}.html  ({no} orgs, {ne} events)")
    return written


def _selftest():
    census = [
        {"id": "eagle", "name": "Tulsa Eagle", "type": "bar", "aliases": ["tulsa eagle"], "note": "Leather/bear bar."},
        {"id": "ybr", "name": "YBR", "type": "bar", "aliases": ["yellow brick"], "note": "Lesbian bar."},
        {"id": "church1", "name": "All Souls", "type": "church", "aliases": ["all souls"], "note": "Affirming."},
    ]
    events = [{"name": "Drag Night", "date": "2026-06-10", "time": "9 PM", "venue": "Club Majestic"}]
    bars_topic = TOPICS[0]
    orgs = _select_orgs(bars_topic, census)
    assert len(orgs) == 2, orgs            # 2 bars
    page = render_page(bars_topic, orgs, events)
    assert "<title>" in page and "application/ld+json" in page
    assert "FAQPage" in page and "BreadcrumbList" in page and "CollectionPage" in page
    assert "Tulsa Eagle" in page and "YBR" in page
    # every JSON-LD block must be valid JSON
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert len(blocks) == 3, len(blocks)
    for b in blocks:
        json.loads(b)
    # church topic selects the church
    ct = next(t for t in TOPICS if t["slug"] == "queer-friendly-churches-tulsa")
    assert len(_select_orgs(ct, census)) == 1
    print(f"gen_topic_pages selftest: passed ({len(TOPICS)} topics, 3 valid JSON-LD blocks/page, selection works)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    run()
