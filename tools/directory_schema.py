"""Merge verified telephone / openingHours into the JSON-LD ItemList in docs/directory.html.

docs/directory.html is HAND-MAINTAINED: the weekly directory-scan task adds the visible
cards and the matching JSON-LD ListItems by editing the file (no generator exists).
That is why the 2026-10-27 audit found 0 telephone and 0 openingHours on every entry:
nothing ever had a place to put them. data/directory_contacts.json is that place, and
this tool merges it into the page's ItemList.

Rules (never invent a value)
  * Only entries named in data/directory_contacts.json are touched; every value there
    carries a `source` naming the file/line it was read from.
  * telephone is valid on LocalBusiness and Organization; openingHours only on
    LocalBusiness (schema.org), so an Organization entry never gets openingHours.
  * An existing value is never overwritten. A source value that disagrees with a value
    already on the page is reported as a CONFLICT (and fails --check), not applied.
  * Re-running is a no-op (idempotent). The block is re-serialised with the exact
    layout the file already uses (json.dumps indent=2), so the diff is only the
    added keys.

Usage
    python tools/directory_schema.py            # apply to docs/directory.html
    python tools/directory_schema.py --check    # exit 1 if not applied / stale / conflict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIRECTORY_HTML = REPO / "docs" / "directory.html"
CONTACTS_JSON = REPO / "data" / "directory_contacts.json"

_LD_RX = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
_PHONE_RX = re.compile(r"^\+1-\d{3}-\d{3}-\d{4}$")
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su)"
_HOURS_RX = re.compile(rf"^{_DAY}(?:-{_DAY})? \d{{2}}:\d{{2}}-\d{{2}}:\d{{2}}$")


def validate_contact(name: str, entry: dict) -> list:
    """Problems with one contacts entry (empty list = fine)."""
    problems = []
    if not isinstance(entry, dict):
        return [f"{name}: entry is not an object"]
    if not str(entry.get("source") or "").strip():
        problems.append(f"{name}: missing `source` (every value must trace to a file/line)")
    tel = entry.get("telephone")
    if tel is not None and not (isinstance(tel, str) and _PHONE_RX.match(tel)):
        problems.append(f"{name}: telephone {tel!r} is not +1-NNN-NNN-NNNN")
    hrs = entry.get("openingHours")
    if hrs is not None:
        if not (isinstance(hrs, list) and hrs and all(isinstance(h, str) and _HOURS_RX.match(h) for h in hrs)):
            problems.append(f"{name}: openingHours {hrs!r} must be a list of 'Mo-Th 06:30-22:00' strings")
        elif not str(entry.get("hours_as_of") or "").strip():
            problems.append(f"{name}: openingHours needs `hours_as_of` (when the hours were verified)")
    if tel is None and hrs is None:
        problems.append(f"{name}: has neither telephone nor openingHours")
    return problems


def load_contacts(path: Path = CONTACTS_JSON) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    contacts = data.get("contacts") or {}
    problems = []
    for name, entry in contacts.items():
        problems += validate_contact(name, entry)
    if problems:
        raise ValueError("directory_contacts.json invalid:\n  " + "\n  ".join(problems))
    return contacts


def apply_contacts(html: str, contacts: dict):
    """Return (new_html, report). report keys: applied, already, conflicts, unmatched, skipped."""
    report = {"applied": [], "already": [], "conflicts": [], "unmatched": [], "skipped": []}
    target = None
    for m in _LD_RX.finditer(html):
        try:
            data = json.loads(m.group(2))
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            target = (m, data)
            break
    if target is None:
        raise ValueError("no ItemList JSON-LD block found in directory html")
    m, data = target

    seen = set()
    for li in data.get("itemListElement", []):
        item = li.get("item") or {}
        name = item.get("name")
        entry = contacts.get(name)
        if not entry:
            continue
        seen.add(name)
        changed = False
        tel = entry.get("telephone")
        if tel:
            have = item.get("telephone")
            if have is None:
                item["telephone"] = tel
                changed = True
            elif have != tel:
                report["conflicts"].append(f"{name}: page has telephone {have}, source says {tel}")
        hrs = entry.get("openingHours")
        if hrs:
            if item.get("@type") != "LocalBusiness":
                report["skipped"].append(f"{name}: openingHours not valid on {item.get('@type')}")
            else:
                have = item.get("openingHours")
                if have is None:
                    item["openingHours"] = hrs if len(hrs) > 1 else hrs[0]
                    changed = True
                elif (have if isinstance(have, list) else [have]) != hrs:
                    report["conflicts"].append(f"{name}: page has openingHours {have}, source says {hrs}")
        (report["applied"] if changed else report["already"]).append(name)

    report["unmatched"] = sorted(set(contacts) - seen)

    raw = m.group(2)
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    new_block = m.group(1) + lead + json.dumps(data, indent=2, ensure_ascii=False) + trail + m.group(3)
    new_html = html[: m.start()] + new_block + html[m.end():]
    return new_html, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if out of sync")
    ap.add_argument("--file", default=str(DIRECTORY_HTML))
    ap.add_argument("--contacts", default=str(CONTACTS_JSON))
    args = ap.parse_args(argv)

    contacts = load_contacts(Path(args.contacts))
    path = Path(args.file)
    raw = path.read_bytes()
    crlf = b"\r\n" in raw          # the repo's working tree is CRLF on Windows: keep it
    html = raw.decode("utf-8").replace("\r\n", "\n")
    new_html, rep = apply_contacts(html, contacts)

    print(f"directory contacts: {len(contacts)} sourced entries | "
          f"applied {len(rep['applied'])} | already present {len(rep['already'])} | "
          f"conflicts {len(rep['conflicts'])} | unmatched {len(rep['unmatched'])} | "
          f"skipped {len(rep['skipped'])}")
    for key in ("conflicts", "unmatched", "skipped"):
        for line in rep[key]:
            print(f"  [{key}] {line}")

    bad = bool(rep["conflicts"] or rep["unmatched"])
    if args.check:
        stale = new_html != html
        if stale:
            print("  [check] directory.html is missing sourced values; run without --check")
        return 1 if (bad or stale) else 0
    if rep["conflicts"]:
        print("  refusing to write while conflicts exist")
        return 1
    if new_html != html:
        out = new_html.replace("\n", "\r\n") if crlf else new_html
        path.write_bytes(out.encode("utf-8"))
        print(f"  wrote {path}")
    else:
        print("  no change (already in sync)")
    return 1 if rep["unmatched"] else 0


if __name__ == "__main__":
    sys.exit(main())
