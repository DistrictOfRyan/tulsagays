"""Sponsor pipeline tracker for TulsaGays (Rung 3: the roster + MRR).

Turns the prospect list into a managed sales pipeline. Tracks each prospect
through stages, computes recurring revenue, and flags who needs follow-up so a
sponsor relationship never silently lapses (the #1 way small ad businesses leak
money).

Data: data/sponsors.json -- a list of:
    {"name","tier","monthly_amount","stage","last_contact":"YYYY-MM-DD",
     "next_action","notes"}
Stages: prospect -> contacted -> negotiating -> active -> lapsed

`report()` prints MRR, pipeline value, and a follow-up list (contacted/
negotiating with no contact in >FOLLOWUP_DAYS). `--selftest` proves the math.
"""

import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SPONSORS_FILE = os.path.join(config.DATA_DIR, "sponsors.json")
FOLLOWUP_DAYS = 7
STAGES = ["prospect", "contacted", "negotiating", "active", "lapsed"]


def load():
    if os.path.exists(SPONSORS_FILE):
        try:
            d = json.load(open(SPONSORS_FILE, encoding="utf-8"))
            return d.get("sponsors", d) if isinstance(d, dict) else d
        except Exception:
            return []
    return []


def save(sponsors):
    config.ensure_dirs()
    json.dump({"sponsors": sponsors}, open(SPONSORS_FILE, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)


def _age_days(date_str, today):
    try:
        return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return 0


def summarize(sponsors, today):
    active = [s for s in sponsors if s.get("stage") == "active"]
    mrr = sum(float(s.get("monthly_amount", 0)) for s in active)
    pipeline = [s for s in sponsors if s.get("stage") in ("contacted", "negotiating")]
    pipeline_value = sum(float(s.get("monthly_amount", 0)) for s in pipeline)
    needs_followup = [s for s in pipeline
                      if _age_days(s.get("last_contact", today), today) >= FOLLOWUP_DAYS]
    by_stage = {st: sum(1 for s in sponsors if s.get("stage") == st) for st in STAGES}
    return {"mrr": round(mrr, 2), "active": len(active),
            "pipeline_count": len(pipeline), "pipeline_value": round(pipeline_value, 2),
            "needs_followup": needs_followup, "by_stage": by_stage, "annual": round(mrr * 12, 2)}


def report():
    sponsors = load()
    today = os.environ.get("SOURCE_GROWTH_DATE") or datetime.now().strftime("%Y-%m-%d")
    s = summarize(sponsors, today)
    print(f"=== TulsaGays sponsor pipeline ({today}) ===")
    print(f"  MRR: ${s['mrr']}/mo  (${s['annual']}/yr)  from {s['active']} active sponsor(s)")
    print(f"  Pipeline: {s['pipeline_count']} in play, ${s['pipeline_value']}/mo potential")
    print(f"  Stages: " + ", ".join(f"{k}={v}" for k, v in s['by_stage'].items()))
    if s["needs_followup"]:
        print(f"\n  FOLLOW UP ({FOLLOWUP_DAYS}+ days quiet):")
        for f in s["needs_followup"]:
            print(f"    - {f['name']} ({f['stage']}, last {f.get('last_contact','?')}) "
                  f"-> {f.get('next_action','follow up')}")
    return s


def _selftest():
    today = "2026-06-04"
    sponsors = [
        {"name": "Gray Matters", "tier": "Partner", "monthly_amount": 65, "stage": "active", "last_contact": "2026-06-01"},
        {"name": "Il Seme", "tier": "Community", "monthly_amount": 35, "stage": "active", "last_contact": "2026-06-02"},
        {"name": "Mark Reed", "tier": "Partner", "monthly_amount": 65, "stage": "negotiating", "last_contact": "2026-05-20", "next_action": "send rate card"},
        {"name": "YBR", "tier": "Partner", "monthly_amount": 65, "stage": "contacted", "last_contact": "2026-06-03"},
        {"name": "Old Sponsor", "tier": "Community", "monthly_amount": 35, "stage": "lapsed", "last_contact": "2026-03-01"},
    ]
    s = summarize(sponsors, today)
    assert s["mrr"] == 100.0, s          # 65 + 35 active
    assert s["active"] == 2, s
    assert s["annual"] == 1200.0, s
    assert s["pipeline_count"] == 2, s   # negotiating + contacted
    # Mark Reed last_contact 5/20 -> >7d quiet -> follow up; YBR 6/03 -> fresh
    names = [f["name"] for f in s["needs_followup"]]
    assert names == ["Mark Reed"], names
    print(f"sponsor_pipeline selftest: passed (MRR ${s['mrr']}, {s['active']} active, "
          f"follow-up flagged: {names})")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seed-prospects", action="store_true",
                    help="seed sponsors.json from the prospect list (stage=prospect)")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    if args.seed_prospects and not load():
        seed = [
            {"name": n, "tier": t, "monthly_amount": a, "stage": "prospect",
             "last_contact": "", "next_action": "research contact + pitch", "notes": ""}
            for n, t, a in [
                ("Gray Matters Counseling", "Partner", 65), ("Compass Therapy", "Partner", 65),
                ("Mark Reed Realtor", "Partner", 65), ("Tina Gay Century21", "Community", 35),
                ("Il Seme", "Community", 35), ("At the Donut Hole", "Community", 35),
                ("American Solera", "Community", 35), ("Tonsorial Barbershop", "Community", 35),
                ("Tulsa Eagle", "Partner", 65), ("YBR", "Partner", 65), ("Club Majestic", "Partner", 65),
            ]
        ]
        save(seed)
        print(f"seeded {len(seed)} prospects -> {SPONSORS_FILE}")
    report()
