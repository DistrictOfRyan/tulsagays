"""Post-run success gate for the weekly Monday carousel.

The 2026-06-15 failure logged "OK rc=0" while nothing was scraped, built, or
posted. rc=0 only means the agent ended its turn cleanly, NOT that the pipeline
succeeded. This verifier checks the ACTUAL artifacts so a silent failure exits
non-zero and the task runner marks it FAILED (and alerts/retries) instead of
recording a false success.

Usage:
  python tools/postrun_verify.py --phase build   # after slides are generated
  python tools/postrun_verify.py --phase post    # after FB/IG/groups posting
  python tools/postrun_verify.py                  # both phases

Exit 0 = every checked artifact is present and valid. Exit 1 = real failure.
"""
import argparse, json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
try:
    from tools.preflight_post import _looks_templated
except Exception:
    def _looks_templated(_t):
        return False


def _build_checks(week, data_dir):
    errs = []
    post_dir = os.path.join(data_dir, "posts", week)
    # 1. nine slides, each a real (non-blank) PNG
    slides = [f"all__{i:02d}.png" for i in range(1, 10)]
    present = [s for s in slides if os.path.exists(os.path.join(post_dir, s))]
    if len(present) < 9:
        errs.append(f"only {len(present)}/9 carousel slides exist in {post_dir}")
    for s in present:
        if os.path.getsize(os.path.join(post_dir, s)) < 30 * 1024:
            errs.append(f"slide {s} is {os.path.getsize(os.path.join(post_dir, s))//1024}KB (<30KB, likely blank)")
    # 2. manifest: every day >=3 featured, and featured copy is real (not templated)
    man_path = os.path.join(post_dir, "slide_manifest.json")
    if not os.path.exists(man_path):
        errs.append("slide_manifest.json missing")
        return errs
    man = json.load(open(man_path, encoding="utf-8"))
    fbd = man.get("featured_by_day", {})
    if len(fbd) < 7:
        errs.append(f"manifest has {len(fbd)}/7 days")
    tpl = 0
    feat = 0
    for day, evs in fbd.items():
        if len(evs) < 3:
            errs.append(f"{day} has only {len(evs)} featured event(s) (need >=3)")
        for e in evs:
            feat += 1
            if _looks_templated(e.get("description")) or _looks_templated(e.get("website_description")):
                tpl += 1
    if feat and tpl / feat > 0.25:
        errs.append(f"{tpl}/{feat} featured blurbs are templated filler — the voice pass (Step 2.1) did not run")
    return errs


def _post_checks(week, data_dir):
    errs = []
    ds = os.path.join(data_dir, "distribution_scores.jsonl")
    if not os.path.exists(ds):
        errs.append("distribution_scores.jsonl missing — posting/metrics never ran")
        return errs
    rows = [json.loads(l) for l in open(ds, encoding="utf-8") if l.strip()]
    wk_rows = [r for r in rows if r.get("week") == week]
    if not wk_rows:
        errs.append(f"no distribution_scores entry for {week} — the carousel was NOT posted this week")
        return errs
    last = wk_rows[-1]
    if not (last.get("fb_posted") or last.get("ig_posted") or last.get("groups_live")):
        errs.append(f"{week} distribution row shows no successful FB/IG/group delivery: {last}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["build", "post", "all"], default="all")
    ap.add_argument("--week", default=None)
    args = ap.parse_args()
    week = args.week or config.current_week_key()
    data_dir = config.DATA_DIR

    errs = []
    if args.phase in ("build", "all"):
        errs += _build_checks(week, data_dir)
    if args.phase in ("post", "all"):
        errs += _post_checks(week, data_dir)

    print(f"=== POST-RUN VERIFY {week} (phase={args.phase}) ===")
    if errs:
        print(f"[X] FAILED — {len(errs)} problem(s):")
        for e in errs:
            print(f"   - {e}")
        sys.exit(1)
    print("[OK] all checks passed — the run produced what it claims.")
    sys.exit(0)


if __name__ == "__main__":
    main()
