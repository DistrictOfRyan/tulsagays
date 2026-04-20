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

today = datetime.now().date()
week_monday = today - timedelta(days=today.weekday())
week_sunday = week_monday + timedelta(days=6)

DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
day_dates = {d: week_monday + timedelta(i) for i, d in enumerate(DAYS)}
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
    kw = ['bowling', 'aa meeting', 'alcoholics', 'support group', 'yoga', 'meditation']
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

def _parse_minutes(t):
    """Convert time string to minutes since midnight for proper chronological sort."""
    if not t:
        return 9999
    t = t.strip().upper()
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

for day in DAYS:
    events_by_day[day].sort(key=time_sort_key)

# Find EOTW
all_flat = [e for day in DAYS for e in events_by_day[day]]
hh = [e for e in all_flat if _is_homo_hotel(e)]
council = [e for e in all_flat if _is_council_oak(e)]
specials = [e for e in all_flat if not _is_homo_hotel(e) and not _is_council_oak(e) and not _is_recurring(e)]

eotw = hh[0] if hh else (council[0] if council else (specials[0] if specials else None))
eotw_key = (eotw.get('name', ''), eotw.get('date', '')) if eotw else None

def esc(s):
    if not s:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def format_time(t):
    if not t:
        return None, None
    t = t.strip().upper()
    for fmt in ['%I:%M %p', '%H:%M', '%I:%M%p', '%I %p']:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.strftime('%I:%M').lstrip('0') or '12:00', dt.strftime('%p')
        except Exception:
            pass
    parts = t.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return t, ''

lines = []

for day in DAYS:
    day_evs = events_by_day[day]
    css_var = day_css[day]
    dt_obj = day_dates[day]
    # Windows-compatible date format (no %-d)
    date_str = dt_obj.strftime('%B %d').lstrip('0').replace(' 0', ' ')
    # Actually strftime on Windows doesn't support %-d, use this:
    date_str = dt_obj.strftime('%B') + ' ' + str(dt_obj.day)

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
            card_cls = 'event-card featured' if is_featured else 'event-card'
            name_color = 'var(--gold)' if is_featured else f'var({css_var})'
            time_color = 'var(--gold)' if is_featured else f'var({css_var})'

            hour, ampm = format_time(ev.get('time', '') or '')
            venue = esc(ev.get('venue', '') or '')
            location = ev.get('location', '') or ''
            if location and location.lower() not in (ev.get('venue', '') or '').lower():
                venue_str = f'{venue} &middot; {esc(location)}'
            else:
                venue_str = venue

            desc = (ev.get('description') or '').strip()
            url = ev.get('url', '') or ''

            lines.append('')
            lines.append(f'                <div class="{card_cls}">')
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
with open('/tmp/day_sections.html', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Generated {len(lines)} lines, {len(result)} chars")
for d in DAYS:
    print(f"  {d}: {len(events_by_day[d])} events")
print(f"EOTW: {eotw_key}")
