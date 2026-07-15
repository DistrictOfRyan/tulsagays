#!/usr/bin/env python3
"""Directory-submission dedupe guard + reconciler (gap G109).

Two `directory_submissions.json` tracking files had diverged:
  - CANONICAL (repo):   C:/Users/willi/tulsagays/data/directory_submissions.json
  - ORPHAN (mirror):    C:/Users/willi/claude-ops/tulsagays/directory_submissions.json
The orphan was an older, flat `pending_review` list of ~132 directories; the
canonical file is the curated, richly-statused SSOT the monthly
`tulsagays-directory-submissions` task actually reads/writes. Because the two
diverged AND the task deduped on EXACT directory name, variant spellings slipped
the guard and were re-pitched: "Gay Travel Info" went out twice and OKEQ was hit
3-4x under names like "OKEQ Community Partner Resources",
"Oklahomans for Equality Community Resources", "OKEQ Equality Business Alliance".

This module fixes both halves:
  1. `canonical_key()` — normalizes a directory name (case, punctuation,
     parentheticals, org aliases) so variants collapse to one key.
  2. `already_contacted()` — the DEDUPE GUARD. True if a canonical match with a
     decided status exists, so a re-pitch is refused.
  3. `reconcile()` — merges the orphan's unique directories into the canonical
     SSOT (variants collapsed, decided statuses preserved), producing ONE file.

The canonical file is the single source of truth. The orphan is deprecated and
must not be read by any task (see `_meta.deprecated_mirrors`).

CLI:
  python tools/directory_dedupe.py --selftest
  python tools/directory_dedupe.py --reconcile [--dry-run]
  python tools/directory_dedupe.py --check "Some Directory Name"
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_FILE = REPO_ROOT / "data" / "directory_submissions.json"
# Orphan mirror is OUTSIDE the repo. We READ it once to reconcile, never write it.
ORPHAN_FILE = Path(os.path.expanduser("~")) / "claude-ops" / "tulsagays" / "directory_submissions.json"

# Statuses that mean "a decision was already made — do NOT pitch again".
DECIDED_STATUSES = {
    "submitted", "listed", "queued_william", "editorial_pitch",
    "paid_skip", "poor_fit", "no_submission_form",
}
# Statuses that mean "still open — pitching is allowed".
OPEN_STATUSES = {"research_needed", "pending_review", "", None}

# Map an orphan status onto the canonical status legend (conservative: only
# preserve a genuinely-decided status; treat vague "pending_review" as open
# research so we don't falsely believe outreach completed).
_STATUS_MAP = {
    "submitted": "submitted",
    "listed": "listed",
    "requires_payment": "paid_skip",
    "paid_skip": "paid_skip",
    "no_submission_form": "no_submission_form",
    "needs_manual_submission": "queued_william",
    "queued_william": "queued_william",
    "editorial_pitch": "editorial_pitch",
    "poor_fit": "poor_fit",
    "pending_review": "research_needed",
    "research_needed": "research_needed",
}

# Org alias resolution: any canonical string CONTAINING a trigger collapses to
# the mapped key. Order matters (first hit wins). This is what stops OKEQ /
# TravelGay / TravelOK / do918 variants from multiplying.
_ALIAS_CONTAINS = [
    ("oklahomans for equality", "okeq"),
    ("okeq", "okeq"),
    ("travel gay", "travelgay"),
    ("travelgay", "travelgay"),
    ("travelok", "travelok"),
    ("travel oklahoma", "travelok"),
    ("oklahoma tourism", "travelok"),
    ("visit tulsa", "visit tulsa"),
    ("gay travel information", "gay travel information"),
    ("gaytravelinformation", "gay travel information"),
    ("do918", "downtown tulsa do918"),
    ("downtown tulsa", "downtown tulsa do918"),
    ("everywhere is queer", "everywhere is queer"),
    ("purple roofs", "purple roofs"),
    ("damron", "damron"),
    ("out traveler", "out traveler"),
    ("lgbtq nation", "lgbtq nation"),
    ("my gay travel guide", "my gay travel guide"),
    ("gay destinations", "gay destinations"),
    ("rainbow index", "rainbow index"),
    ("gaycities", "gaycities"),
    ("equaldex", "equaldex"),
    ("patch tulsa", "patch tulsa"),
]


def canonical_key(name: str) -> str:
    """Normalize a directory name to a dedupe key.

    Lowercases, expands '&', strips parentheticals and punctuation, collapses
    whitespace, then applies the org-alias map so known variants converge.
    """
    if not name:
        return ""
    s = name.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)          # drop (parentheticals)
    s = s.replace("--", " ")                 # em-dash-as-double-hyphen separators
    s = re.sub(r"[^a-z0-9]+", " ", s)        # punctuation -> space
    s = re.sub(r"\s+", " ", s).strip()
    for trigger, key in _ALIAS_CONTAINS:
        if trigger in s:
            return key
    return s


def already_contacted(history: dict, name: str) -> bool:
    """DEDUPE GUARD: True if `name` (by canonical key) already has a decided
    status in history. Call this BEFORE any new outreach to a directory."""
    key = canonical_key(name)
    for s in history.get("submissions", []):
        if canonical_key(s.get("directory", "")) == key and s.get("status") in DECIDED_STATUSES:
            return True
    return False


def find_entry(history: dict, name: str):
    """Return the existing submission dict matching `name` by canonical key, or None."""
    key = canonical_key(name)
    for s in history.get("submissions", []):
        if canonical_key(s.get("directory", "")) == key:
            return s
    return None


def load_history(path=CANONICAL_FILE) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"submissions": []}


def _status_rank(status) -> int:
    """Higher = more authoritative. Decided > open, listed > submitted."""
    order = {"listed": 5, "submitted": 4, "queued_william": 3, "editorial_pitch": 3,
             "paid_skip": 3, "poor_fit": 3, "no_submission_form": 2,
             "research_needed": 1, "pending_review": 1, "": 0, None: 0}
    return order.get(status, 1)


def reconcile(canonical_path=CANONICAL_FILE, orphan_path=ORPHAN_FILE, dry_run=False):
    """Merge the orphan mirror's unique directories into the canonical SSOT.

    - Canonical entries always win (curated, richer). Never overwritten.
    - Orphan-only directories are appended (compact, status-mapped, tagged
      `imported_from`). Variants collapse via canonical_key.
    - Internal orphan duplicates collapse to the highest-ranked status.
    Returns a summary dict.
    """
    canon = load_history(canonical_path)
    canon.setdefault("submissions", [])
    # index existing canonical entries by key
    existing = {}
    for s in canon["submissions"]:
        existing.setdefault(canonical_key(s.get("directory", "")), s)

    imported, skipped_dup, collapsed = [], 0, 0
    if Path(orphan_path).exists():
        with open(orphan_path, encoding="utf-8") as f:
            orphan = json.load(f)
        staged = {}  # key -> best orphan entry to import
        for s in orphan.get("submissions", []):
            key = canonical_key(s.get("directory", ""))
            if not key:
                continue
            if key in existing:
                skipped_dup += 1
                continue
            prev = staged.get(key)
            if prev is None:
                staged[key] = s
            else:
                collapsed += 1
                if _status_rank(s.get("status")) > _status_rank(prev.get("status")):
                    staged[key] = s
        for key, s in staged.items():
            mapped = _STATUS_MAP.get(s.get("status"), "research_needed")
            note = (s.get("notes") or "").strip()
            if len(note) > 400:
                note = note[:397] + "..."
            imported.append({
                "directory": s.get("directory", ""),
                "url": s.get("url"),
                "status": mapped,
                "canonical_key": key,
                "imported_from": "claude-ops-mirror (reconciled 2026-07-15, gap G109)",
                "original_status": s.get("status"),
                "notes": note,
            })

    canon["submissions"].extend(imported)
    # declare SSOT + deprecate the mirror so divergence can't recur silently
    meta = canon.setdefault("_meta", {})
    meta["canonical_source"] = str(canonical_path).replace("\\", "/")
    meta["deprecated_mirrors"] = [str(orphan_path).replace("\\", "/")]
    meta["dedupe_guard"] = "tools/directory_dedupe.py :: already_contacted() — call before any outreach"
    meta["reconciled"] = "2026-07-15"

    summary = {
        "canonical_before": len(existing),
        "orphan_skipped_as_dup": skipped_dup,
        "orphan_variants_collapsed": collapsed,
        "imported": len(imported),
        "canonical_after": len(canon["submissions"]),
    }
    if not dry_run:
        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(canon, f, indent=1, ensure_ascii=False)
    return summary


def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS" if cond else "FAIL") + " " + msg)
        ok = ok and cond

    # canonical key collapses the real-world variants that caused G109
    check(canonical_key("OKEQ Community Partner Resources")
          == canonical_key("Oklahomans for Equality Community Resources")
          == canonical_key("Oklahomans for Equality -- Arts, Entertainment & Media")
          == canonical_key("OKEQ Equality Business Alliance"),
          "all OKEQ variants collapse to one key")
    check(canonical_key("Travel Gay") == canonical_key("TravelGay"),
          "Travel Gay == TravelGay")
    check(canonical_key("TravelOK (Oklahoma Tourism)") == canonical_key("TravelOK"),
          "TravelOK variants collapse")
    check(canonical_key("Gay Travel Information") == canonical_key("gaytravelinformation.com listing")
          == "gay travel information", "Gay Travel Info variants collapse")
    check(canonical_key("Downtown Tulsa Partnership (do918/Downtown Tulsa calendar)")
          == canonical_key("Do918") == canonical_key("Downtown Tulsa Calendar"),
          "do918 / Downtown Tulsa variants collapse")
    check(canonical_key("Visit Tulsa (PartnerNet)") == canonical_key("Visit Tulsa"),
          "Visit Tulsa variants collapse")
    # distinct directories stay distinct
    check(canonical_key("GayCities") != canonical_key("Gay Destinations"),
          "distinct directories keep distinct keys")

    # dedupe guard blocks a decided variant, allows an open one
    hist = {"submissions": [
        {"directory": "Gay Travel Information", "status": "submitted"},
        {"directory": "Purple Roofs", "status": "research_needed"},
    ]}
    check(already_contacted(hist, "gaytravelinformation.com") is True,
          "guard blocks re-pitch of a decided variant")
    check(already_contacted(hist, "Purple Roofs") is False,
          "guard allows an open (research_needed) directory")
    check(already_contacted(hist, "Brand New Directory") is False,
          "guard allows a never-seen directory")

    print("SELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(_selftest())
    if "--check" in args:
        i = args.index("--check")
        name = args[i + 1]
        h = load_history()
        print(f"canonical_key: {canonical_key(name)!r}")
        print(f"already_contacted: {already_contacted(h, name)}")
        e = find_entry(h, name)
        print(f"existing entry: {e.get('directory') + ' / ' + str(e.get('status')) if e else 'none'}")
        sys.exit(0)
    if "--reconcile" in args:
        dry = "--dry-run" in args
        s = reconcile(dry_run=dry)
        print(("DRY-RUN " if dry else "") + "reconcile summary:")
        print(json.dumps(s, indent=1))
        sys.exit(0)
    print(__doc__)
    sys.exit(0)
