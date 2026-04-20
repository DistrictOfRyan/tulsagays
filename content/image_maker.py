"""Generate Tulsa Gays Instagram carousel slides (1080x1080).

Brand: Modern Geometric Deco. Dark bg, Poiret One headers, Neon Pink accents.
NOT the HHHH brand — no burnt orange, no rainbow bars, no gold deco lines.
"""

import re
import sys
import os
import textwrap
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Paths ─────────────────────────────────────────────────────────────────
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

# ── Canvas ────────────────────────────────────────────────────────────────
SIZE = (1080, 1080)
W, H = SIZE
PAD = 96  # side padding

# ── Tulsa Gays Color Palette ──────────────────────────────────────────────
BG            = (10, 10, 10)       # #0a0a0a — all slides
NEON_PINK     = "#FF1493"          # primary accent: "GAYS", bars, links, highlights
WHITE         = "#FFFFFF"          # "TULSA", primary text, event names
LIGHT_GRAY    = "#CCCCCC"          # descriptions, secondary text
GRAY          = "#888888"          # times, muted info
DARK_GRAY     = "#555555"          # dividers, subtle elements
STRIP_BG      = (18, 18, 18)       # "Also happening" section background

# Day accent colors — per DESIGN_STANDARD.md
DAY_ACCENTS = {
    "Monday":    "#A8D8A8",  # Bright Sage
    "Tuesday":   "#C0AEFF",  # Bright Lavender
    "Wednesday": "#FFD060",  # Warm Gold
    "Thursday":  "#F0A0B0",  # Bright Rose
    "Friday":    "#FF1493",  # Neon Pink
    "Saturday":  "#C0AEFF",  # Bright Lavender
    "Sunday":    "#80CCFF",  # Sky Blue
}

# Sassy cover taglines — rotate weekly
COVER_TAGLINES = [
    "Nothing to do in Tulsa? Sounds like a straight person problem.",
    "There's only nothing to do in Tulsa if you're boring.",
    "If you're bored in Tulsa, that's a you problem.",
    "You said there's nothing to do? Girl, keep up.",
    "Boring people say Tulsa is boring. We stay booked.",
    "Tulsa has nothing to do? You're just not invited to the right things.",
]

SKIP_NAMES = {"event calendar", "events", "calendar", "untitled", "",
              "map", "google calendar", "get your tickets", "upcoming events"}

# Unique footer taglines per day — FOMO-baiting, sassy, never the same line twice
DAY_FOOTER_TAGLINES = {
    "Monday":    "This is already happening. Are you there or are you on the couch again?",
    "Tuesday":   "Your friends went. You'll hear about it Wednesday. Or you could just go.",
    "Wednesday": "Half the week already poppin' and you're just now looking. Get in.",
    "Thursday":  "Thursday is warming up. The people who show up are the ones with the stories.",
    "Friday":    "Everyone you know is out tonight. You know that, right?",
    "Saturday":  "The weekend peaked. You were either there or you weren't.",
    "Sunday":    "You'll wake up Monday wishing you went. We're just saying.",
}


# ── Font Loading ──────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font. Checks project fonts/ dir first, then Windows system fonts."""
    project_map = {
        "poiret":   "PoiretOne-Regular.ttf",
        "cinzel":   "Cinzel.ttf",
        "playfair": "PlayfairDisplay.ttf",
    }
    if name.lower() in project_map:
        path = os.path.join(FONTS_DIR, project_map[name.lower()])
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    system_map = {
        "segoe":         "segoeui.ttf",
        "segoe-light":   "segoeuil.ttf",
        "segoe-bold":    "segoeuib.ttf",
        "segoe-semi":    "seguisb.ttf",
        "arial":         "arial.ttf",
        "arial-bold":    "arialbd.ttf",
    }
    filename = system_map.get(name.lower(), f"{name}.ttf")
    path = os.path.join(win_fonts, filename)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)

    for fallback in ["segoeuil.ttf", "segoeui.ttf", "arial.ttf"]:
        fb = os.path.join(win_fonts, fallback)
        if os.path.exists(fb):
            return ImageFont.truetype(fb, size)
    return ImageFont.load_default()


# ── Text Utilities ────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Strip emoji, non-ASCII decorative chars, excess whitespace."""
    if not text:
        return ""
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
        r'\U0001F900-\U0001F9FF\U00002600-\U000026FF\U0000200D'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+', '', text
    )
    return re.sub(r'\s+', ' ', text).strip()


def format_date(date_str: str) -> str:
    """Convert YYYY-MM-DD or similar to 'Mon, Apr 6' format."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                "%A, %B %d, %Y", "%B %d", "%b %d"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%a, %b %#d") if os.name == "nt" else dt.strftime("%a, %b %-d")
        except ValueError:
            continue
    return date_str


def _text_width(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _text_height(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _wrap_to_width(draw: ImageDraw.Draw, text: str,
                   font: ImageFont.FreeTypeFont, max_px: int) -> List[str]:
    """Wrap text to fit within max_px. Returns list of lines."""
    words = clean_text(text).split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if _text_width(draw, candidate, font) <= max_px:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _draw_centered(draw: ImageDraw.Draw, text: str, y: int,
                   font: ImageFont.FreeTypeFont, fill: str) -> int:
    """Draw horizontally centered text with visual top at y. Returns y after text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    # Draw with visual top at y (subtract bbox[1] offset so ink starts at y)
    draw.text(((W - tw) // 2, y - bbox[1]), text, font=font, fill=fill)
    # Advance by the actual visual height (bbox[3] - bbox[1])
    return y + (bbox[3] - bbox[1])


def _draw_wrapped(draw: ImageDraw.Draw, text: str, y: int,
                  font: ImageFont.FreeTypeFont, fill: str,
                  max_px: int = W - PAD * 2,
                  max_lines: int = 3, line_gap: int = 6) -> int:
    """Draw word-wrapped centered text. Returns y after last line."""
    lines = _wrap_to_width(draw, text, font, max_px)[:max_lines]
    for line in lines:
        y = _draw_centered(draw, line, y, font, fill)
        y += line_gap
    return y


def _pink_bar(draw: ImageDraw.Draw, y: int, height: int = 3) -> int:
    """Draw a neon pink horizontal bar across the full width."""
    draw.rectangle([0, y, W, y + height - 1], fill=NEON_PINK)
    return y + height


def _thin_divider(draw: ImageDraw.Draw, y: int,
                  margin: int = PAD, color: str = "#2a2a2a") -> int:
    """Draw a subtle 1px divider. Returns y after."""
    draw.line([(margin, y), (W - margin, y)], fill=color, width=1)
    return y + 1


def _watermark(draw: ImageDraw.Draw):
    """Tiny 'TULSA GAYS' in bottom-right corner."""
    font = _font("segoe", 14)
    text = "TULSA GAYS"
    tw = _text_width(draw, text, font)
    draw.text((W - tw - 28, H - 36), text, font=font, fill=DARK_GRAY)


def _is_garbage(event: Dict) -> bool:
    name = clean_text(event.get("name", "")).lower().strip()
    return name in SKIP_NAMES or len(name) < 3


def _parse_event_time(time_str: str) -> int:
    """Return minutes-since-midnight for sorting. Unknown times sort last.
    Handles ranges like '5:30 - 7:00 PM' (uses start time) and prefixes
    like 'Doors 7 PM, Show 8 PM' (uses first time found).
    """
    if not time_str:
        return 9999
    # Find first AM/PM time marker in the string
    m = re.search(r'(\d{1,2}):?(\d{0,2})\s*(AM|PM)', time_str, re.IGNORECASE)
    if not m:
        return 9999
    ampm = m.group(3).upper()
    # Check if there's an H:MM time before this AM/PM marker (range start)
    prefix = time_str[:m.start()]
    early_matches = list(re.finditer(r'(\d{1,2}):(\d{2})', prefix))
    m_early = early_matches[-1] if early_matches else None
    if m_early:
        hour   = int(m_early.group(1))
        minute = int(m_early.group(2))
        ref_h  = int(m.group(1))
        # If range start hour is less than ref hour, it's same meridiem
        if ampm == "PM" and hour < ref_h:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
    else:
        hour   = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if ampm == "PM" and hour != 12:
            hour += 12
        if ampm == "AM" and hour == 12:
            hour = 0
    return hour * 60 + minute


# ── Slide Generators ──────────────────────────────────────────────────────

def make_cover_slide(post_type: str, date_range: str,
                     featured_event: Optional[Dict] = None,
                     tagline: Optional[str] = None,
                     upcoming_event: Optional[Dict] = None) -> Image.Image:
    """Slide 1: Cover + Event of the Week.
    Top ~half: TULSA GAYS branding + date.
    Bottom half: featured event of the week with name, time, venue, pitch.
    """
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    week_num = datetime.now().isocalendar()[1]
    if tagline is None:
        tagline = COVER_TAGLINES[week_num % len(COVER_TAGLINES)]

    f_week_label    = _font("segoe-semi", 44)
    f_date          = _font("segoe-light", 28)
    f_tulsa         = _font("poiret", 96)
    f_gays          = _font("poiret", 96)
    f_eotw_label    = _font("poiret", 30)
    f_eotw_name     = _font("poiret", 52)
    f_eotw_name2    = _font("poiret", 40)
    f_eotw_dt       = _font("segoe", 24)
    f_eotw_venue    = _font("segoe", 24)
    f_eotw_pitch    = _font("segoe", 21)
    f_footer        = _font("poiret", 36)
    f_upc_label     = _font("poiret", 28)
    f_upc_name      = _font("poiret", 46)
    f_upc_detail    = _font("segoe-light", 22)
    f_upc_link      = _font("segoe-semi", 26)

    _pink_bar(draw, 0, height=4)

    # ── Top branding block ────────────────────────────────────────────────
    y = 28
    y = _draw_centered(draw, "YOUR QUEER WEEK IN TULSA", y, f_week_label, WHITE)
    y += 6
    bar_accent_w = 180
    draw.rectangle([(W - bar_accent_w) // 2, y, (W + bar_accent_w) // 2, y + 3], fill=NEON_PINK)
    y += 16
    y = _draw_centered(draw, date_range.upper(), y, f_date, NEON_PINK)
    y += 10
    if tagline:
        f_tagline = _font("segoe", 19)
        y = _draw_wrapped(draw, tagline, y, f_tagline, LIGHT_GRAY,
                          max_px=W - PAD * 2, max_lines=1, line_gap=4)
    y += 24

    y = _draw_centered(draw, "TULSA", y, f_tulsa, WHITE)
    y += 4
    y = _draw_centered(draw, "GAYS", y, f_gays, NEON_PINK)
    y += 16

    bar_w = 240
    draw.rectangle([(W - bar_w) // 2, y, (W + bar_w) // 2, y + 3], fill=NEON_PINK)
    y += 3

    branding_bottom = y

    # ── Divider ───────────────────────────────────────────────────────────
    y += 14
    _thin_divider(draw, y, margin=PAD, color="#333333")
    y += 20

    # ── Event of the Week ─────────────────────────────────────────────────
    if featured_event and not _is_garbage(featured_event):
        ev_name  = clean_text(featured_event.get("name", ""))
        ev_time  = featured_event.get("time", "")
        ev_venue = clean_text(featured_event.get("venue", ""))
        ev_desc  = featured_event.get("description", "")
        ev_date  = format_date(featured_event.get("date", ""))

        eotw_box_top = y - 10

        y = _draw_centered(draw, "EVENT OF THE WEEK", y, f_eotw_label, WHITE)
        y += 16

        name_font = f_eotw_name if len(ev_name) <= 32 else f_eotw_name2
        y = _draw_wrapped(draw, ev_name, y, name_font, WHITE, max_px=W - 120, max_lines=2, line_gap=8)
        y += 12

        dt_line = f"{ev_date}  ·  {ev_time}" if ev_date and ev_time else (ev_date or ev_time)
        if dt_line:
            y = _draw_centered(draw, dt_line, y, f_eotw_dt, GRAY)
            y += 10

        if ev_venue:
            y = _draw_wrapped(draw, f"@ {ev_venue}", y, f_eotw_venue, NEON_PINK,
                              max_px=W - 140, max_lines=1, line_gap=6)
            y += 10

        if ev_desc:
            y = _draw_wrapped(draw, ev_desc, y, f_eotw_pitch, LIGHT_GRAY,
                              max_px=W - 160, max_lines=6, line_gap=7)
            y += 10

        ev_url = featured_event.get("url", "") if featured_event else ""
        if ev_url:
            f_eotw_link = _font("segoe-semi", 22)
            display_url = re.sub(r'^https?://', '', ev_url).split("?")[0]
            if len(display_url) > 55:
                display_url = display_url[:55] + "..."
            y = _draw_centered(draw, f"TICKETS  \u2192  {display_url}", y,
                               f_eotw_link, NEON_PINK)

        # Pink highlight box around the entire EOTW section
        draw.rounded_rectangle(
            [PAD - 22, eotw_box_top, W - PAD + 22, y + 14],
            radius=12,
            outline=NEON_PINK,
            width=3,
        )
    else:
        # No featured event — show tagline instead
        y = _draw_wrapped(draw, tagline, y, f_eotw_pitch, LIGHT_GRAY,
                          max_px=W - 160, max_lines=3, line_gap=8)

    # ── Upcoming Featured Event ───────────────────────────────────────────────
    cover_footer_top = H - 76  # keep COMING UP content above the footer bar
    if upcoming_event and not _is_garbage(upcoming_event):
        upc_name   = clean_text(upcoming_event.get("name", ""))
        upc_date   = format_date(upcoming_event.get("date", ""))
        upc_hype   = upcoming_event.get("hype", "")
        upc_url    = upcoming_event.get("url", "")
        upc_img    = upcoming_event.get("image_path", "")

        if upc_name and y < cover_footer_top - 60:
            y += 18
            _thin_divider(draw, y, margin=PAD, color="#2a2a2a")
            y += 14

            if y < cover_footer_top:
                y = _draw_centered(draw, "COMING UP", y, f_upc_label, WHITE)
                y += 8

            # ── Optional event image ──────────────────────────────────────
            if upc_img and os.path.exists(upc_img) and y < cover_footer_top:
                try:
                    ev_img = Image.open(upc_img).convert("RGB")
                    max_w  = W - PAD * 2
                    max_h  = 100
                    scale  = min(max_w / ev_img.width, max_h / ev_img.height)
                    img_w  = int(ev_img.width * scale)
                    img_h  = int(ev_img.height * scale)
                    ev_img = ev_img.resize((img_w, img_h), Image.LANCZOS)
                    img.paste(ev_img, ((W - img_w) // 2, y))
                    y += img_h + 10
                except Exception:
                    pass  # silently skip if image fails to load

            if y < cover_footer_top:
                y = _draw_wrapped(draw, upc_name, y, f_upc_name, WHITE,
                                  max_px=W - 120, max_lines=2, line_gap=4)
                y += 4

            if upc_date and y < cover_footer_top:
                y = _draw_centered(draw, upc_date, y, f_upc_detail, GRAY)
                y += 4

            if upc_hype and y < cover_footer_top:
                y = _draw_wrapped(draw, upc_hype, y, f_upc_detail, LIGHT_GRAY,
                                  max_px=W - 140, max_lines=2, line_gap=4)
                y += 4

            if upc_url and y < cover_footer_top:
                ticket_line = f"GET TICKETS  \u2192  {upc_url}"
                y = _draw_wrapped(draw, ticket_line, y, f_upc_link, NEON_PINK,
                                  max_px=W - 80, max_lines=2, line_gap=4)

    # Footer — prominent TULSAGAYS.COM with "hundreds of events" call-to-action
    _pink_bar(draw, H - 100, height=2)
    _draw_centered(draw, "TULSAGAYS.COM", H - 88, f_footer, WHITE)
    f_footer_cta = _font("segoe", 17)
    _draw_centered(draw, "Hundreds of fabulous events this week \u00b7 visit to see the full list",
                   H - 48, f_footer_cta, LIGHT_GRAY)
    _pink_bar(draw, H - 10, height=3)
    _watermark(draw)
    return img


def make_featured_slide(event: Dict) -> Image.Image:
    """Slide 2: Featured event of the week."""
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    name        = clean_text(event.get("name", ""))
    time_str    = event.get("time", "")
    venue       = clean_text(event.get("venue", ""))
    description = event.get("description", "")
    raw_date    = event.get("date", "")
    nice_date   = format_date(raw_date)

    # Is this HHHH?
    is_hhhh = "homo hotel" in name.lower()

    f_label  = _font("poiret", 40)
    f_name   = _font("poiret", 82)
    f_name2  = _font("poiret", 66)
    f_dt     = _font("segoe", 42)
    f_venue  = _font("segoe", 40)
    f_desc   = _font("segoe", 34)
    f_footer = _font("poiret", 26)

    # Top pink bar
    _pink_bar(draw, 0, height=4)

    # Vertically center the whole content block
    label_text = "HOMO HOTEL HAPPY HOUR" if is_hhhh else "FEATURED EVENT OF THE WEEK"
    name_font  = f_name if len(name) <= 30 else f_name2

    # Estimate content height
    name_lines = _wrap_to_width(draw, name, name_font, W - 120)[:3]
    est_h  = _text_height(draw, "X", f_label) + 14 + 2 + 48   # label + bar
    est_h += sum(_text_height(draw, ln, name_font) + 10 for ln in name_lines) + 24
    est_h += _text_height(draw, "X", f_dt) + 16
    est_h += _text_height(draw, "X", f_venue) * 2 + 20
    est_h += _text_height(draw, "X", f_desc) * 3 + 24

    y = max(80, (H - est_h) // 2 - 20)

    # Label
    y = _draw_centered(draw, label_text, y, f_label, WHITE)
    y += 14
    bar_w = 80
    draw.rectangle([(W - bar_w) // 2, y, (W + bar_w) // 2, y + 2], fill=NEON_PINK)
    y += 48

    # Event name
    y = _draw_wrapped(draw, name, y, name_font, WHITE,
                      max_px=W - 120, max_lines=3, line_gap=10)
    y += 24

    # Date / time
    if nice_date and time_str:
        dt_line = f"{nice_date}  ·  {time_str}"
    elif time_str:
        dt_line = time_str
    elif nice_date:
        dt_line = nice_date
    else:
        dt_line = ""
    if dt_line:
        y = _draw_centered(draw, dt_line, y, f_dt, GRAY)
        y += 16

    # Venue
    if venue:
        y = _draw_wrapped(draw, f"@ {venue}", y, f_venue, NEON_PINK,
                          max_px=W - 140, max_lines=2, line_gap=8)
        y += 20

    # Description
    if description:
        y = _draw_wrapped(draw, description, y, f_desc, LIGHT_GRAY,
                          max_px=W - 140, max_lines=4, line_gap=8)

    # Bottom
    _draw_centered(draw, "tulsagays.com", H - 60, f_footer, GRAY)
    _pink_bar(draw, H - 4, height=4)
    _watermark(draw)
    return img


def make_day_slide(day_name: str, events: List[Dict],
                   also_happening: Optional[List[Dict]] = None) -> Image.Image:
    """Day slide: ALL events in a flowing layout with ○ ○ ○ separators.
    Font sizes scale with event count. No slot-based layout — content flows
    top to bottom, no wasted space.
    """
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    # Merge ALL events — show every one as a full entry, not a tiny strip
    all_events = [e for e in events if not _is_garbage(e)]
    if also_happening:
        all_events.extend([e for e in also_happening if not _is_garbage(e)])
    all_events = all_events[:4]  # cap at 4 events — guarantees no overflow

    # The first event in the original list is the featured/highlighted one.
    # Sort all events chronologically, then find where the featured event landed.
    featured_event_obj = all_events[0] if all_events else None
    all_events = sorted(all_events, key=lambda e: _parse_event_time(e.get("time", "")))
    feat_idx = next(
        (i for i, e in enumerate(all_events) if e is featured_event_obj), 0
    )

    n      = len(all_events)
    accent = DAY_ACCENTS.get(day_name, GRAY)

    # ── Font sizes scale with event count ─────────────────────────────────
    if n <= 1:
        f_name, f_det, f_pitch, f_url = (
            _font("poiret", 80), _font("segoe", 36),
            _font("segoe", 30),  _font("segoe", 26))
        name_max_lines, pitch_max_lines, sep_gap = 2, 4, 0
    elif n == 2:
        f_name, f_det, f_pitch, f_url = (
            _font("poiret", 64), _font("segoe", 30),
            _font("segoe", 26),  _font("segoe", 24))
        name_max_lines, pitch_max_lines, sep_gap = 2, 3, 24
    elif n == 3:
        f_name, f_det, f_pitch, f_url = (
            _font("poiret", 52), _font("segoe", 26),
            _font("segoe", 22),  _font("segoe", 22))
        name_max_lines, pitch_max_lines, sep_gap = 2, 3, 22
    elif n == 4:
        f_name, f_det, f_pitch, f_url = (
            _font("poiret", 44), _font("segoe", 20),
            _font("segoe", 19),  _font("segoe", 21))
        name_max_lines, pitch_max_lines, sep_gap = 1, 1, 14
    else:  # n >= 5 — safety net only, cap should prevent this
        f_name, f_det, f_pitch, f_url = (
            _font("poiret", 38), _font("segoe", 18),
            _font("segoe", 16),  _font("segoe", 18))
        name_max_lines, pitch_max_lines, sep_gap = 1, 0, 10

    f_day          = _font("poiret", 60)
    f_sep          = _font("segoe", 20)
    f_footer_big   = _font("poiret", 42)
    f_footer_sub   = _font("segoe", 17)

    # ── Header ────────────────────────────────────────────────────────────
    _pink_bar(draw, 0, height=4)
    y = 20
    y = _draw_centered(draw, day_name.upper(), y, f_day, accent)
    y += 14
    bar_w = 60
    draw.rectangle([(W - bar_w) // 2, y, (W + bar_w) // 2, y + 3], fill=NEON_PINK)
    y += 3 + 22

    # ── Footer reserve (three-line block: FOMO tagline + CTA + site) ────────
    footer_big_h  = _text_height(draw, "TULSAGAYS.COM", f_footer_big)
    footer_sub_h  = _text_height(draw, "X", f_footer_sub)
    footer_h      = footer_big_h + footer_sub_h * 2 + 64   # extra line for CTA
    content_bottom = H - footer_h - 16  # safety margin above footer

    # ── Flow layout — all events top to bottom ────────────────────────────
    if n == 0:
        mid = y + (content_bottom - y) // 2
        _draw_centered(draw, "Check tulsagays.com for events", mid, _font("segoe", 26), GRAY)
    else:
        y_first_start = None
        y_first_end   = None

        for i, event in enumerate(all_events):
            if y >= content_bottom:
                break

            # Extra gap before the featured event (if it's not the first rendered)
            if i == feat_idx and i > 0:
                y += 10

            if i == feat_idx:
                y_first_start = y - 10  # box padding above featured event

            ev_name  = clean_text(event.get("name", ""))
            ev_time  = event.get("time", "")
            ev_venue = clean_text(event.get("venue", ""))
            ev_pitch = event.get("description", "")
            ev_url   = event.get("url", "")
            nice_dt  = format_date(event.get("date", ""))

            # Name
            name_lines_drawn = _wrap_to_width(draw, ev_name, f_name, W - PAD * 2)[:name_max_lines]
            for ln in name_lines_drawn:
                if y >= content_bottom:
                    break
                _draw_centered(draw, ln, y, f_name, WHITE)
                y += _text_height(draw, ln, f_name) + 4
            y += 6

            # Time · Venue
            if y < content_bottom:
                det_parts = []
                if nice_dt and ev_time:
                    det_parts.append(f"{nice_dt}  ·  {ev_time}")
                elif ev_time:
                    det_parts.append(ev_time)
                elif nice_dt:
                    det_parts.append(nice_dt)
                if ev_venue:
                    det_parts.append(ev_venue[:45])  # tighter truncation prevents 2-line wraps

                if det_parts:
                    det_str = "  ·  ".join(det_parts)
                    if len(det_parts) == 2 and _text_width(draw, det_str, f_det) > W - PAD * 2:
                        _draw_centered(draw, det_parts[0], y, f_det, GRAY)
                        y += _text_height(draw, "X", f_det) + 4
                        if y < content_bottom:
                            _draw_centered(draw, f"@ {det_parts[1]}", y, f_det, NEON_PINK)
                            y += _text_height(draw, "X", f_det) + 5
                    else:
                        _draw_centered(draw, det_str, y, f_det, GRAY)
                        y += _text_height(draw, "X", f_det) + 5

            # Pitch
            if ev_pitch and y < content_bottom:
                pitch_list = _wrap_to_width(draw, ev_pitch, f_pitch, W - PAD * 2 - 40)[:pitch_max_lines]
                for pl in pitch_list:
                    if y >= content_bottom:
                        break
                    _draw_centered(draw, pl, y, f_pitch, LIGHT_GRAY)
                    y += _text_height(draw, pl, f_pitch) + 4
                y += 4

            # URL
            if ev_url and y < content_bottom:
                display_url = re.sub(r'^https?://', '', ev_url).split("?")[0]
                if len(display_url) > 50:
                    display_url = display_url[:50] + "..."
                _draw_centered(draw, display_url, y, f_url, NEON_PINK)
                y += _text_height(draw, "X", f_url) + 4

            # Track featured event bottom bound (for the highlight box)
            if i == feat_idx:
                y_first_end = y + 14

            # ○ ○ ○ separator between events
            if i < n - 1 and y < content_bottom - sep_gap * 4:
                y += sep_gap
                _draw_centered(draw, "\u25cb  \u25cb  \u25cb", y, f_sep, "#555555")
                y += _text_height(draw, "\u25cb  \u25cb  \u25cb", f_sep) + sep_gap

        # ── Pink highlight box around top recommended event ────────────────
        if y_first_start is not None and y_first_end is not None:
            draw.rounded_rectangle(
                [PAD - 22, y_first_start,
                 W - PAD + 22, y_first_end],
                radius=12,
                outline=NEON_PINK,
                width=3
            )

    # ── Footer ── FOMO tagline + TULSAGAYS.COM + "hundreds of events" CTA ──
    footer_y = H - footer_h + 16
    day_tagline = DAY_FOOTER_TAGLINES.get(day_name, "Hundreds of fabulous events this week in Tulsa.")
    _draw_centered(draw, day_tagline, footer_y, f_footer_sub, NEON_PINK)
    footer_y += footer_sub_h + 10
    _draw_centered(draw, "TULSAGAYS.COM", footer_y, f_footer_big, WHITE)
    footer_y += footer_big_h + 6
    _draw_centered(draw, "Hundreds of fabulous events this week \u00b7 visit to see the full list",
                   footer_y, f_footer_sub, LIGHT_GRAY)
    _watermark(draw)
    return img


def make_closing_slide() -> Image.Image:
    """Slide 10: CTA. DM us, follow, linktr.ee."""
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    f_intro   = _font("segoe-semi", 42)
    f_handle  = _font("poiret", 88)
    f_sub     = _font("segoe", 36)
    f_link    = _font("segoe", 36)

    _pink_bar(draw, 0, height=4)

    # Estimate total content height to vertically center it
    intro_h  = _text_height(draw, "X", f_intro)
    handle_h = _text_height(draw, "DM US", f_handle)
    at_h     = _text_height(draw, "@TULSAGAYS", f_handle)
    sub_h    = _text_height(draw, "X", f_sub)
    link_h   = _text_height(draw, "X", f_link)
    total_h  = intro_h + 16 + handle_h + 10 + at_h + 32 + 2 + 32 + sub_h + 24 + link_h

    y = max(80, (H - total_h) // 2)

    y = _draw_centered(draw, "Know about an event?", y, f_intro, LIGHT_GRAY)
    y += 16
    y = _draw_centered(draw, "DM US", y, f_handle, WHITE)
    y += 10
    y = _draw_centered(draw, "@TULSAGAYS", y, f_handle, NEON_PINK)
    y += 32

    bar_w = 200
    draw.rectangle([(W - bar_w) // 2, y, (W + bar_w) // 2, y + 2], fill=NEON_PINK)
    y += 32

    y = _draw_centered(draw, "Hundreds of fabulous events this week in Tulsa.", y, f_sub, LIGHT_GRAY)
    y += 10
    y = _draw_centered(draw, "Visit tulsagays.com to see the full list.", y, f_sub, LIGHT_GRAY)
    y += 24
    y = _draw_centered(draw, "tulsagays.com  \u00b7  linktr.ee/tulsagays", y, f_link, NEON_PINK)

    _pink_bar(draw, H - 4, height=4)
    _watermark(draw)
    return img


def make_category_slide(category_name: str, events: List[Dict],
                        accent_color: str = GRAY) -> Image.Image:
    """Legacy category slide — kept for backward compatibility."""
    day_equiv = {
        "community": "Monday",
        "arts": "Tuesday",
        "nightlife": "Thursday",
    }
    day = day_equiv.get(category_name.lower(), "Monday")
    return make_day_slide(day, events)


def make_homo_hotel_slide(event: Dict) -> Image.Image:
    """HHHH featured slide — delegates to make_featured_slide."""
    return make_featured_slide(event)


# ── Carousel Builder ──────────────────────────────────────────────────────

def create_carousel(events_by_category: Dict[str, List[Dict]],
                    post_type: str,
                    date_range: str,
                    logo_path: Optional[str] = None,
                    events_by_day: Optional[Dict[str, List[Dict]]] = None,
                    featured_event: Optional[Dict] = None,
                    upcoming_event: Optional[Dict] = None) -> List[Image.Image]:
    """Build full 10-slide carousel: Cover → Featured → Mon-Sun → CTA."""
    slides: List[Image.Image] = []
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]

    # Resolve featured event — priority order:
    # 1. Homo Hotel Happy Hour (always wins if present)
    # 2. Council Oak Men's Chorus (any event with "council oak" in name/source)
    # 3. Any non-recurring special event (exclude source=="recurring" and sports)
    # NEVER pick a recurring event (bowling, AA, support groups, etc.)
    eotw = featured_event
    if not eotw or _is_garbage(eotw):
        all_events_flat = [
            e for cat in events_by_category.values()
            for e in cat
            if not _is_garbage(e)
        ]

        def _is_recurring(e: Dict) -> bool:
            src = (e.get("source") or "").lower()
            name = (e.get("name") or "").lower()
            recurring_sources = {"recurring", "aa_meetings", "bars"}
            recurring_keywords = {
                "bowling", "aa meeting", "support group", "outreach group",
                "sound bath", "sonic ray", "sound sanctuary", "sound meditation",
            }
            if src in recurring_sources:
                return True
            return any(kw in name for kw in recurring_keywords)

        def _is_homo_hotel(e: Dict) -> bool:
            return ("homo hotel" in (e.get("name") or "").lower()
                    or (e.get("source") or "").lower() == "homo_hotel")

        def _is_council_oak(e: Dict) -> bool:
            combined = ((e.get("name") or "") + " " + (e.get("source") or "")).lower()
            return "council oak" in combined or "comc" in combined

        QUEER_PERFORMANCE_KEYWORDS = [
            "drag", "drag show", "drag bingo", "drag brunch", "drag queen",
            "drag king", "drag race", "cabaret", "pride show", "pride event",
            "pride night", "queer night", "gay night", "lgbtq+ night",
            "twisted arts", "okeq", "rainbow", "pride dance", "pride party",
        ]

        def _is_queer_performance(e: Dict) -> bool:
            combined = " ".join([
                (e.get("name") or ""), (e.get("description") or ""),
                (e.get("venue") or ""), (e.get("source") or "")
            ]).lower()
            return any(kw in combined for kw in QUEER_PERFORMANCE_KEYWORDS)

        # Compute this week's Monday-Sunday date range
        from datetime import timedelta
        today = datetime.now().date()
        week_monday = today - timedelta(days=today.weekday())
        week_sunday = week_monday + timedelta(days=6)

        def _event_in_week(e: Dict) -> bool:
            date_str = e.get("date", "")
            if not date_str:
                return False
            try:
                ev_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                return week_monday <= ev_date <= week_sunday
            except ValueError:
                return False

        # Priority 1: Homo Hotel Happy Hour — only if it falls within THIS week
        hh_this_week = [e for e in all_events_flat if _is_homo_hotel(e) and _event_in_week(e)]
        hh_upcoming  = [e for e in all_events_flat if _is_homo_hotel(e) and not _event_in_week(e)]
        if hh_this_week:
            eotw = hh_this_week[0]
        else:
            # HHHH not this week — save it as upcoming teaser if no upcoming_event yet
            if not upcoming_event and hh_upcoming:
                upcoming_event = hh_upcoming[0]
            # Priority 2: Council Oak Men's Chorus (concerts/cabarets)
            council = [e for e in all_events_flat if _is_council_oak(e)]
            if council:
                eotw = council[0]
            else:
                # Priority 3: Drag shows, queer performances, explicitly LGBTQ events
                queer_perf = [e for e in all_events_flat
                              if _is_queer_performance(e) and not _is_recurring(e)]
                if queer_perf:
                    eotw = queer_perf[0]
                else:
                    # Priority 4: Best non-recurring special event
                    special = [e for e in all_events_flat if not _is_recurring(e)]
                    if special:
                        eotw = special[0]
                    elif all_events_flat:
                        eotw = all_events_flat[0]

    # Slide 1: Cover + Event of the Week combined
    slides.append(make_cover_slide(post_type, date_range, featured_event=eotw,
                                   upcoming_event=upcoming_event))

    # Slides 3-9: One per day
    if events_by_day:
        for day in days_of_week:
            day_events = [e for e in events_by_day.get(day, [])
                          if not _is_garbage(e)]
            # Ensure EOTW appears first on its own day slide
            if eotw and day_events:
                eotw_in_day = [e for e in day_events if e is eotw or (
                    e.get("name") == (eotw.get("name") if eotw else None)
                    and e.get("date") == (eotw.get("date") if eotw else None)
                )]
                if eotw_in_day:
                    day_events = [eotw_in_day[0]] + [
                        e for e in day_events if e is not eotw_in_day[0]
                        and not (e.get("name") == eotw_in_day[0].get("name")
                                 and e.get("date") == eotw_in_day[0].get("date"))
                    ]
            slides.append(make_day_slide(day, day_events[:3]))
    else:
        # Fallback: map categories to day slides
        cat_day_map = {"community": "Monday", "arts": "Wednesday", "nightlife": "Friday"}
        for cat, day in cat_day_map.items():
            ev = [e for e in events_by_category.get(cat, []) if not _is_garbage(e)]
            slides.append(make_day_slide(day, ev[:3], also_happening=ev[3:6] or None))
        # Fill remaining days
        filled = set(cat_day_map.values())
        for day in days_of_week:
            if day not in filled:
                slides.append(make_day_slide(day, []))

    # Slide 10: CTA
    slides.append(make_closing_slide())

    return slides


def save_carousel(images: List[Image.Image], output_dir: str,
                  prefix: str = "slide") -> List[str]:
    """Save slides as numbered PNGs. Returns list of file paths."""
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, img in enumerate(images, start=1):
        path = os.path.join(output_dir, f"{prefix}_{i:02d}.png")
        img.save(path, "PNG", optimize=True)
        paths.append(path)
    return paths


# ── CLI test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating Tulsa Gays carousel (corrected design)...")

    events_by_day = {
        "Monday": [
            {"name": "Lambda Bowling League", "time": "7:00 PM",
             "venue": "AMF Sheridan Lanes, 3121 S Sheridan",
             "description": "Tulsa's LGBTQ+ bowling league rolls every Monday. All skill levels. Show up at 7.",
             "url": "facebook.com/groups/tulsalambda",
             "date": "2026-04-06"},
            {"name": "Gay AA Meeting (Lambda Unity)", "time": "8:00 PM",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
             "description": "LGBTQ+ AA meeting. All are welcome.",
             "url": "okeq.org",
             "date": "2026-04-06"},
            {"name": "All Souls Sunday Reset", "time": "Various times",
             "venue": "All Souls Unitarian, 2952 S Peoria",
             "description": "Missed Sunday? All Souls has multiple weekly gatherings. LGBTQ+ affirming community.",
             "url": "allsoulschurch.org",
             "date": "2026-04-06"},
        ],
        "Tuesday": [
            {"name": "Mamma Mia! Opening Night", "time": "7:30 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "ABBA on a Broadway stage in Tulsa. The touring production opens tonight. The gay cultural event of the season.",
             "url": "tulsapac.com",
             "date": "2026-04-07"},
            {"name": "OSU Tulsa Queer Support Group", "time": "6:00 PM",
             "venue": "OSU Tulsa Campus, 700 N Greenwood",
             "description": "Free, open to all adults every Tuesday. Real people talking about real stuff in a safe space.",
             "url": "events.tulsa.okstate.edu",
             "date": "2026-04-07"},
            {"name": "Gender Outreach Support Group", "time": "7:00 PM",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
             "description": "Free weekly support for trans, nonbinary, and gender-questioning folks. Run by OKEQ.",
             "url": "okeq.org",
             "date": "2026-04-07"},
        ],
        "Wednesday": [
            {"name": "Mamma Mia! (Wednesday)", "time": "7:30 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "ABBA on Broadway, mid-week. Go before the weekend crowds. Still tickets available.",
             "url": "tulsapac.com",
             "date": "2026-04-08"},
            {"name": "Gender Outreach Support Group", "time": "7:00 PM - 9:00 PM",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
             "description": "Free weekly support for trans, nonbinary, and gender-questioning folks. Run by OKEQ. No judgment.",
             "url": "okeq.org",
             "date": "2026-04-08"},
            {"name": "Queer Women's Collective", "time": "7:00 PM",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
             "description": "1st Wednesday monthly. Space for queer women and femmes in Tulsa. Community, connection, good people.",
             "url": "okeq.org",
             "date": "2026-04-08"},
        ],
        "Thursday": [
            {"name": "DRAGNIFICENT! Drag Show", "time": "Doors 9 PM, Show 10 PM",
             "venue": "Club Majestic, 124 N Boston Ave",
             "description": "Tulsa's weekly Thursday drag institution hosted by Shanel Sterling. Rotating performers who come to slay. 18+ ($8/$4 cover).",
             "url": "clubmajestic.com",
             "date": "2026-04-09"},
            {"name": "Mamma Mia! (Thursday)", "time": "7:30 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "Thursday night Broadway. ABBA, dancing, a mystery dad. Catch it before the weekend shows sell out.",
             "url": "tulsapac.com",
             "date": "2026-04-09"},
            {"name": "Green Country Bears Monthly Meetup", "time": "7:00 PM",
             "venue": "Restaurant varies, check greencountrybears.com",
             "description": "Second Thursday. Tulsa's bear community gathers for food and good company. All bears and friends welcome.",
             "url": "greencountrybears.com",
             "date": "2026-04-09"},
        ],
        "Friday": [
            {"name": "Mamma Mia! (Friday Night)", "time": "8:00 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "Friday night Broadway. ABBA, sequins, a wild story about who's the dad. Date night sorted.",
             "url": "tulsapac.com",
             "date": "2026-04-10"},
            {"name": "Tulsa Eagle Friday Night", "time": "9:00 PM",
             "venue": "Tulsa Eagle, 1820 E 5th Pl",
             "description": "The leather bar is open. Strong drinks, strong community. 21+.",
             "url": "tulsaeagle.com",
             "date": "2026-04-10"},
            {"name": "Yellow Brick Road Weekend", "time": "9:00 PM",
             "venue": "Yellow Brick Road, 3314 E 32nd Pl",
             "description": "Tulsa's LGBTQ+ bar is open and the dance floor is yours. Friday vibes.",
             "url": "facebook.com/ybrtulsa",
             "date": "2026-04-10"},
        ],
        "Saturday": [
            {"name": "Elote Drag Brunch", "time": "11:00 AM + 1:30 PM",
             "venue": "Elote Cafe, 514 S Boston Ave",
             "description": "Two seatings. Glitter as gospel, brunch as blessing. This sells out every time. Get tickets on Eventbrite now.",
             "url": "eloterestaurant.com",
             "date": "2026-04-11"},
            {"name": "Mamma Mia! (Saturday Shows)", "time": "2:00 PM + 8:00 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "Two shows Saturday. Your last weekend chance. Book the matinee and be home for dinner, or do the 8pm for full glamour.",
             "url": "tulsapac.com",
             "date": "2026-04-11"},
            {"name": "Yellow Brick Road Saturday Night", "time": "9:00 PM",
             "venue": "Yellow Brick Road, 3314 E 32nd Pl",
             "description": "Saturday at YBR. The main event. Full bar, dancing, and your people.",
             "url": "facebook.com/ybrtulsa",
             "date": "2026-04-11"},
        ],
        "Sunday": [
            {"name": "Mamma Mia! Closing Day", "time": "1:00 PM + 6:30 PM",
             "venue": "Chapman Music Hall, Tulsa PAC",
             "description": "Last day. Two shows. ABBA on Broadway. Your last shot. Don't let it slip away.",
             "url": "tulsapac.com",
             "date": "2026-04-12"},
            {"name": "Sunday Showdown Open Talent Night", "time": "Doors 9 PM, Show 11 PM",
             "venue": "Club Majestic, 124 N Boston Ave",
             "description": "Hosted by Shanel Sterling. Come watch or come perform. 18+. Sunday nights at Majestic are always a moment.",
             "url": "clubmajestic.com",
             "date": "2026-04-12"},
            {"name": "All Souls Unitarian Sunday Services", "time": "10:00 AM + 11:15 AM",
             "venue": "All Souls Unitarian Church, 2952 S Peoria Ave",
             "description": "The largest UU congregation in the US. LGBTQ+ affirming since forever. Walk in as you are.",
             "url": "allsoulschurch.org",
             "date": "2026-04-12"},
        ],
    }

    featured = {
        "name": "Mamma Mia! (Broadway Touring)",
        "date": "2026-04-07",
        "time": "7:30 PM",
        "venue": "Chapman Music Hall, Tulsa PAC",
        "description": "ABBA on Broadway in Tulsa all week. The gay cultural event of the season. Runs Apr 7-12.",
        "url": "tulsapac.com",
    }

    slides = create_carousel(
        events_by_category={},
        post_type="weekday",
        date_range="April 6 - 12, 2026",
        events_by_day=events_by_day,
        featured_event=featured,
    )

    output = os.path.join("docs", "images", "weekly")
    paths = save_carousel(slides, output)
    print(f"Generated {len(paths)} slides:")
    for p in paths:
        print(f"  {os.path.basename(p)}")
