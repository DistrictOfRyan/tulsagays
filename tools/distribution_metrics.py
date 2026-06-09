"""
Weekly distribution metrics for the TulsaGays auto-distribution engine
(nextlevel Rung 1: Measured & Optimized).

Closes the loop on "did it actually go out, and how far." Aggregates each week's
ledgers into one row and appends to data/distribution_scores.jsonl so reach +
delivery health is trackable over time and feedable into tuning. Honest about
blocked data sources: FB/IG follower-level insights need pages_read_engagement /
instagram_manage_insights (Meta App Review), so this measures what's reliably
available — channel delivery + group reach counts + content volume — not vanity
follower metrics.

Tracks per week:
  fb_posted, ig_posted, website_updated (from post_results + git)
  groups_live, groups_pending, groups_skipped, groups_total (group_blast_results)
  events_featured, events_total (slide_manifest)
  preflight_passed

Usage: python tools/distribution_metrics.py [WEEK_KEY]   (defaults to current week)
Prints a digest + appends the row. Idempotent per (week) — re-running updates.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

LOG = ROOT / "data" / "distribution_scores.jsonl"


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def collect(week_key):
    d = ROOT / "data" / "posts" / week_key
    row = {"week": week_key, "ts": datetime.now().isoformat(timespec="seconds")}

    pr = _load(d / "post_results.json") or {}
    fb = pr.get("fb_post_id", "")
    ig = pr.get("ig_post_id", "")
    row["fb_posted"] = bool(fb) and "dry" not in str(fb).lower() and "fail" not in str(fb).lower()
    row["ig_posted"] = bool(ig) and "skip" not in str(ig).lower() and "fail" not in str(ig).lower()

    gb = _load(d / "group_blast_results.json") or {}
    counts = gb.get("counts", {}) if isinstance(gb, dict) else {}
    row["groups_live"] = counts.get("live", 0)
    row["groups_pending"] = counts.get("pending", 0)
    row["groups_skipped"] = counts.get("skipped", 0)
    row["groups_error"] = counts.get("error", 0)
    row["groups_submitted"] = row["groups_live"] + row["groups_pending"]

    man = _load(d / "slide_manifest.json") or {}
    feat = man.get("featured_by_day", {})
    row["events_featured"] = sum(len(v) for v in feat.values()) if isinstance(feat, dict) else 0
    row["events_total"] = len(man.get("all_shown", []))

    pf = _load(d / "preflight_status.json") or {}
    row["preflight_passed"] = (len(pf.get("errors", [])) == 0) if pf else None

    # composite reach proxy: channels delivered (page/IG/site) + groups submitted
    row["channels_delivered"] = sum([row["fb_posted"], row["ig_posted"]])
    return row


def write_row(row):
    # dedupe by week: drop any prior row for this week, append the new one
    existing = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("week") != row["week"]:
                    existing.append(r)
            except Exception:
                continue
    existing.append(row)
    LOG.write_text("\n".join(json.dumps(r) for r in existing) + "\n", encoding="utf-8")


def main():
    wk = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else config.current_week_key()
    row = collect(wk)
    write_row(row)
    print(f"=== Distribution metrics — {wk} ===")
    print(f"  FB page posted:   {row['fb_posted']}")
    print(f"  Instagram posted: {row['ig_posted']}")
    print(f"  Groups: {row['groups_submitted']} submitted "
          f"({row['groups_live']} live + {row['groups_pending']} pending), "
          f"{row['groups_skipped']} skipped, {row['groups_error']} error")
    print(f"  Events: {row['events_featured']} featured / {row['events_total']} on site")
    print(f"  Preflight passed: {row['preflight_passed']}")
    print(f"  -> logged to {LOG.name}")
    print("  NOTE: follower-level FB/IG insights need Meta App Review (blocked); "
          "this tracks delivery + group reach, the reliably-available signals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
