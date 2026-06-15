"""run_weekly.py — single-command weekly carousel orchestrator.

WHY THIS EXISTS (2026-06-15): the Monday post failed because the agent
backgrounded the scrape and yielded, expecting a wakeup that never comes in a
headless `claude -p` run — rc=0, nothing posted. Every downstream step (website,
FB/IG, groups) was silently skipped. This orchestrator removes that whole class
of failure:

  * Each phase is ONE blocking process — the agent runs it and waits. There is
    nothing to background, so the background-and-yield trap cannot happen.
  * Steps are chained deterministically, so the website / groups / verify can
    never be "forgotten."
  * Any real failure exits NON-ZERO and stops the chain, so the task runner
    records FAILED instead of a false "OK rc=0."

Usage (the only two commands the Monday agent runs, with the voice pass between):

  python run_weekly.py --pre     # scrape -> clean -> generate (fast rule-based)
  #   ... then the agent writes the featured/EOTW blurbs in-voice (Step 2.1) ...
  python run_weekly.py --post    # preflight -> website -> FB/IG -> groups -> verify

Add --dry to --post to do everything EXCEPT actually posting (preflight + website
build + group dry-run + gates), for a safe end-to-end rehearsal.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

PY = sys.executable
WEEK = config.current_week_key()
POST_DIR = ROOT / "data" / "posts" / WEEK
EVENTS = ROOT / "data" / "events" / f"{WEEK}_all.json"


def _env(**extra):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e.update({k: str(v) for k, v in extra.items()})
    return e


def step(label, cmd, timeout, env=None, required=True, cwd=ROOT):
    """Run one blocking step. Print a clear banner. On failure, fail LOUD."""
    print(f"\n{'='*64}\n[STEP] {label}\n{'='*64}", flush=True)
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, cwd=str(cwd), env=env or _env(),
                           timeout=timeout, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(f"  [X] TIMEOUT after {timeout}s — {label}", flush=True)
        if required:
            sys.exit(2)
        return False
    out = (r.stdout or "") + (r.stderr or "")
    # echo the tail so the run log shows what happened
    tail = "\n".join(out.splitlines()[-25:])
    print(tail, flush=True)
    print(f"  -> rc={r.returncode}  ({time.monotonic()-t0:.0f}s)", flush=True)
    if r.returncode != 0 and required:
        print(f"  [X] FAILED (required step): {label}", flush=True)
        sys.exit(1)
    return r.returncode == 0


def _event_count():
    try:
        d = json.loads(EVENTS.read_text(encoding="utf-8"))
        evs = d if isinstance(d, list) else d.get("events", d)
        return len(evs)
    except Exception:
        return 0


def run_pre():
    print(f"### WEEKLY PRE-PHASE :: {WEEK} ###", flush=True)
    # 1. FB session check — informational only (other scrapers work regardless).
    step("FB session check", [PY, "tools/check_fb_session.py"],
         timeout=120, required=False)
    # 2. Full scrape (the long step) — blocking, then verify it produced events.
    step("Scrape this week's events", [PY, "main.py", "scrape"], timeout=2400)
    n = _event_count()
    if n < 20:
        print(f"  [X] SCRAPE TOO THIN: only {n} events in {EVENTS.name} "
              f"(scrape-first rule: a partial scrape is NOT done)", flush=True)
        sys.exit(1)
    print(f"  [ok] scrape produced {n} events", flush=True)
    # 3. Clean recurring scraper artifacts before slides render.
    step("Clean event data", [PY, "tools/clean_event_data.py"], timeout=300)
    # 4. Generate slides — FAST rule-based path (no nested-CLI hang).
    step("Generate carousel (rule-based)", [PY, "main.py", "generate-all"],
         timeout=900, env=_env(TULSAGAYS_RULE_ENRICH="1"))
    # 5. Confirm 9 slides exist (voice pass + templated check happen in --post).
    slides = sorted(POST_DIR.glob("all__*.png"))
    if len(slides) < 9:
        print(f"  [X] only {len(slides)}/9 slides generated", flush=True)
        sys.exit(1)
    print(f"\n[ok] PRE-PHASE complete — {len(slides)} slides, {n} events.", flush=True)
    print("NEXT: do the VOICE PASS (Step 2.1) — rewrite every FEATURED + EOTW "
          "blurb in the Alicia/RuPaul/Dolly voice (describe the event, why-go, "
          "best-time tip) into data/events/<week>_all.json, then run:", flush=True)
    print("  python run_weekly.py --post", flush=True)
    # surface the featured set so the agent knows exactly what to rewrite
    try:
        man = json.loads((POST_DIR / "slide_manifest.json").read_text(encoding="utf-8"))
        print("\nFEATURED EVENTS TO VOICE (by day):", flush=True)
        for day, evs in man.get("featured_by_day", {}).items():
            for e in evs:
                print(f"  {day[:3]} | {e.get('name','')[:48]} @ {(e.get('venue') or '')[:24]}", flush=True)
    except Exception:
        pass


def run_post(dry=False):
    print(f"### WEEKLY POST-PHASE :: {WEEK} (dry={dry}) ###", flush=True)
    # 1. Preflight HARD GATE — enforces voice pass done, gay-first, links, no junk.
    step("Preflight gate", [PY, "tools/preflight_post.py"], timeout=300)
    # 2. Write the approval gate (preflight passed).
    step("Write approval gate", [PY, "-c",
         "import json,config;wk=config.current_week_key();"
         "p=f'data/posts/{wk}/approval_status.json';"
         "json.dump({'approved':True,'approved_by':'run_weekly','approved_at':__import__('datetime').date.today().isoformat(),"
         "'note':'preflight passed'},open(p,'w',encoding='utf-8'),indent=2);print('approved',p)"],
         timeout=60)
    # 3. Website — regenerate homepage + share pages (the step that was skipped).
    step("Update website (gen_website_html)", [PY, "tools/gen_website_html.py"],
         timeout=600, env=_env(TULSAGAYS_SKIP_ENRICH="1"))
    if dry:
        step("Group blast DRY-RUN", [PY, "-m", "posting.group_blast", "--dry-run"],
             timeout=120, required=False)
        print("\n[ok] DRY POST-PHASE complete (no FB/IG/group posts made).", flush=True)
        step("Success gate: build", [PY, "tools/postrun_verify.py", "--phase", "build"],
             timeout=120)
        return
    # 4. Token precheck — cannot post without it.
    if not (getattr(config, "TULSAGAYS_PAGE_ACCESS_TOKEN", "") or "").strip():
        print("  [X] Meta page token missing — cannot post FB/IG. Set "
              "TULSAGAYS_PAGE_ACCESS_TOKEN and re-run --post.", flush=True)
        sys.exit(1)
    # 5. Post to FB page + Instagram (graphics).
    step("Post to FB + Instagram", [PY, "tools/post_weekly.py"],
         timeout=900, env=_env(TULSAGAYS_SKIP_ENRICH="1"))
    # 6. Blast the GRAPHICS to FB groups. Two passes: the per-run wall-clock cap
    #    may not reach every group in one pass; the 5-day cooldown makes the 2nd
    #    pass skip everything already posted, so it only picks up stragglers.
    step("Group blast (graphics) pass 1", [PY, "-m", "posting.group_blast"],
         timeout=1500, required=False)
    step("Group blast (graphics) pass 2 (stragglers)", [PY, "-m", "posting.group_blast"],
         timeout=900, required=False)
    # 7. Log distribution metrics.
    step("Distribution metrics", [PY, "tools/distribution_metrics.py"],
         timeout=120, required=False)
    # 7b. Stage the weekly email newsletter as a DRAFT (community channel). Never
    #     auto-broadcasts — send_newsletter.py without --send only stages a Kit
    #     draft for William to review and send. (Deepen-Tulsa rung, 2026-06-15.)
    step("Stage newsletter draft (no send)", [PY, "tools/send_newsletter.py"],
         timeout=180, required=False)
    # 8. SUCCESS GATE — prove FB/IG actually posted (fail loud if not).
    step("Success gate: post", [PY, "tools/postrun_verify.py", "--phase", "post"],
         timeout=120)
    print(f"\n[ok] POST-PHASE complete — carousel posted + verified for {WEEK}.", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--dry", action="store_true", help="with --post: rehearse, no posting")
    a = ap.parse_args()
    if a.pre:
        run_pre()
    elif a.post:
        run_post(dry=a.dry)
    else:
        ap.error("specify --pre or --post")


if __name__ == "__main__":
    main()
