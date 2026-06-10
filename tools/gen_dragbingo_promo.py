# -*- coding: utf-8 -*-
"""One-off promo graphic for Drag Bingo @ Bricktown Comedy Club, Sun 6/14/2026.
TulsaGays brand: near-black bg, neon pink accent, Sunday=sky blue. Outputs a
1080x1080 feed image and a 1080x1920 story image to data/posts/dragbingo-2026-06-14/.
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")
OUT = os.path.join(ROOT, "data", "posts", "dragbingo-2026-06-14")
os.makedirs(OUT, exist_ok=True)

BG        = (10, 10, 10)
PINK      = (255, 20, 147)     # #FF1493
WHITE     = (255, 255, 255)
SKY       = (128, 204, 255)    # #80CCFF Sunday
LGRAY     = (204, 204, 204)
GRAY      = (136, 136, 136)
DGRID     = (28, 28, 28)

WINF = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

def font(name, size):
    paths = {
        "cinzel":   os.path.join(FONTS, "Cinzel.ttf"),
        "playfair": os.path.join(FONTS, "PlayfairDisplay.ttf"),
        "poiret":   os.path.join(FONTS, "PoiretOne-Regular.ttf"),
        "segoe":    os.path.join(WINF, "segoeui.ttf"),
        "segoe-bold": os.path.join(WINF, "segoeuib.ttf"),
        "segoe-light": os.path.join(WINF, "segoeuil.ttf"),
        "segoe-semi": os.path.join(WINF, "seguisb.ttf"),
    }
    p = paths.get(name)
    if p and os.path.exists(p):
        return ImageFont.truetype(p, size)
    return ImageFont.truetype(os.path.join(WINF, "arial.ttf"), size)

def ctext(d, cx, y, text, fnt, fill, ls=0):
    if ls:
        text = (" " * 0).join(text)  # placeholder, handled by spacing arg below
    w = d.textlength(text, font=fnt)
    d.text((cx - w / 2, y), text, font=fnt, fill=fill)
    bbox = d.textbbox((0, 0), text, font=fnt)
    return bbox[3] - bbox[1]

def ctext_sp(d, cx, y, text, fnt, fill, tracking):
    """Centered text with letter tracking."""
    widths = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=fnt, fill=fill)
        x += w + tracking
    return fnt.size

def dot_grid(d, W, H):
    step = 70
    for gx in range(0, W + step, step):
        for gy in range(0, H + step, step):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=DGRID)

def bingo_row(d, cx, y, box, gap):
    letters = "BINGO"
    cols = [PINK, SKY, WHITE, SKY, PINK]
    total = len(letters) * box + (len(letters) - 1) * gap
    x = cx - total / 2
    f = font("segoe-bold", int(box * 0.6))
    for ch, col in zip(letters, cols):
        d.rounded_rectangle([x, y, x + box, y + box], radius=14, outline=col, width=5)
        w = d.textlength(ch, font=f)
        bb = d.textbbox((0, 0), ch, font=f)
        ch_h = bb[3] - bb[1]
        d.text((x + box / 2 - w / 2, y + box / 2 - ch_h / 2 - bb[1]), ch, font=f, fill=col)
        x += box + gap

def build(W, H, story=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    dot_grid(d, W, H)
    cx = W / 2

    # per-format vertical metrics (square is tight; story has room to breathe)
    if story:
        m = dict(top=170, wm=64, b_off=140, box=0.135, b_gap=110, t_size=120,
                 t_gap=132, h_off=170, h_size=50, div=110, d_off=64,
                 dt_size=62, dt_gap=96, st_size=46, st_off=80, v_size=40,
                 v_gap=64, p_gap=58, pill_h=96, pill_from_bottom=300)
    else:
        m = dict(top=46, wm=54, b_off=74, box=0.125, b_gap=44, t_size=92,
                 t_gap=104, h_off=120, h_size=42, div=64, d_off=44,
                 dt_size=52, dt_gap=76, st_size=40, st_off=62, v_size=34,
                 v_gap=50, p_gap=46, pill_h=84, pill_from_bottom=0)

    top = m["top"]
    fw = font("poiret", m["wm"])
    tw = d.textlength("TULSA ", font=fw)
    gw = d.textlength("GAYS", font=fw)
    startx = cx - (tw + gw) / 2
    d.text((startx, top), "TULSA ", font=fw, fill=WHITE)
    d.text((startx + tw, top), "GAYS", font=fw, fill=PINK)

    y = top + m["b_off"]
    box = int(W * m["box"])
    bingo_row(d, cx, y, box=box, gap=int(W * 0.025))

    y += box + m["b_gap"]
    ft = font("cinzel", m["t_size"])
    ctext_sp(d, cx, y, "DRAG", ft, WHITE, 6)
    y += m["t_gap"]
    ctext_sp(d, cx, y, "BINGO", ft, PINK, 6)

    y += m["h_off"]
    fh = font("playfair", m["h_size"])
    ctext(d, cx, y, "hosted by Porsche Lynn", fh, LGRAY)

    y += m["div"]
    d.line([(cx - 180, y), (cx + 180, y)], fill=PINK, width=3)
    y += m["d_off"]

    fd = font("segoe-bold", m["dt_size"])
    ctext_sp(d, cx, y, "SUNDAY  JUNE 14", fd, SKY, 2)
    y += m["dt_gap"]
    ft2 = font("segoe-semi", m["st_size"])
    ctext(d, cx, y, "Doors 2 PM  -  Show 3 PM", ft2, WHITE)
    y += m["st_off"]
    fv = font("segoe", m["v_size"])
    ctext(d, cx, y, "Bricktown Comedy Club  -  Tulsa", fv, LGRAY)
    y += m["v_gap"]
    ctext(d, cx, y, "5982 S Yale Ave   -   18+   -   $15", fv, GRAY)

    # ticket CTA pill
    if story:
        by = H - m["pill_from_bottom"]
    else:
        by = y + m["p_gap"] + 38
    pill_w, pill_h = int(W * 0.78), m["pill_h"]
    d.rounded_rectangle([cx - pill_w / 2, by, cx + pill_w / 2, by + pill_h], radius=pill_h // 2, fill=PINK)
    fc = font("segoe-bold", 42)
    cta = "TICKETS  -  bricktowntulsa.com"
    w = d.textlength(cta, font=fc)
    bb = d.textbbox((0, 0), cta, font=fc)
    d.text((cx - w / 2, by + pill_h / 2 - (bb[3] - bb[1]) / 2 - bb[1]), cta, font=fc, fill=BG)

    return img

for name, (W, H, story) in {
    "dragbingo_feed_1080.png": (1080, 1080, False),
    "dragbingo_story_1080x1920.png": (1080, 1920, True),
}.items():
    build(W, H, story).save(os.path.join(OUT, name), "PNG")
    print("wrote", os.path.join(OUT, name))
