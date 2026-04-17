"""Regenerate May 2026 HHHH promo (Hotel TBD) - Brut pulled out."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 1080, 1420
OUT = Path(r"C:\Users\ryan\OneDrive\Desktop\repos\tulsagays\docs\images\hhhh\hhhh_promo_2026-05.png")

WHITE = (255, 255, 255)
BLACK = (30, 30, 30)
ORANGE = (235, 120, 40)
GRAY = (100, 100, 100)
LIGHT = (200, 200, 200)

FONT_DIR = Path(r"C:\Windows\Fonts")
def ttf(name, size):
    for p in (FONT_DIR/name, Path(name)):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()

im = Image.new("RGB", (W, H), WHITE)
d = ImageDraw.Draw(im)

# HHHH logo badge (4-square)
cx, cy = W // 2, 280
r = 220
d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLACK)
s = 110
colors = [(147, 51, 182), (85, 165, 70), (235, 130, 45), (72, 172, 206)]  # purple, green, orange, cyan
letters = ["H", "H", "H", "H"]
positions = [(-s - 8, -s - 8), (8, -s - 8), (-s - 8, 8), (8, 8)]
try:
    badge_font = ttf("arialbd.ttf", 90)
except Exception:
    badge_font = ImageFont.load_default()
for (dx, dy), col, L in zip(positions, colors, letters):
    x0, y0 = cx + dx, cy + dy
    x1, y1 = x0 + s, y0 + s
    d.rectangle((x0, y0, x1, y1), fill=col)
    bb = d.textbbox((0, 0), L, font=badge_font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((x0 + (s - tw)/2 - bb[0], y0 + (s - th)/2 - bb[1] - 6), L, fill=WHITE, font=badge_font)

# Title "HOMO HOTEL" / "HAPPY HOUR"
title_font = ttf("arialbd.ttf", 96)
t1 = "HOMO HOTEL"
bb = d.textbbox((0, 0), t1, font=title_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 560), t1, fill=BLACK, font=title_font)
t2 = "HAPPY HOUR"
bb = d.textbbox((0, 0), t2, font=title_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 670), t2, fill=ORANGE, font=title_font)

# Thin divider under title
d.line((W/2 - 180, 790, W/2 + 180, 790), fill=ORANGE, width=4)

# Date
serif = ttf("georgiab.ttf", 62)
date_s = "Friday, May 1"
bb = d.textbbox((0, 0), date_s, font=serif)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 830), date_s, fill=BLACK, font=serif)

time_font = ttf("georgiab.ttf", 42)
time_s = "6:00 – 8:00 PM"
bb = d.textbbox((0, 0), time_s, font=time_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 910), time_s, fill=BLACK, font=time_font)

# Separator
d.line((W/2 - 220, 985, W/2 + 220, 985), fill=LIGHT, width=2)

# Venue - Hotel TBD
venue_font = ttf("arialbd.ttf", 52)
v = "Hotel TBD"
bb = d.textbbox((0, 0), v, font=venue_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 1005), v, fill=BLACK, font=venue_font)

sub_font = ttf("arial.ttf", 34)
sub = "Venue reveal coming soon"
bb = d.textbbox((0, 0), sub, font=sub_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 1075), sub, fill=GRAY, font=sub_font)

sub2 = "Follow @homohotelhappyhour for the announcement"
bb = d.textbbox((0, 0), sub2, font=sub_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], 1120), sub2, fill=GRAY, font=sub_font)

# Orange band - BENEFITTING
band_top, band_bot = 1185, 1360
d.rectangle((0, band_top, W, band_bot), fill=ORANGE)
ben_font = ttf("arialbd.ttf", 30)
ben = "BENEFITTING"
bb = d.textbbox((0, 0), ben, font=ben_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], band_top + 18), ben, fill=WHITE, font=ben_font)

charity_font = ttf("georgiab.ttf", 56)
ch = "Paws in Need"
bb = d.textbbox((0, 0), ch, font=charity_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], band_top + 68), ch, fill=WHITE, font=charity_font)

# Footer URL
foot_font = ttf("arial.ttf", 26)
foot = "homohotelhappyhour.com"
bb = d.textbbox((0, 0), foot, font=foot_font)
d.text(((W - (bb[2] - bb[0]))/2 - bb[0], band_bot + 14), foot, fill=GRAY, font=foot_font)

im.save(OUT, "PNG", optimize=True)
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
