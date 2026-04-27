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

# Show ALL events on the website — gay score distinguishes LGBTQ events from general ones
# Trusted LGBTQ sources get a score boost
_TRUSTED_SOURCES = {"homo_hotel", "recurring", "manual", "okeq", "extended_calendars",
                    "community_groups", "facebook_events", "meetup"}

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
# True gay bars — any event here is automatically super gay (5 flamingos)
_GAY_BAR_VENUES = {
    'club majestic', 'tulsa eagle', 'yellow brick', 'majestic tulsa',
    '1330 e 3rd', '1338 e 3rd', 'the vanguard',
    'pump bar', '602 south lewis', '602 s. lewis', '602 s lewis',
}
# Queer-friendly venues (not exclusively gay) → 4 flamingos
_FOUR_VENUES = {
    'dvl', '302 south frankfort', '302 s. frankfort', '302 s frankfort',
    'elote',
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
# Performing arts and specific community events — always 3, even if name contains 2-tier words
_THREE_FL = [
    # Art crawls
    'first friday art crawl', 'art crawl',
    # Performing arts (live stage events)
    'ballet', 'symphony', 'orchestra', 'choir', 'chorale', 'choral',
    'performing arts', 'theatre', 'theater', 'cabaret',
    'live performance', 'stage production', 'dance performance',
    'recital', 'repertory', 'philharmonic',
    # LGBTQ-affirming venues / orgs (not exclusively gay, but always welcome)
    'all souls',
]
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
    if source in ('homo_hotel', 'okeq'):
        return 4
    if source in _LGBTQ_COMMUNITY_SOURCES and any(kw in content for kw in _COMMUNITY_KW):
        return 3
    if any(kw in content for kw in _THREE_FL):
        return 3
    if any(kw in content for kw in _TWO_FL):
        return 2
    return 2  # 1 flamingo is reserved for truly exclusionary/corporate-only events

_FL_LABELS = ['', 'Mostly straight', 'Gay-friendly', 'LGBTQ-friendly', 'Very queer', 'Super gay']

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
    combined = ((e.get('name') or '') + ' ' + (e.get('source') or '')).lower()
    return 'homo hotel' in combined

def _is_council_oak(e):
    combined = ((e.get('name') or '') + ' ' + (e.get('source') or '')).lower()
    return 'council oak' in combined or 'comc' in combined

def _is_recurring(e):
    name = (e.get('name') or '').lower()
    kw = ['bowling', 'aa meeting', 'alcoholics', 'support group', 'yoga', 'meditation',
          'sound bath', 'sonic ray', 'sound sanctuary', 'sound meditation']
    return any(k in name for k in kw)

QUEER_PERFORMANCE_KEYWORDS = [
    'drag', 'drag show', 'drag bingo', 'drag brunch', 'drag queen', 'drag king',
    'cabaret', 'pride show', 'pride event', 'pride night', 'queer night',
    'gay night', 'lgbtq+ night', 'twisted arts', 'okeq', 'rainbow',
    'pride dance', 'pride party',
]

def _is_queer_performance(e):
    combined = ' '.join([
        (e.get('name') or ''), (e.get('description') or ''),
        (e.get('venue') or ''), (e.get('source') or '')
    ]).lower()
    return any(kw in combined for kw in QUEER_PERFORMANCE_KEYWORDS)

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

def _parse_minutes(t):
    """Convert time string to minutes since midnight. Extracts start time from ranges."""
    if not t:
        return 9999
    t = t.strip().upper()
    # Extract first recognizable time from ranges like "6:00 PM - 8:00 PM",
    # "Doors 9 PM, Show 10 PM", "10:00 AM and 11:15 AM"
    m = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM)|\b\d{1,2}\s+(?:AM|PM))\b', t)
    if m:
        t = m.group(1).strip()
    for fmt in ['%I:%M %p', '%H:%M', '%I:%M%p', '%I %p']:
        try:
            dt = datetime.strptime(t, fmt)
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

# Find EOTW — priority: HH → Council Oak → Drag/Queer Performance → other specials
all_flat = [e for day in DAYS for e in events_by_day[day]]
hh = [e for e in all_flat if _is_homo_hotel(e)]
council = [e for e in all_flat if _is_council_oak(e)]
queer_perf = [e for e in all_flat if _is_queer_performance(e) and not _is_recurring(e)
              and not _is_homo_hotel(e) and not _is_council_oak(e)]
specials = [e for e in all_flat if not _is_homo_hotel(e) and not _is_council_oak(e)
            and not _is_queer_performance(e) and not _is_recurring(e)]

eotw = (hh[0] if hh else
        council[0] if council else
        queer_perf[0] if queer_perf else
        specials[0] if specials else None)
eotw_key = (eotw.get('name', ''), eotw.get('date', '')) if eotw else None

# Top event per day — lowest priority wins, then earliest time. Gets a pink featured box.
def _day_sort_key(e):
    return (e.get('priority', 99), _parse_minutes(e.get('time') or ''))

day_top_keys = set()
for day in DAYS:
    if events_by_day[day]:
        top = min(events_by_day[day], key=_day_sort_key)
        day_top_keys.add((top.get('name', ''), top.get('date', '')))

def esc(s):
    if not s:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

_VENUE_JUNK = ('shared by ', 'posted by ', 'reposted by ', 'event by ')
# Known address fragments → display name (checked before address-stripping)
_VENUE_NAME_MAP = {
    '302 south frankfort': 'DVL Club & Lounge',
    '302 s. frankfort':    'DVL Club & Lounge',
    '302 s frankfort':     'DVL Club & Lounge',
    '1338 e 3rd':          'Tulsa Eagle',
    '1330 e 3rd':          'Tulsa Eagle',
    '602 south lewis':     'Pump Bar',
    '602 s. lewis':        'Pump Bar',
    '602 s lewis':         'Pump Bar',
    '6808 s. memorial':    'Loony Bin Comedy Club',
    '6808 s memorial':     'Loony Bin Comedy Club',
    '1124 s. lewis':       'WEL Bar',
    '1301 s. boston':      'Boston Ave UMC',
    '2224 w 51st':         'Zarrow Library',
}

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

def format_time(t):
    if not t:
        return None, None
    t_orig = t.strip()
    t = t_orig.upper()
    # Extract start time from ranges like "6:00 PM - 8:00 PM", "Doors 9 PM, Show 10 PM"
    m = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM)|\b\d{1,2}\s+(?:AM|PM))\b', t)
    if m:
        t = m.group(1).strip()
    for fmt in ['%I:%M %p', '%H:%M', '%I:%M%p', '%I %p']:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.strftime('%I:%M').lstrip('0') or '12:00', dt.strftime('%p')
        except Exception:
            pass
    parts = t.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return t_orig, ''

_LEGEND_HTML = '''\
        <div class="flamingo-legend">
            <span class="flamingo-legend-title">Gay Score</span>
            <span class="flamingo-legend-items">
                <span>🦩 Mostly straight</span>
                <span>🦩🦩 Gay-friendly</span>
                <span>🦩🦩🦩 LGBTQ-friendly</span>
                <span>🦩🦩🦩🦩 Very queer</span>
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
    lines.append(f'        <section class="day-section">')
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
            is_day_top = ev_key in day_top_keys
            card_cls = 'event-card featured' if is_featured else 'event-card'
            name_color = 'var(--gold)' if is_featured else f'var({css_var})'
            time_color = 'var(--gold)' if is_featured else f'var({css_var})'
            # Pink box for the top event of each day
            pink_style = (
                ' style="border:2px solid #e84fa0;box-shadow:0 0 14px rgba(232,79,160,0.30);'
                'background:rgba(232,79,160,0.06);border-radius:12px;"'
            ) if is_day_top else ''

            hour, ampm = format_time(ev.get('time', '') or '')
            venue = esc(_clean_venue(ev.get('venue', '') or ''))
            location = ev.get('location', '') or ''
            loc_clean = esc(_clean_venue(location))
            if loc_clean and loc_clean.lower() not in venue.lower():
                venue_str = f'{venue} &middot; {loc_clean}' if venue else loc_clean
            else:
                venue_str = venue

            desc = (ev.get('website_description') or ev.get('description') or '').strip()
            url = ev.get('url', '') or ''
            fl_score = _flamingo_score(ev)
            fl_html = _flamingo_html(fl_score)

            lines.append('')
            lines.append(f'                <div class="{card_cls}"{pink_style}>')
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
            lines.append(f'                        <div class="event-flamingo">{fl_html}</div>')
            if desc:
                lines.append(f'                        <div class="event-description">{esc(desc)}</div>')
            if url:
                link_lbl = esc(ev_name[:50]) + ' &rarr;' if len(ev_name) > 50 else esc(ev_name) + ' &rarr;'
                lines.append(f'                        <a href="{esc(url)}" class="event-link" target="_blank" rel="noopener">{link_lbl}</a>')
            lines.append(f'                    </div>')
            lines.append(f'                </div>')

    lines.append(f'            </div>')
    lines.append(f'        </section>')

result = '\n'.join(lines)

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

with open(_idx_path, 'w', encoding='utf-8') as _f:
    _f.write(_html2)
print(f"Updated date range: {_week_start} — {_week_end}")
print(f"Updated EOTW banner: {eotw.get('name') if eotw else 'none'}")
