"""Run every line in data/holiday_themes.json through the real preflight rules:
BANNED_PHRASES, TEMPLATE_SIGNATURES, the anonymity check, and the no-em-dash rule.
Exit 0 only if every line is clean."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import preflight_post as pf

themes = json.load(open(os.path.join(ROOT, "data", "holiday_themes.json"), encoding="utf-8"))["themes"]
lines = []
for t in themes:
    for k in ("taglines", "footer_note", "closing_line", "caption_line"):
        v = t.get(k)
        lines += [(t["key"], k, x) for x in (v if isinstance(v, list) else [v]) if x]

bad = []
for key, field, text in lines:
    low = text.lower()
    for ph in pf.BANNED_PHRASES:
        if ph.lower() in low:
            bad.append(f"{key}.{field}: banned phrase '{ph}'")
    for sig in getattr(pf, "TEMPLATE_SIGNATURES", []):
        if isinstance(sig, str) and sig.lower() in low:
            bad.append(f"{key}.{field}: template signature '{sig}'")
    if "—" in text or "–" in text:
        bad.append(f"{key}.{field}: dash")
    errs, warns = [], []
    pf._check_anonymity(text, f"{key}.{field}", errs, warns)
    bad += errs
print(f"{len(lines)} seasonal lines checked against preflight; problems: {bad or 'none'}")
sys.exit(1 if bad else 0)
