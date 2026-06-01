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


def _check_desc(ev, errors, warnings, is_eotw=False):
    name = ev.get("name", "?")
    short = (ev.get("description") or "").strip()
    longd = (ev.get("website_description") or "").strip()
    tag = "EOTW" if is_eotw else "event"
    if not short:
        errors.append(f"[desc] {tag} '{name}' has NO short description")
    if not longd:
        errors.append(f"[desc] {tag} '{name}' has NO website (long) description")
    for field, txt in (("short", short), ("long", longd)):
        low = txt.lower()
        if "—" in txt or " - - " in txt:
            errors.append(f"[voice] {tag} '{name}' {field} contains an em dash")
        for p in BANNED_PHRASES:
            if p in low:
                errors.append(f"[voice] {tag} '{name}' {field} uses banned phrase '{p}'")
        for rx in ARTIFACT_PATTERNS:
            if rx.search(txt):
                errors.append(f"[voice] {tag} '{name}' {field} looks like raw scraper text / junk")
                break
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

    # ── DESCRIPTIONS / VOICE ────────────────────────────────────────────
    eotw_names = {(e.get("name"), e.get("date")) for e in eotw}
    for e in eotw:
        _check_desc(e, errors, warnings, is_eotw=True)
    for e in all_shown:
        if (e.get("name"), e.get("date")) in eotw_names:
            continue
        _check_desc(e, errors, warnings, is_eotw=False)

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
