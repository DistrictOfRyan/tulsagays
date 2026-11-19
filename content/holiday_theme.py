"""Holiday touch for TulsaGays posts.

William 2026-11-18: "When you do my posts for Tulsa Gays give them a little extra
special holiday touch when they land on a holiday month. Elegantly classy and
minimalist but give it some extra flair."

How it stays classy:
  * Zero layout cost. Motifs sit in the empty space beside the TULSA/GAYS wordmark
    and in the top corners of day/closing slides; seasonal copy replaces the one-line
    tagline / footer note / closing line it already occupies. Nothing moves, so the
    cover overflow guard and preflight are untouched.
  * One motif family per holiday, drawn with thin supersampled lines in the brand
    palette (no burnt orange, no gold deco lines, no rainbow bars: those are HHHH's).
  * Captions get one seasonal phrase and one seasonal emoji, never a holiday ad.

Themes live in data/holiday_themes.json. A week is themed by its Thursday, so a
Nov 30 - Dec 6 deck is a December deck.
  TULSAGAYS_HOLIDAY=off              disable entirely
  TULSAGAYS_HOLIDAY_DATE=YYYY-MM-DD  preview the theme for that date
"""

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from PIL import Image, ImageDraw

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_THEMES_PATH = os.path.join(_ROOT, "data", "holiday_themes.json")
_SS = 4  # supersampling factor for crisp thin lines

# Set by image_maker.create_carousel() to the week being rendered.
_ACTIVE_REF: Optional[date] = None


def _load() -> list:
    try:
        with open(_THEMES_PATH, encoding="utf-8") as f:
            return json.load(f).get("themes", [])
    except Exception:
        return []


def _ref_date(ref=None) -> Optional[date]:
    if os.environ.get("TULSAGAYS_HOLIDAY", "").lower() in ("off", "0", "false", "no"):
        return None
    forced = os.environ.get("TULSAGAYS_HOLIDAY_DATE", "").strip()
    if forced:
        try:
            return datetime.strptime(forced, "%Y-%m-%d").date()
        except ValueError:
            pass
    if ref is None:
        ref = _ACTIVE_REF or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()
    return ref


def week_thursday(d: date) -> date:
    return d - timedelta(days=d.weekday()) + timedelta(days=3)


def set_active_week(any_day_in_week: Optional[date]) -> None:
    """Pin the theme to the week being rendered (its Thursday)."""
    global _ACTIVE_REF
    _ACTIVE_REF = week_thursday(any_day_in_week) if any_day_in_week else None


def theme_for(ref=None) -> Optional[Dict]:
    """Theme dict for the date (default: active week, else this week), or None."""
    d = _ref_date(ref)
    if d is None:
        return None
    if ref is None and not os.environ.get("TULSAGAYS_HOLIDAY_DATE") and _ACTIVE_REF is None:
        d = week_thursday(d)
    themes = _load()
    # Week-scoped themes first (the Fourth of July week): only the Mon-Sun deck that
    # contains the date, so the rest of the month stays plain.
    mon = d - timedelta(days=d.weekday())
    for t in themes:
        for mmdd in t.get("week_of", []):
            try:
                target = date(d.year, int(mmdd[:2]), int(mmdd[3:5]))
            except ValueError:
                continue
            if mon <= target <= mon + timedelta(days=6):
                out = dict(t)
                out["_ref"] = d.isoformat()
                return out
    for t in themes:
        if d.month in t.get("months", []):
            until = t.get("until_day")
            if until and d.day > until:
                continue
            out = dict(t)
            out["_ref"] = d.isoformat()
            return out
    return None


def pick_line(theme: Optional[Dict], key: str, fallback: Optional[str] = None) -> Optional[str]:
    """Theme copy for `key`; list values rotate by ISO week so weeks differ."""
    if not theme:
        return fallback
    val = theme.get(key)
    if isinstance(val, list):
        if not val:
            return fallback
        wk = datetime.strptime(theme["_ref"], "%Y-%m-%d").isocalendar()[1]
        return val[wk % len(val)]
    return val or fallback


# ── The holiday's own day ────────────────────────────────────────────────────
# "Whenever they come up" (William 2026-11-18): the month touch says the season; the
# day label says the day. The slide for the holiday's own date carries its name beside
# the date ("11/26 · THANKSGIVING"), in every month, on the line the date already uses.

def _easter(year: int) -> date:
    """Western Easter (anonymous Gregorian algorithm). check_days.py proves it
    against dateutil.easter."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _day_dates(entry: Dict, year: int) -> list:
    out = []
    try:
        if entry.get("date"):
            mm, dd = entry["date"].split("-")
            out.append(date(year, int(mm), int(dd)))
        rule = entry.get("rule", "")
        if rule == "easter":
            out.append(_easter(year))
        elif rule == "easter-47":
            out.append(_easter(year) - timedelta(days=47))
        elif rule.startswith("nth:"):
            _, month, wd, n = rule.split(":")
            first = date(year, int(month), 1)
            off = (int(wd) - first.weekday()) % 7
            out.append(first + timedelta(days=off + 7 * (int(n) - 1)))
        for s in entry.get("dates", []):
            dd = datetime.strptime(s, "%Y-%m-%d").date()
            if dd.year == year:
                out.append(dd)
    except (ValueError, KeyError):
        pass
    return out


def _off() -> bool:
    return os.environ.get("TULSAGAYS_HOLIDAY", "").lower() in ("off", "0", "false", "no")


def day_holidays(d) -> list:
    """Holiday entries that fall exactly on date `d` (empty when the layer is off)."""
    if _off() or d is None:
        return []
    if isinstance(d, datetime):
        d = d.date()
    try:
        with open(_THEMES_PATH, encoding="utf-8") as f:
            days = json.load(f).get("days", [])
    except Exception:
        return []
    return [e for e in days if d in _day_dates(e, d.year)]


def day_label(d) -> Optional[str]:
    """'Thanksgiving', 'Christmas Eve & Hanukkah begins', or None."""
    hits = day_holidays(d)
    return " & ".join(e["label"] for e in hits) if hits else None


def is_solemn_day(d) -> bool:
    """A memorial date (Trans Day of Remembrance, World AIDS Day): no festive motif."""
    return any(e.get("solemn") for e in day_holidays(d))


def week_holidays(any_day) -> list:
    """[(date, entry)] for every holiday in the Mon-Sun week containing `any_day`."""
    if any_day is None:
        return []
    if isinstance(any_day, datetime):
        any_day = any_day.date()
    mon = any_day - timedelta(days=any_day.weekday())
    out = []
    for i in range(7):
        dd = mon + timedelta(days=i)
        out += [(dd, e) for e in day_holidays(dd)]
    return out


def preview_today() -> Optional[date]:
    """TULSAGAYS_HOLIDAY_DATE as a date (previews only), else None. Lets a preview
    render show that week's dates on day slides; never set in production."""
    forced = os.environ.get("TULSAGAYS_HOLIDAY_DATE", "").strip()
    try:
        return datetime.strptime(forced, "%Y-%m-%d").date() if forced else None
    except ValueError:
        return None


def week_note(dates) -> Optional[str]:
    """'Halloween is Saturday.' for festive holidays among `dates` (caption line)."""
    seen, bits = set(), []
    for s in dates or []:
        try:
            dd = s if isinstance(s, date) else datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if dd in seen:
            continue
        seen.add(dd)
        for e in day_holidays(dd):
            if not e.get("solemn"):
                bits.append(f"{e['label']} is {dd.strftime('%A')}.")
    return " ".join(bits) or None


# ── Restraint: memorial weeks ────────────────────────────────────────────────
# A holiday flourish next to a vigil reads as tone-deaf. The 2026-W47 deck's Event of
# the Week was the Trans Day of Remembrance (Fri 11/20), in Friendsgiving month, and
# Dec 1 is World AIDS Day. Wherever a solemn event leads (cover, a day slide, the
# caption's top picks), that surface stays plain.
# Word-bounded and specific: a bare "memorial" or "candlelight" hit "First Thursday Art
# Show (Allie Jensen Memorial Art Gallery)" in the real W47 data, and would hit every
# "Candlelight: A Tribute to ..." concert, swapping a party cover to the memorial line.
import re as _re
_SOLEMN = _re.compile(
    r"\bremembrance\b|\bvigils?\b|\bin memoriam\b|\bworld aids day\b|\bday of mourning\b"
    r"|\bcelebration of life\b|\bfuneral\b"
    r"|\bmemorial (service|gathering|ceremony|walk|vigil|for)\b", _re.I)


def is_solemn(event: Optional[Dict]) -> bool:
    if not event:
        return False
    text = " ".join(str(event.get(k) or "") for k in ("name", "cover_name", "description"))
    return bool(_SOLEMN.search(text))


def theme_unless_solemn(theme: Optional[Dict], events) -> Optional[Dict]:
    """The theme, or None when any of `events` is a memorial/vigil."""
    if not theme:
        return None
    return None if any(is_solemn(e) for e in (events or []) if e) else theme


# ── Motifs ───────────────────────────────────────────────────────────────────

def _rgba(hex_color: str, alpha: int = 255):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _sparkle(d: ImageDraw.ImageDraw, cx, cy, r, color, waist=0.16):
    w = r * waist
    pts = [(cx, cy - r), (cx + w, cy - w), (cx + r, cy), (cx + w, cy + w),
           (cx, cy + r), (cx - w, cy + w), (cx - r, cy), (cx - w, cy - w)]
    d.polygon(pts, fill=color)


def _snowflake(d, cx, cy, r, color, lw):
    for k in range(6):
        a = math.radians(90 + k * 60)
        ex, ey = cx + r * math.cos(a), cy - r * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=color, width=lw)
        for frac, blen in ((0.55, 0.30), (0.78, 0.20)):
            bx, by = cx + r * frac * math.cos(a), cy - r * frac * math.sin(a)
            for s in (-1, 1):
                b = a + s * math.radians(40)
                d.line([(bx, by), (bx + r * blen * math.cos(b), by - r * blen * math.sin(b))],
                       fill=color, width=lw)
    d.ellipse([cx - lw, cy - lw, cx + lw, cy + lw], fill=color)


def _heart(d, cx, cy, r, color):
    rr = r * 0.52
    d.ellipse([cx - 2 * rr, cy - rr * 1.3, cx, cy + rr * 0.7], fill=color)
    d.ellipse([cx, cy - rr * 1.3, cx + 2 * rr, cy + rr * 0.7], fill=color)
    d.polygon([(cx - 1.93 * rr, cy - 0.05 * rr), (cx + 1.93 * rr, cy - 0.05 * rr),
               (cx, cy + r * 1.05)], fill=color)


def _moon(layer, cx, cy, r, color):
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    off = r * 0.42
    d.ellipse([cx - r + off, cy - r - off * 0.35, cx + r + off, cy + r - off * 0.35],
              fill=(0, 0, 0, 0))


def _leaf(d, cx, cy, r, color, lw, angle_deg=35):
    a = math.radians(angle_deg)
    pts = []
    for i in range(41):
        t = -1 + 2 * i / 40
        x, y = t * r, (1 - t * t) * r * 0.42
        pts.append((x, y))
    pts += [(x, -y) for (x, y) in reversed(pts)]
    rot = [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a))
           for (x, y) in pts]
    d.line(rot + [rot[0]], fill=color, width=lw, joint="curve")
    tip = (cx + r * math.cos(a), cy + r * math.sin(a))
    base = (cx - r * math.cos(a), cy - r * math.sin(a))
    d.line([base, tip], fill=color, width=max(1, lw - _SS))
    d.line([base, (base[0] - r * 0.35 * math.cos(a), base[1] - r * 0.35 * math.sin(a))],
           fill=color, width=lw)


def _firework(d, cx, cy, r, color, accent, lw):
    """Thin starburst: 12 spokes from a hollow centre, a dot at each tip."""
    for k in range(12):
        a = math.radians(k * 30 + 15)
        r0 = r * 0.30
        r1 = r * (1.0 if k % 2 == 0 else 0.78)
        x0, y0 = cx + r0 * math.cos(a), cy - r0 * math.sin(a)
        x1, y1 = cx + r1 * math.cos(a), cy - r1 * math.sin(a)
        d.line([(x0, y0), (x1, y1)], fill=color, width=lw)
        dot = lw * 1.3
        tip = accent if k % 2 == 0 else color
        d.ellipse([x1 - dot, y1 - dot, x1 + dot, y1 + dot], fill=tip)


def _cluster(theme: Dict, size: int, mirror: bool = False) -> Image.Image:
    """One motif cluster (main motif + two small sparkles) as an RGBA tile."""
    S = size * _SS
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cols = theme.get("colors") or ["#FFFFFF", "#FF1493"]
    main, accent = _rgba(cols[0]), _rgba(cols[1 % len(cols)])
    soft = _rgba(cols[-1], 200)
    lw = max(2, round(S * 0.022))
    cx, cy, r = S * 0.44, S * 0.52, S * 0.30
    kind = theme.get("motif", "sparkle")
    if kind == "snowflake":
        _snowflake(d, cx, cy, r, main, lw)
    elif kind == "heart":
        _heart(d, cx, cy + r * 0.05, r * 0.82, accent)
    elif kind == "moon":
        _moon(layer, cx, cy, r * 0.82, main)
        d = ImageDraw.Draw(layer)
    elif kind == "firework":
        _firework(d, cx, cy, r, main, accent, lw)
    elif kind == "leaf":
        _leaf(d, cx - r * 0.12, cy + r * 0.10, r * 0.85, main, lw, angle_deg=35)
        _leaf(d, cx + r * 0.40, cy - r * 0.42, r * 0.50, accent, lw, angle_deg=-20)
    elif kind == "pride_sparkle":
        ring = cols[:6]
        for k, c in enumerate(ring):
            a = math.radians(90 + k * 60)
            _sparkle(d, cx + r * 0.62 * math.cos(a), cy - r * 0.62 * math.sin(a),
                     r * 0.26, _rgba(c))
        _sparkle(d, cx, cy, r * 0.34, _rgba("#FFFFFF"))
    else:
        _sparkle(d, cx, cy, r, main, waist=0.13)
    # satellites: the "flair"
    _sparkle(d, S * 0.84, S * 0.18, S * 0.075, accent)
    _sparkle(d, S * 0.16, S * 0.86, S * 0.05, soft)
    tile = layer.resize((size, size), Image.LANCZOS)
    return tile.transpose(Image.FLIP_LEFT_RIGHT) if mirror else tile


def _paste(img: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    img.paste(tile, (int(x), int(y)), tile)


def decorate_cover(img: Image.Image, theme: Optional[Dict], wm_top: int, wm_bottom: int) -> None:
    """Flank the TULSA/GAYS wordmark with a mirrored motif pair (no layout change)."""
    if not theme:
        return
    W = img.size[0]
    size = 150
    cy = (wm_top + wm_bottom) // 2
    _paste(img, _cluster(theme, size), 92, cy - size // 2)
    _paste(img, _cluster(theme, size, mirror=True), W - 92 - size, cy - size // 2)


def decorate_corners(img: Image.Image, theme: Optional[Dict], y: int = 22, size: int = 84) -> None:
    """Small mirrored motifs in the two top corners (day / closing / engagement slides)."""
    if not theme:
        return
    W = img.size[0]
    _paste(img, _cluster(theme, size), 34, y)
    _paste(img, _cluster(theme, size, mirror=True), W - 34 - size, y)


# ── Captions ─────────────────────────────────────────────────────────────────

def caption_prompt_note(theme: Optional[Dict], week_of=None) -> str:
    """Extra instruction for the caption LLM in a holiday month, plus a one-line nod
    for any holiday that falls inside the week (`week_of` = any day in the week).
    Empty when there is neither."""
    note = ""
    if theme:
        note += (
            f"\nSEASON: it is {theme['label']} in Tulsa. Give the hook a light, classy "
            f"{theme['label']} touch: one seasonal phrase and the {theme['emoji']} emoji, "
            "no more. Do not turn the post into a holiday ad, do not invent holiday events, "
            "and only call an event holiday-themed if its listing says so.\n"
        )
    days = week_holidays(week_of)
    festive = [f"{e['label']} ({dd.strftime('%A')} {dd.month}/{dd.day})"
               for dd, e in days if not e.get("solemn")]
    solemn = [f"{e['label']} ({dd.strftime('%A')} {dd.month}/{dd.day})"
              for dd, e in days if e.get("solemn")]
    if festive:
        note += ("\nHOLIDAY THIS WEEK: " + ", ".join(festive) + ". One light, warm nod to it "
                 "is welcome. Do not claim an event is a holiday party unless its listing says so.\n")
    if solemn:
        note += ("\nMEMORIAL THIS WEEK: " + ", ".join(solemn) + ". If you mention it, be "
                 "respectful and brief: no jokes, no emoji next to it, no holiday flourish near it.\n")
    return note


def apply_caption_flourish(caption: str, theme: Optional[Dict]) -> str:
    """Guarantee the seasonal touch: the theme emoji on line 1. Idempotent."""
    if not theme or not caption:
        return caption
    emoji = theme.get("emoji", "")
    lines = caption.split("\n")
    if emoji and emoji not in lines[0]:
        lines[0] = f"{emoji} {lines[0].lstrip()}"
    return "\n".join(lines)


def season_caption(caption: str, events=None, ref=None, note_dates=None) -> str:
    """One call for the mid-week / weekend captions: the seasonal emoji on line 1
    (skipped when a listed event is a memorial) and, when `note_dates` holds a festive
    holiday, a short 'Thanksgiving is Thursday.' line under the first line."""
    if not caption:
        return caption
    theme = theme_unless_solemn(theme_for(ref), events)
    note = week_note(note_dates)
    if note and note not in caption:
        lines = caption.split("\n")
        lines.insert(1, note)
        caption = "\n".join(lines)
    return apply_caption_flourish(caption, theme)


def fallback_opener(theme: Optional[Dict]) -> Optional[str]:
    """Seasonal first line for template (non-LLM) captions."""
    return theme.get("caption_line") if theme else None


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or [date.today().isoformat()]:
        t = theme_for(datetime.strptime(s, "%Y-%m-%d").date())
        print(s, "->", t["key"] if t else None)
