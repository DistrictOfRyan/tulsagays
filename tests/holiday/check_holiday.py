"""Acceptance checks for the holiday theme layer (William 2026-11-18)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from PIL import Image
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # captions carry emoji
OUT =os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
def side_ink(path):
    im = Image.open(path).convert("RGB"); w, h = im.size
    n = 0
    # the bands beside the TULSA/GAYS wordmark (y ~150-335); the divider, the tagline
    # and the Event of the Week box all sit outside this window
    for x in list(range(40, 250, 3)) + list(range(w - 250, w - 40, 3)):
        for y in range(150, 340, 3):
            r, g, b = im.getpixel((x, y))
            if r + g + b > 120: n += 1
    return n
mode = sys.argv[1]
if mode == "dec_motif":
    n = side_ink(os.path.join(OUT, "dec", "cover.png")); print("dec side ink", n); sys.exit(0 if n > 40 else 1)
if mode == "plain_clean":
    n = side_ink(os.path.join(OUT, "sep", "cover.png")); print("sep side ink", n); sys.exit(0 if n == 0 else 1)
if mode == "solemn":
    n = side_ink(os.path.join(OUT, "tdor", "cover.png")); print("tdor side ink", n); sys.exit(0 if n == 0 else 1)
if mode == "layout":
    bad = []
    for m in ("dec", "nov", "oct", "feb", "jun", "jan", "sep", "tdor", "thx", "xmas", "jul"):
        p = os.path.join(OUT, m, "layout_report.json")
        if not os.path.exists(p): bad.append(m + ":missing"); continue
        w = json.load(open(p)).get("warnings", [])
        if w: bad.append(f"{m}:{w}")
    print("layout", bad or "clean"); sys.exit(0 if not bad else 1)
if mode == "caption":
    from content import holiday_theme as ht
    import datetime as dt
    t = ht.theme_for(dt.date(2026, 12, 9))
    cap = ht.apply_caption_flourish("Tulsa is busy this week.\n\nFull list at tulsagays.com\n\n#tulsagays", t)
    ok = t["emoji"] in cap.splitlines()[0] and "—" not in cap and "tulsagays.com" in cap
    plain = ht.apply_caption_flourish("x\n\ntulsagays.com", ht.theme_for(dt.date(2026, 9, 9)))
    print(cap.splitlines()[0], "| plain:", plain.splitlines()[0]); sys.exit(0 if ok and plain.startswith("x") else 1)
