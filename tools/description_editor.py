"""
Editorial quality pass for event descriptions (nextlevel Rung 5).

Scores each posted (featured/EOTW) description 0-100 against the TulsaGays voice
bar, rewrites the weakest deterministically (venue tip + on-voice variation), and
logs the weekly score distribution so quality is trackable over time. This is the
"self-improving editor" — minus the engagement-weighting half, which is BLOCKED
behind Meta Insights API Review (instagram_manage_insights). That half is stubbed:
if data/engagement_signals.json ever exists, scores fold it in; until then the
heuristic score stands alone.

Heuristic score (no LLM needed, so it runs reliably every week):
  + in slide-length band, + second-person voice markers, + concrete specificity
  (venue/lineup/time), - templated signatures, - banned phrases, - em dashes.

API:
    score(event) -> (int 0-100, list[str] reasons)
    edit_weak(events, threshold=55) -> dict   # rewrites featured below threshold
    run(week_key=None) -> dict                # full weekly pass + score log
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

SCORE_LOG = ROOT / "data" / "description_scores.jsonl"
ENGAGEMENT = ROOT / "data" / "engagement_signals.json"  # future (Meta-blocked)

# Single source of truth: preflight's signature list (drifted copies meant the
# editor scored "main-character energy" filler 97/100 while preflight blocked
# on it — found in the 2026-07-06 Monday dress rehearsal).
try:
    from tools.preflight_post import TEMPLATE_SIGNATURES as TEMPLATE_SIGS
except Exception:
    TEMPLATE_SIGS = [
        "put this on your calendar and actually go", "the people in that room are your people",
        "arrive before it starts. find a spot", "clear your calendar, because",
        "here is your permission slip", "nobody ever regretted going to",
        "if you do one thing this week", "is calling and the answer is yes",
        "do future-you a favor", "treat yourself to",
    ]
BANNED = ["vibrant community", "safe space", "don't miss out", "something for everyone",
          "whether you're", "whether you are", "nestled",
          "make sure to go", "actually go", "put this on your calendar",
          "you will thank yourself", "zero excuses"]
VOICE = ["you", "your", "go ", "get ", "honey", "girl", "darling", "show up"]


def score(event):
    short = (event.get("description") or "").strip()
    longd = (event.get("website_description") or "").strip()
    text = (short + " " + longd).strip()
    low = text.lower()
    reasons, s = [], 50
    if not short:
        return 0, ["no short description"]
    # length band
    if 40 <= len(short) <= 200:
        s += 10
    else:
        reasons.append(f"short len {len(short)} out of 40-200 band")
    # voice markers
    if any(v in low for v in VOICE):
        s += 10
    else:
        s -= 15; reasons.append("no second-person/encouraging voice markers")
    # templated
    if any(sig in low for sig in TEMPLATE_SIGS):
        s -= 35; reasons.append("uses templated/fallback copy")
    else:
        s += 15
    # banned
    if any(b in low for b in BANNED):
        s -= 20; reasons.append("uses a banned phrase")
    # em dash
    if "—" in text:
        s -= 15; reasons.append("contains an em dash")
    # specificity: venue, a time, or a proper-noun-ish detail
    if (event.get("venue") and event["venue"].split(",")[0].strip().lower() in low) \
            or re.search(r"\b\d{1,2}\s?(am|pm)\b", low) or re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", text):
        s += 15
    else:
        reasons.append("low specificity (no venue/time/name detail)")
    # engagement stub (Meta-blocked) — fold in if a signals file appears
    if ENGAGEMENT.exists():
        try:
            sig = json.loads(ENGAGEMENT.read_text(encoding="utf-8"))
            key = event.get("name", "")
            if key in sig:
                s += int(sig[key].get("boost", 0))
                reasons.append(f"engagement boost {sig[key].get('boost', 0)}")
        except Exception:
            pass
    return max(0, min(100, s)), reasons


def edit_weak(events, threshold=55, posted_only=True):
    from tools.dedupe_descriptions import _unique_desc, _norm
    seen = set()
    fixed = []
    # seed seen with current good descriptions to keep uniqueness
    for e in events:
        k = _norm(e.get("description"))
        if k:
            seen.add(k)
    for e in events:
        if posted_only and not (e.get("featured") or e.get("is_eotw") or e.get("eotw")):
            # caller decides which are posted; default scores all if flags absent
            pass
        sc, reasons = score(e)
        if sc < threshold:
            for salt in range(1, 40):
                cand = _unique_desc(e, f"editor{salt}", long=False)
                if _norm(cand) not in seen:
                    old = e.get("description", "")
                    e["description"] = cand
                    seen.discard(_norm(old))
                    seen.add(_norm(cand))
                    new_sc, _ = score(e)
                    fixed.append({"name": e.get("name"), "from_score": sc,
                                  "to_score": new_sc})
                    break
    return {"rewritten": len(fixed), "detail": fixed}


def run(week_key=None):
    week_key = week_key or config.current_week_key()
    path = Path(config.DATA_DIR) / "events" / f"{week_key}_all.json"
    if not path.exists():
        return {"ok": False, "error": f"no events file {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", [])
    scores = [score(e)[0] for e in events if (e.get("description") or "").strip()]
    res = edit_weak(events)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    dist = {
        "week": week_key,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n": len(scores),
        "avg": round(sum(scores) / len(scores), 1) if scores else 0,
        "below_55": sum(1 for s in scores if s < 55),
        "rewritten": res["rewritten"],
    }
    with open(SCORE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dist) + "\n")
    return {"ok": True, **dist}


if __name__ == "__main__":
    if "--run" in sys.argv:
        print(json.dumps(run(), indent=2))
    else:
        # self-test on exemplars
        gold = json.loads((ROOT / "data" / "gold_descriptions.json").read_text(encoding="utf-8"))
        for ex in gold["exemplars"]:
            sc, r = score({"name": "X", "venue": "Club", "description": ex["short"],
                           "website_description": ex["long"]})
            print(f"GOLD {ex['type']:10} score={sc}")
        bad = {"name": "Y", "venue": "Z", "description": "Put this on your calendar and actually go."}
        print("BAD templated score=", score(bad)[0], score(bad)[1])
