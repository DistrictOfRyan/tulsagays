"""Inject approved community-submitted events into docs/index.html.

Reads content/community_events.json and patches the day sections in
docs/index.html, inserting community event cards at the TOP of each
matching day's events-list div.

Run: python tools/inject_community_events.py
"""

import json
import os
import re
from datetime import datetime, timedelta
import html as html_lib

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_JSON = os.path.join(REPO_ROOT, 'content', 'community_events.json')
INDEX_HTML = os.path.join(REPO_ROOT, 'docs', 'index.html')

# ── Helpers ───────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    """HTML-escape a string."""
    return html_lib.escape(str(text or ''), quote=True)


def current_week_bounds():
    """Return (monday, sunday) date objects for the current ISO week."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


DAY_CSS_VARS = {
    0: '--day-mon',
    1: '--day-tue',
    2: '--day-wed',
    3: '--day-thu',
    4: '--day-fri',
    5: '--day-sat',
    6: '--day-sun',
}

DAY_COMMENT_TAGS = {
    0: '<!-- MONDAY -->',
    1: '<!-- TUESDAY -->',
    2: '<!-- WEDNESDAY -->',
    3: '<!-- THURSDAY -->',
    4: '<!-- FRIDAY -->',
    5: '<!-- SATURDAY -->',
    6: '<!-- SUNDAY -->',
}

FLAMINGO_THREE = (
    '<span class="flamingo-score">'
    '\U0001F9A9\U0001F9A9\U0001F9A9'
    '</span>'
    '<span class="flamingo-label">LGBTQ-friendly</span>'
)


def build_card(ev: dict, css_var: str) -> str:
    """Build the HTML for a single community event card."""
    name = esc(ev.get('name', 'Untitled Event'))
    raw_venue = (ev.get('venue_name', '') or ev.get('venue', '')).strip()
    venue = esc(raw_venue)
    raw_address = (ev.get('venue_address', '') or ev.get('address', '')).strip()
    address = esc(raw_address)
    # Venue line shows venue name only; address shown separately (#10)
    if venue:
        venue_str = venue
        addr_display = address if raw_address and raw_address.lower() not in raw_venue.lower() else ''
    else:
        venue_str = address  # fallback: show address as the venue line
        addr_display = ''

    start = esc(ev.get('start_time', ''))
    end = esc(ev.get('end_time', ''))
    time_str = start
    if end:
        time_str = f'{start} &ndash; {end}'

    desc = esc(ev.get('description', ''))
    url = (ev.get('event_url', '') or ev.get('url', '')).strip()
    ev_date_iso = (ev.get('date', '') or ev.get('event_date', '')).strip()

    # Build share text (#9)
    _share_parts = [ev.get('name', 'Untitled Event')]
    if raw_venue:
        _share_parts.append(f'at {raw_venue}')
    if raw_address and not raw_venue:
        _share_parts.append(f'at {raw_address}')
    if ev_date_iso:
        try:
            from datetime import datetime as _dt
            _sd = _dt.strptime(ev_date_iso, '%Y-%m-%d')
            _share_parts.append(_sd.strftime('%A, %B ') + str(_sd.day))
        except Exception:
            pass
    raw_start = (ev.get('start_time', '') or '').strip()
    if raw_start:
        _share_parts.append(raw_start)
    _share_text = ' | '.join(_share_parts)

    lines = []
    lines.append(f'                <div class="event-card community-event" data-date="{esc(ev_date_iso)}">')
    lines.append(f'                    <div class="event-details">')
    lines.append(f'                        <span class="community-badge">Community Submission</span>')

    lines.append(f'                        <div class="event-name" style="color:var({css_var})">{name}</div>')

    if time_str:
        lines.append(f'                        <div class="event-venue" style="color:var({css_var})">{time_str}</div>')

    if venue_str:
        lines.append(f'                        <div class="event-venue" style="color:var({css_var})">{venue_str}</div>')

    if addr_display:
        lines.append(f'                        <div class="event-address">{addr_display}</div>')

    lines.append(f'                        <div class="event-flamingo">{FLAMINGO_THREE}</div>')

    if desc:
        lines.append(f'                        <div class="event-description">{desc}</div>')

    if url:
        link_lbl = name[:50] + ' &rarr;' if len(name) > 50 else name + ' &rarr;'
        lines.append(
            f'                        <a href="{esc(url)}" class="event-link" '
            f'target="_blank" rel="noopener">{link_lbl}</a>'
        )

    lines.append(
        f'                        <button class="share-btn" onclick="shareEvent(this)" '
        f'data-title="{esc(ev.get("name", "")[:80])}" data-text="{esc(_share_text)}" '
        f'aria-label="Share this event">&#8599; Tell Your Gays</button>'
    )
    lines.append(f'                    </div>')
    lines.append(f'                </div>')
    return '\n'.join(lines)


def get_event_dates(ev: dict, monday: 'datetime.date', sunday: 'datetime.date'):
    """Return list of dates (within this week) this event should appear on."""
    approved = ev.get('approved', True)
    if approved is False:
        return []

    date_str = ev.get('event_date') or ev.get('date', '')
    is_recurring = ev.get('is_recurring') in (True, 'yes', 'true', '1')

    matched_dates = []

    if date_str:
        try:
            ev_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return []

        if is_recurring:
            # For recurring events, match any week date with same weekday
            runs_until_str = ev.get('runs_until', '')
            if runs_until_str:
                try:
                    runs_until = datetime.strptime(runs_until_str, '%Y-%m-%d').date()
                except ValueError:
                    runs_until = sunday
            else:
                runs_until = sunday

            weekday = ev_date.weekday()
            candidate = monday + timedelta(days=weekday)
            if monday <= candidate <= sunday and candidate <= runs_until and candidate >= ev_date:
                matched_dates.append(candidate)
        else:
            if monday <= ev_date <= sunday:
                matched_dates.append(ev_date)

    return matched_dates


def inject_into_day(html: str, day_comment: str, card_html: str) -> str:
    """Find the events-list div under `day_comment` and prepend card_html inside it."""
    # Find the day comment
    comment_pos = html.find(day_comment)
    if comment_pos == -1:
        return html

    # Find the next events-list opening tag after the comment
    search_from = comment_pos + len(day_comment)
    events_list_tag = '<div class="events-list">'
    tag_pos = html.find(events_list_tag, search_from)

    # Make sure we haven't jumped past the next day comment
    next_day_comments = [
        '<!-- MONDAY -->', '<!-- TUESDAY -->', '<!-- WEDNESDAY -->',
        '<!-- THURSDAY -->', '<!-- FRIDAY -->', '<!-- SATURDAY -->', '<!-- SUNDAY -->',
    ]
    for nd in next_day_comments:
        if nd == day_comment:
            continue
        nd_pos = html.find(nd, search_from)
        if nd_pos != -1 and nd_pos < tag_pos:
            return html  # events-list found in wrong section

    if tag_pos == -1:
        return html

    insert_pos = tag_pos + len(events_list_tag)
    return html[:insert_pos] + '\n' + card_html + '\n' + html[insert_pos:]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load events
    if not os.path.exists(EVENTS_JSON):
        print(f'[info] No community events file found at {EVENTS_JSON}. Nothing to inject.')
        return

    with open(EVENTS_JSON, encoding='utf-8') as f:
        events = json.load(f)

    if not events:
        print('[info] community_events.json is empty. Nothing to inject.')
        return

    # Load index.html
    with open(INDEX_HTML, encoding='utf-8') as f:
        html = f.read()

    monday, sunday = current_week_bounds()

    inject_count = 0
    days_injected = set()

    for ev in events:
        matched_dates = get_event_dates(ev, monday, sunday)
        for ev_date in matched_dates:
            weekday_idx = ev_date.weekday()  # 0=Mon … 6=Sun
            css_var = DAY_CSS_VARS.get(weekday_idx, '--day-mon')
            day_comment = DAY_COMMENT_TAGS.get(weekday_idx)
            if not day_comment:
                continue

            card = build_card(ev, css_var)
            html = inject_into_day(html, day_comment, card)
            inject_count += 1
            day_label = day_comment.replace('<!--', '').replace('-->', '').strip()
            days_injected.add(day_label)
            ev_name = ev.get('name', '?')
            print(f'  [+] Injected "{ev_name}" on {ev_date} ({day_label.capitalize()})')

    if inject_count == 0:
        print('[info] No community events matched this week. index.html unchanged.')
        return

    # Write updated index.html
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'\nDone. Injected {inject_count} community event(s) into {len(days_injected)} day section(s).')
    print('Days touched: ' + ', '.join(sorted(days_injected)))


if __name__ == '__main__':
    main()
