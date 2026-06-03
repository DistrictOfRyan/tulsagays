"""Generate the branded 1200x630 Open Graph image used for event share previews.
One-time / idempotent asset. Output: docs/images/og-event.png

Art Deco look: near-black ground, berry (#9B1E5F) double-rule frame, white
serif wordmark, pride accent bar. Used as og:image on every /e/<slug>.html page
so a Facebook share shows a clean Tulsa Gays card (event title + description
ride in as text). Run once; re-run only to refresh the art.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (10, 10, 10)
BERRY = (155, 30, 95)
WHITE = (255, 255, 255)
MUTED = (170, 170, 170)
PRIDE = [(228, 3, 3), (255, 140, 0), (255, 237, 0), (0, 128, 38), (0, 77, 255), (117, 7, 135)]

FONTS = r"C:\Windows\Fonts"

def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

def center(draw, text, fnt, y, fill, tracking=0):
    if tracking:
        # manual letter-spacing
        widths = [draw.textbbox((0, 0), ch, font=fnt)[2] for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = (W - total) / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=fnt, fill=fill)
            x += w + tracking
    else:
        bb = draw.textbbox((0, 0), text, font=fnt)
        draw.text(((W - (bb[2] - bb[0])) / 2 - bb[0], y), text, font=fnt, fill=fill)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# Double-rule Art Deco frame
d.rectangle([30, 30, W - 31, H - 31], outline=BERRY, width=4)
d.rectangle([44, 44, W - 45, H - 45], outline=BERRY, width=1)

# Corner deco ticks
for cx, cy in [(44, 44), (W - 45, 44), (44, H - 45), (W - 45, H - 45)]:
    sx = 1 if cx < W / 2 else -1
    sy = 1 if cy < H / 2 else -1
    d.line([(cx, cy), (cx + sx * 26, cy)], fill=BERRY, width=3)
    d.line([(cx, cy), (cx, cy + sy * 26)], fill=BERRY, width=3)

# Eyebrow
center(d, "THE LGBTQ+ EVENT GUIDE", font("georgia.ttf", 30), 168, MUTED, tracking=8)

# Wordmark
center(d, "TULSA GAYS", font("georgiab.ttf", 132), 222, WHITE, tracking=4)

# Berry underline
d.rectangle([(W / 2 - 220, 392), (W / 2 + 220, 398)], fill=BERRY)

# Tagline
center(d, "Every LGBTQ+ event in Tulsa, every week.", font("georgiai.ttf", 38), 430, MUTED)

# Pride accent bar near the bottom
bar_w, bar_h, by = 360, 10, 510
seg = bar_w / len(PRIDE)
bx = (W - bar_w) / 2
for i, col in enumerate(PRIDE):
    d.rectangle([(bx + i * seg, by), (bx + (i + 1) * seg, by + bar_h)], fill=col)

# Domain
center(d, "tulsagays.com", font("georgia.ttf", 28), 548, BERRY, tracking=4)

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "images", "og-event.png")
img.save(out, "PNG")
print("wrote", out, img.size)
