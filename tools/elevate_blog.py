"""
Elevate all TulsaGays blog articles with:
1. Read time + last verified badge
2. Table of contents (for long articles)
3. Google Maps embeds for venue articles
4. Venue social media callout boxes
5. Live events widget (JS fetch from /data/events-current.json)
6. Newsletter + Submit Event CTAs
7. Related posts section
"""

import re
import json
from bs4 import BeautifulSoup, NavigableString
from pathlib import Path
from datetime import date

BLOG_DIR = Path(__file__).resolve().parent.parent / "docs" / "blog"
ROOT = Path(__file__).resolve().parent.parent

# ── Per-article metadata ──────────────────────────────────────────────────────

ARTICLE_META = {
    "gay-bars-tulsa": {
        "published": "2026-05-07",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Club Majestic", "address": "124 N Boston Ave, Tulsa, OK 74103",
             "q": "Club+Majestic+124+N+Boston+Ave+Tulsa+OK"},
            {"name": "Tulsa Eagle", "address": "1338 E 3rd St, Tulsa, OK 74120",
             "q": "Tulsa+Eagle+Bar+1338+E+3rd+St+Tulsa+OK"},
            {"name": "Yellow Brick Road", "address": "2630 E 15th St, Tulsa, OK 74104",
             "q": "Yellow+Brick+Road+YBR+2630+E+15th+St+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Club Majestic", "ig": "clubmajestictulsa", "fb": "https://www.facebook.com/clubmajestictulsa"},
            {"name": "Tulsa Eagle", "ig": "tulsaeagleok", "fb": "https://www.facebook.com/tulsaeagle"},
            {"name": "Yellow Brick Road", "ig": "ybrtulsa", "fb": "https://www.facebook.com/YBRTulsa"},
        ],
        "related": ["gay-tulsa-travel-guide", "date-night-queer-tulsa", "new-to-tulsa-queer-starter-pack"],
        "toc": True,
    },
    "bruce-goff-gay-architect-tulsa": {
        "published": "2026-04-29",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Tulsa Club Hotel", "address": "124 W 5th St, Tulsa, OK 74103",
             "q": "Tulsa+Club+Hotel+124+W+5th+St+Tulsa+OK"},
            {"name": "Boston Avenue Methodist Church", "address": "1301 S Boston Ave, Tulsa, OK 74119",
             "q": "Boston+Avenue+Methodist+Church+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Tulsa Club Hotel", "ig": "tulsaclubhotel", "fb": "https://www.facebook.com/tulsaclubhotel"},
        ],
        "related": ["gay-tulsa-travel-guide", "gay-bars-tulsa", "date-night-queer-tulsa"],
        "toc": False,
    },
    "gay-tulsa-travel-guide": {
        "published": "2026-04-27",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Gathering Place", "address": "2650 S John Williams Way E, Tulsa, OK 74114",
             "q": "Gathering+Place+Tulsa+OK"},
            {"name": "Philbrook Museum of Art", "address": "2727 S Rockford Rd, Tulsa, OK 74114",
             "q": "Philbrook+Museum+of+Art+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Oklahomans for Equality", "ig": "okeqtulsa", "fb": "https://www.facebook.com/OKEqualityTulsa"},
        ],
        "related": ["gay-bars-tulsa", "date-night-queer-tulsa", "new-to-tulsa-queer-starter-pack"],
        "toc": True,
    },
    "new-to-tulsa-queer-starter-pack": {
        "published": "2026-04-15",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Dennis R. Neill Equality Center", "address": "621 E 4th St, Tulsa, OK 74120",
             "q": "Dennis+Neill+Equality+Center+621+E+4th+St+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Oklahomans for Equality", "ig": "okeqtulsa", "fb": "https://www.facebook.com/OKEqualityTulsa"},
            {"name": "Tulsa Gays", "ig": "tulsagays", "fb": "https://www.facebook.com/profile.php?id=61575591958277"},
        ],
        "related": ["gay-bars-tulsa", "gay-tulsa-travel-guide", "lgbtq-sports-tulsa"],
        "toc": False,
    },
    "date-night-queer-tulsa": {
        "published": "2026-04-08",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Philbrook Museum of Art", "address": "2727 S Rockford Rd, Tulsa, OK 74114",
             "q": "Philbrook+Museum+of+Art+Tulsa+OK"},
            {"name": "Gathering Place", "address": "2650 S John Williams Way E, Tulsa, OK 74114",
             "q": "Gathering+Place+Tulsa+OK"},
            {"name": "Circle Cinema", "address": "10 S Lewis Ave, Tulsa, OK 74104",
             "q": "Circle+Cinema+10+S+Lewis+Ave+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Philbrook Museum", "ig": "philbrookmuseum", "fb": "https://www.facebook.com/PhilbrookMuseum"},
            {"name": "Gathering Place", "ig": "gatheringplacetulsa", "fb": "https://www.facebook.com/GatheringPlaceTulsa"},
        ],
        "related": ["gay-bars-tulsa", "gay-tulsa-travel-guide", "new-to-tulsa-queer-starter-pack"],
        "toc": False,
    },
    "lgbtq-sports-tulsa": {
        "published": "2026-04-08",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Gathering Place (outdoor fields)", "address": "2650 S John Williams Way E, Tulsa, OK 74114",
             "q": "Gathering+Place+Tulsa+OK+sports"},
        ],
        "socials": [
            {"name": "Tulsa Gays", "ig": "tulsagays", "fb": "https://www.facebook.com/profile.php?id=61575591958277"},
        ],
        "related": ["new-to-tulsa-queer-starter-pack", "gay-bars-tulsa", "gay-tulsa-travel-guide"],
        "toc": False,
    },
    "gilcrease-uncrease-free-arts-series": {
        "published": "2026-04-07",
        "verified": "2026-05-13",
        "maps": [
            {"name": "Gilcrease Museum", "address": "2100 N Gilcrease Museum Rd, Tulsa, OK 74127",
             "q": "Gilcrease+Museum+Tulsa+OK"},
        ],
        "socials": [
            {"name": "Gilcrease Museum", "ig": "gilcreasemuseum", "fb": "https://www.facebook.com/GilcreaseMuseum"},
        ],
        "related": ["date-night-queer-tulsa", "gay-tulsa-travel-guide", "how-we-find-every-queer-event"],
        "toc": False,
    },
    "how-we-find-every-queer-event": {
        "published": "2026-03-31",
        "verified": "2026-05-13",
        "maps": [],
        "socials": [
            {"name": "Tulsa Gays", "ig": "tulsagays", "fb": "https://www.facebook.com/profile.php?id=61575591958277"},
        ],
        "related": ["gay-bars-tulsa", "new-to-tulsa-queer-starter-pack", "lgbtq-sports-tulsa"],
        "toc": False,
    },
}

BLOG_INDEX = {
    "gay-bars-tulsa": "Gay Bars in Tulsa: The Complete Guide to LGBTQ+ Nightlife",
    "bruce-goff-gay-architect-tulsa": "Sleep Inside His Masterpiece: Bruce Goff, Tulsa's Gay Architect",
    "gay-tulsa-travel-guide": "Gay Tulsa Travel Guide: Is Tulsa LGBTQ+ Friendly? (Yes. Here's Proof.)",
    "new-to-tulsa-queer-starter-pack": "New to Tulsa? Here's Your Queer Starter Pack",
    "date-night-queer-tulsa": "Date Night Ideas for Queer Couples in Tulsa",
    "lgbtq-sports-tulsa": "LGBTQ+ Sports in Tulsa: Bowling, Kickball, Softball, and More",
    "gilcrease-uncrease-free-arts-series": "Gilcrease UnCrease: A Free Arts Series Running All Spring",
    "how-we-find-every-queer-event": "How We Find Every Queer Event in Tulsa (So You Don't Have To)",
}

# ── HTML block generators ─────────────────────────────────────────────────────

def read_time_badge(html_text, pub_date, verified_date):
    word_count = len(re.sub(r'<[^>]+>', '', html_text).split())
    minutes = max(2, round(word_count / 220))
    pub_display = date.fromisoformat(pub_date).strftime("%B %d, %Y").replace(" 0", " ")
    ver_display = date.fromisoformat(verified_date).strftime("%B %d, %Y").replace(" 0", " ")
    return f"""<div class="article-meta-bar">
    <span class="meta-item">&#128338; {minutes} min read</span>
    <span class="meta-divider">&#183;</span>
    <span class="meta-item">Published {pub_display}</span>
    <span class="meta-divider">&#183;</span>
    <span class="meta-item meta-verified">&#10003; Verified {ver_display}</span>
</div>"""

def toc_block(soup):
    h2s = [(h.get("id") or re.sub(r'[^a-z0-9]+', '-', h.get_text().lower().strip()), h.get_text().strip())
           for h in soup.find_all("h2") if h.get_text().strip()]
    if len(h2s) < 3:
        return ""
    # Assign IDs to h2 tags
    for h in soup.find_all("h2"):
        text = h.get_text().strip()
        if text:
            h["id"] = re.sub(r'[^a-z0-9]+', '-', text.lower().strip()).strip('-')
    items = "\n".join(f'    <li><a href="#{slug}">{title}</a></li>' for slug, title in h2s)
    return f"""<nav class="toc-box" aria-label="Table of contents">
    <p class="toc-label">In this guide</p>
    <ul>
{items}
    </ul>
</nav>"""

def map_block(maps):
    if not maps:
        return ""
    parts = ['<div class="venue-maps">']
    parts.append('<h2 class="venue-maps-title">Find It</h2>')
    for m in maps:
        embed_url = f"https://maps.google.com/maps?q={m['q']}&output=embed"
        parts.append(f"""<div class="venue-map-item">
    <p class="venue-map-name">{m['name']} &mdash; {m['address']}</p>
    <iframe src="{embed_url}" width="100%" height="250" style="border:0;border-radius:6px;display:block;" allowfullscreen="" loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="Map: {m['name']}"></iframe>
</div>""")
    parts.append('</div>')
    return "\n".join(parts)

def social_block(socials):
    if not socials:
        return ""
    items = []
    for s in socials:
        ig_link = f'<a href="https://instagram.com/{s["ig"]}" target="_blank" rel="noopener">@{s["ig"]}</a>' if s.get("ig") else ""
        fb_link = f'<a href="{s["fb"]}" target="_blank" rel="noopener">Facebook</a>' if s.get("fb") else ""
        links = " &bull; ".join(filter(None, [ig_link, fb_link]))
        items.append(f'<div class="social-row"><span class="social-name">{s["name"]}</span><span class="social-links">{links}</span></div>')
    return f"""<div class="social-callout">
    <p class="social-callout-title">Follow Along</p>
    {"".join(items)}
</div>"""

LIVE_EVENTS_WIDGET = """<div class="live-events-block" id="live-events-widget">
    <p class="lew-title">&#127881; What's Happening This Week</p>
    <div id="lew-list"><p class="lew-loading">Loading this week's events...</p></div>
    <a href="/" class="lew-more">See the full calendar at tulsagays.com &rarr;</a>
</div>
<script>
(function(){
    var w = document.getElementById('lew-list');
    fetch('/events-current.json')
        .then(function(r){ return r.ok ? r.json() : Promise.reject(); })
        .then(function(events){
            if (!events || !events.length) { w.innerHTML = '<p class="lew-empty">Check <a href="/">tulsagays.com</a> for this week\'s full list.</p>'; return; }
            w.innerHTML = events.slice(0,5).map(function(e){
                return '<div class="lew-event"><span class="lew-day">' + (e.day_short||e.date||'') + '</span><span class="lew-name">' + e.name + '</span><span class="lew-venue">' + (e.venue||'') + '</span></div>';
            }).join('');
        })
        .catch(function(){ w.innerHTML = '<p class="lew-empty">See <a href="/">tulsagays.com</a> for this week\'s events.</p>'; });
})();
</script>"""

def newsletter_cta():
    return """<div class="newsletter-cta-block">
    <p class="ncta-title">Get it in your inbox</p>
    <p class="ncta-sub">Every Monday morning: the full Tulsa queer event calendar, delivered before you need it.</p>
    <a href="/newsletter.html" class="ncta-btn">Subscribe &rarr;</a>
</div>"""

def submit_cta():
    return """<div class="submit-cta-block">
    <p class="scta-title">Know something we don't?</p>
    <p class="scta-sub">Got an event, venue, or org we should be covering? Hit submit and we'll add it.</p>
    <a href="/submit.html" class="scta-btn">Submit an Event &rarr;</a>
</div>"""

def related_posts(slug):
    slugs = ARTICLE_META[slug].get("related", [])
    if not slugs:
        return ""
    cards = []
    for s in slugs[:3]:
        title = BLOG_INDEX.get(s, s.replace("-", " ").title())
        cards.append(f'<a href="{s}.html" class="related-card"><span class="related-title">{title}</span></a>')
    return f"""<div class="related-posts">
    <p class="related-label">Keep reading</p>
    {"".join(cards)}
</div>"""

# ── CSS additions ─────────────────────────────────────────────────────────────

ELEVATION_CSS = """
        /* ── Article meta bar ── */
        .article-meta-bar {
            display: flex; flex-wrap: wrap; gap: 0.4rem 0.75rem;
            font-size: 0.8rem; color: var(--text-muted,#888);
            margin-bottom: 2rem; justify-content: center; align-items: center;
        }
        .meta-verified { color: #4ade80; }
        .meta-divider { color: var(--text-muted,#888); }

        /* ── Table of contents ── */
        .toc-box {
            background: var(--bg-card,#111); border-left: 3px solid var(--gold,#f59e0b);
            padding: 1rem 1.25rem; margin: 0 0 2rem; font-size: 0.9rem;
        }
        .toc-label { font-weight: 700; color: var(--gold,#f59e0b); margin-bottom: 0.5rem; font-size: 0.8rem; letter-spacing: 1px; text-transform: uppercase; }
        .toc-box ul { margin: 0; padding-left: 1rem; list-style: disc; }
        .toc-box li { margin-bottom: 0.3rem; }
        .toc-box a { color: var(--text-secondary,#ccc); border: none !important; }
        .toc-box a:hover { color: var(--gold,#f59e0b); }

        /* ── Google Maps ── */
        .venue-maps { margin: 2.5rem 0; }
        .venue-maps-title { font-family: 'Cinzel',serif; font-size: 1.1rem; color: var(--gold,#f59e0b); letter-spacing: 2px; text-transform: uppercase; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(155,30,95,0.3); }
        .venue-map-item { margin-bottom: 1.5rem; }
        .venue-map-name { font-size: 0.85rem; color: var(--text-muted,#888); margin-bottom: 0.4rem; }

        /* ── Social callout ── */
        .social-callout {
            background: var(--bg-card,#111); border: 1px solid rgba(155,30,95,0.2);
            padding: 1rem 1.25rem; margin: 2rem 0; font-size: 0.9rem;
        }
        .social-callout-title { font-weight: 700; color: var(--gold,#f59e0b); margin-bottom: 0.6rem; font-size: 0.8rem; letter-spacing: 1px; text-transform: uppercase; }
        .social-row { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.25rem; padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .social-row:last-child { border-bottom: none; }
        .social-name { color: var(--text-primary,#fff); font-weight: 600; }
        .social-links a { color: var(--gold,#f59e0b); border: none !important; font-size: 0.85rem; }
        .social-links a:hover { text-decoration: underline; }

        /* ── Live events widget ── */
        .live-events-block {
            background: var(--bg-card,#111); border: 1px solid rgba(155,30,95,0.3);
            padding: 1.25rem 1.5rem; margin: 2.5rem 0;
        }
        .lew-title { font-family: 'Cinzel',serif; font-size: 1rem; color: var(--gold,#f59e0b); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 0.75rem; }
        .lew-event { display: flex; gap: 0.75rem; padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.88rem; }
        .lew-event:last-child { border-bottom: none; }
        .lew-day { color: var(--gold,#f59e0b); min-width: 40px; font-weight: 700; font-size: 0.75rem; text-transform: uppercase; padding-top: 0.1rem; }
        .lew-name { color: var(--text-primary,#fff); flex: 1; }
        .lew-venue { color: var(--text-muted,#888); font-size: 0.78rem; white-space: nowrap; }
        .lew-loading, .lew-empty { color: var(--text-muted,#888); font-size: 0.85rem; }
        .lew-more { display: inline-block; margin-top: 0.75rem; font-size: 0.8rem; color: var(--gold,#f59e0b); border: none !important; }

        /* ── Newsletter CTA ── */
        .newsletter-cta-block {
            background: linear-gradient(135deg,#1a0a2e 0%,#0a0a1a 100%);
            border: 1px solid rgba(155,30,95,0.4); padding: 1.5rem; text-align: center; margin: 2.5rem 0;
        }
        .ncta-title { font-family: 'Poiret One',sans-serif; font-size: 1.4rem; color: #FF1493; margin-bottom: 0.4rem; }
        .ncta-sub { color: var(--text-muted,#888); font-size: 0.9rem; margin-bottom: 1rem; }
        .ncta-btn { display: inline-block; background: #FF1493; color: #fff !important; padding: 0.6rem 1.4rem; font-family: 'Cinzel',serif; font-size: 0.8rem; letter-spacing: 1.5px; text-transform: uppercase; border: none !important; border-radius: 2px; }
        .ncta-btn:hover { opacity: 0.85; }

        /* ── Submit CTA ── */
        .submit-cta-block {
            background: var(--bg-card,#111); border-left: 3px solid #FF1493;
            padding: 1rem 1.25rem; margin: 1.5rem 0; text-align: left;
        }
        .scta-title { font-weight: 700; color: var(--text-primary,#fff); margin-bottom: 0.25rem; }
        .scta-sub { color: var(--text-muted,#888); font-size: 0.85rem; margin-bottom: 0.75rem; }
        .scta-btn { display: inline-block; color: #FF1493 !important; font-size: 0.85rem; font-weight: 700; border: none !important; }

        /* ── Related posts ── */
        .related-posts { margin: 2.5rem 0; }
        .related-label { font-family: 'Cinzel',serif; font-size: 0.8rem; color: var(--text-muted,#888); letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.75rem; }
        .related-card {
            display: block; background: var(--bg-card,#111); border: 1px solid rgba(155,30,95,0.2);
            padding: 0.85rem 1rem; margin-bottom: 0.5rem; text-decoration: none !important; border-left: 3px solid var(--gold,#f59e0b);
        }
        .related-card:hover { border-left-color: #FF1493; }
        .related-title { color: var(--text-primary,#fff); font-size: 0.9rem; }
"""

# ── Main processing ───────────────────────────────────────────────────────────

def elevate_article(slug, meta):
    path = BLOG_DIR / f"{slug}.html"
    if not path.exists():
        print(f"[SKIP] {slug}.html not found")
        return

    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Inject CSS
    style_tag = soup.find("style")
    if style_tag and ELEVATION_CSS not in (style_tag.string or ""):
        style_tag.string = (style_tag.string or "") + ELEVATION_CSS

    # Find post-body
    post_body = soup.find(class_="post-body")
    if not post_body:
        post_body = soup.find(style=lambda s: s and "max-width:700px" in s.replace(" ", ""))
    if not post_body:
        print(f"[WARN] No post-body in {slug}.html")
        return

    # ── 1. Read time + verified badge ──────────────────────────────────────────
    if not soup.find(class_="article-meta-bar"):
        badge = BeautifulSoup(read_time_badge(str(post_body), meta["published"], meta["verified"]), "html.parser")
        first = post_body.find(True)
        if first:
            first.insert_before(badge)
        else:
            post_body.insert(0, badge)

    # ── 2. Table of contents (long articles only) ──────────────────────────────
    if meta.get("toc") and not soup.find(class_="toc-box"):
        toc_html = toc_block(soup)  # Also assigns IDs to h2s
        if toc_html:
            meta_bar = post_body.find(class_="article-meta-bar")
            insert_after = meta_bar or post_body.find(class_="post-figure")
            if insert_after:
                toc_tag = BeautifulSoup(toc_html, "html.parser")
                insert_after.insert_after(toc_tag)

    # ── 3. Find the closing CTA block (insert new blocks before it) ────────────
    post_cta = post_body.find(class_="post-cta") or post_body.find(class_="post-nav")
    insert_before = post_cta

    def append_or_insert(html_str):
        tag = BeautifulSoup(html_str, "html.parser")
        if insert_before:
            insert_before.insert_before(tag)
        else:
            post_body.append(tag)

    # ── 4. Live events widget ──────────────────────────────────────────────────
    if not soup.find(class_="live-events-block"):
        append_or_insert(LIVE_EVENTS_WIDGET)

    # ── 5. Google Maps ─────────────────────────────────────────────────────────
    if meta.get("maps") and not soup.find(class_="venue-maps"):
        append_or_insert(map_block(meta["maps"]))

    # ── 6. Social callout ─────────────────────────────────────────────────────
    if meta.get("socials") and not soup.find(class_="social-callout"):
        append_or_insert(social_block(meta["socials"]))

    # ── 7. Newsletter CTA ─────────────────────────────────────────────────────
    if not soup.find(class_="newsletter-cta-block"):
        append_or_insert(newsletter_cta())

    # ── 8. Submit CTA ─────────────────────────────────────────────────────────
    if not soup.find(class_="submit-cta-block"):
        append_or_insert(submit_cta())

    # ── 9. Related posts ──────────────────────────────────────────────────────
    if not soup.find(class_="related-posts"):
        append_or_insert(related_posts(slug))

    path.write_text(str(soup), encoding="utf-8")
    print(f"[ok] {slug}.html elevated")


def write_events_current_json():
    """Write a current-events.json for the live widget — top 8 events this week."""
    import glob, sys
    sys.path.insert(0, str(ROOT))
    try:
        import config
        wk = config.current_week_key()
        events_path = ROOT / "data" / "events" / f"{wk}_all.json"
        if not events_path.exists():
            all_files = sorted(ROOT.glob("data/events/*_all.json"))
            events_path = all_files[-1] if all_files else None
        if not events_path:
            print("[SKIP] No events file for live widget")
            return
        with open(events_path, encoding="utf-8") as f:
            data = json.load(f)
        events = data if isinstance(data, list) else data.get("events", [])
        # Filter to this week, sort by date, pick top 8
        from datetime import datetime, timedelta
        today = datetime.now().date()
        week_mon = today - timedelta(days=today.weekday())
        week_sun = week_mon + timedelta(days=6)
        week_events = [
            e for e in events
            if week_mon.strftime("%Y-%m-%d") <= e.get("date","") <= week_sun.strftime("%Y-%m-%d")
        ]
        week_events.sort(key=lambda e: (e.get("date",""), e.get("time","")))
        slim = []
        for e in week_events[:8]:
            d = e.get("date","")
            try:
                day_short = datetime.strptime(d, "%Y-%m-%d").strftime("%a").upper()
            except Exception:
                day_short = ""
            slim.append({
                "name": e.get("name",""),
                "venue": e.get("venue",""),
                "date": d,
                "day_short": day_short,
                "time": e.get("time",""),
            })
        out = ROOT / "docs" / "events-current.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(slim, f, indent=2)
        print(f"[ok] events-current.json written ({len(slim)} events)")
    except Exception as e:
        print(f"[WARN] Could not write events-current.json: {e}")


if __name__ == "__main__":
    print("Elevating TulsaGays blog articles...")
    write_events_current_json()
    for slug, meta in ARTICLE_META.items():
        elevate_article(slug, meta)
    print("\nDone. Commit and push to deploy.")
