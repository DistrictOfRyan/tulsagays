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


# ── Final deck review (William 2026-07-09): the last-eyes pass over the
# generated deck — cancelled, dupes, recurring-vs-one-off, best picks.
def test_ig_date_anchor_contract():
    """W33 (2026-08-10) was HARD-BLOCKED by a Saturday duplicate because the IG
    caption extractor resolved BARE weekday captions against the CURRENT WEEK
    instead of the post date. A 'SATURDAY NIGHT!' post made 2026-08-06 (for 8/08)
    landed on 8/15 and collided with the real 8/15 flyer event; 'SUNDAY NIGHT!'
    posted 8/07 (for 8/09) landed on 8/16.

    The behaviour lives in a prompt, so this locks the CONTRACT: the anchoring
    rules must stay in the prompt and the system line must not reintroduce
    'today's date' as a co-equal anchor. Verified live 2026-08-10 against the real
    captions: bare weekdays resolved to 8/08 and 8/09, while the explicit
    'SATURDAY 8/15' and the 18-day-out 'THURSDAY AUGUST 27TH' were preserved.
    Do not weaken without re-running that check. See gap G428.
    """
    print("IG caption date-anchor contract:")
    try:
        src = os.path.join(ROOT, "scraper", "instagram_orgs.py")
        with open(src, encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        check("instagram_orgs.py readable", False, str(e))
        return

    check("anchors on the POST DATE, not the current week",
          "against THE POST DATE, never against the current week" in code)
    check("explicit dates win over a bare weekday",
          "EXPLICIT date in the caption ALWAYS wins" in code)
    check("bare weekday = first occurrence ON OR AFTER the post date",
          "FIRST such weekday ON OR AFTER the post date" in code)
    check("never emits a date before the post date",
          "NEVER output a date BEFORE the post date" in code)
    # The old wording is what produced the W33 collision.
    check("old 'post date and today's date' anchor is gone",
          "against the post date and today's" not in code)
    # The window must stay loose enough for real advance announcements
    # ('THURSDAY AUGUST 27TH' posted 8/09 = 18 days out is legitimate).
    try:
        sys.path.insert(0, os.path.join(ROOT, "scraper"))
        from scraper.instagram_orgs import InstagramOrgScraper as IOS
        check("announce window still allows a real advance post",
              IOS._within_announce_window("2026-08-27", "2026-08-09") is True)
        check("announce window still rejects a pre-post date",
              IOS._within_announce_window("2026-08-01", "2026-08-09") is False)
    except Exception as e:
        check("instagram_orgs importable", False, str(e))


def test_anonymity_allowlist():
    """The account is anonymous, so preflight warns on any standalone 'ryan' /
    'william' / 'hunt'. Real Tulsa venues carry those words in their own names
    ('The Hunt Club', 224 N Main St), which fired a false warning EVERY week and
    buried the warnings that matter -- W33's real blocker was a Saturday
    duplicate while the alert text led with the Hunt Club flag.

    IDENTITY_SOFT_ALLOWLIST masks those venue strings for the SOFT scan only.
    The point of this lock: masking must NEVER reach the hard checks. A genuine
    operator leak has to keep blocking even when it sits inside an allowlisted
    string. Never weaken these assertions.
    """
    print("anonymity allowlist (soft-only masking):")
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from preflight_post import _check_anonymity
    except Exception as e:
        check("preflight_post importable", False, str(e))
        return

    def scan(text):
        errs, warns = [], []
        _check_anonymity(text, "t", errs, warns)
        return errs, warns

    # Real venue names: fully clean, no noise.
    for txt in ("Taco Tuesday at The Hunt Club, 224 N Main St",
                "Open Mic Comedy Night at The Hunt Club runs 8 to 10",
                "A scavenger hunt through the Arts District"):
        e, w = scan(txt)
        check(f"clean: {txt[:38]}", not e and not w)

    # Hard leaks still BLOCK -- including inside an allowlisted venue string.
    for txt, why in (
        ("This account is run by Ryan Hunt", "operator full name"),
        ("Open mic at The Hunt Club, hosted by William Hunt", "full name beside allowlisted venue"),
        ("I run this account, dm me", "operator self-ID phrase"),
    ):
        e, _ = scan(txt)
        check(f"still blocks ({why})", len(e) > 0, f"got 0 errors for {txt!r}")

    # Un-allowlisted soft terms still warn (the guard is not globally disabled).
    for txt, term in (("The hunt for the best taco in Tulsa", "hunt"),
                      ("DJ Ryan spins at 10", "ryan"),
                      ("Hosted by William, your local drag mother", "william")):
        _, w = scan(txt)
        check(f"still warns on bare '{term}'", len(w) > 0)


def test_final_deck_review():
    print("final deck review selftest:")
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import final_deck_review as fdr
        check("final_deck_review selftest passes", fdr._selftest() == 0)
    except Exception as e:
        check("final_deck_review importable", False, str(e))


def test_w32_venue_relocation():
    """W32 shipped the WRONG ADDRESS for Homo Hotel Happy Hour on the carousel
    cover slide: title 'Homo Hotel Happy Hour at Courtyard Downtown' printed over
    '@ Dennis R. Neill Equality Center, 621 E 4th St' -- a different building a
    mile from the real one, for William's OWN event.

    Cause: deduplicate()'s venue backfill treated 'has a comma or a digit' as
    'is a better venue' and copied the loser's venue onto the winner without ever
    checking the two strings named the same building. An address ENRICHMENT
    silently became an address RELOCATION."""
    print("W32 venue-relocation locks:")
    try:
        from scraper.runner import (_same_venue_place, _venue_place_tokens,
                                    deduplicate)
        from scraper.venue_overrides import load_venue_varies, has_override_for
    except Exception as e:
        check("runner/venue helpers importable", False, str(e))
        return

    # --- the comparator ---
    check("Courtyard vs Equality Center = DIFFERENT places",
          not _same_venue_place("Courtyard Tulsa Downtown",
                                "Dennis R. Neill Equality Center, 621 E 4th St"))
    check("same venue + street detail = SAME place",
          _same_venue_place("Courtyard Tulsa Downtown",
                            "Courtyard Downtown, 415 S Boston Ave"))
    check("Elote enrichment still reads as same place",
          _same_venue_place("Elote Cafe & Catering",
                            "Elote Cafe & Catering, 514 S Boston Ave"))
    check("venues that are only generic words never match",
          not _same_venue_place("The Bar", "The Hotel"))
    check("'downtown'/'tulsa' alone don't prove a shared venue",
          not _same_venue_place("Tulsa Downtown", "Downtown Tulsa Center"))

    # --- THE PATH THAT ACTUALLY SHIPPED IT: main._dedup_day's __hhhh__ bucket ---
    # All HHHH variants on a date collapse into one bucket, then fields were taken
    # "best of" independently: the title from whichever record said " at ", the
    # venue from whichever address string was longest, the copy from whichever was
    # longest. Three records, one slide, no consistency check between them.
    try:
        from main import _dedup_day as _dd
    except Exception as e:
        check("main._dedup_day importable (hoisted for testing)", False, str(e))
        _dd = None

    w32_records = [
        {"name": "Homo Hotel Happy Hour", "date": "2026-08-07", "venue": "",
         "time": "6:00 PM - 8:00 PM", "priority": 1, "source": "homo_hotel",
         "description": "First Friday means the Homo Hotel throws its doors wide open."},
        {"name": "Homo Hotel Happy Hour (4H)", "date": "2026-08-07",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St", "time": "6:00 PM",
         "priority": 1, "source": "okeq",
         "description": "Leave the phone in your pocket, baby."},
        {"name": "Homo Hotel Happy Hour at Courtyard Downtown", "date": "2026-08-07",
         "venue": "Courtyard Tulsa Downtown", "time": "11:00 PM", "priority": 2,
         "source": "meetup", "description": "Dress up a little, honey."},
        {"name": "HHHH First Friday: PFLAG Tulsa Fundraiser", "date": "2026-08-07",
         "venue": "Courtyard Downtown, 415 S Boston Ave", "time": "6:00 PM - 8:00 PM",
         "priority": 3, "source": "manual",
         "description": "Homo Hotel Happy Hour takes over the Courtyard Downtown, and "
                        "this month every dollar raised goes to PFLAG Tulsa."},
    ]
    if _dd:
        got = _dd([dict(r) for r in w32_records])
        check("the four HHHH records still collapse to one", len(got) == 1,
              f"got {len(got)}")
        if got:
            v = (got[0].get("venue") or "")
            n = (got[0].get("name") or "")
            check("merged HHHH is NOT at the Equality Center",
                  "Dennis" not in v and "621 E 4th" not in v, f"venue={v!r}")
            check("merged HHHH slide does not contradict itself",
                  ("courtyard" in n.lower()) <= ("ourtyard" in v.lower()),
                  f"name={n!r} venue={v!r}")
    # A blank venue must still be filled, and same-place detail still enriches.
    blank = deduplicate([
        {"name": "Drag Brunch", "date": "2026-08-08", "venue": "",
         "priority": 1, "source": "a"},
        {"name": "Drag Brunch", "date": "2026-08-08",
         "venue": "Elote Cafe & Catering, 514 S Boston Ave", "priority": 2, "source": "b"},
    ])
    check("a BLANK venue is still backfilled",
          blank and "Elote" in (blank[0].get("venue") or ""))
    enrich = deduplicate([
        {"name": "Drag Brunch", "date": "2026-08-08", "venue": "Elote Cafe & Catering",
         "priority": 1, "source": "a"},
        {"name": "Drag Brunch", "date": "2026-08-08",
         "venue": "Elote Cafe & Catering, 514 S Boston Ave", "priority": 2, "source": "b"},
    ])
    check("same-place street detail is still adopted",
          enrich and "514 S Boston" in (enrich[0].get("venue") or ""))

    # --- hand-written site copy must survive the merge (2026-08-26) ---
    # _dedup_day carried `description` across a merge but not `website_description`.
    # A submitted event that was ALSO scraped from somewhere else therefore came out
    # of the merge with an empty website_description, and content/generator.py then
    # filled it with generated copy -- silently replacing a human's words. Caught on
    # "Equality & Justyce" (2026-W35), whose flyer copy never reached the site.
    if _dd:
        submitted_copy = "Fashion show by RE:APOLLO drawing selections from the Apollo Archive. " * 3
        merged = _dd([
            {"name": "Equality & Justyce", "date": "2026-08-29", "source": "okeq",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St", "priority": 1,
             "description": "Short scraped blurb."},
            {"name": "Equality & Justyce", "date": "2026-08-29", "source": "manual",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St", "priority": 1,
             "description": "A longer hand-written description than the scraped one.",
             "website_description": submitted_copy},
        ])
        check("submitted event still collapses to one record", len(merged) == 1,
              f"got {len(merged)}")
        if merged:
            check("hand-written website_description survives the merge",
                  (merged[0].get("website_description") or "") == submitted_copy,
                  f"got {(merged[0].get('website_description') or '')[:40]!r}")
            check("longest description still wins",
                  "hand-written" in (merged[0].get("description") or ""),
                  f"got {(merged[0].get('description') or '')[:40]!r}")
        # The reverse ordering must behave identically -- scrape order is not stable.
        merged_rev = _dd([
            {"name": "Equality & Justyce", "date": "2026-08-29", "source": "manual",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St", "priority": 1,
             "description": "A longer hand-written description than the scraped one.",
             "website_description": submitted_copy},
            {"name": "Equality & Justyce", "date": "2026-08-29", "source": "okeq",
             "venue": "Dennis R. Neill Equality Center, 621 E 4th St", "priority": 1,
             "description": "Short scraped blurb."},
        ])
        check("site copy survives regardless of scrape order",
              merged_rev and (merged_rev[0].get("website_description") or "") == submitted_copy)

    # --- HHHH is now a registered rotating venue with a confirmed August venue ---
    check("'homo hotel' registered in venue_varies",
          "homo hotel" in load_venue_varies())
    check("HHHH has a CONFIRMED venue for August 2026",
          has_override_for("Homo Hotel Happy Hour", "2026-08-07"))
    check("HHHH with no override for a future month would BLOCK",
          not has_override_for("Homo Hotel Happy Hour", "2026-12-04"))


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
    test_w32_venue_relocation()
    test_ig_date_anchor_contract()
    test_anonymity_allowlist()
    test_final_deck_review()
    print()
    if FAILS:
        print(f"[X] {len(FAILS)} FAILED: {', '.join(FAILS)}")
        sys.exit(1)
    print("[OK] all regression checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()


def test_html_entities_never_ship_in_event_names():
    """Regression lock, 2026-09-02: HTML entities leaked into event NAMES.

    Found by tulsagays-campus-sources-verify. "August OK So: LET&#8217;S GET IT
    ON" (Living Arts, via rendered_sites) and "&#8220;A Dozen Loops&#8221;"
    (Woody Guthrie Center, via extended_calendars) had shipped in stored event
    data for six consecutive weeks (W30-W35, 20 files). Two DIFFERENT scrapers
    produced it, which is why the fix is central (runner.clean_html_artifacts,
    step 5e, last transform before save) rather than per-scraper. Never move
    this cleanup back into individual scrapers -- there are ~250 sources and the
    next WordPress-backed one added would leak again.
    """
    from scraper.runner import clean_html_artifacts, _deentitize

    # The two real names that shipped.
    assert _deentitize("August OK So: LET&#8217;S GET IT ON") == \
        "August OK So: LET’S GET IT ON"
    assert _deentitize("The Beginnings of &#8220;A Dozen Loops&#8221;") == \
        "The Beginnings of “A Dozen Loops”"
    # Double-escaped survives (needs more than one unescape pass).
    assert _deentitize("Men&amp;#8217;s Soccer") == "Men’s Soccer"
    # Clean text is untouched (idempotent).
    assert _deentitize("Drag Brunch at Elote") == "Drag Brunch at Elote"

    # Descriptions get TAGS stripped too: some sources escape raw HTML into the
    # body, so a bare unescape would inject literal markup into slide copy.
    events = [{
        "name": "Pride Night &#8211; Fall Kickoff",
        "venue": "Metro Campus &amp; Student Union",
        "description": "&lt;p&gt;Join us &amp;amp; friends&lt;/p&gt;",
        "website_description": "&lt;strong&gt;Come as you are&lt;/strong&gt;",
    }]
    clean_html_artifacts(events)
    ev = events[0]
    assert ev["name"] == "Pride Night – Fall Kickoff"
    assert ev["venue"] == "Metro Campus & Student Union"
    assert "<" not in ev["description"]          # tags stripped, not decoded in
    assert ev["description"] == "Join us & friends"
    assert ev["website_description"] == "Come as you are"

    # Running twice changes nothing.
    snapshot = dict(ev)
    clean_html_artifacts(events)
    assert events[0] == snapshot
