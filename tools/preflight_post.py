"""
Pre-post preflight for the Tulsa Gays weekly carousel.

HARD GATE that must pass before any Monday post goes out. It verifies the
generated slides against William's rules and catches the failures that broke
past weeks:

  EVENTS    - Event(s) of the Week present; manual override honored; no
              service/never-feature event in any featured top-3; everything
              in the current Mon-Sun week.
  TEXT      - No overlapping/overflowing slide text (reads layout_report.json
              emitted by image_maker during render).
  VOICE     - Descriptions are present, in-voice (sassy, encouraging, no AI
              tells, no em dashes, no raw scraper junk). EOTW copy held to a
              higher bar (substantive + second-person "get off the couch" voice).
  LINKS     - Featured event URLs are well-formed; EOTW links reachable.

Usage:
    python tools/preflight_post.py [WEEK_KEY]      # defaults to current week
Exit code 0 = safe to post. Exit code 1 = BLOCKED (see printed report +
preflight_status.json in the week's posts dir).
"""
import json
import os
import re
import sys
from datetime import date, datetime

# Windows scheduled tasks / cp1252 consoles can't encode the emoji and special
# chars that appear in event names and report lines. Without this, the report
# print() raises UnicodeEncodeError and crashes the whole gate (and any caller
# such as post_weekly.py) instead of returning a clean pass/fail. errors=replace
# keeps the gate alive on any console.
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_this = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_this)
if _root not in sys.path:
    sys.path.insert(0, _root)

import config  # noqa: E402

# ── Voice policy (the rules, in code) ──────────────────────────────────────
BANNED_PHRASES = [
    "vibrant community", "safe space", "don't miss out", "dont miss out",
    "something for everyone", "whether you're", "whether you are",
    "nestled", "look no further", "let yourself feel things",
    "come one come all", "fun for all ages",
    # Flat motivational filler (William 2026-06-17: "wasted space", "too generic").
    "make sure to go", "make sure you go", "actually go", "be sure to go",
    "put this on your calendar", "put it on your calendar",
    "you will thank yourself", "zero excuses", "no excuses not to",
    "you'll only know that if you show up", "your people, and",
]
ARTIFACT_PATTERNS = [
    re.compile(r"^\s*\w+\s+\d{1,2},\s*\d{4}\s*\|"),     # "June 5, 2026 | 6:00 pm ..."
    re.compile(r"we are thrilled to share", re.I),
    re.compile(r"\bwellness room\b", re.I),
    re.compile(r"<[a-z/][^>]*>"),                        # stray HTML
    re.compile(r"\bticket options may be available\b", re.I),
]
VOICE_MARKERS = ("you", "your", "honey", "baby", "sweetheart", "girl",
                 "darling", "go ", "get ")  # second-person / encouraging cues

# Signatures of TEMPLATED / fallback copy (rule-based templates + dedupe pool
# openers). On a FEATURED slide these read as filler, not the hand-written
# RuPaul x Dolly voice — flag them (warning) so the Monday voice-pass rewrites
# them. Not a hard block (dedupe already guarantees uniqueness); a quality nudge.
TEMPLATE_SIGNATURES = [
    "put this on your calendar and actually go",
    "the people in that room are your people",
    "arrive before it starts. find a spot",
    "clear your calendar, because",
    "here is your permission slip",
    "nobody ever regretted going to",
    "if you do one thing this week",
    "is calling and the answer is yes",
    "do future-you a favor",
    "treat yourself to",
    "stop scrolling and go be among your people",
]


def _looks_templated(text):
    low = (text or "").strip().lower()
    return any(sig in low for sig in TEMPLATE_SIGNATURES)

# ── Anonymity policy ────────────────────────────────────────────────────────
# The account is ANONYMOUS — nothing posted may reveal who runs it. Block any
# operator name or "I run this account" style self-identification.
# Hard block: full operator names + handles (unambiguous identity leaks).
IDENTITY_TERMS_HARD = [
    "ryan hunt", "william hunt", "william ryan hunt", "william ryan",
    "districtofryan", "wmhunt", "whunt", "ryanhunt", "ryan william hunt",
]
# Soft (warn + eyeball): standalone first names / surname — could be a real
# performer ("scavenger hunt", a DJ named Ryan), so warn rather than block.
IDENTITY_TERMS_SOFT = ["ryan", "william", "hunt"]
OPERATOR_PHRASES = [
    "i run this", "i run the", "i created this", "i started this", "i curate",
    "my account", "account is run by", "run by me", "founder of this",
    "i'm the organizer", "i am the organizer", "i'm the admin", "dm me",
    "message me personally", "reach out to me", "the person behind",
    "who runs this", "my name is", "i manage this", "i'm the one behind",
]


def _word(term, low):
    return re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low) is not None


def _check_anonymity(text, where, errors, warnings):
    """Flag anything that could reveal the operator's identity (account is anonymous)."""
    if not text:
        return
    low = text.lower()
    for term in IDENTITY_TERMS_HARD:
        if term in low:
            errors.append(f"[anonymity] {where} reveals operator identity '{term}' — account MUST stay anonymous")
    for phrase in OPERATOR_PHRASES:
        if phrase in low:
            errors.append(f"[anonymity] {where} self-identifies the operator ('{phrase}') — account MUST stay anonymous")
    for term in IDENTITY_TERMS_SOFT:
        if _word(term, low):
            warnings.append(f"[anonymity] {where} contains '{term}' — verify it's a real event detail, not the operator")


def _week_range(week_key):
    try:
        y, w = week_key.split("-W")
        monday = date.fromisocalendar(int(y), int(w), 1)
        return monday, date.fromisocalendar(int(y), int(w), 7)
    except Exception:
        today = date.today()
        mon = today.fromordinal(today.toordinal() - today.weekday())
        return mon, date.fromordinal(mon.toordinal() + 6)


def _check_desc(ev, errors, warnings, is_eotw=False, posted=True):
    # "posted" = this event appears on a carousel slide (featured) or is an EOTW,
    # i.e. it actually goes out in the FB/IG post. Website-only filler events
    # (scraped civic/community items that only populate the full site list, never
    # a slide) are gated leniently: their copy gaps are WARNINGS, not hard blocks,
    # so a thin farmers-market listing can't stop the whole week's post. Anonymity
    # and harness-leak leaks are STILL hard-gated for every event in the dedicated
    # loops below — those protect the published site too, not just the slides.
    sink = errors if posted else warnings
    name = ev.get("name", "?")
    short = (ev.get("description") or "").strip()
    longd = (ev.get("website_description") or "").strip()
    tag = "EOTW" if is_eotw else "event"
    # SHORT description is rendered onto the carousel slide -> it IS posted to
    # FB/IG, so hard-gate it for slide/EOTW events.
    if not short:
        sink.append(f"[desc] {tag} '{name}' has NO short description")
    # LONG (website_description) only ever appears on the website, never in the
    # FB/IG post. Gate only what's posted: hard-block a missing long desc only
    # for the EOTW hero (held to a high bar); everyone else is a warning.
    if not longd:
        (errors if is_eotw else warnings).append(
            f"[desc] {tag} '{name}' has NO website (long) description")
    for field, txt in (("short", short), ("long", longd)):
        low = txt.lower()
        if "—" in txt or " - - " in txt:
            sink.append(f"[voice] {tag} '{name}' {field} contains an em dash")
        for p in BANNED_PHRASES:
            if p in low:
                sink.append(f"[voice] {tag} '{name}' {field} uses banned phrase '{p}'")
        for rx in ARTIFACT_PATTERNS:
            if rx.search(txt):
                sink.append(f"[voice] {tag} '{name}' {field} looks like raw scraper text / junk")
                break
    # Voice-quality nudge: a posted (slide/EOTW) event leaning on templated
    # fallback copy should be rewritten by the Monday voice-pass.
    if posted and _looks_templated(short):
        warnings.append(f"[voice-quality] {tag} '{name}' uses templated/fallback copy "
                        f"— rewrite in the RuPaul x Dolly voice (Monday STEP 2.1)")
    # Rung 4: channel length contracts (slide-safe short, substantive EOTW long).
    if posted:
        try:
            from tools.channel_copy import contract_violations
            for v in contract_violations(ev, is_eotw=is_eotw):
                warnings.append(f"[channel-contract] {v}")
        except Exception:
            pass
    if len(short) > 240:
        warnings.append(f"[voice] {tag} '{name}' short desc is {len(short)} chars (long for a slide)")
    if is_eotw:
        if len(short) < 50:
            errors.append(f"[voice] EOTW '{name}' short desc too thin ({len(short)} chars) — needs real sass")
        if len(longd) < 200:
            errors.append(f"[voice] EOTW '{name}' long desc too thin ({len(longd)} chars)")
        if not any(m in short.lower() for m in VOICE_MARKERS):
            warnings.append(f"[voice] EOTW '{name}' short desc lacks an encouraging/second-person hook")


def run(week_key=None):
    week_key = week_key or config.current_week_key()
    post_dir = os.path.join(config.DATA_DIR, "posts", week_key)
    errors, warnings = [], []

    manifest_path = os.path.join(post_dir, "slide_manifest.json")
    if not os.path.exists(manifest_path):
        errors.append(f"[setup] No slide_manifest.json in {post_dir} — run generate first")
        return _finish(week_key, post_dir, errors, warnings)
    manifest = json.load(open(manifest_path, encoding="utf-8"))

    monday, sunday = _week_range(week_key)
    eotw = manifest.get("eotw", [])
    featured_by_day = manifest.get("featured_by_day", {})
    all_shown = manifest.get("all_shown", [])

    # ── EVENTS ──────────────────────────────────────────────────────────
    if not eotw:
        errors.append("[events] No Event(s) of the Week selected")
    for m in manifest.get("manual_eotw_keys", []):
        frag = (m.get("match") or "").lower()
        if frag and not any(frag in (e.get("name", "").lower()) for e in eotw):
            errors.append(f"[events] manual EOTW '{frag}' was pinned but is not in the cover EOTW set")

    featured_all = []
    for day, evs in featured_by_day.items():
        # HARD RULE (William): every day must have at least 3 featured events.
        if len(evs) < 3:
            errors.append(f"[events] {day} has only {len(evs)} featured event(s) — HARD RULE requires >=3 per day (fix scrape supply)")
        if len(evs) > 3:
            warnings.append(f"[events] {day} has {len(evs)} featured (>3)")
        for e in evs:
            featured_all.append(e)
            if e.get("never_feature"):
                errors.append(f"[events] {day} features a never-feature/service event: '{e.get('name')}'")
            # Quality guards (insurance behind tools/clean_event_data.py): a
            # featured event is on a slide, so flag artifacts that should have
            # been cleaned. Warnings, not blocks, so they never death-spiral.
            _nm = e.get("name", "")
            if "—" in _nm or "–" in _nm:
                warnings.append(f"[quality] featured '{_nm}' title still has an em dash — run clean_event_data.py")
            _u = (e.get("url") or "")
            if re.search(r"google\.[a-z.]+/search|bing\.com/search|/search\?", _u, re.I):
                warnings.append(f"[quality] featured '{_nm}' has a placeholder search URL — run clean_event_data.py")
            d = e.get("date", "")
            try:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
                if not (monday <= dd <= sunday):
                    errors.append(f"[events] {day} features out-of-week event '{e.get('name')}' ({d})")
            except Exception:
                errors.append(f"[events] featured event '{e.get('name')}' has bad/missing date '{d}'")

    if featured_all:
        gay = sum(1 for e in featured_all if e.get("flamingo", 0) >= 4 or e.get("lgbtq_relevant"))
        pct = gay / len(featured_all)
        if pct < 0.60:
            warnings.append(f"[events] only {pct:.0%} of featured events are clearly LGBTQ (target >=60%)")

    # ── VENUE STALENESS (the "wrong venue shipped" class) ──────────────────
    # Recurring events whose location rotates month to month (Queer Women's
    # Collective, etc.) cannot carry a trustworthy hardcoded/scraped venue.
    # data/venue_overrides.json lists those names in `venue_varies`; each month
    # an `overrides` entry supplies the real venue. Featuring such an event with
    # NO confirmed venue for this month is a hard block -- that is exactly how the
    # stale Equality Center venue went out. Resurfaced-ledger venues get eyeballed.
    try:
        from scraper.venue_overrides import load_venue_varies, has_override_for
        _varies = load_venue_varies()
        for e in eotw + featured_all:
            nm = e.get("name", "?")
            low = nm.lower()
            d = e.get("date", "")
            if any(v in low for v in _varies) and not has_override_for(nm, d):
                errors.append(
                    f"[venue] featured/EOTW '{nm}' rotates venue monthly and has NO confirmed "
                    f"venue for {monday.strftime('%Y-%m')} -- add an entry to data/venue_overrides.json "
                    f"(match + month + venue) before posting (its scraped venue is likely stale)")
            elif e.get("resurfaced_from_upcoming") or e.get("from_upcoming_ledger"):
                warnings.append(
                    f"[venue] featured '{nm}' was resurfaced from the upcoming ledger; its venue "
                    f"'{(e.get('venue') or '').strip() or '(blank)'}' may be weeks old -- confirm it's correct")
    except Exception as _ve:
        warnings.append(f"[venue] venue-staleness check failed: {_ve}")

    # ── RECURRING EVENT VERIFICATION (still happening? still here?) ─────────
    # Every recurring event carries a confirmation freshness clock (ledger:
    # data/recurring_confirmations.json, refreshed by scraper/recurring_verify
    # each scrape). TIERED: a FEATURED recurring event that's merely stale
    # (>stale_after_days since last confirmed) WARNS; one unconfirmed past
    # block_after_days (default 180d) is BLOCKED from being featured -- it can
    # still sit in the website list, but it won't headline a slide unverified.
    try:
        from scraper.recurring_verify import load_ledger, lookup_tier
        _rled = load_ledger()
        _rtoday = date.today().isoformat()
        for e in eotw + featured_all:
            nm = e.get("name", "?")
            is_tracked, tier, days, entry = lookup_tier(nm, _rtoday, _rled)
            if not is_tracked:
                continue
            _lv = (entry or {}).get("last_verified") or "never"
            _vv = (entry or {}).get("verified_venue") or (e.get("venue") or "").strip() or "(blank)"
            if tier == "expired":
                errors.append(
                    f"[recurring] featured/EOTW '{nm}' has NOT been confirmed (still happening + "
                    f"venue still '{_vv}') since {_lv} -- past the {_rled.get('block_after_days', 180)}-day "
                    f"limit. Confirm it in data/recurring_confirmations.json (or set status dead/paused) "
                    f"before featuring it")
            elif tier == "stale":
                warnings.append(
                    f"[recurring] featured '{nm}' last confirmed {_lv} ({days}d ago) -- verify it still "
                    f"runs and is still at '{_vv}', then stamp data/recurring_confirmations.json")
            _conf = (entry or {}).get("pending_venue_conflict")
            if _conf:
                warnings.append(
                    f"[recurring] featured '{nm}' may have MOVED: a live scrape shows "
                    f"'{_conf.get('live_venue')}' ({_conf.get('source')}) vs known "
                    f"'{_conf.get('known_venue')}' -- confirm the venue before posting "
                    f"(stamp data/recurring_confirmations.json to resolve)")
    except Exception as _re:
        warnings.append(f"[recurring] verification check failed: {_re}")

    # ── SANITY (the W24 'Owasso city council' class of nonsense) ───────────
    # Re-apply the sanity drop rules to what is about to POST: a featured/EOTW
    # event matching a drop rule is a hard block; website-shown junk warns.
    try:
        from tools.sanity_check_events import rules_pass as _sanity_rules
        _, _dropped, _ = _sanity_rules([dict(e) for e in eotw + featured_all])
        for _e, _r in _dropped:
            errors.append(f"[sanity] featured/EOTW event is off-topic junk ({_r}): '{_e.get('name')}'")
        _, _dropped2, _ = _sanity_rules([dict(e) for e in all_shown])
        _featured_keys = {(e.get("name"), e.get("date")) for e in eotw + featured_all}
        for _e, _r in _dropped2:
            if (_e.get("name"), _e.get("date")) not in _featured_keys:
                warnings.append(f"[sanity] shown event is off-topic junk ({_r}): '{_e.get('name')}'")
        # Surface scrape-time sanity flags (implausible times, truncated names)
        for _e in eotw + featured_all:
            for _f in _e.get("sanity_flags") or []:
                warnings.append(f"[sanity] featured '{_e.get('name')}': {_f}")
    except Exception as _ex:
        warnings.append(f"[sanity] could not run sanity rules: {_ex}")
    _sanity_report = os.path.join(config.DATA_DIR, "events", f"{week_key}_sanity_report.json")
    if not os.path.exists(_sanity_report):
        warnings.append("[sanity] no sanity report for this week — "
                        "run tools/sanity_check_events.py after the scrape")

    # ── SLIDE COPY VOICE (the hero cards people actually see) ──
    # The W24 embarrassment was templated filler ON THE SLIDES. That is the
    # hard block: FEATURED + EOTW copy must be real Alicia/RuPaul/Dolly voice,
    # written in the Monday voice pass (Step 2.1), never pool filler.
    # Rule-based copy is the ACCEPTED FLOOR for the hundreds of non-featured
    # website listings (the automated pipeline does not run nested-LLM
    # enrichment over all 213), so the full-file ratio is only a warning now.
    # (Re-scoped 2026-06-15 — see feedback_tulsagays_featured_gay_first.)
    _slide_events = list(eotw) + list(featured_all)
    if _slide_events:
        _stpl = sum(
            1 for e in _slide_events
            if _looks_templated(e.get("description"))
            or _looks_templated(e.get("website_description")))
        _sratio = _stpl / len(_slide_events)
        if _sratio > 0.25:
            errors.append(
                f"[voice] {_stpl}/{len(_slide_events)} ({_sratio:.0%}) FEATURED/EOTW slide "
                f"descriptions are templated filler — rewrite them in the RuPaul x Dolly voice "
                f"(Monday Step 2.1) before posting; the slides are the hero content")
    try:
        _all_path = os.path.join(config.DATA_DIR, "events", f"{week_key}_all.json")
        with open(_all_path, encoding="utf-8") as _af:
            _all_data = json.load(_af)
        _all_events = _all_data.get("events", []) if isinstance(_all_data, dict) else _all_data
        if _all_events:
            _tpl = sum(
                1 for e in _all_events
                if _looks_templated(e.get("description"))
                or _looks_templated(e.get("website_description")))
            _ratio = _tpl / len(_all_events)
            if _ratio > 0.10:
                warnings.append(
                    f"[voice] {_tpl}/{len(_all_events)} ({_ratio:.0%}) website-tail descriptions are "
                    f"rule-based filler — acceptable as a floor; improve via the voice pass over time")
    except FileNotFoundError:
        warnings.append(f"[voice] no {week_key}_all.json — cannot check website copy")
    except Exception as _ve:
        warnings.append(f"[voice] website copy check failed: {_ve}")

    # ── DESCRIPTIONS / VOICE ────────────────────────────────────────────
    # "gate only what's posted": featured (slide) events + EOTW are hard-gated;
    # website-only filler events are gated as warnings (see _check_desc).
    eotw_names = {(e.get("name"), e.get("date")) for e in eotw}
    featured_names = {(e.get("name"), e.get("date")) for e in featured_all}
    for e in eotw:
        _check_desc(e, errors, warnings, is_eotw=True, posted=True)
    for e in all_shown:
        if (e.get("name"), e.get("date")) in eotw_names:
            continue
        on_slide = (e.get("name"), e.get("date")) in featured_names
        _check_desc(e, errors, warnings, is_eotw=False, posted=on_slide)

    # ── DUPLICATE COPY (the 2026-06-08 embarrassment: 6 slides shared the same
    # "Put this on your calendar and actually go..." fallback line). A repeated
    # description on the carousel is a hard defect — block it. tools/
    # dedupe_descriptions.py resolves dups before this runs, so this is a
    # structural backstop, not the primary fix.
    def _norm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())
    # Dedupe the posted set by event identity first, so the EOTW (which appears
    # in both `eotw` and `featured_all`) is never compared against itself.
    posted_events, _seen_ids = [], set()
    for e in list(eotw) + list(featured_all):
        _eid = (e.get("name"), e.get("date"), e.get("time"))
        if _eid in _seen_ids:
            continue
        _seen_ids.add(_eid)
        posted_events.append(e)
    for field, label in (("description", "short"), ("website_description", "long")):
        seen = {}
        for e in posted_events:
            key = _norm(e.get(field))
            if not key or len(key) < 25:
                continue
            if key in seen:
                errors.append(
                    f"[duplicate] {label} copy is reused on slides: "
                    f"'{seen[key]}' and '{e.get('name')}' share the same text "
                    f"— run tools/dedupe_descriptions.py")
            else:
                seen[key] = e.get("name")

    # ── HARNESS / INTERNAL MARKER LEAK (never let agent/system text post) ──
    HARNESS_MARKERS = [
        "SUPERVISOR_TASK_COMPLETE", "SUPERVISOR:", "system-reminder",
        "</system-reminder>", "TASK_COMPLETE", "As an AI", "I cannot",
        "assistant:", "<commentary>", "tool_use", "ANTHROPIC",
    ]
    def _scan_harness(text, where):
        if not text:
            return
        for m in HARNESS_MARKERS:
            if m.lower() in text.lower():
                errors.append(f"[harness-leak] {where} contains internal marker '{m}' — must NEVER post")
    for e in eotw + all_shown:
        _scan_harness(e.get("description", ""), f"'{e.get('name')}' short")
        _scan_harness(e.get("website_description", ""), f"'{e.get('name')}' long")
    # Captions: the Monday post is a claude-tier task that is itself told to emit
    # SUPERVISOR_TASK_COMPLETE, so that marker periodically leaks onto the END of
    # the generated caption. Hard-blocking the whole week's post on it is brittle
    # (post_weekly.py also strips markers at post time). So here we SELF-HEAL: cut
    # the trailing marker block, write the cleaned caption back, and warn. Only if
    # a marker survives the scrub (i.e. embedded mid-caption contamination, which
    # is genuinely unsafe) do we hard-error.
    import glob as _g2
    for cap_path in _g2.glob(os.path.join(post_dir, "*_post.json")):
        try:
            cdata = json.load(open(cap_path, encoding="utf-8"))
        except Exception:
            continue
        cap = cdata.get("caption")
        if not isinstance(cap, str) or not cap:
            continue
        cleaned = re.split(
            r"\s*(?:SUPERVISOR_TASK_COMPLETE|SUPERVISOR:|TASK_COMPLETE)\b.*$",
            cap, flags=re.S)[0].rstrip()
        if cleaned != cap:
            cdata["caption"] = cleaned
            try:
                json.dump(cdata, open(cap_path, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                warnings.append(f"[harness-leak] caption ({os.path.basename(cap_path)}) "
                                f"had a trailing internal marker — auto-scrubbed before post")
            except Exception:
                pass
        _scan_harness(cleaned, f"caption ({os.path.basename(cap_path)})")

    # ── ANONYMITY (account must never reveal who runs it) ───────────────
    for e in eotw + all_shown:
        nm = e.get("name", "?")
        _check_anonymity(e.get("description", ""), f"'{nm}' short desc", errors, warnings)
        _check_anonymity(e.get("website_description", ""), f"'{nm}' long desc", errors, warnings)
    # Scan the generated caption(s) too.
    import glob as _glob
    for cap_path in _glob.glob(os.path.join(post_dir, "*_post.json")):
        try:
            cap = json.load(open(cap_path, encoding="utf-8")).get("caption", "")
            _check_anonymity(cap, f"caption ({os.path.basename(cap_path)})", errors, warnings)
        except Exception:
            pass

    # ── LINKS ───────────────────────────────────────────────────────────
    for e in featured_all:
        url = (e.get("url") or "").strip()
        if url and not re.match(r"^https?://", url):
            errors.append(f"[links] '{e.get('name')}' has malformed URL: {url}")
    # EOTW links should actually resolve (best-effort; network issues = warning).
    try:
        import requests
        for e in eotw:
            url = (e.get("url") or "").strip()
            if not url:
                warnings.append(f"[links] EOTW '{e.get('name')}' has no URL")
                continue
            try:
                r = requests.head(url, timeout=10, allow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code >= 400:
                    r = requests.get(url, timeout=10, allow_redirects=True, stream=True,
                                     headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code >= 400:
                    warnings.append(f"[links] EOTW '{e.get('name')}' URL returned {r.status_code}: {url}")
            except Exception as ex:
                warnings.append(f"[links] EOTW '{e.get('name')}' URL not reachable ({str(ex)[:50]}): {url}")
    except ImportError:
        warnings.append("[links] requests not available — skipped live link check")

    # ── TEXT OVERFLOW / OVERLAP ─────────────────────────────────────────
    layout_path = os.path.join(post_dir, "layout_report.json")
    try:
        with open(layout_path, encoding="utf-8") as lf:
            raw = lf.read().strip()
        layout = json.loads(raw) if raw else {"warnings": []}
        for w in layout.get("warnings", []):
            errors.append(f"[overlap] slide '{w.get('slide')}': {w.get('issue')}")
    except FileNotFoundError:
        warnings.append("[overlap] no layout_report.json found — cannot confirm text fit")
    except (ValueError, OSError):
        warnings.append("[overlap] layout_report.json unreadable — cannot confirm text fit")

    return _finish(week_key, post_dir, errors, warnings)


def _finish(week_key, post_dir, errors, warnings):
    passed = len(errors) == 0
    status = {
        "week_key": week_key,
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "checked_at": None,  # stamped by caller env if needed
    }
    try:
        os.makedirs(post_dir, exist_ok=True)
        with open(os.path.join(post_dir, "preflight_status.json"), "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    print("=" * 68)
    print(f"PRE-POST PREFLIGHT - {week_key}")
    print("=" * 68)
    if errors:
        print(f"\n[X] {len(errors)} BLOCKING ERROR(S):")
        for e in errors:
            print(f"   - {e}")
    if warnings:
        print(f"\n[!] {len(warnings)} warning(s):")
        for w in warnings:
            print(f"   - {w}")
    if passed:
        print(f"\n[PASS] safe to post (with {len(warnings)} warning(s) to eyeball).")
    else:
        print(f"\n[BLOCKED] fix the {len(errors)} error(s) above before posting.")
    print("=" * 68)
    return passed


if __name__ == "__main__":
    wk = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if run(wk) else 1)
