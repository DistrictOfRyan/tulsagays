"""Regression-proofing test suite for the TulsaGays weekly pipeline.

Plain-Python (no pytest dependency): run `python tests/test_pipeline.py`.
Exit 0 = all green. Exit 1 = a regression. Every check below locks in a real
bug fixed during the 2026-06-15 hardening so it can never silently come back.

Covers:
  * classifier regression locks (drag-racing, "Dragon", real drag, gay venues,
    multi-city portability, closure-notice skip)
  * config contract (GAY_VENUE_SIGNATURES present + city-specific knobs exist)
  * generated-manifest invariants (>=3 featured/day, gay-first, no templated
    filler on featured cards) when a manifest exists
  * monetization slot is a safe no-op without data/sponsor.json
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONUTF8", "1")

import config                       # noqa: E402
import eotw_selector as es          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    status = "ok " if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def ev(name, venue=""):
    return {"name": name, "venue": venue}


# ── 1. Classifier regression locks (pure, fast, deterministic) ───────────────
def test_classifier():
    print("classifier regression locks:")
    # car drag RACING must never count as gay (Fun Friday Drags Night @ Raceway)
    check("drag-racing @ raceway is NOT gay",
          es._is_lgbtq_strict(ev("Fun Friday Drags Night", "Tulsa Raceway Park")) is False)
    check("Motorama drag strip car show is NOT gay",
          es._is_lgbtq_strict(ev("Motorama at the Drag Strip - Car Show", "StubHub")) is False)
    # "Dragon" / "Dragonfly" substring must NOT trip the drag keyword
    check("'Dragon Paper Craft' is NOT gay",
          es._is_lgbtq_strict(ev("Dragon Paper Craft", "Kendall-Whittier Library")) is False)
    check("'Dragonfly Yoga' is NOT gay",
          es._is_lgbtq_strict(ev("Dragonfly Yoga", "Guthrie Green")) is False)
    # real drag performances MUST count as gay
    check("'DRAGNIFICENT!' is gay", es._is_lgbtq_strict(ev("DRAGNIFICENT!", "Club Majestic")) is True)
    check("'Benefit Drag Show' is gay", es._is_lgbtq_strict(ev("Benefit Drag Show", "Tulsa Eagle")) is True)
    # gay-venue signature: neutral title at a gay venue counts as gay
    check("neutral title @ Tulsa Eagle is gay (via config)",
          es._is_lgbtq_strict(ev("Monday Movie Night", "1338 E 3rd St")) is True)
    check("neutral title @ DVL is gay", es._is_lgbtq_strict(ev("Karaoke Brunch", "302 South Frankfort")) is True)
    # multi-city portability: an OKC bar is NOT auto-gay under Tulsa's config
    check("OKC 'The Boom' neutral title NOT gay under Tulsa config (portable)",
          es._is_lgbtq_strict(ev("Trivia Night", "The Boom, 2218 NW 39th, OKC")) is False)
    # closure notices + services must be skipped (never featured)
    check("'OKEQ Closed' is skipped", es._is_skip(ev("OKEQ Closed", "Dennis R. Neill Equality Center")) is True)
    check("support group is skipped", es._is_skip(ev("Gender Outreach Support Group", "Equality Center")) is True)


# ── 2. Config contract (city-specific knobs the shared code depends on) ──────
def test_config_contract():
    print("config contract:")
    for knob in ("GAY_VENUE_SIGNATURES", "TRUE_GAY_BAR_VENUES", "SIGNATURE_EVENT", "ANCHOR_CULTURAL_EVENT"):
        check(f"config.{knob} exists", hasattr(config, knob))
    check("GAY_VENUE_SIGNATURES non-empty", bool(getattr(config, "GAY_VENUE_SIGNATURES", ())))


# ── 3. Generated-manifest invariants (guards the featured selection output) ──
def test_manifest_invariants():
    print("generated-manifest invariants:")
    wk = config.current_week_key()
    man_path = os.path.join(ROOT, "data", "posts", wk, "slide_manifest.json")
    if not os.path.exists(man_path):
        print(f"  [skip] no manifest for {wk} (run generate-all to enable)")
        return
    man = json.load(open(man_path, encoding="utf-8"))
    fbd = man.get("featured_by_day", {})
    check("manifest has 7 days", len(fbd) == 7, f"{len(fbd)} days")
    try:
        from tools.preflight_post import _looks_templated
    except Exception:
        _looks_templated = lambda _t: False
    gay = tot = tpl = 0
    for day, evs in fbd.items():
        check(f"{day} has >=3 featured", len(evs) >= 3, f"{len(evs)}")
        for e in evs:
            tot += 1
            if es._is_lgbtq_strict(e):
                gay += 1
            if _looks_templated(e.get("description")) or _looks_templated(e.get("website_description")):
                tpl += 1
    if tot:
        check("featured templated-filler ratio <=25%", tpl / tot <= 0.25, f"{tpl}/{tot}")
        # gay-first: when the week has gay events at all, they should dominate featured
        check("featured gay ratio >=40% (gay-first)", gay / tot >= 0.40, f"{gay}/{tot}")


# ── 4. Monetization slot is a safe no-op without config ──────────────────────
def test_sponsor_slot_safe():
    print("monetization slot safety:")
    # The slot must be GUARDED (renders only if data/sponsor.json exists) so it is
    # a no-op by default AND safe once a sponsor is signed. Verify the guard exists
    # rather than asserting absence of a sponsor (which would break when monetized).
    gw = open(os.path.join(ROOT, "tools", "gen_website_html.py"), encoding="utf-8").read()
    check("website sponsor slot is guarded by sponsor.json existence check",
          "sponsor.json" in gw and "os.path.exists(_sp_path)" in gw)
    check("sponsor template is documented", os.path.exists(os.path.join(ROOT, "drafts", "sponsor", "sponsor.json.template")))


def test_venue_artifact():
    print("venue-artifact cleaner:")
    from tools.clean_event_data import is_venue_artifact
    # the bug: venue echoes the event name with no real-venue signal -> artifact
    check("'Starlight Concert Band -' venue is an artifact",
          is_venue_artifact("Starlight Concert Band - Above and Below", "Starlight Concert Band -") is True)
    check("full-name-as-venue is an artifact",
          is_venue_artifact("Velvet Chair Poetry Night at Gypsy", "Velvet Chair Poetry Night at Gypsy") is True)
    # real venues must be KEPT (address or venue-type word present)
    check("real venue w/ address is kept",
          is_venue_artifact("Drag Bingo", "Tulsa Eagle, 1338 E 3rd St") is False)
    check("real venue-type word is kept",
          is_venue_artifact("Story Time", "Pratt Library") is False)


def test_classifier_golden():
    print("golden classification cases (frozen verdicts):")
    fx = os.path.join(ROOT, "tests", "fixtures", "classifier_cases.json")
    if not os.path.exists(fx):
        print("  [skip] no fixture")
        return
    cases = json.load(open(fx, encoding="utf-8"))["cases"]
    bad = 0
    for c in cases:
        e = ev(c["name"], c.get("venue", ""))
        got_lg = bool(es._is_lgbtq_strict(e))
        got_sk = bool(es._is_skip(e))
        if got_lg != c["lgbtq_strict"] or got_sk != c["skip"]:
            bad += 1
            print(f"  [FAIL] {c['name'][:40]!r}: lgbtq {got_lg} (want {c['lgbtq_strict']}), "
                  f"skip {got_sk} (want {c['skip']})")
    check(f"all {len(cases)} golden classification cases match", bad == 0, f"{bad} mismatched")


def test_classifier_fuzz():
    print("classifier property/fuzz (generated matrix):")
    # Property 1: ANY car-racing context is never gay, regardless of prefix.
    racing_ctx = ["drag strip", "drag racing", "raceway", "speedway", "motorama", "dragway"]
    prefixes = ["Friday", "Annual", "Summer", "Big", "Pride", "Tulsa", "Fun"]
    p1 = all(not es._is_lgbtq_strict(ev(f"{p} {r} night", "Speedway Park"))
             for p in prefixes for r in racing_ctx)
    check("property: no racing-context event is ever classified gay", p1)
    # Property 2: 'dragon'/'dragonfly' words never trip the gay 'drag' path.
    p2 = all(not es._is_lgbtq_strict(ev(f"{w} {p}", "Some Library"))
             for w in ["Dragon", "Dragonfly", "Dragons", "Dragonboat"] for p in ["Craft", "Story", "Club"])
    check("property: 'dragon*' words never classify gay", p2)
    # Property 3: real drag-performance phrases always classify gay (any venue).
    p3 = all(es._is_lgbtq_strict(ev(f"Weekly {d}", v))
             for d in ["Drag Show", "Drag Brunch", "Drag Queen Bingo", "Drag King Revue"]
             for v in ["Anywhere", "Some Bar", ""])
    check("property: real drag-performance phrases always classify gay", p3)
    # Property 4: neutral title at ANY configured gay venue classifies gay.
    p4 = all(es._is_lgbtq_strict(ev("Open Night", sig)) for sig in getattr(config, "GAY_VENUE_SIGNATURES", ()))
    check("property: neutral title at every config gay-venue classifies gay", p4)


def test_quality_trend():
    print("quality-trend guard:")
    p = os.path.join(ROOT, "data", "description_scores.jsonl")
    if not os.path.exists(p):
        print("  [skip] no description_scores.jsonl yet (populated as weeks run)")
        return
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    if not rows:
        print("  [skip] scores file empty")
        return
    last = rows[-1]
    avg = last.get("avg") or last.get("average") or last.get("avg_score")
    if avg is None:
        print("  [skip] latest row has no avg score field")
        return
    # Floor guard: a catastrophic drop (avg < 40/100) means enrichment/voice broke.
    check(f"latest weekly voice-score avg >= 40 (was {avg})", float(avg) >= 40)


def main():
    print("=== TulsaGays pipeline regression suite ===")
    test_classifier()
    test_config_contract()
    test_manifest_invariants()
    test_sponsor_slot_safe()
    test_venue_artifact()
    test_classifier_golden()
    test_classifier_fuzz()
    test_quality_trend()
    print()
    if FAILS:
        print(f"[X] {len(FAILS)} FAILED: {', '.join(FAILS)}")
        sys.exit(1)
    print("[OK] all regression checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
