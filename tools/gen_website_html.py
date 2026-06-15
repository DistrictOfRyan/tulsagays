"""Generate day-sections HTML for docs/index.html from this week's events JSON."""
import json, sys, re, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import config

wk = config.current_week_key()
with open(f'data/events/{wk}_all.json', encoding='utf-8') as f:
    raw = json.load(f)

events = raw if isinstance(raw, list) else raw.get('events', [])

# Scraper artifacts and non-events — filter these out before display
_GARBAGE_NAMES = {
    '(map)', 'stay connected!', 'our partners', 'event application',
    'event calendar', 'bruce goff event center',
}
def _is_garbage(ev):
    name = (ev.get('name') or '').strip()
    if not name or len(name) < 4:
        return True
    if name.lower() in _GARBAGE_NAMES:
        return True
    return False
events = [e for e in events if not _is_garbage(e)]

# Show ALL events on the website — gay score distinguishes LGBTQ events from general ones.
# All city-specific data (venues, source keys, anchor keywords) reads from config.py.
# Generic universal patterns stay here in shared code. See city-growth-playbook §15.5.

_TRUSTED_SOURCES = (
    {"recurring", "manual", "extended_calendars",
     "community_groups", "facebook_events", "meetup"}
    | getattr(config, "LGBTQ_COMMUNITY_SOURCES", set())
)

# Generic FIVE-flamingo keywords — universal across cities.
_FIVE_FL_GENERIC = [
    'drag show', 'drag bingo', 'drag brunch', 'drag queen', 'drag king', 'drag race',
    'drag sing', 'drag along', 'drag perform', 'drag night',
    'pride show', 'pride party', 'pride dance', 'pride night', 'queer night',
    'gay night', 'lgbtq+ night', 'rainbow night',
    'queer cabaret', 'dragnificent',
    'queer support group', 'lgbtq support group', 'gender outreach support',
    'queer women', 'sapphic social', 'queer social', 'trans support group',
    'queer support', 'pflag',
    'bar crawl', 'pub crawl', 'pride crawl',
]
_FIVE_FL = _FIVE_FL_GENERIC + getattr(config, "FIVE_FL_KEYWORDS_CITY", [])

# True gay bars — any event here automatically scores 5. City-specific via config.
_GAY_BAR_VENUES = getattr(config, "TRUE_GAY_BAR_VENUES", set())

# Queer-friendly venues — score 4. City-specific via config.
_FOUR_VENUES = getattr(config, "QUEER_FRIENDLY_VENUES", set())

# Generic FOUR-flamingo keywords. City-specific anchors via config.
_FOUR_FL_GENERIC = [
    'lgbtq', 'lgbt', 'queer', 'lesbian', 'bisexual', 'sapphic',
    'transgender', 'nonbinary', 'non-binary', 'gender outreach',
    'rainbow pride', 'pride month',
    'gay bar', 'gay club',
    'support group', 'trans support',
    'musical', 'the musical', 'pride', 'opera', 'broadway',
]
_FOUR_FL = _FOUR_FL_GENERIC + getattr(config, "FOUR_FL_KEYWORDS_CITY", [])

_LGBTQ_COMMUNITY_SOURCES = getattr(config, "LGBTQ_COMMUNITY_SOURCES", set())
_COMMUNITY_KW = [
    'support', 'group', 'meeting', 'collective', 'social', 'community',
    'bowling', 'yoga', 'meditation', 'sound bath', 'seniors', 'testing', 'coffee',
]
# Generic THREE-flamingo (performing arts) + city-specific affirming venues
_THREE_FL_GENERIC = [
    'first friday art crawl', 'art crawl',
    'ballet', 'symphony', 'orchestra', 'choir', 'chorale', 'choral',
    'performing arts', 'theatre', 'theater', 'cabaret',
    'live performance', 'stage production', 'dance performance',
    'recital', 'repertory', 'philharmonic',
]
_THREE_FL = _THREE_FL_GENERIC + getattr(config, "AFFIRMING_VENUE_KEYWORDS_CITY", [])
_TWO_FL = [
    'art', 'music', 'concert', 'gallery', 'theater', 'theatre', 'comedy',
    'poetry', 'film', 'cinema', 'festival', 'cabaret', 'dance', 'live music',
    'cultural', 'brunch', 'karaoke', 'trivia', 'open mic', 'rooftop',
    'bingo', 'scavenger', 'sketch', 'craft', 'workshop', 'coffee',
]

def _flamingo_score(ev) -> int:
    name   = ev.get('name', '').lower()
    venue  = ev.get('venue', '').lower()   # raw, before address cleaning
    source = ev.get('source', '')
    content = f"{name} {venue}"

    if any(kw in content for kw in _FIVE_FL):
        return 5
    if any(bar in venue for bar in _GAY_BAR_VENUES):
        return 5
    if any(kw in content for kw in _FOUR_FL):
        return 4
    if any(v in venue for v in _FOUR_VENUES):
        return 4
    # Events from LGBTQ-community-organizing sources (signature event, equality center, etc.)
    if source in _LGBTQ_COMMUNITY_SOURCES:
        return 4
    _community_subset = {s for s in _LGBTQ_COMMUNITY_SOURCES if s in ("recurring", "manual")}
    if source in _community_subset and any(kw in content for kw in _COMMUNITY_KW):
        return 3
    if any(kw in content for kw in _THREE_FL):
        return 3
    if any(kw in content for kw in _TWO_FL):
        return 2
    return 2  # 1 flamingo is reserved for truly exclusionary/corporate-only events

_FL_LABELS = ['', 'Mostly straight', 'Gay-friendly', 'LGBTQ-friendly', 'Very LGBTQIA+', 'Super gay']

def _flamingo_html(score: int) -> str:
    filled = '🦩' * score
    empty  = '<span style="opacity:0.18">🦩</span>' * (5 - score)
    label  = _FL_LABELS[score]
    return (f'<span class="flamingo-score">{filled}{empty}</span>'
            f'<span class="flamingo-label">{label}</span>')

# Enrich events with sassy descriptions before rendering
try:
    from content.generator import _rule_based_enrich_all
    events = _rule_based_enrich_all(events)
except Exception as _e:
    print(f"[warn] description enrichment skipped: {_e}")

# Hard de-dup on the EXACT field the cards render (website_description or
# description fallback). Rule-based templates give same-category events identical
# copy (2026-06-08: 21 cards shared one line). This guarantees no two cards show
# the same blurb. Operates on the rendered field so it can't be bypassed.
try:
    import os as _os2, sys as _sys2
    _sys2.path.insert(0, _os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__))))
    from tools.dedupe_descriptions import _unique_desc as _uq, _norm as _nm
    _seen2, _fixed2 = {}, 0
    for _ev in events:
        _fld = 'website_description' if (_ev.get('website_description') or '').strip() else 'description'
        _key2 = _nm(_ev.get(_fld))
        if not _key2 or len(_key2) < 25:
            continue
        if _key2 in _seen2:
            for _s in range(1, 50):
                _cand2 = _uq(_ev, f'web{_s}', long=(_fld == 'website_description'))
                if _nm(_cand2) not in _seen2:
                    _ev[_fld] = _cand2
                    _seen2[_nm(_cand2)] = 1
                    _fixed2 += 1
                    break
        else:
            _seen2[_key2] = 1
    print(f"[dedupe] website cards: {_fixed2} duplicate blurbs rewritten unique")
except Exception as _e:
    print(f"[warn] website dedupe skipped: {_e}")

today = datetime.now().date()
week_monday = today - timedelta(days=today.weekday())
week_sunday = week_monday + timedelta(days=6)

DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
day_dates = {d: week_monday + timedelta(i) for i, d in enumerate(DAYS)}

# Reorder so today is first; past days move to the bottom
today_name = today.strftime('%A')
today_idx = DAYS.index(today_name) if today_name in DAYS else 0
DAYS_ORDERED = DAYS[today_idx:] + DAYS[:today_idx]  # today+future, then past
DAYS_PAST = set(DAYS[:today_idx])  # days already gone this week
day_css = {
    'Monday': '--day-mon', 'Tuesday': '--day-tue', 'Wednesday': '--day-wed',
    'Thursday': '--day-thu', 'Friday': '--day-fri', 'Saturday': '--day-sat',
    'Sunday': '--day-sun',
}

def _is_homo_hotel(e):
    """Match the city's signature event (config.SIGNATURE_EVENT)."""
    sig = getattr(config, "SIGNATURE_EVENT", None) or {}
    if not sig:
        return False
    src_key = sig.get("source_key", "")
    if src_key and (e.get('source') or '').lower() == src_key.lower():
        return True
    combined = ((e.get('name') or '') + ' ' + (e.get('source') or '')).lower()
    return any(kw.lower() in combined for kw in sig.get("name_keywords", []))

def _is_council_oak(e):
    """Match the city's anchor cultural event (config.ANCHOR_CULTURAL_EVENT)."""
    anchor = getattr(config, "ANCHOR_CULTURAL_EVENT", None) or {}
    if not anchor:
        return False
    src_key = anchor.get("source_key", "")
    if src_key and (e.get('source') or '').lower() == src_key.lower():
        return True
    combined = ((e.get('name') or '') + ' ' + (e.get('source') or '')).lower()
    return any(kw.lower() in combined for kw in anchor.get("name_keywords", []))

def _is_recurring(e):
    name = (e.get('name') or '').lower()
    # Generic recurring keywords + city-specific community partner keywords
    _generic_kw = ['bowling', 'aa meeting', 'alcoholics', 'support group', 'yoga', 'meditation',
                   'sound bath', 'sound sanctuary', 'sound meditation']
    _city_partner_kw = [k.lower() for k in getattr(config, "COMMUNITY_PARTNER_KEYWORDS", [])]
    kw = _generic_kw + _city_partner_kw
    return any(k in name for k in kw)

# Group events by day (only this week)
events_by_day = defaultdict(list)
for ev in events:
    d = ev.get('date', '')
    if not d:
        continue
    try:
        dt = datetime.strptime(d, '%Y-%m-%d')
        ev_date = dt.date()
        if not (week_monday <= ev_date <= week_sunday):
            continue
        events_by_day[dt.strftime('%A')].append(ev)
    except Exception:
        pass

def _extract_start_time(t):
    """Return the START time token of a time string as 'H:MM AM/PM' (or None).

    Critical: in ranges like '9:00 - 10:30 AM' or '6 - 10 PM' the AM/PM only
    appears on the END time. The old regex required the meridiem to be attached
    to the match, so it grabbed the END time and the website displayed events
    at their end time (W24: a 6-10 PM convention showed as 10 PM, a 9-10:30 AM
    workshop as 10:30 AM). Here the FIRST numeric token wins and inherits the
    first AM/PM that appears after it in the string.
    """
    if not t:
        return None
    import unicodedata
    t = ''.join(' ' if unicodedata.category(c) == 'Zs' else c for c in t.strip().upper())
    t = re.sub('[‐‑‒–—―−]', '-', t)
    m = re.search(r'(\d{1,2}(?::\d{2})?)\s*(AM|PM)?', t)
    if not m:
        return None
    num, mer = m.group(1), m.group(2)
    if not mer:
        m2 = re.search(r'(?<![A-Z])(AM|PM)(?![A-Z])', t[m.end():])
        mer = m2.group(1) if m2 else None
    return (num + ' ' + mer) if mer else num


def _parse_minutes(t):
    """Convert time string to minutes since midnight. Extracts START time from ranges."""
    if not t:
        return 9999
    tok = _extract_start_time(t)
    if not tok:
        return 9998
    for fmt in ['%I:%M %p', '%H:%M', '%I %p']:
        try:
            dt = datetime.strptime(tok, fmt)
            return dt.hour * 60 + dt.minute
        except Exception:
            pass
    return 9998


def time_sort_key(e):
    t = (e.get('time') or '').strip()
    return _parse_minutes(t)

def _dedup_events(evs):
    """Collapse events with similar names on the same day. Keeps highest-priority source.
    Uses substring matching so 'Cindy Kaza' dedupes with 'Cindy Kaza @ The Loony Bin...'
    and 'Homo Hotel' dedupes with '4H: Homo Hotel Happy Hour, May @ DoubleTree'.
    """
    _src_prio = {'homo_hotel': 0, 'okeq': 1, 'recurring': 2, 'manual': 3}
    norms = []   # parallel list of normalized names for each event in result
    result = []

    def _norm(name):
        return re.sub(r'[^a-z0-9]', '', name.lower())

    def _is_dup(n1, n2):
        if not n1 or not n2:
            return False
        short, long = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
        if len(short) < 7:
            return n1 == n2
        return short in long

    for ev in evs:
        n = _norm(ev.get('name', ''))
        dup_idx = next((i for i, en in enumerate(norms) if _is_dup(n, en)), None)
        if dup_idx is None:
            norms.append(n)
            result.append(ev)
        else:
            existing = result[dup_idx]
            ex_p = _src_prio.get(existing.get('source', ''), 99)
            nw_p = _src_prio.get(ev.get('source', ''), 99)
            if nw_p < ex_p:
                result[dup_idx] = ev
                norms[dup_idx] = n
    return result

for day in DAYS:
    events_by_day[day] = _dedup_events(events_by_day[day])
    events_by_day[day].sort(key=time_sort_key)

# Find EOTW — use canonical eotw_selector.py (the single source of truth for all EOTW rules).
# NEVER duplicate or override those rules here. eotw_selector enforces:
#   - _SKIP_SOURCES (recurring, bars, aa_meetings)
#   - _SKIP_VENUES (majestic, etc.)
#   - _SKIP_NAME_FRAGMENTS (bowling, support groups, etc.)
#   - Tier priority: HH → Council Oak → Drag → Queer Perf → Trusted LGBTQ → LGBTQ keywords
from eotw_selector import select_eotw

all_flat = [e for day in DAYS for e in events_by_day[day]]

# FINAL de-dup, immediately before render, on the EXACT events the cards iterate
# and the EXACT field they show (website_description or description). Same-
# category rule-based templates repeat (2026-06-08: 21 cards shared one line);
# this is the last gate before HTML so nothing downstream can re-introduce a dup.
try:
    import os as _osd, sys as _sysd
    _sysd.path.insert(0, _osd.path.dirname(_osd.path.dirname(_osd.path.abspath(__file__))))
    from tools.dedupe_descriptions import _unique_desc as _uqd, _norm as _nmd
    _seend, _fixedd = {}, 0
    for _evd in all_flat:
        _fldd = 'website_description' if (_evd.get('website_description') or '').strip() else 'description'
        _kd = _nmd(_evd.get(_fldd))
        if not _kd or len(_kd) < 25:
            continue
        if _kd in _seend:
            for _sd in range(1, 60):
                _cd = _uqd(_evd, f'card{_sd}', long=(_fldd == 'website_description'))
                if _nmd(_cd) not in _seend:
                    _evd[_fldd] = _cd
                    _seend[_nmd(_cd)] = 1
                    _fixedd += 1
                    break
        else:
            _seend[_kd] = 1
    print(f"[dedupe] final card pass: {_fixedd} duplicate blurbs rewritten")
except Exception as _ed:
    print(f"[warn] final card dedupe skipped: {_ed}")

eotw = select_eotw(all_flat)
eotw_key = (eotw.get('name', ''), eotw.get('date', '')) if eotw else None

def _day_sort_key(e):
    return (e.get('priority', 99), _parse_minutes(e.get('time') or ''))

def esc(s):
    if not s:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

SITE = 'https://www.tulsagays.com'

def _slugify_js(s):
    """Mirror the client-side _slugify() in docs/index.html EXACTLY so the
    static card ids match the per-event share-page filenames and the
    ?event= deep-link scroll."""
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'^-+|-+$', '', s)
    return s[:60]

_slug_counts = {}
def _card_id(name, date, hour):
    """Reproduce the JS card-id scheme (event- prefix + dedup suffix), called
    in DOM order so ids are stable and collision-free."""
    # JS reads the rendered .event-time textContent — empty when there is no
    # time-col — so a falsy hour must contribute nothing (not the literal
    # "None"/"none"), keeping Python ids identical to the client-side scheme.
    base = 'event-' + _slugify_js(f'{name}-{date}-{hour or ""}')
    if base in _slug_counts:
        _slug_counts[base] += 1
        return f'{base}-{_slug_counts[base]}'
    _slug_counts[base] = 1
    return base

# Collected per-event data for /e/<id>.html share pages: dicts with keys
# id, name, desc, when, venue, url
_share_pages = []

_DOMAIN_LABELS = {
    'eventbrite.com': 'Eventbrite',
    'facebook.com': 'Facebook',
    'fb.com': 'Facebook',
    'meetup.com': 'Meetup',
    'ticketmaster.com': 'Ticketmaster',
    'axs.com': 'AXS',
    'instagram.com': 'Instagram',
    'tickets.com': 'Tickets',
}

def _url_label(url: str) -> str:
    """Return a short display label for a URL based on its hostname."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ''
        host = host.lower().lstrip('www.')
        if host in _DOMAIN_LABELS:
            return _DOMAIN_LABELS[host]
        # Capitalize first segment before the first dot
        return host.split('.')[0].capitalize() if host else 'Link'
    except Exception:
        return 'Link'

_VENUE_JUNK = ('shared by ', 'posted by ', 'reposted by ', 'event by ')
# Address fragment → display name. City-specific via config.VENUE_NAME_MAP with safe
# empty fallback for new-city scaffolds (until VENUE_FACTS / Phase 3 source discovery
# populate it).
_VENUE_NAME_MAP = getattr(config, "VENUE_NAME_MAP", {})

def _clean_venue(raw: str) -> str:
    """Return a display-ready venue name, stripping scraper artifacts and raw addresses."""
    v = (raw or '').strip()
    if not v:
        return ''
    low = v.lower()
    if any(low.startswith(j) for j in _VENUE_JUNK):
        return ''
    # Map known address fragments to business names
    for addr, name in _VENUE_NAME_MAP.items():
        if addr in low:
            return name
    # "Business Name, Street Address, City, State" → keep only the business name
    parts = [p.strip() for p in v.split(',')]
    if len(parts) >= 2 and parts[0] and not parts[0][0].isdigit():
        return parts[0]
    # Pure street address — show just the street segment (without city/state)
    if parts[0] and parts[0][0].isdigit():
        return parts[0]
    return v


def _extract_address(raw: str) -> str:
    """Extract a street address from a raw location string for a separate display line.

    Examples:
      "Tulsa Eagle, 1338 E 3rd St, Tulsa, OK"  → "1338 E 3rd St"
      "1338 E 3rd St, Tulsa, OK"               → "1338 E 3rd St"
      "Tulsa Eagle"                             → ""
    """
    v = (raw or '').strip()
    if not v:
        return ''
    parts = [p.strip() for p in v.split(',')]
    # "Venue Name, Street, City, State" — pick the street segment (part[1] if it starts with a digit)
    if len(parts) >= 2 and parts[0] and not parts[0][0].isdigit():
        if parts[1] and parts[1][0].isdigit():
            return parts[1]
        return ''
    # "123 Street, City, State" — pick just the street
    if parts[0] and parts[0][0].isdigit():
        return parts[0]
    return ''

def format_time(t):
    if not t:
        return None, None
    # Treat placeholder strings as untimed
    if re.match(r'^check', t.strip(), re.I):
        return None, None
    # Use the range-aware START extractor (shared with _parse_minutes) so a
    # '9:00 - 10:30 AM' event displays as 9:00 AM, never its end time.
    tok = _extract_start_time(t)
    if not tok:
        return None, None
    for fmt in ['%I:%M %p', '%H:%M', '%I %p']:
        try:
            dt = datetime.strptime(tok, fmt)
            return dt.strftime('%I:%M').lstrip('0') or '12:00', dt.strftime('%p')
        except Exception:
            pass
    parts = tok.split()
    if len(parts) >= 2 and parts[1].upper() in ('AM', 'PM'):
        return parts[0], parts[1]
    return None, None
_LEGEND_HTML = '''\
        <div class="flamingo-legend">
            <span class="flamingo-legend-title">Gay Score</span>
            <span class="flamingo-legend-items">
                <span>🦩 Mostly straight</span>
                <span>🦩🦩 Gay-friendly</span>
                <span>🦩🦩🦩 LGBTQ-friendly</span>
                <span>🦩🦩🦩🦩 Very LGBTQIA+</span>
                <span>🦩🦩🦩🦩🦩 Super gay</span>
            </span>
        </div>'''

lines = [_LEGEND_HTML]
_past_divider_added = False

for day in DAYS_ORDERED:
    day_evs = events_by_day[day]
    css_var = day_css[day]
    dt_obj = day_dates[day]
    date_str = dt_obj.strftime('%B') + ' ' + str(dt_obj.day)

    # Insert "Earlier This Week" divider before the first past day (if any have events)
    if day in DAYS_PAST and not _past_divider_added:
        past_has_events = any(events_by_day[d] for d in DAYS_PAST)
        if past_has_events:
            lines.append('')
            lines.append('        <div class="earlier-this-week">')
            lines.append('            <span>Earlier This Week</span>')
            lines.append('        </div>')
            _past_divider_added = True

    lines.append('')
    lines.append(f'        <!-- {day.upper()} -->')
    lines.append(f'        <section class="day-section" style="--day-color:var({css_var})">')
    lines.append(f'            <h2 class="day-title" style="color:var({css_var})">{day}</h2>')
    lines.append(f'            <div class="day-date">{date_str}</div>')
    lines.append(f'            <hr class="day-divider">')
    lines.append(f'            <div class="events-list">')

    if not day_evs:
        lines.append('                <div class="event-card"><div class="event-details">'
                     '<div class="event-description" style="font-style:italic;opacity:0.6">'
                     'No events found for this day. Check back next week!</div></div></div>')
    else:
        for ev in day_evs:
            ev_name = ev.get('name', '')
            ev_key = (ev_name, ev.get('date', ''))
            is_featured = bool(eotw_key and ev_key == eotw_key)
            card_cls = 'event-card featured' if is_featured else 'event-card'
            name_color = 'var(--gold)' if is_featured else f'var({css_var})'
            time_color = 'var(--gold)' if is_featured else f'var({css_var})'
            pink_style = ''

            hour, ampm = format_time(ev.get('time', '') or '')
            venue = esc(_clean_venue(ev.get('venue', '') or ''))
            location = ev.get('location', '') or ''
            loc_clean = esc(_clean_venue(location))
            if loc_clean and loc_clean.lower() not in venue.lower():
                venue_str = f'{venue} &middot; {loc_clean}' if venue else loc_clean
            else:
                venue_str = venue
            # Extract street address for a separate muted display line (#10)
            raw_addr = _extract_address(location)
            address_line = esc(raw_addr) if raw_addr and raw_addr.lower() not in venue_str.lower() else ''

            desc = (ev.get('website_description') or ev.get('description') or '').strip()
            url = ev.get('url', '') or ''
            fl_score = _flamingo_score(ev)
            fl_html = _flamingo_html(fl_score)
            ev_date_iso = ev.get('date', '')

            # Stable id (matches the JS slug scheme) so shares deep-link AND
            # the per-event /e/<id>.html share page filename lines up.
            card_id = _card_id(ev_name, ev_date_iso, hour)

            lines.append('')
            lines.append(f'                <div class="{card_cls}"{pink_style} id="{card_id}" data-date="{ev_date_iso}">')
            if hour:
                lines.append(f'                    <div class="event-time-col">')
                lines.append(f'                        <div class="event-time" style="color:{time_color}">{esc(hour)}</div>')
                if ampm:
                    lines.append(f'                        <div class="event-ampm">{esc(ampm)}</div>')
                lines.append(f'                    </div>')

            lines.append(f'                    <div class="event-details">')

            lines.append(f'                        <div class="event-name" style="color:{name_color}">{esc(ev_name)}</div>')
            if venue_str:
                lines.append(f'                        <div class="event-venue" style="color:var({css_var})">{venue_str}</div>')
            if address_line:
                lines.append(f'                        <div class="event-address">{address_line}</div>')
            lines.append(f'                        <div class="event-flamingo">{fl_html}</div>')
            if desc:
                lines.append(f'                        <div class="event-description">{esc(desc)}</div>')
            # ── Exactly ONE link per card (consistency fix) ──────────────
            # Previously: events with multiple source_urls rendered 2+ links
            # while events with no url rendered 0 ("2 on some, none on others").
            # Now every card shows a single link. If we have an external
            # source, link straight to it; otherwise link to the event's own
            # /e/<id>.html detail page so no card is ever link-less.
            source_urls = ev.get('source_urls') or []
            best_url = next((u for u in source_urls if u), '') or url
            if best_url:
                link_lbl = (esc(ev_name[:50]) + '…' if len(ev_name) > 50 else esc(ev_name)) + ' &rarr;'
                lines.append(f'                        <a href="{esc(best_url)}" class="event-link" target="_blank" rel="noopener">{link_lbl}</a>')
            else:
                lines.append(f'                        <a href="/e/{card_id}.html" class="event-link">Event details &rarr;</a>')
            # Share button (#9)
            _raw_venue = _clean_venue(ev.get('venue', '') or '') or _clean_venue(location)
            _share_parts = [ev_name]
            if _raw_venue:
                _share_parts.append(f'at {_raw_venue}')
            if ev_date_iso:
                try:
                    _sd = datetime.strptime(ev_date_iso, '%Y-%m-%d')
                    _share_parts.append(_sd.strftime('%A, %B ') + str(_sd.day))
                except Exception:
                    pass
            if hour:
                _share_parts.append(f'{hour} {ampm}'.strip() if ampm else hour)
            _share_text = ' | '.join(_share_parts)
            lines.append(f'                        <button class="share-btn" onclick="shareEvent(this)" '
                         f'data-title="{esc(ev_name[:80])}" data-text="{esc(_share_text)}" '
                         f'aria-label="Share this event">&#8599; Tell Your Gays</button>')
            lines.append(f'                    </div>')
            lines.append(f'                </div>')

            # Collect data for this event's /e/<id>.html share page (gives FB
            # the real event title/description instead of generic homepage OG).
            _when_bits = []
            if ev_date_iso:
                try:
                    _wd = datetime.strptime(ev_date_iso, '%Y-%m-%d')
                    _when_bits.append(_wd.strftime('%A, %B ') + str(_wd.day))
                except Exception:
                    pass
            if hour:
                _when_bits.append(f'{hour} {ampm}'.strip() if ampm else hour)
            _share_pages.append({
                'id': card_id,
                'name': ev_name,
                'desc': desc,
                'when': ' · '.join(_when_bits),
                'venue': _clean_venue(ev.get('venue', '') or '') or _clean_venue(location),
                'url': best_url,
            })

    lines.append(f'            </div>')
    lines.append(f'        </section>')

result = '\n'.join(lines)

# Optional weekly SPONSOR credit (monetization slot, 2026-06-15). Renders ONLY if
# data/sponsor.json exists with a name — otherwise a no-op, so the default site is
# unchanged until a sponsor is signed. Anonymity-safe: credits a sponsor OF the
# guide, never the operator. Pairs with drafts/sponsor/tulsagays_sponsor_onepager.md.
_sponsor_html = ''
try:
    _sp_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sponsor.json')
    if os.path.exists(_sp_path):
        _sp = json.load(open(_sp_path, encoding='utf-8'))
        _spname = (_sp.get('name') or '').strip()
        if _spname:
            _spurl = (_sp.get('url') or '').strip()
            _credit = f'<a href="{_spurl}" target="_blank" rel="noopener">{_spname}</a>' if _spurl else _spname
            _sponsor_html = (
                '        <section class="sponsor-credit" style="text-align:center;'
                'margin:1.2rem auto;font-size:0.95rem;opacity:0.85;">'
                f'This week’s guide is brought to you by {_credit} \U0001f49c'
                '</section>\n')
except Exception:
    _sponsor_html = ''
result = _sponsor_html + result

# Auto-inject into docs/index.html between the first day comment and </main>
_idx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'index.html')
with open(_idx_path, encoding='utf-8') as _f:
    _html = _f.read()

# Find injection boundaries: EVENTS-START marker → closing </main>
_inject_start = _html.find('<!-- EVENTS-START -->')
if _inject_start != -1:
    _inject_start += len('<!-- EVENTS-START -->')
_inject_end = _html.find('</main>', _inject_start if _inject_start != -1 else 0)

if _inject_start != -1 and _inject_end != -1:
    _new_html = _html[:_inject_start] + result + '\n\n\n        ' + _html[_inject_end:]
    with open(_idx_path, 'w', encoding='utf-8') as _f:
        _f.write(_new_html)
    print(f"Injected into docs/index.html (replaced chars {_inject_start}-{_inject_end})")
else:
    print(f"[warn] Could not find injection boundaries in index.html")
    with open('/tmp/day_sections.html', 'w', encoding='utf-8') as f:
        f.write(result)
    print("Wrote to /tmp/day_sections.html instead")

print(f"Generated {len(lines)} lines, {len(result)} chars")
for d in DAYS:
    print(f"  {d}: {len(events_by_day[d])} events")
print(f"EOTW: {eotw_key}")
print(f"Day order: {' -> '.join(DAYS_ORDERED)}")

# ── Also update the static header: date-range + EOTW banner ──────────────────
with open(_idx_path, encoding='utf-8') as _f:
    _html2 = _f.read()

# 1. Date range header (between <!-- DATE-RANGE --> markers)
_week_start = day_dates[DAYS[0]].strftime('%B ') + str(day_dates[DAYS[0]].day)
_week_end_dt = day_dates[DAYS[-1]]
_week_end = _week_end_dt.strftime('%B ') + str(_week_end_dt.day) + ', ' + str(_week_end_dt.year)
_new_date_range = f'<!-- DATE-RANGE -->{_week_start} &mdash; {_week_end}<!-- /DATE-RANGE -->'
_html2 = re.sub(r'<!-- DATE-RANGE -->.*?<!-- /DATE-RANGE -->', _new_date_range, _html2)

# 2. EOTW banner (between <!-- EOTW-START --> and <!-- EOTW-END --> markers)
if eotw:
    _e = eotw
    _ename = _e.get('name', '')
    _ewords = _ename.upper().split()
    _half = max(1, len(_ewords) // 2)
    _gold_part = ' '.join(_ewords[:_half])
    _pink_part = ' '.join(_ewords[_half:])

    _edate = _e.get('date', '')
    _etime = _e.get('time', '')
    try:
        _eday = datetime.strptime(_edate, '%Y-%m-%d').strftime('%A, %B ') + str(datetime.strptime(_edate, '%Y-%m-%d').day)
    except Exception:
        _eday = _edate
    _ewhen = f'{_eday} &middot; {_etime}' if _etime else _eday

    _evenue_raw = _e.get('venue', '')
    _evenue = _evenue_raw.split(',')[0].strip() if _evenue_raw else ''

    _edesc = (_e.get('website_description') or _e.get('description') or '').strip()
    # Trim to ~3 sentences for the banner
    _esents = [s.strip() for s in _edesc.replace('\n', ' ').split('.') if s.strip()]
    _edesc_short = '. '.join(_esents[:4]) + '.' if _esents else ''

    _eurl = _e.get('url', '')
    _elink = f'<a href="{esc(_eurl)}" class="event-link" style="margin-top:12px;display:inline-block" target="_blank" rel="noopener">{esc(_ename)} &rarr;</a>' if _eurl else ''

    _eotw_html = f'''
        <div class="featured-banner">
            <div class="featured-label">Event of the Week</div>
            <div class="deco-double"><span></span><span></span></div>
            <div class="featured-name"><span class="gold">{esc(_gold_part)}</span> <span class="peacock">{esc(_pink_part)}</span></div>
            <div class="diamond-sep"><div class="diamond"></div></div>
            <div class="featured-when">{_ewhen}</div>
            <div class="featured-where">{esc(_evenue)}</div>
            <div class="featured-desc">{esc(_edesc_short)}</div>
            {_elink}
        </div>
        '''
    _html2 = re.sub(
        r'<!-- EOTW-START -->.*?<!-- EOTW-END -->',
        '<!-- EOTW-START -->' + _eotw_html + '<!-- EOTW-END -->',
        _html2,
        flags=re.DOTALL,
    )

# 3. Event structured data (schema.org/Event ItemList) on the INDEXABLE homepage
#    — makes the week's events eligible for Google event rich-results and AI
#    citation (the per-event /e/ pages are noindex, so this is where SEO value
#    lives). nextlevel Rung 3: Discovery Layer.
def _iso_start(date_str, time_str):
    if not date_str:
        return None
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)', (time_str or ''), re.I)
    if m:
        h = int(m.group(1)) % 12
        if m.group(3).lower().startswith('p'):
            h += 12
        return f"{date_str}T{h:02d}:{int(m.group(2) or 0):02d}:00-05:00"
    return date_str  # date-only startDate is valid

_events_ld = []
for _ev in all_flat:
    _d = _ev.get('date', '')
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', _d or ''):
        continue
    _venue = (_ev.get('venue') or '').split(',')[0].strip()
    _slug = _slugify(f"{_ev.get('name','')}-{_d}-{_ev.get('time','')}") if '_slugify' in dir() else None
    _obj = {
        "@type": "Event",
        "name": _ev.get('name', '')[:110],
        "startDate": _iso_start(_d, _ev.get('time', '')),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {
            "@type": "Place",
            "name": _venue or "Tulsa, OK",
            "address": {"@type": "PostalAddress", "addressLocality": "Tulsa",
                        "addressRegion": "OK", "addressCountry": "US"},
        },
        "organizer": {"@type": "Organization", "name": "Tulsa Gays", "url": SITE},
        "image": SITE + "/images/og-event.png",
    }
    _desc = (_ev.get('website_description') or _ev.get('description') or '').strip()
    if _desc:
        _obj["description"] = ' '.join(_desc.split())[:300]
    _u = (_ev.get('url') or '').strip()
    if _u.startswith('http'):
        _obj["url"] = _u
    _events_ld.append(_obj)

if _events_ld:
    _itemlist = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"LGBTQ+ Events in Tulsa — {_week_start} to {_week_end}",
        "itemListElement": [
            {"@type": "ListItem", "position": _i + 1, "item": _o}
            for _i, _o in enumerate(_events_ld)
        ],
    }
    _ld_block = ('<!-- EVENTS-JSONLD-START -->\n<script type="application/ld+json">'
                 + json.dumps(_itemlist, ensure_ascii=False)
                 + '</script>\n<!-- EVENTS-JSONLD-END -->')
    if '<!-- EVENTS-JSONLD-START -->' in _html2:
        _html2 = re.sub(r'<!-- EVENTS-JSONLD-START -->.*?<!-- EVENTS-JSONLD-END -->',
                        lambda _: _ld_block, _html2, flags=re.DOTALL)
    else:
        _html2 = _html2.replace('</head>', _ld_block + '\n</head>', 1)
    print(f"Injected schema.org/Event ItemList ({len(_events_ld)} events) into index.html")

with open(_idx_path, 'w', encoding='utf-8') as _f:
    _f.write(_html2)
print(f"Updated date range: {_week_start} — {_week_end}")
print(f"Updated EOTW banner: {eotw.get('name') if eotw else 'none'}")


# ── Per-event share pages: docs/e/<id>.html ────────────────────────────────
# Static GitHub Pages can't vary OG tags by ?query param, so each event gets
# its own tiny page carrying real og:title / og:description / og:image. The
# "Tell Your Gays" share button (and link-less cards) point here, so a
# Facebook share shows the ACTUAL event, and humans land on a real on-site
# event page (traffic stays on tulsagays.com).
def _trunc(s, n):
    s = ' '.join((s or '').split())
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'

def _render_event_page(p):
    _id = p['id']
    _name = p['name']
    _url = SITE + '/e/' + _id + '.html'
    _deep = SITE + '/?event=' + _id
    _img = SITE + '/images/og-event.png'
    _lead = '. '.join([b for b in (p.get('when'), p.get('venue')) if b])
    _full = (_lead + '. ' if _lead else '') + (p.get('desc') or '')
    _og_desc = _trunc(_full, 300)
    _meta_desc = _trunc(_full, 160)
    _title = _trunc(_name, 90) + ' — Tulsa Gays'
    _src_btn = (f'<a class="ev-btn" href="{esc(p["url"])}" target="_blank" rel="noopener">Get tickets / more info &rarr;</a>'
                if p.get('url') else '')
    _when_html = f'<p class="ev-when">{esc(p["when"])}</p>' if p.get('when') else ''
    _venue_html = f'<p class="ev-venue">{esc(p["venue"])}</p>' if p.get('venue') else ''
    _desc_html = f'<p class="ev-desc">{esc(p["desc"])}</p>' if p.get('desc') else ''
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(_title)}</title>
<meta name="description" content="{esc(_meta_desc)}">
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="{esc(_deep)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Tulsa Gays">
<meta property="og:locale" content="en_US">
<meta property="og:title" content="{esc(_trunc(_name, 90))}">
<meta property="og:description" content="{esc(_og_desc)}">
<meta property="og:url" content="{esc(_url)}">
<meta property="og:image" content="{_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Tulsa Gays — LGBTQ+ Event Guide">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(_trunc(_name, 90))}">
<meta name="twitter:description" content="{esc(_meta_desc)}">
<meta name="twitter:image" content="{_img}">
<link rel="icon" href="/favicon.ico">
<link rel="stylesheet" href="/style.css">
<style>
.ev-wrap{{max-width:680px;margin:0 auto;padding:48px 24px 64px}}
.ev-eyebrow{{color:var(--gold);font-size:.8rem;letter-spacing:.18em;text-transform:uppercase;margin-bottom:14px}}
.ev-name{{color:var(--text-primary);font-size:2rem;line-height:1.15;margin:0 0 14px}}
.ev-when{{color:var(--gold);font-weight:700;margin:0 0 4px}}
.ev-venue{{color:var(--text-secondary);margin:0 0 22px}}
.ev-desc{{color:var(--text-secondary);line-height:1.7;margin:0 0 28px}}
.ev-btn{{display:inline-block;background:var(--gold);color:#fff;padding:12px 22px;border-radius:8px;font-weight:700;text-decoration:none;margin:0 14px 12px 0}}
.ev-btn.alt{{background:transparent;border:1px solid var(--gold);color:var(--gold)}}
.ev-foot{{margin-top:36px;color:var(--text-muted);font-size:.85rem}}
.ev-foot a{{color:var(--gold)}}
</style>
</head>
<body>
<div class="ev-wrap">
<div class="ev-eyebrow">Tulsa Gays · LGBTQ+ Event</div>
<h1 class="ev-name">{esc(_name)}</h1>
{_when_html}
{_venue_html}
{_desc_html}
{_src_btn}
<a class="ev-btn alt" href="{esc(_deep)}">See it on the full calendar &rarr;</a>
<p class="ev-foot">Found via <a href="/">tulsagays.com</a> — every LGBTQ+ event in Tulsa, every week. <a href="/newsletter.html">Get the newsletter &rarr;</a></p>
</div>
</body>
</html>
'''

_e_dir = os.path.join(os.path.dirname(_idx_path), 'e')
os.makedirs(_e_dir, exist_ok=True)
# Clear stale pages from previous weeks so /e/ only holds current events.
for _old in os.listdir(_e_dir):
    if _old.endswith('.html'):
        try:
            os.remove(os.path.join(_e_dir, _old))
        except OSError:
            pass
_written = 0
for _p in _share_pages:
    if not _p.get('id'):
        continue
    try:
        with open(os.path.join(_e_dir, _p['id'] + '.html'), 'w', encoding='utf-8') as _ef:
            _ef.write(_render_event_page(_p))
        _written += 1
    except OSError:
        pass
print(f"Wrote {_written} per-event share pages to docs/e/")
