"""Render one preview deck per holiday month (+ September as the control, + the real
Trans Day of Remembrance lead as the memorial check) from this week's real events.
Output: tests/holiday/out/<deck>/slide_NN.png + cover.png + layout_report.json.
Preview only: never posted."""
import json
import os
import re
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from content.image_maker import create_carousel, save_carousel
from content import holiday_theme as ht

OUT = os.path.join(ROOT, "tests", "holiday", "out")
WEEK = sys.argv[1] if len(sys.argv) > 1 else "2026-W47"
evs = json.load(open(os.path.join(ROOT, "data", "events", f"{WEEK}_all.json"), encoding="utf-8"))
evs = evs.get("events", evs) if isinstance(evs, dict) else evs
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
by_day = {d: [] for d in days}
for e in evs:
    try:
        d = datetime.strptime(e.get("date", ""), "%Y-%m-%d").strftime("%A")
    except ValueError:
        continue
    if e.get("never_feature") or e.get("hidden"):
        continue
    by_day[d].append(e)
for d in days:
    by_day[d].sort(key=lambda e: (0 if e.get("featured") else 1,
                                  0 if e.get("lgbtq_relevant") else 1, e.get("priority", 9)))

real_eotw = (next((e for e in evs if e.get("eotw") or e.get("is_eotw")), None)
             or next((e for d in days for e in by_day[d][:1]), None))
# Month decks need a non-memorial lead to show the motif; "tdor" keeps the real lead.
QUEER = re.compile(r"\b(drag|queer|pride|gay)\b", re.I)
eotw = (next((e for d in days for e in by_day[d]
              if QUEER.search(e.get("name", "")) and not ht.is_solemn(e)), None)
        or next((e for d in days for e in by_day[d]
                 if e.get("lgbtq_relevant") and not ht.is_solemn(e)), real_eotw))

DECKS = {"dec": "2026-12-09", "nov": "2026-11-18", "oct": "2026-10-14", "feb": "2027-02-10",
         "jun": "2027-06-09", "jan": "2027-01-06", "sep": "2026-09-16", "tdor": "2026-11-18",
         # holiday-DAY decks: the holiday's own slide carries its name
         "thx": "2026-11-25", "xmas": "2026-12-23", "jul": "2027-07-01"}
for m, d in DECKS.items():
    os.environ["TULSAGAYS_HOLIDAY_DATE"] = d
    out = os.path.join(OUT, m)
    shutil.rmtree(out, ignore_errors=True)
    # "tdor" leads with the week's real memorial event (the Trans Day of Remembrance
    # listing); W47's eotw flag was cleared by a later refresh, so do not rely on it.
    tdor_lead = next((e for dd in days for e in by_day[dd] if ht.is_solemn(e)), real_eotw)
    lead = tdor_lead if m == "tdor" else eotw
    from datetime import timedelta
    _mon = datetime.strptime(d, "%Y-%m-%d").date()
    _mon -= timedelta(days=_mon.weekday())
    _rng = f"{_mon:%b} {_mon.day} - {(_mon + timedelta(days=6)):%b} {(_mon + timedelta(days=6)).day}"
    slides = create_carousel({}, "weekday", _rng, events_by_day=by_day, featured_event=lead)
    paths = save_carousel(slides, out)
    shutil.copy(paths[0], os.path.join(out, "cover.png"))
    print(m, d, len(paths), "slides | lead:", (lead or {}).get("name", "")[:50],
          "| solemn:", ht.is_solemn(lead))
