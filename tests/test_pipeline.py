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


def test_featured_selection_golden():
    print("featured-selection golden (W25 lineup anchor):")
    gp = os.path.join(ROOT, "tests", "golden", "2026-W25_featured.json")
    man_path = os.path.join(ROOT, "data", "posts", "2026-W25", "slide_manifest.json")
    if not (os.path.exists(gp) and os.path.exists(man_path)):
        print("  [skip] golden or W25 manifest absent")
        return
    golden = json.load(open(gp, encoding="utf-8"))["featured_by_day"]
    man = json.load(open(man_path, encoding="utf-8"))["featured_by_day"]
    cur = {d: [e.get("name") for e in evs] for d, evs in man.items()}
    # Only meaningful while the W25 fixture data is in place; compares the exact
    # featured lineup so a selection-logic change that silently reorders/drops the
    # shipped W25 cards is caught. (Drift on a fresh scrape is expected — re-snapshot.)
    drift = [d for d in golden if cur.get(d) != golden[d]]
    check("W25 featured lineup matches golden snapshot", not drift,
          f"drifted days: {drift}")


def test_youth_screen():
    print("youth/under-18 non-gay screen:")
    yn = es._is_youth_nongay
    # under-18 programming, not gay -> screened OUT
    for n in ["Adopt a Pet Rock", "Dino Discovery", "Toddler Storytime",
              "Balloon-Twisting Workshop With Joe Coover", "Teen Craft Time",
              "Native Culture Make and Take: Corn-Husk Dolls", "2 News Weather Show!"]:
        check(f"DROP youth: {n[:34]}", yn(ev(n)) is True)
    # explicitly-gay youth programming -> PROTECTED (kept)
    for n, v in [("Drag Queen Story Hour", "Central Library"),
                 ("Queer Youth Group", "Equality Center"),
                 ("GSA Teen Meetup", "Dennis R. Neill")]:
        check(f"KEEP queer youth: {n[:30]}", yn(ev(n, v)) is False)
    # adult events -> never screened as youth
    for n, v in [("David Sedaris", "Magic City Books"), ("Pride Day Bingo", "Tulsa Eagle"),
                 ("Saturday Board Games at the Library", "Central Library")]:
        check(f"KEEP adult: {n[:30]}", yn(ev(n, v)) is False)


def test_gpra_source_registered():
    print("GPRA source wired:")
    ds = os.path.join(ROOT, "data", "dynamic_sources.json")
    if os.path.exists(ds):
        blob = open(ds, encoding="utf-8").read().lower()
        check("Great Plains Rodeo registered in dynamic_sources", "great plains rodeo" in blob)


def test_graphic_gate():
    """Lock in the 2026-06-21 fix: a cheap 'boxes with X's' (tofu) graphic must
    be structurally un-postable. Every low-level posting primitive must DEFINE a
    _gate AND CALL it, and the gate must block the known-bad fixture and pass the
    clean one. Regresses the bug where the Saturday IG image shipped ungated."""
    print("graphic gate (tofu / broken-image) locks:")
    fx = os.path.join(ROOT, "tests", "fixtures")
    bad = os.path.join(fx, "tofu_weekend_live.png")
    good = os.path.join(fx, "clean_weekend_ref.png")

    # detector + shared chokepoint
    try:
        from tools.preflight_image import gate_images
        import tools.detect_tofu as dt
        check("detector flags the known-bad tofu fixture",
              os.path.exists(bad) and not dt.scan_image(bad)["clean"])
        check("detector passes the known-good fixture",
              os.path.exists(good) and dt.scan_image(good)["clean"])
        raised = False
        try:
            gate_images([bad])
        except RuntimeError:
            raised = True
        check("gate_images raises on the bad image", raised)
        try:
            gate_images([good]); ok = True
        except Exception:
            ok = False
        check("gate_images passes the clean image", ok)
    except Exception as e:
        check("gate tooling importable", False, str(e))

    # every posting primitive must DEFINE _gate AND CALL it (call site present)
    primitives = {
        "posting/facebook.py": "posting.facebook",
        "posting/instagram.py": "posting.instagram",
        "posting/group_post.py": "posting.group_post",
        "posting/group_blast.py": "posting.group_blast",
    }
    for relpath, modname in primitives.items():
        src = open(os.path.join(ROOT, relpath), encoding="utf-8").read()
        has_def = "def _gate(" in src
        # >=1 call beyond the definition itself
        has_call = src.count("_gate(") >= 2
        check(f"{relpath} defines AND calls _gate", has_def and has_call,
              f"def={has_def} call={has_call}")
        try:
            mod = __import__(modname, fromlist=["_gate"])
            r = False
            try:
                mod._gate([bad])
            except RuntimeError:
                r = True
            check(f"{modname}._gate blocks the bad image", r)
        except Exception as e:
            check(f"{modname} importable for gate check", False, str(e))


def test_ybr_highlighting():
    """Lock in William 2026-06-21 + VENUE_FACTS.md: Yellow Brick Road events must
    be featured (any event at YBR counts as LGBTQ even with a neutral title) and
    framed as inclusive / everyone-welcome."""
    print("YBR highlighting (feature + inclusive framing):")
    check("YBR in config.GAY_VENUE_SIGNATURES",
          any("yellow brick" in s or s == "ybr" for s in getattr(config, "GAY_VENUE_SIGNATURES", ())))
    check("neutral-title YBR event is featurable",
          es._is_lgbtq_strict({"name": "Karaoke Night", "venue": "Yellow Brick Road, 2630 E 15th St"}) is True)
    check("YBR Pub event is featurable",
          es._is_lgbtq_strict({"name": "Dance Night", "venue": "YBR Pub"}) is True)
    check("a random sports bar is still NOT gay",
          es._is_lgbtq_strict({"name": "Trivia", "venue": "Some Sports Bar"}) is False)
    try:
        import content.generator as g
        out = g._apply_ybr_inclusive_note([{"name": "Karaoke", "venue": "Yellow Brick Road",
                                            "description": "Friday karaoke."}])
        check("YBR description gains inclusive framing",
              "everyone is welcome" in out[0]["description"].lower())
        non = g._apply_ybr_inclusive_note([{"name": "Trivia", "venue": "Sports Bar",
                                            "description": "Pub trivia."}])
        check("non-YBR description untouched", non[0]["description"] == "Pub trivia.")
    except Exception as e:
        check("inclusive-note helper importable", False, str(e))


# ── W28 Saturday carousel failures (William 2026-07-08): the same Elote drag
# brunch featured twice under two titles + a cancelled event as the third
# highlight. Locks: cross-source venue dedup, cancelled detection, and that
# neither guard over-fires on legit distinct events / ticket boilerplate.
def test_w28_saturday_dedup_and_cancelled():
    print("W28 Saturday dedup + cancelled locks:")
    try:
        from scraper.runner import (_same_event_by_venue, _is_cancelled,
                                    _is_never_feature, deduplicate)
    except Exception as e:
        check("runner dedup/cancelled helpers importable", False, str(e))
        return
    a = {"name": "Elote Drag Brunch", "date": "2026-07-11",
         "venue": "Elote Cafe & Catering, 514 S Boston Ave",
         "priority": 1, "source": "recurring"}
    b = {"name": "Drag Brunch : jul. 11th - stars, stripes & sequins",
         "date": "2026-07-11", "venue": "Elote Cafe & Catering",
         "priority": 2, "source": "community_groups"}
    check("Elote brunch under two titles = ONE event", _same_event_by_venue(a, b))
    check("deduplicate() collapses the Elote pair", len(deduplicate([dict(a), dict(b)])) == 1)
    check("'(Cancelled) Clothing Swap!' is cancelled",
          _is_cancelled({"name": "(Cancelled) Clothing Swap!", "description": ""}))
    check("cancelled implies never_feature",
          _is_never_feature({"name": "CANCELED: Pride Picnic", "description": ""}))
    check("'has been cancelled' in description caught",
          _is_cancelled({"name": "Movie Night",
                         "description": "This event has been cancelled due to weather."}))
    # Must-NOT-fire cases
    check("two different DJs same bar NOT merged",
          not _same_event_by_venue(
              {"name": "DJ | Gus", "date": "2026-07-11", "venue": "Club Majestic"},
              {"name": "DJ | Sir Juice", "date": "2026-07-11", "venue": "Club Majestic"}))
    check("same event name on DIFFERENT dates NOT venue-merged",
          not _same_event_by_venue(
              {"name": "Elote Drag Brunch", "date": "2026-07-11", "venue": "Elote Cafe & Catering"},
              {"name": "Elote Drag Brunch", "date": "2026-07-12", "venue": "Elote Cafe & Catering"}))
    check("'free cancellation' ticket boilerplate NOT flagged",
          not _is_cancelled({"name": "Comedy Show",
                             "description": "Free cancellation up to 24 hours. Flexible cancellation policy."}))
    # Real W28 near-misses surfaced by the dry-run: distinct same-venue events
    # sharing only GENERIC words or the VENUE's own name must never merge.
    eq = "Dennis R. Neill Equality Center, 621 E 4th St"
    check("two different support groups NOT merged",
          not _same_event_by_venue(
              {"name": "Gender Outreach Support Group", "date": "2026-07-08", "venue": eq},
              {"name": "Non-binary Support Group", "date": "2026-07-08", "venue": eq}))
    sat = "Saturn Room209 N Boulder, Tulsa, OK, United States"
    check("venue name in two titles NOT merge evidence",
          not _same_event_by_venue(
              {"name": "Happy Hour at Saturn Room", "date": "2026-07-06", "venue": sat},
              {"name": "Record Night at Saturn Room", "date": "2026-07-06", "venue": sat}))
    ybr = "Yellow Brick Road, 2630 E 15th St"
    check("'Clothing Swap' vs 'Monthly Clothing Swap at YBR' IS merged",
          _same_event_by_venue(
              {"name": "Clothing Swap", "date": "2026-07-06", "venue": ybr},
              {"name": "Monthly Clothing Swap at YBR", "date": "2026-07-06", "venue": ybr}))


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
    test_featured_selection_golden()
    test_youth_screen()
    test_gpra_source_registered()
    test_graphic_gate()
    test_ybr_highlighting()
    test_w28_saturday_dedup_and_cancelled()
    print()
    if FAILS:
        print(f"[X] {len(FAILS)} FAILED: {', '.join(FAILS)}")
        sys.exit(1)
    print("[OK] all regression checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
