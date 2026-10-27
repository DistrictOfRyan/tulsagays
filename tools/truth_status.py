"""Which rows count as POSITIVELY CONFIRMED for a featured / EOTW slot.

One implementation, shared by everything that has an opinion about it:

  tools/preflight_post.py   the gate (blocks a featured/EOTW row that is not confirmed)
  main.py                   the featured picker (prefers confirmed rows)
  eotw_selector.py          the Event-of-the-Week pick (prefers confirmed rows)
  tools/auto_fix_deck.py    the healer (demotes unconfirmed featured rows)
  tools/auto_verify_featured.py and the prep degrade ladder

Why it exists (2026-10-27). W40, W41, W42, W43 and W44 all blocked at preflight on
the same rule: "featured/EOTW '<name>' is not confirmed by its source or a recorded
human check". The gate had a definition of "confirmed"; the picker had none, so
every Monday it featured whatever ranked as most fun and the gate then refused a
different unconfirmable filler (W44: 'Intersex Awareness Day', 'TAFF 2024',
'Sunset Cinema: FILMAGE' ...) while 105 machine-confirmed rows sat unused. A picker
and a gate that disagree about the same fact guarantee a block, so they now read it
from here.

A row is CONFIRMED when any of these holds (exactly the preflight rule):
  1. (name, date) is in data/posts/<week>/truth_report.json "confirmed"
     (tools/verify_week_truth.py read the source and it agreed);
  2. the row carries human_verified.evidence_url (and action != "hidden"),
     on the row itself or on its record in data/events/<week>_all.json;
  3. it is a recurring event tracked FRESH or STALE in
     data/recurring_confirmations.json (matched by name).

FEATURABLE = confirmed and not EXPIRED in that recurring ledger (preflight
separately hard-blocks an expired recurring row even when it is confirmed).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import config  # noqa: E402


def _key(e: dict) -> tuple:
    return (e.get("name"), e.get("date"))


class TruthStatus:
    def __init__(self, week_key: str, confirmed_keys: set, rows_by_key: dict,
                 report_present: bool, report_has_confirmed: bool, ledger=None,
                 today: str | None = None):
        self.week_key = week_key
        self.confirmed_keys = confirmed_keys
        self.rows_by_key = rows_by_key
        self.report_present = report_present
        self.report_has_confirmed = report_has_confirmed
        self._ledger = ledger
        self._today = today or date.today().isoformat()

    # -- the three proofs ---------------------------------------------------
    def human_verified(self, e: dict) -> bool:
        hv = e.get("human_verified") or (self.rows_by_key.get(_key(e)) or {}).get("human_verified") or {}
        return bool(hv.get("evidence_url")) and hv.get("action") != "hidden"

    def _tier(self, e: dict):
        if self._ledger is None:
            return False, "untracked"
        try:
            from scraper.recurring_verify import lookup_tier
            is_tracked, tier, _, _ = lookup_tier(e.get("name") or "", self._today, self._ledger)
            return is_tracked, tier
        except Exception:
            return False, "untracked"

    def ledger_fresh(self, e: dict) -> bool:
        is_tracked, tier = self._tier(e)
        return is_tracked and tier in ("fresh", "stale")

    def expired(self, e: dict) -> bool:
        is_tracked, tier = self._tier(e)
        return is_tracked and tier == "expired"

    # -- verdicts -----------------------------------------------------------
    def confirmed(self, e: dict) -> bool:
        """Exactly what preflight's truth gate accepts for a featured/EOTW slot."""
        return (_key(e) in self.confirmed_keys
                or self.human_verified(e)
                or self.ledger_fresh(e))

    def featurable(self, e: dict) -> bool:
        """Safe to feature as far as the truth + recurring gates are concerned."""
        return self.confirmed(e) and not self.expired(e)


def load(week_key: str | None = None) -> TruthStatus:
    week_key = week_key or config.current_week_key()
    post_dir = os.path.join(config.DATA_DIR, "posts", week_key)
    truth_path = os.path.join(post_dir, "truth_report.json")
    confirmed, present, has_conf = set(), False, False
    try:
        with open(truth_path, encoding="utf-8") as f:
            tr = json.load(f)
        present = True
        has_conf = "confirmed" in tr
        confirmed = {(c.get("name"), c.get("date")) for c in tr.get("confirmed", []) or []}
    except FileNotFoundError:
        pass
    except Exception:
        present = True   # exists but unreadable: preflight blocks it; confirm nothing here
    rows = {}
    try:
        with open(os.path.join(config.EVENTS_DIR, f"{week_key}_all.json"), encoding="utf-8") as f:
            raw = json.load(f)
        raw = raw.get("events", []) if isinstance(raw, dict) else raw
        rows = {_key(e): e for e in raw if isinstance(e, dict)}
    except Exception:
        rows = {}
    try:
        from scraper.recurring_verify import load_ledger
        ledger = load_ledger()
    except Exception:
        ledger = None
    return TruthStatus(week_key, confirmed, rows, present, has_conf, ledger)


# A row we must never demote just because a machine could not read its source:
# William's own pins and paid/partner deals, and the flagship marquee nights.
def protected_from_demotion(e: dict, week_key: str | None = None) -> str | None:
    """Return why this row is exempt from automatic truth demotion, or None.

    Exempt: a data/manual_eotw.json pin for the week, an active partner in
    data/featured_partners.json, or a _FLAGSHIP_KEYWORDS match (scraper/runner.py).
    The healer's final round demotes every other unconfirmed featured row."""
    name = (e.get("name") or "").lower()
    try:
        from eotw_selector import load_manual_eotw, _partner_of, _load_partner_matchers
        for m in load_manual_eotw(week_key or config.current_week_key()):
            frag = (m.get("match") or "").lower()
            if frag and frag in ((e.get("name") or "") + " " + (e.get("source") or "")).lower():
                if not m.get("date") or m.get("date") == e.get("date"):
                    return f"manual_eotw pin '{frag}'"
        p = _partner_of(e, _load_partner_matchers())
        if p:
            return f"featured partner '{p}'"
    except Exception:
        pass
    # NAME only: runner's flagship test also reads the description, but "festival"
    # somewhere in a scraped blurb is not a reason to keep an unverified row on a slide.
    try:
        from scraper.runner import _FLAGSHIP_KEYWORDS
        for kw in _FLAGSHIP_KEYWORDS:
            if kw in f" {name} ":
                return f"flagship keyword '{kw.strip()}'"
    except Exception:
        pass
    return None


def _selftest() -> int:
    ts = TruthStatus(
        "2026-W44",
        confirmed_keys={("A", "2026-10-26")},
        rows_by_key={("B", "2026-10-27"): {"name": "B", "date": "2026-10-27",
                                           "human_verified": {"evidence_url": "https://x"}},
                     ("H", "2026-10-27"): {"name": "H", "date": "2026-10-27",
                                           "human_verified": {"evidence_url": "https://x",
                                                              "action": "hidden"}}},
        report_present=True, report_has_confirmed=True, ledger=None)
    assert ts.confirmed({"name": "A", "date": "2026-10-26"})
    assert not ts.confirmed({"name": "A", "date": "2026-10-27"}), "date is part of the key"
    assert ts.confirmed({"name": "B", "date": "2026-10-27"}), "human_verified on the _all.json row"
    assert not ts.confirmed({"name": "H", "date": "2026-10-27"}), "a hidden verification is not a proof"
    assert ts.confirmed({"name": "Z", "date": "2026-10-28",
                         "human_verified": {"evidence_url": "https://y"}}), "evidence on the row itself"
    assert not ts.confirmed({"name": "Z", "date": "2026-10-28"})
    assert ts.featurable({"name": "A", "date": "2026-10-26"})
    print("truth_status selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    wk = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    st = load(wk)
    print(json.dumps({"week": st.week_key, "report_present": st.report_present,
                      "confirmed_rows": len(st.confirmed_keys),
                      "human_verified_rows": sum(1 for r in st.rows_by_key.values()
                                                 if st.human_verified(r))}, indent=2))
