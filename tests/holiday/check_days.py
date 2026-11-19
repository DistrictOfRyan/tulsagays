"""Acceptance checks for the holiday-DAY layer (William 2026-11-18: "just for the
holidays, whenever they come up ... simple little classy details ... festive but not
over the top").

  labels          holiday dates resolve to names; Thanksgiving/Christmas/New Year's/
                  Juneteenth cross-checked LIVE against date.nager.at, Hanukkah against
                  hebcal.com, Easter against dateutil
  header          the 11/26 Thursday slide carries THANKSGIVING on its date line, and
                  every pixel below the header is identical to the plain render
  solemn_day      TDoR (11/20) and World AIDS Day (12/1) slides get no corner motif
  july4           the Fourth of July week is themed, the rest of July is not
  plain_identical a non-holiday week renders byte-identical with the layer on vs off
  captions        weekend + Wednesday captions carry the seasonal touch only when due
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from content import holiday_theme as ht  # noqa: E402

BG = (10, 10, 10)
EV = lambda d, name="Drag Brunch at Elote": {  # noqa: E731
    "name": name, "venue": "Elote Cafe", "time": "11:00 AM", "date": d,
    "description": "Mimosas, sequins and a lip sync you will talk about all week.",
    "lgbtq_relevant": True}


def _env(date_str=None, off=False):
    os.environ.pop("TULSAGAYS_HOLIDAY_DATE", None)
    os.environ.pop("TULSAGAYS_HOLIDAY", None)
    if date_str:
        os.environ["TULSAGAYS_HOLIDAY_DATE"] = date_str
    if off:
        os.environ["TULSAGAYS_HOLIDAY"] = "off"


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "holiday-check/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _fail(msgs):
    print("FAIL:", *msgs, sep="\n  ")
    sys.exit(1)


def labels():
    _env()
    bad = []
    expect = {
        date(2026, 11, 26): "Thanksgiving", date(2027, 11, 25): "Thanksgiving",
        date(2026, 12, 24): "Christmas Eve", date(2026, 12, 25): "Christmas",
        date(2027, 12, 24): "Christmas Eve & Hanukkah begins",
        date(2026, 12, 31): "New Year's Eve", date(2027, 1, 1): "New Year's Day",
        date(2027, 7, 4): "Fourth of July", date(2026, 10, 31): "Halloween",
        date(2026, 10, 11): "National Coming Out Day", date(2027, 3, 28): "Easter",
        date(2027, 2, 9): "Mardi Gras", date(2027, 2, 14): "Valentine's Day",
        date(2026, 11, 20): "Trans Day of Remembrance", date(2026, 12, 1): "World AIDS Day",
        date(2026, 9, 16): None, date(2026, 11, 27): None,
    }
    for d, want in expect.items():
        got = ht.day_label(d)
        if got != want:
            bad.append(f"{d}: want {want!r} got {got!r}")
    # Outside judge 1: date.nager.at (US public holidays) for the fixed-rule days.
    nager_map = {"Thanksgiving Day": "Thanksgiving", "Christmas Day": "Christmas",
                 "New Year's Day": "New Year's Day",
                 "Juneteenth National Independence Day": "Juneteenth"}
    for y in (2026, 2027, 2028):
        for h in _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{y}/US"):
            ours = nager_map.get(h["name"])
            if not ours:
                continue
            d = date.fromisoformat(h["date"])
            # nager lists the OBSERVED weekday for fixed dates that land on a weekend;
            # only compare when it is the actual date.
            if h["name"] != "Thanksgiving Day" and (d.month, d.day) not in ((12, 25), (1, 1), (6, 19)):
                continue
            lab = ht.day_label(d) or ""
            if ours not in lab:
                bad.append(f"nager {h['date']} {h['name']}: our label {lab!r}")
    # Outside judge 2: hebcal.com, first Chanukah candle.
    for y in range(2026, 2031):
        items = _get_json("https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off&mod=off"
                          f"&nx=off&ss=off&mf=off&c=off&year={y}")["items"]
        for it in items:
            if it["title"] == "Chanukah: 1 Candle":
                d = date.fromisoformat(it["date"][:10])
                if "Hanukkah begins" not in (ht.day_label(d) or ""):
                    bad.append(f"hebcal {d}: first candle not labelled")
    # Easter algorithm vs dateutil, 2020-2045.
    from dateutil.easter import easter
    for y in range(2020, 2046):
        if ht._easter(y) != easter(y):
            bad.append(f"easter {y}: {ht._easter(y)} vs {easter(y)}")
    _env(off=True)
    if ht.day_label(date(2026, 11, 26)) is not None:
        bad.append("TULSAGAYS_HOLIDAY=off still labels Thanksgiving")
    _env()
    if bad:
        _fail(bad)
    print(f"labels ok: {len(expect)} fixed cases, nager + hebcal + dateutil agree")


def _pink(px):
    r, g, b = px
    return r > 200 and g < 90 and b > 100


def _render_day(day_name, date_str, off=False, events=None):
    _env(date_str, off)
    from content.image_maker import make_day_slide
    mon = date.fromisoformat(date_str) - timedelta(days=date.fromisoformat(date_str).weekday())
    idx = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(day_name)
    d = (mon + timedelta(days=idx)).isoformat()
    evs = events or [EV(d), EV(d, "Queer Trivia Night"), EV(d, "Gaymer Night at the Eagle")]
    img = make_day_slide(day_name, evs).convert("RGB")
    _env()
    return img


def header():
    on = _render_day("Thursday", "2026-11-26")
    off = _render_day("Thursday", "2026-11-26", off=True)
    W, H = on.size
    band = [(x, y) for x in range(130, W - 130, 2) for y in range(40, 140, 2)]  # clear of corners
    # pink pixels the holiday layer ADDED on the date line (the day name's own accent
    # colour is pink on some days, so compare against the same slide with the layer off)
    pink_on = sum(_pink(on.getpixel(p)) and not _pink(off.getpixel(p)) for p in band)
    pink_off = sum(on.getpixel(p) != off.getpixel(p) for p in band if not _pink(on.getpixel(p)))
    body_same = on.crop((0, 140, W, H)).tobytes() == off.crop((0, 140, W, H)).tobytes()
    wed_on = _render_day("Wednesday", "2026-11-26")
    wed_off = _render_day("Wednesday", "2026-11-26", off=True)
    pink_wed = sum(wed_on.getpixel(p) != wed_off.getpixel(p) for p in band)
    print(f"header: pink px added by THANKSGIVING={pink_on}, non-pink px changed={pink_off} | "
          f"Wednesday (no holiday) header px changed={pink_wed}"
          f" | body below header identical={body_same}")
    # (non-pink changes are the date itself re-centring to make room: expected)
    if not (pink_on > 30 and pink_wed == 0 and body_same):
        _fail(["thanksgiving label missing, leaking, or it moved the layout"])
    os.makedirs(os.path.join(os.path.dirname(__file__), "out", "days"), exist_ok=True)
    on.save(os.path.join(os.path.dirname(__file__), "out", "days", "thanksgiving_thursday.png"))


def _corner_ink(img):
    return sum(img.getpixel((x, y)) != BG for x in range(34, 118, 2) for y in range(22, 106, 2))


def solemn_day():
    cases = [("Friday", "2026-11-18", 0, "TDoR 11/20"), ("Thursday", "2026-11-18", 1, "11/19"),
             ("Tuesday", "2026-12-02", 0, "World AIDS Day 12/1"), ("Wednesday", "2026-12-02", 1, "12/2")]
    bad = []
    # Event-level memorial detection: real listings, both directions.
    must = ["Trans Day of Remembrance Event", "Candlelight Vigil for Club Q",
            "What Will I Become? Transgender Day of Remembrance and Resilience Screening",
            "Memorial Service for a Tulsa Queen"]
    never = ["First Thursday Art Show (Allie Jensen Memorial Art Gallery)",
             "Candlelight: A Tribute to Taylor Swift", "Memorial Day Pool Party",
             "Drag Brunch at Elote"]
    bad += [f"missed memorial: {n}" for n in must if not ht.is_solemn({"name": n})]
    bad += [f"false memorial: {n}" for n in never if ht.is_solemn({"name": n})]
    out = os.path.join(os.path.dirname(__file__), "out", "days")
    os.makedirs(out, exist_ok=True)
    for day, ref, want_ink, what in cases:
        img = _render_day(day, ref)
        ink = _corner_ink(img)
        print(f"solemn_day: {what} ({day}) corner ink={ink}")
        if (ink > 0) != bool(want_ink):
            bad.append(f"{what}: corner ink {ink}, want {'some' if want_ink else 'none'}")
        img.save(os.path.join(out, f"{ref}_{day.lower()}.png"))
    if bad:
        _fail(bad)


def july4():
    _env()
    k = lambda d: (ht.theme_for(d) or {}).get("key")  # noqa: E731
    cases = {date(2027, 7, 1): "independence_day", date(2026, 7, 2): "independence_day",
             date(2027, 7, 15): None, date(2026, 7, 9): None, date(2026, 6, 25): "pride",
             date(2026, 8, 13): None}
    bad = [f"{d}: want {w} got {k(d)}" for d, w in cases.items() if k(d) != w]
    from content.image_maker import make_cover_slide
    _env("2027-07-01")
    img = make_cover_slide("weekday", "Jun 28 - Jul 4", featured_event=EV("2027-07-03")).convert("RGB")
    _env()
    w = img.size[0]
    ink = sum(sum(img.getpixel((x, y))) > 120 for x in list(range(40, 250, 3)) + list(range(w - 250, w - 40, 3))
              for y in range(150, 340, 3))
    out = os.path.join(os.path.dirname(__file__), "out", "days")
    os.makedirs(out, exist_ok=True)
    img.save(os.path.join(out, "july4_cover.png"))
    print(f"july4: themes {[(str(d), k(d)) for d in cases]} | cover side ink={ink}")
    if ink <= 40:
        bad.append(f"july4 cover has no firework motif (ink {ink})")
    if bad:
        _fail(bad)


def plain_identical():
    from content.image_maker import create_carousel
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    bad = []
    for ref in ("2026-09-16", "2027-03-03", "2027-08-11"):
        mon = date.fromisoformat(ref) - timedelta(days=date.fromisoformat(ref).weekday())
        by_day = {d: [EV((mon + timedelta(days=i)).isoformat()),
                      EV((mon + timedelta(days=i)).isoformat(), "Queer Trivia Night"),
                      EV((mon + timedelta(days=i)).isoformat(), "Karaoke at YBR")]
                  for i, d in enumerate(days)}
        renders = []
        for off in (False, True):
            _env(ref, off)
            slides = create_carousel({}, "weekday", "plain week", events_by_day=by_day,
                                     featured_event=by_day["Friday"][0])
            renders.append([s.convert("RGB").tobytes() for s in slides])
        _env()
        same = len(renders[0]) == len(renders[1]) and all(a == b for a, b in zip(*renders))
        print(f"plain_identical: week of {mon} -> {len(renders[0])} slides, on == off: {same}")
        if not same:
            bad.append(f"week of {mon} differs with the holiday layer on")
    if bad:
        _fail(bad)


def captions():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from weekend_carousel import build_caption
    bad = []

    def sel(f, s, u, evs=None):
        return {"friday": f, "saturday": s, "sunday": u, "weeklies": [], "thin": False,
                "headlines": {f: evs or [EV(f)], s: [EV(s, "Queer Costume Ball")], u: [EV(u, "Sunday Showdown")]}}

    _env()
    hal = build_caption(sel("2026-10-30", "2026-10-31", "2026-11-01"))
    sep = build_caption(sel("2026-09-18", "2026-09-19", "2026-09-20"))
    vig = build_caption(sel("2026-11-20", "2026-11-21", "2026-11-22",
                            [EV("2026-11-20", "Trans Day of Remembrance Vigil")]))
    l1 = lambda c: c.splitlines()[0]  # noqa: E731
    print("weekend Halloween:", l1(hal), "|", hal.splitlines()[1])
    print("weekend September:", l1(sep))
    print("weekend TDoR vigil:", l1(vig))
    if not (l1(hal).startswith("🦇") and "Halloween is Saturday." in hal):
        bad.append("Halloween weekend caption missing emoji or note")
    if l1(sep) != "THIS WEEKEND IN TULSA" or "is Saturday." in sep or "is Friday." in sep:
        bad.append("plain September weekend caption was touched")
    if l1(vig) != "THIS WEEKEND IN TULSA" or "Remembrance is" in vig:
        bad.append("memorial weekend caption got a flourish")
    if "—" in hal or "tulsagays.com" not in hal:
        bad.append("Halloween caption broke the em-dash / URL rules")

    # Wednesday last-minute: exercise the same call the script makes, then prove it is wired.
    base = "Just added since Monday. Mid-week intel only.\n• X, Wed 8 PM at Y\n\nFull week at tulsagays.com."
    _env("2026-11-25")
    wed = ht.season_caption(base, [EV("2026-11-25")],
                            note_dates=[date(2026, 11, 25) + timedelta(days=i) for i in range(5)])
    _env("2026-09-16")
    wed_plain = ht.season_caption(base, [EV("2026-09-16")],
                                  note_dates=[date(2026, 9, 16) + timedelta(days=i) for i in range(5)])
    _env()
    print("wednesday Thanksgiving week:", wed.splitlines()[0], "|", wed.splitlines()[1])
    print("wednesday September:", wed_plain.splitlines()[0])
    if not (wed.startswith("🍂") and "Thanksgiving is Thursday." in wed):
        bad.append("Wednesday Thanksgiving-week caption missing emoji or note")
    if wed_plain != base:
        bad.append("Wednesday plain-week caption was touched")
    src = open(os.path.join(ROOT, "tools", "run_wednesday_lastminute.py"), encoding="utf-8").read()
    if "_ht.season_caption(" not in src:
        bad.append("run_wednesday_lastminute.py does not call season_caption")
    if bad:
        _fail(bad)


if __name__ == "__main__":
    {"labels": labels, "header": header, "solemn_day": solemn_day, "july4": july4,
     "plain_identical": plain_identical, "captions": captions}[sys.argv[1]]()
