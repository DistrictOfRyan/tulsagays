"""
Tulsa Gays - Main Orchestrator
Coordinates scraping, content generation, image creation, posting, and blog updates.

Usage:
    py main.py scrape               # Run all scrapers
    py main.py verify [2026-W18]    # Run pre-slide verification (optional week arg)
    py main.py generate             # Generate content for this week
    py main.py post-weekday         # Post weekday events
    py main.py post-weekend         # Post weekend events
    py main.py update-blog          # Update the blog with current events
    py main.py discover             # Discover new event sources
    py main.py report               # Generate engagement report
    py main.py full-run             # Run the complete weekly pipeline
    py main.py test                 # Test run without posting
"""

import sys
import os
import re
import json
import time
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def get_date_range(post_type):
    """Get the date range string for the current week's post type."""
    today = datetime.now()
    # Always use the current week's Monday (Monday=0 in weekday())
    monday = today - timedelta(days=today.weekday())

    if post_type == "weekday":
        start = monday
        end = monday + timedelta(days=3)  # Mon-Thu
    elif post_type == "all":
        start = monday
        end = monday + timedelta(days=6)  # Mon-Sun
    else:
        start = monday + timedelta(days=4)  # Friday
        end = monday + timedelta(days=6)  # Sunday

    return f"{start.strftime('%b %d')} - {end.strftime('%b %d')}"


def cmd_scrape():
    """Run all event scrapers."""
    print("=" * 50)
    print("SCRAPING EVENTS")
    print("=" * 50)

    from scraper.runner import main as run_scrapers
    events = run_scrapers()
    print(f"\nTotal events found: {len(events) if events else 0}")

    # On Mondays, mirror the snapshot + full events JSON into docs/ so the
    # GitHub Actions mid-week workflows (lastminute, spotlight) can read them.
    # data/ is gitignored, so anything that lives only there is invisible to
    # GHA runners. The git push at the bottom is best-effort: if the working
    # tree is dirty or the remote is unreachable, the scrape still succeeds.
    if datetime.now().weekday() == 0:
        try:
            week_key = config.current_week_key()
            repo_root = os.path.dirname(os.path.abspath(__file__))
            snap_filename = f"{week_key}_monday_snapshot.json"
            full_filename = f"{week_key}_all.json"
            snap_local = os.path.join(config.EVENTS_DIR, snap_filename)
            docs_snap_dir = os.path.join(repo_root, "docs", "snapshots")
            docs_data_dir = os.path.join(repo_root, "docs", "data", "events")
            os.makedirs(docs_snap_dir, exist_ok=True)
            os.makedirs(docs_data_dir, exist_ok=True)
            docs_snap_path = os.path.join(docs_snap_dir, snap_filename)
            docs_full_path = os.path.join(docs_data_dir, full_filename)
            live_path = os.path.join(config.EVENTS_DIR, full_filename)

            if os.path.exists(live_path):
                with open(live_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                live_events = payload.get("events", payload) if isinstance(payload, (dict, list)) else []
                snapshot = {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "week": week_key,
                    "count": len(live_events),
                    "event_keys": sorted({
                        f"{e.get('date','')}|{(e.get('name','') or '').strip().lower()}|{(e.get('venue','') or '').strip().lower()}"
                        for e in live_events if isinstance(e, dict)
                    }),
                }
                for path in (snap_local, docs_snap_path):
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(snapshot, f, indent=2, ensure_ascii=False)
                with open(docs_full_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                print(
                    f"Monday snapshot + events committed: "
                    f"{docs_snap_path} + {docs_full_path} ({snapshot['count']} events)"
                )

                try:
                    import subprocess

                    subprocess.run(
                        ["git", "add",
                         os.path.relpath(docs_snap_path, repo_root),
                         os.path.relpath(docs_full_path, repo_root)],
                        cwd=repo_root, check=True,
                    )
                    diff = subprocess.run(
                        ["git", "diff", "--cached", "--quiet"], cwd=repo_root
                    )
                    if diff.returncode != 0:
                        subprocess.run(
                            ["git", "commit", "-m",
                             f"events: Monday snapshot + full week JSON ({week_key})"],
                            cwd=repo_root, check=True,
                        )
                        subprocess.run(
                            ["git", "pull", "--rebase", "origin", "main"],
                            cwd=repo_root, check=False,
                        )
                        subprocess.run(
                            ["git", "push", "origin", "HEAD:main"],
                            cwd=repo_root, check=True,
                        )
                        print(f"events: pushed snapshot + {week_key}_all.json to main")
                except Exception as e:
                    print(f"WARN: git push of events data failed (non-fatal): {e}")
        except Exception as e:
            print(f"WARN: monday snapshot save failed: {e}")

    return events


def cmd_verify(week=None):
    """Run pre-generation verification checks on the week's events.

    Loads events from data/events/<week>_all.json and runs six checks:
      A - Same-venue/time/date duplicates
      B - HHHH venue validation (auto-fixes DoubleTree)
      C - Day-of-week description mismatches
      D - Garbage event filter
      E - Flamingo score sanity
      F - Never-feature event ordering

    Exits with code 1 if any FAIL check is found (WARN = auto-fixed = OK).
    """
    import sys as _sys
    from tools.verify_week import run_verification

    week_key = week or config.current_week_key()
    exit_code = run_verification(week_key)
    if exit_code != 0:
        print("\n[STOP] Verification failed. Fix the issues above before generating slides.")
        _sys.exit(exit_code)


def cmd_generate(post_type="weekday"):
    """Generate content (caption + images) for a post."""
    print("=" * 50)
    print(f"GENERATING {post_type.upper()} CONTENT")
    print("=" * 50)

    config.ensure_dirs()
    week_key = config.current_week_key()

    # Load events for this post type
    events_file = os.path.join(config.EVENTS_DIR, f"{week_key}_{post_type}.json")
    if not os.path.exists(events_file):
        print(f"No events file found at {events_file}")
        print("Run 'py main.py scrape' first.")
        return None

    with open(events_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both formats: list of events or dict with 'events' key
    if isinstance(data, dict):
        events = data.get("events", [])
    else:
        events = data

    if not events:
        print("No events found for this period.")
        return None

    # Sanity rules (defense-in-depth): the scraper sanitizes before saving,
    # but late additions (Wednesday last-minute, manual injects) re-enter via
    # these files. Drop off-topic junk before it costs enrichment calls or
    # reaches a slide. Rules only — fast, deterministic, idempotent.
    try:
        from tools.sanity_check_events import rules_pass as _sanity_rules
        events, _dropped, _ = _sanity_rules(events)
        if _dropped:
            print(f"[sanity] dropped {len(_dropped)} off-topic/junk events before generation:")
            for _e, _r in _dropped:
                print(f"  - [{_r}] {(_e.get('name') or '')[:60]}")
    except Exception as _ex:
        print(f"[sanity] rules pass skipped: {_ex}")

    if not events:
        print("No events left after sanity rules.")
        return None

    date_range = get_date_range(post_type)

    # Enrich events with exciting descriptions
    print("\nEnriching event descriptions...")
    try:
        from content.generator import enrich_event_descriptions
        events = enrich_event_descriptions(events)
        print(f"Enriched {len(events)} events with compelling descriptions")
        # Save enriched descriptions back to JSON so website and other tools use them
        with open(events_file, "w", encoding="utf-8") as _f:
            json.dump(events, _f, ensure_ascii=False, indent=2)
        print(f"Enriched descriptions saved to {events_file}")
    except Exception as e:
        print(f"Event enrichment skipped: {e}")

    # Generate caption
    print("\nGenerating caption...")
    try:
        from content.generator import generate_post_caption
        result = generate_post_caption(events, post_type, date_range)
        caption = result["caption"]
        category_events = result["category_events"]
        print(f"Caption generated ({len(caption)} chars)")
    except Exception as e:
        print(f"Caption generation failed: {e}")
        print("Using fallback template...")
        caption = _fallback_caption(events, post_type, date_range)
        category_events = _categorize_events(events)

    # Build events_by_day — only events within THIS week's Mon-Sun date range
    # AND only events that pass eotw_selector._is_skip() (the single source of
    # truth for banned events: bowling leagues, support groups, health
    # clinics, AA, "open for business" hours announcements, etc.). Without
    # this filter, banned events showed up on slides as #2/#3 (W22: EBA:
    # Open for Business on Thursday).
    try:
        from eotw_selector import _is_skip as _eotw_is_skip
    except Exception as _e:
        print(f"WARNING: eotw_selector import failed ({_e}); slides will NOT "
              f"filter banned events. Review every slide before posting.")
        def _eotw_is_skip(_ev):
            return False

    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]
    events_by_day = {day: [] for day in days_of_week}
    no_date_events = []
    _today = datetime.now().date()
    _week_monday = _today - timedelta(days=_today.weekday())
    _week_sunday = _week_monday + timedelta(days=6)
    _skipped_count = 0
    # LGBTQ-FIRST MODE: slides show 3 events per day, with LGBTQ events
    # prioritized at the top. Community events fill remaining slots when
    # the week is light on explicit LGBTQ programming. Only HARD-banned
    # events (AA privacy, generic weekly bar promos) are excluded — recurring
    # OKEQ community programming (TTRPG, support groups, clinics) shows
    # as filler at the bottom of day slides via the tier system.
    try:
        from eotw_selector import _is_hard_skip as _slide_skip
    except ImportError:
        _slide_skip = _eotw_is_skip
    for ev in events:
        if _slide_skip(ev):
            _skipped_count += 1
            continue
        date_str = ev.get("date", "")
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                ev_date = dt.date()
                if not (_week_monday <= ev_date <= _week_sunday):
                    continue
                day_name = dt.strftime("%A")
                if day_name in events_by_day:
                    events_by_day[day_name].append(ev)
            except ValueError:
                no_date_events.append(ev)
        else:
            no_date_events.append(ev)
    print(f"[slides] Filtered out {_skipped_count} banned/recurring events "
          f"via eotw_selector._is_skip()")
    # Priority sort: LGBTQ non-bar non-recurring first, bars and non-LGBTQ last.
    # Within each tier, sort by actual time (AM/PM parsed correctly, untimed last).
    _BAR_VENUES = {"1338 e 3rd", "302 south frankfort", "302 s. frankfort",
                   "302 s frankfort", "124 n boston", "frequency lounge", "sutures bar"}
    _BAR_NAME_FRAGMENTS = {"touchtunes", "leather night", "shenanigans", "eagle bingo",
                           "derby watch party", "derby hat"}
    _LGBTQ_KEYWORDS = {
        "lgbtq", "queer", "gay", "lesbian", "trans", "drag", "pride",
        "bisexual", "nonbinary", "non-binary", "equality", "homo hotel",
        "hhhh", "two-spirit", "pflag", "okeq", "rainbow", "gender outreach",
        "lambda bowling", "lambda league",
    }
    # Known gay bars / LGBTQ venues — events here are LGBTQ even without keywords
    _LGBTQ_VENUES = {"dennis r. neill", "dennis r neill", "oklahomans for equality",
                     "positive space", "okeq",
                     "1338 e 3rd",        # Tulsa Eagle
                     "302 south frankfort", "302 s frankfort", "302 s. frankfort",  # DVL
                     "124 n boston",      # Club Majestic
                     }
    _LGBTQ_SOURCES = {"homo_hotel", "okeq", "community_groups"}
    _RECURRING_SOURCES = {"recurring"}
    _RECURRING_NAME_FRAGMENTS = {
        "bowling league", "support group", "lambda unity",
        "outreach group", "monthly meeting",
        "happy hour!",   # generic bar open-door entries (DVL, etc.) — not real events
        "touchtunes",    # weekly Eagle promo, every Friday
        "ttrpg",         # weekly/recurring tabletop RPG sessions
        "tabletop",      # generic tabletop gaming — recurring
        "hope testing",  # recurring 2nd/4th Tuesday HIV testing clinic
        "health clinic", # recurring clinic appointments
        "health outreach",  # recurring outreach services
        "zoom only",     # online-only, not a real in-person recurring event
    }
    # These events should never appear in the top 3 — deprioritize to T6+
    _ALWAYS_DEPRIORITIZE = {
        "mix and mingle",     # straight networking, not a community event
        "aa meeting",         # valuable but not a highlight event
        "aa meetings",
        "book club - tulsa",  # org-specific book clubs (Tulsa SWE, etc.)
        "shut up & write",    # productivity meetup
        "raise your spiritual iq",  # generic self-help
        "okeq senior",        # seniors program — important but never the featured event
        "girl scout",         # troop meetings — community but not a featured highlight
        "hope testing",       # recurring HIV testing clinic — valuable service, never featured
        "health outreach",    # recurring health outreach services
        "okeq health",        # recurring clinic — never feature
        "zoom only",          # online-only events — not in-person community events
        "midweek meditation", # recurring online meditation
    }
    # Venue-level deprioritization REMOVED 2026-06-12 (William): Majestic and
    # other gay-bar special events are featurable. Weekly bar filler is still
    # held back by the recurring/never-feature rules above.
    _DEPRIORITIZE_VENUES = set()
    # Cultural/entertainment events get a sub-tier boost so they float above
    # generic T5 events even when their start time is later
    _CULTURAL_KEYWORDS = {
        "concert", "symphony", "musical", "opera", "ballet",
        "film", "cinema", "silent film", "live music",
        "guthrie green", "cain's ballroom", "performing arts center",
    }

    def _parse_time_minutes(t):
        # Range-aware START extraction: '6 - 10 PM' means 6 PM (the start
        # inherits the end's meridiem). The old split-then-parse failed on the
        # bare '6' and sorted the event as untimed.
        if not t:
            return 9999
        import re as _re
        import unicodedata as _ud
        t = ''.join(' ' if _ud.category(c) == 'Zs' else c for c in t.strip().upper())
        t = _re.sub(r'[‐‑‒–—―−]', '-', t)
        m = _re.search(r'(\d{1,2}(?::\d{2})?)\s*(AM|PM)?', t)
        if not m:
            return 9999
        num, mer = m.group(1), m.group(2)
        if not mer:
            m2 = _re.search(r'(?<![A-Z])(AM|PM)(?![A-Z])', t[m.end():])
            mer = m2.group(1) if m2 else None
        tok = f"{num} {mer}" if mer else num
        for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
            try:
                dt_parsed = datetime.strptime(tok, fmt)
                return dt_parsed.hour * 60 + dt_parsed.minute
            except ValueError:
                continue
        return 9999

    def _slide_priority(e):
        venue  = (e.get("venue") or "").lower()
        name   = (e.get("name") or "").lower()
        src    = (e.get("source") or "").lower()
        desc   = (e.get("description") or "").lower()
        combo  = f"{name} {desc} {venue} {src}"
        is_bar = (src == "bars"
                  or any(bv in venue for bv in _BAR_VENUES)
                  or any(bf in name  for bf in _BAR_NAME_FRAGMENTS))
        # Use strict eotw_selector check (name/venue only, no description),
        # so events like "Zoolightful at Tulsa Zoo" and "Open Meditation"
        # don't get tagged LGBTQ because their description mentions
        # "affirming spaces for LGBTQIA+ people".
        try:
            from eotw_selector import _is_lgbtq_strict as _strict_lgbtq
            is_lgbtq = _strict_lgbtq(e)
        except Exception:
            is_lgbtq = (any(kw in combo for kw in _LGBTQ_KEYWORDS)
                        or any(v in combo for v in _LGBTQ_VENUES)
                        or src in _LGBTQ_SOURCES)
        is_recurring = (src in _RECURRING_SOURCES
                        or any(kw in name for kw in _RECURRING_NAME_FRAGMENTS))
        # Authoritative never-feature guard: the BROAD eotw skip list
        # (health clinics, support groups, bowling, AA, sound baths, etc.).
        # Anything matching it can never lead a day, regardless of source.
        try:
            from eotw_selector import _is_skip as _eotw_broad_skip
            _never_feature = _eotw_broad_skip(e)
        except Exception:
            _never_feature = False
        is_deprioritized = (
            _never_feature
            or any(kw in name for kw in _ALWAYS_DEPRIORITIZE)
            or any(v in venue for v in _DEPRIORITIZE_VENUES)
        )
        # Cultural events float above generic events at the same tier
        is_cultural = any(kw in combo for kw in _CULTURAL_KEYWORDS)
        sub_tier = 0 if is_cultural else 1
        minutes = _parse_time_minutes(e.get("time", ""))
        # Drag/performance shows at bars still rank high — they're worth featuring
        _PERFORMANCE_KEYWORDS = {
            "drag", "talent night", "open talent", "cabaret", "variety show",
            "twisted arts drag", "inner circle drag",
        }
        is_drag_show = any(kw in combo for kw in _PERFORMANCE_KEYWORDS) and is_lgbtq
        if is_lgbtq and not is_bar and not is_recurring:
            tier = 1   # LGBTQ, non-bar, non-recurring — always show first
        elif is_drag_show and is_bar:
            tier = 2   # Drag/performance at a bar — worth featuring
        elif is_lgbtq and is_bar and not is_recurring:
            tier = 3   # LGBTQ bar, special one-off
        elif not is_lgbtq and not is_bar:
            tier = 4   # Non-LGBTQ cultural (concerts, art, film)
        elif is_lgbtq and not is_bar and is_recurring:
            tier = 5   # HARD RULE: recurring events (bowling, support groups) never lead a day
        elif is_lgbtq and is_bar:
            tier = 6   # Regular bar programming
        else:
            tier = 7   # Non-LGBTQ bar or generic catch-all
        # Deprioritized events never beat real events — sink to T6 minimum
        if is_deprioritized:
            tier = max(tier, 6)
        return (tier, sub_tier, minutes)

    # Fun / featured-worthy signals — the cool, inclusive, everyone-welcome stuff.
    _FUN_KW = (
        "drag", "party", "festival", "fest", "concert", "dance", "brunch",
        "show", "crawl", "pride", "market", "comedy", "karaoke", "trivia",
        "live music", "bingo", "mixer", "social", "cabaret", "disco", "ball",
        "prom", "kickoff", "celebration", "rooftop", "go-go", "art crawl",
        "happy hour", "night", "gala", "premiere", "screening", "open mic",
    )
    _AGGREGATOR_SRC = {"meetup", "extended_calendars", "eventbrite"}

    def _rebalance_featured(day_events):
        """Pick the 3 BEST featured events per day, per William's rules:
          - never service/recurring junk (therapy, clinics, support groups, AA,
            girl scouts, bowling) in the featured 3;
          - prefer FUN, one-off, inclusive events over weekly/recurring ones;
          - keep generic non-LGBTQ aggregator noise out of the featured 3;
          - aim for >=60% genuinely LGBTQ (>=2 of 3) when the day allows.
        Events below the top 3 keep their priority order (still on the website).
        """
        if len(day_events) <= 1:
            return day_events
        try:
            from eotw_selector import _is_lgbtq_strict, _is_skip
        except Exception:
            return day_events

        def _recurring(e):
            src = (e.get("source") or "").lower()
            nm = (e.get("name") or "").lower()
            return src in _RECURRING_SOURCES or any(f in nm for f in _RECURRING_NAME_FRAGMENTS)

        # Clearly off-topic / spammy non-community noise — never featured.
        _JUNK_KW = ("career", "blueprint", "investor", "founders", "real estate",
                    "make money", "webinar", "mlm", "networking for", "side hustle",
                    "crypto", "franchise", "sales training")

        def _eligible(e):
            # Hard-exclude services / girl scouts / therapy / AA / clinics.
            if _is_skip(e) or e.get("never_feature"):
                return False
            combo = ((e.get("name") or "") + " " + (e.get("description") or "")).lower()
            # Exclude clear off-topic business/seminar spam.
            if not _is_lgbtq_strict(e) and any(k in combo for k in _JUNK_KW):
                return False
            # Everything else — LGBTQ events AND inclusive one-off community /
            # cultural happenings (art, festivals, concerts, markets, etc.) — is
            # featured-eligible. _rank still floats the fun, one-off picks up top.
            return True

        def _rank(e):
            combo = ((e.get("name") or "") + " " + (e.get("description") or "")).lower()
            lg = _is_lgbtq_strict(e)
            rec = _recurring(e)
            fun = any(k in combo for k in _FUN_KW)
            # group 0 = fun one-off (best), 1 = lgbtq one-off, 2 = other one-off,
            # 3 = recurring (only if a day is thin). Then lgbtq, then fun.
            if fun and not rec:
                g = 0
            elif lg and not rec:
                g = 1
            elif not rec:
                g = 2
            else:
                g = 3
            return (g, 0 if lg else 1, 0 if fun else 1, _slide_priority(e))

        # Only eligible (fun / one-off / inclusive, non-service) events ever
        # reach the slide. Services/never-feature/aggregator-noise are dropped
        # from the slide list entirely — they still appear on the website's
        # full listing, just never on a carousel card.
        eligible = [e for e in day_events if _eligible(e)]
        feat_pool = sorted(eligible, key=_rank)
        target = min(3, len(feat_pool))

        # Aim for >=60% LGBTQ among the featured 3 when the day allows.
        lg = [e for e in feat_pool if _is_lgbtq_strict(e)]
        need = min(2, len(lg), target)
        top, seen = [], set()
        for e in lg[:need]:
            top.append(e); seen.add(id(e))
        for e in feat_pool:
            if len(top) >= target:
                break
            if id(e) not in seen:
                top.append(e); seen.add(id(e))
        # Remaining eligible events keep their rank order behind the featured 3
        # (they drive the "N more events" count). Services never appear here.
        tail = [e for e in feat_pool if id(e) not in seen]
        return top + tail

    # Deduplicate FIRST (collapse same-event variants, incl. the combined
    # Friday Pride Kickoff), THEN sort + select featured — so the featured 3 are
    # 3 distinct events, not the same event twice.
    def _dedup_day(ev_list):
        def _norm(s):
            return re.sub(r'\W+', ' ', (s or '').lower()).strip()

        def _has_address(venue):
            v = venue or ''
            return ',' in v or any(c.isdigit() for c in v)

        seen = {}   # key -> index in result
        result = []
        for ev in ev_list:
            name_norm = _norm(ev.get('name', ''))
            date = ev.get('date', '')
            venue_norm = _norm(ev.get('venue', ''))
            # Collapse all HHHH + co-hosted Pride Kickoff variants into one
            # bucket. On the combined First-Friday Pride Kickoff date (6/5), the
            # Tulsa Artist Fellowship First Fridays / Flagpole Go-Go events are
            # the SAME night and fold into the one combined event.
            _taf_first_friday = (
                date == '2026-06-05'
                and ('first friday' in name_norm or 'flagpole' in name_norm
                     or 'go go' in name_norm
                     or 'tulsa artist fellowship' in venue_norm
                     or 'flagship' in venue_norm)
            )
            if ('homo hotel' in name_norm or 'hhhh' in name_norm
                    or 'pride kickoff' in name_norm or _taf_first_friday):
                key = ('__hhhh__', date)
            else:
                key = (name_norm[:40], date)

            if key not in seen:
                seen[key] = len(result)
                result.append(dict(ev))
            else:
                idx = seen[key]
                existing = result[idx]
                # Keep the canonical "Pride Kickoff" name for the combined event.
                if 'pride kickoff' in name_norm and 'pride kickoff' not in _norm(existing.get('name', '')):
                    existing['name'] = ev.get('name', existing.get('name'))
                new_venue = ev.get('venue') or ''
                old_venue = existing.get('venue') or ''
                # Always prefer venue that has a street address (has comma or digit)
                if _has_address(new_venue) and not _has_address(old_venue):
                    existing['venue'] = new_venue
                elif _has_address(new_venue) and len(new_venue) > len(old_venue):
                    existing['venue'] = new_venue
                # Take longest/best description (keep sassy copy)
                if len(ev.get('description') or '') > len(existing.get('description') or ''):
                    existing['description'] = ev['description']
                # Take URL if missing
                if ev.get('url') and not existing.get('url'):
                    existing['url'] = ev['url']
        return result

    for day in days_of_week:
        before = len(events_by_day[day])
        events_by_day[day] = _dedup_day(events_by_day[day])
        after = len(events_by_day[day])
        if before != after:
            print(f"  [dedup] {day}: {before} -> {after} events (collapsed {before - after} duplicates)")

    # Now sort + pick the featured (fun, one-off, inclusive) events per day.
    for day in days_of_week:
        events_by_day[day].sort(key=_slide_priority)
        events_by_day[day] = _rebalance_featured(events_by_day[day])

    # Validate: warn if any day has zero events (expected for some days)
    days_with_events = [d for d in days_of_week if events_by_day[d]]
    print(f"\nEvents per day: { {d: len(events_by_day[d]) for d in days_of_week} }")
    if len(days_with_events) < 4:
        print(f"WARNING: Only {len(days_with_events)} days have events. "
              "Check scrapers — some sources may have failed.")

    # Pre-select EOTW from deduplicated events_by_day so the cover uses
    # the merged record (correct venue/address) rather than raw category_events.
    _all_deduped = [e for d in days_of_week for e in events_by_day[d]]
    from eotw_selector import select_eotw_list as _select_eotw_list
    _eotw_list = _select_eotw_list(_all_deduped, week_key=week_key)
    _preselected_eotw = _eotw_list[0] if _eotw_list else None
    if _eotw_list:
        for _i, _ev in enumerate(_eotw_list):
            print(f"  [eotw {_i+1}] {_ev.get('name')} @ {_ev.get('venue')} ({_ev.get('date')})")
    else:
        print("  [eotw] WARNING: No suitable LGBTQ event found for EOTW — cover slide will show generic fallback")

    # Generate carousel images
    print("\nGenerating carousel images...")
    try:
        from content.image_maker import create_carousel, save_carousel
        logo_path = config.LOGO_PATH if os.path.exists(config.LOGO_PATH) else None
        images = create_carousel(
            category_events, post_type, date_range, logo_path,
            events_by_day=events_by_day,
            featured_event=_preselected_eotw,
            featured_events=_eotw_list,
        )
        output_dir = os.path.join(config.DATA_DIR, "posts", week_key)
        os.makedirs(output_dir, exist_ok=True)
        image_paths = save_carousel(images, output_dir, f"{post_type}_")
        print(f"Generated {len(image_paths)} carousel slides")
        # Sanity check: alert if any day slide appears blank (0 events)
        blank_days = [d for d in days_of_week if not events_by_day[d]]
        if blank_days:
            print(f"NOTE: Blank slides for days with no events: {', '.join(blank_days)}")

        # ── Emit slide manifest (exactly what each slide shows) for preflight ──
        try:
            from content.image_maker import _flamingo_score as _flscore
        except Exception:
            _flscore = lambda e: 0
        def _featured_for_day(day):
            evs = [e for e in events_by_day.get(day, [])]
            # Mirror image_maker: promote any EOTW for this day to the front.
            for feat in (_eotw_list or []):
                hit = [e for e in evs if e.get("name") == feat.get("name")
                       and e.get("date") == feat.get("date")]
                if hit:
                    evs = [hit[0]] + [e for e in evs if e is not hit[0]]
            return evs[:3]
        def _slim(e):
            return {
                "name": e.get("name", ""), "date": e.get("date", ""),
                "time": e.get("time", ""), "venue": e.get("venue", ""),
                "source": e.get("source", ""), "url": e.get("url", ""),
                "description": e.get("description", ""),
                "website_description": e.get("website_description", ""),
                "flamingo": _flscore(e),
                "never_feature": bool(e.get("never_feature")),
                "lgbtq_relevant": bool(e.get("lgbtq_relevant")),
            }
        manifest = {
            "week_key": week_key,
            "post_type": post_type,
            "date_range": date_range,
            "eotw": [_slim(e) for e in (_eotw_list or [])],
            "manual_eotw_keys": [m for m in []],  # filled below
            "featured_by_day": {d: [_slim(e) for e in _featured_for_day(d)] for d in days_of_week},
            "all_shown": [_slim(e) for d in days_of_week for e in events_by_day.get(d, [])],
            "slide_count": len(image_paths),
        }
        try:
            from eotw_selector import load_manual_eotw
            manifest["manual_eotw_keys"] = load_manual_eotw(week_key)
        except Exception:
            pass
        with open(os.path.join(output_dir, "slide_manifest.json"), "w", encoding="utf-8") as _mf:
            json.dump(manifest, _mf, indent=2, ensure_ascii=False)
        print(f"Wrote slide_manifest.json ({len(manifest['all_shown'])} shown events)")
    except Exception as e:
        print(f"Image generation failed: {e}")
        image_paths = []

    # Save the post content
    post_data = {
        "week": week_key,
        "post_type": post_type,
        "date_range": date_range,
        "caption": caption,
        "image_paths": image_paths,
        "events_count": len(events),
        "generated_at": datetime.now().isoformat(),
    }

    post_file = os.path.join(config.DATA_DIR, "posts", week_key, f"{post_type}_post.json")
    os.makedirs(os.path.dirname(post_file), exist_ok=True)
    with open(post_file, "w") as f:
        json.dump(post_data, f, indent=2)

    print(f"\nPost content saved to {post_file}")
    # Encode-safe preview: Windows cp1252 consoles crash on emoji (rainbow, etc.).
    _preview = f"\n--- CAPTION PREVIEW ---\n{caption[:500]}..."
    try:
        print(_preview)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((_preview + "\n").encode("utf-8", "replace"))
    return post_data


def cmd_post(post_type):
    """Post to Instagram."""
    print("=" * 50)
    print(f"POSTING {post_type.upper()} TO INSTAGRAM")
    print("=" * 50)

    week_key = config.current_week_key()
    post_file = os.path.join(config.DATA_DIR, "posts", week_key, f"{post_type}_post.json")

    if not os.path.exists(post_file):
        print(f"No post content found. Run 'py main.py generate' first.")
        return False

    with open(post_file, "r") as f:
        post_data = json.load(f)

    if not config.META_ACCESS_TOKEN or not config.META_IG_USER_ID:
        print("ERROR: Meta API credentials not configured.")
        print("Set META_ACCESS_TOKEN and META_IG_USER_ID environment variables.")
        return False

    # Humanize: random delay before posting (1-5 minutes)
    delay = random.randint(60, 300)
    print(f"Humanization delay: waiting {delay} seconds...")
    time.sleep(delay)

    try:
        from posting.instagram import post_carousel, humanize_caption
        caption = humanize_caption(post_data["caption"])
        image_paths = post_data["image_paths"]

        if not image_paths:
            print("No images to post.")
            return False

        result = post_carousel(
            image_paths, caption,
            config.META_ACCESS_TOKEN, config.META_IG_USER_ID
        )
        print(f"Posted successfully! Media ID: {result.get('id', 'unknown')}")

        # Log the post
        from self_improve.engagement_tracker import log_post
        log_post(
            post_id=result.get("id", ""),
            post_type=post_type,
            events_featured=post_data["events_count"],
            caption_style="carousel",
        )
        return True
    except Exception as e:
        print(f"Posting failed: {e}")
        return False


def cmd_update_blog():
    """Update the blog with current events."""
    print("=" * 50)
    print("UPDATING BLOG")
    print("=" * 50)

    try:
        from blog.update_blog import update_blog
        update_blog()
        print("Blog updated successfully!")
    except Exception as e:
        print(f"Blog update failed: {e}")


def cmd_discover():
    """Discover new event sources."""
    print("=" * 50)
    print("DISCOVERING NEW SOURCES")
    print("=" * 50)

    try:
        from self_improve.source_discovery import discover_new_sources
        new_sources = discover_new_sources()
        if new_sources:
            print(f"\nFound {len(new_sources)} new potential sources:")
            for src in new_sources:
                print(f"  - {src}")
        else:
            print("No new sources found.")
    except Exception as e:
        print(f"Source discovery failed: {e}")


def cmd_report():
    """Generate engagement report."""
    print("=" * 50)
    print("ENGAGEMENT REPORT")
    print("=" * 50)

    try:
        from self_improve.engagement_tracker import get_weekly_report
        report = get_weekly_report()
        print(report)
    except Exception as e:
        print(f"Report generation failed: {e}")


def cmd_full_run():
    """Run the complete weekly pipeline."""
    print("*" * 60)
    print("  TULSA GAYS - FULL WEEKLY RUN")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("*" * 60)

    # Step 1: Scrape
    cmd_scrape()

    # Step 2: Verify (runs after scrape, before any slide generation)
    # Exits with code 1 on hard failures, auto-fixes WARN issues in the JSON
    cmd_verify()

    # Step 3: Generate weekday content
    cmd_generate("weekday")

    # Step 4: Generate weekend content
    cmd_generate("weekend")

    # Step 5: Update blog
    cmd_update_blog()

    # Step 6: Discover new sources
    cmd_discover()

    print("\n" + "=" * 60)
    print("FULL RUN COMPLETE")
    print("Posts are ready. Use 'py main.py post-weekday' or 'post-weekend' to publish.")
    print("=" * 60)


def cmd_post_hhhh():
    """Post a caption (and optional images) to the HHHH Facebook Page.

    Usage:
        py main.py post-hhhh "caption text"
        py main.py post-hhhh "caption text" path/to/img1.jpg path/to/img2.jpg
    """
    from posting.facebook import post_to_hhhh, FacebookPostError

    if len(sys.argv) < 3:
        print("Usage: py main.py post-hhhh <caption> [image_path ...]")
        sys.exit(1)

    caption = sys.argv[2]
    image_paths = sys.argv[3:] or None

    if not config.HHHH_PAGE_ID or not config.HHHH_PAGE_ACCESS_TOKEN:
        print("ERROR: HHHH_PAGE_ID and HHHH_PAGE_ACCESS_TOKEN must be set in .env")
        sys.exit(1)

    try:
        result = post_to_hhhh(caption, image_paths=image_paths)
    except FacebookPostError as exc:
        print(f"HHHH post failed: {exc}")
        sys.exit(1)

    print(f"Posted to HHHH Page. Response: {result}")


def cmd_test():
    """Test run - scrape and generate without posting."""
    print("*" * 60)
    print("  TULSA GAYS - TEST RUN (no posting)")
    print("*" * 60)

    cmd_scrape()
    cmd_generate("weekday")
    cmd_generate("weekend")
    print("\nTest run complete! Check data/posts/ for generated content.")


def _categorize_events(events):
    """Simple event categorization fallback."""
    categories = {"featured": [], "community": [], "arts": [], "nightlife": []}
    for event in events:
        source = event.get("source", "").lower()
        priority = event.get("priority", 3)
        if "homo_hotel" in source:
            categories["featured"].append(event)
        elif source in ("okeq", "all_souls", "church_restoration"):
            categories["community"].append(event)
        elif "twisted" in source:
            categories["arts"].append(event)
        elif priority <= 2:
            categories["community"].append(event)
        else:
            categories["nightlife"].append(event)
    return categories


def _fallback_caption(events, post_type, date_range):
    """Generate a simple caption without the API."""
    period = "this week" if post_type == "weekday" else "this weekend"
    lines = [f"Here's what's happening {period} in Tulsa! ({date_range})\n"]

    # Always lead with Homo Hotel
    homo = [e for e in events if "homo" in e.get("source", "").lower() or "homo" in e.get("name", "").lower()]
    if homo:
        h = homo[0]
        lines.append(f"HOMO HOTEL HAPPY HOUR")
        lines.append(f"{h.get('date', '')} | {h.get('time', '')}")
        lines.append(f"{h.get('venue', '')}")
        lines.append(f"{h.get('description', '')}\n")

    # Other events
    other = [e for e in events if e not in homo][:5]
    for event in other:
        lines.append(f"{event['name']}")
        lines.append(f"{event.get('date', '')} | {event.get('time', '')} @ {event.get('venue', '')}")
        if event.get("url"):
            lines.append(f"{event['url']}")
        lines.append("")

    # Hashtags
    hashtags = random.sample(config.HASHTAGS, min(15, len(config.HASHTAGS)))
    lines.append("\n" + " ".join(hashtags))

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower().replace("_", "-")
    commands = {
        "scrape": cmd_scrape,
        "verify": lambda: cmd_verify(sys.argv[2] if len(sys.argv) > 2 else None),
        "generate": lambda: cmd_generate(sys.argv[2] if len(sys.argv) > 2 else "weekday"),
        "generate-all": lambda: cmd_generate("all"),
        "post-weekday": lambda: cmd_post("weekday"),
        "post-weekend": lambda: cmd_post("weekend"),
        "post-hhhh": cmd_post_hhhh,
        "update-blog": cmd_update_blog,
        "discover": cmd_discover,
        "report": cmd_report,
        "full-run": cmd_full_run,
        "test": cmd_test,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
