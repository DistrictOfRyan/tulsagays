"""One-command verify gate for the TulsaGays pipeline.

  python verify_all.py

Compiles every Python module (syntax gate) and runs the regression suite.
Exit 0 = safe to ship. Exit 1 = something is broken — do NOT push or post.
This is the gate the CI workflow runs on every push (.github/workflows/
pipeline-tests.yml), so a regression in the hardened pipeline can't ship unnoticed.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

# Core modules whose syntax must always be valid.
CORE = [
    "config.py", "main.py", "eotw_selector.py", "run_weekly.py", "verify_all.py",
    "content/generator.py", "content/image_maker.py",
    "tools/preflight_post.py", "tools/gen_website_html.py", "tools/postrun_verify.py",
    "tools/clean_event_data.py", "tools/send_newsletter.py", "posting/group_blast.py",
    "tests/test_pipeline.py",
    "scraper/tz_guard.py", "tools/verify_week_truth.py", "posting/group_retract.py",
    "scraper/eventbrite_meetup.py", "scraper/okeq_calendar.py",
]

# Fact-accuracy guards (2026-09-15, after W38 shipped a 2025 festival, every
# Meetup time 5h late and Facebook times 1h early). tz_guard's selftest also
# fails if any scraper reintroduces raw ISO time slicing.
SELFTESTS = [
    ("tz_guard selftest", ["scraper/tz_guard.py"]),
    ("verify_week_truth selftest", ["tools/verify_week_truth.py", "--selftest"]),
]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main():
    fails = []
    print("=== verify_all: syntax gate ===")
    present = [m for m in CORE if os.path.exists(os.path.join(ROOT, m))]
    r = run([PY, "-m", "py_compile", *present])
    if r.returncode != 0:
        fails.append("py_compile")
        print(r.stdout + r.stderr)
    else:
        print(f"  [ok] {len(present)} core modules compile")

    print("=== verify_all: regression suite ===")
    r = run([PY, "tests/test_pipeline.py"])
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        fails.append("test_pipeline")
        sys.stderr.write(r.stderr)

    print("=== verify_all: fact-accuracy guards ===")
    for label, args in SELFTESTS:
        r = run([PY, *args])
        if r.returncode != 0:
            fails.append(label)
            print(r.stdout[-3000:] + r.stderr[-1000:])
        else:
            print(f"  [ok] {label}")

    print()
    if fails:
        print(f"[X] VERIFY FAILED: {', '.join(fails)} — do not ship.")
        sys.exit(1)
    print("[OK] verify_all green — safe to ship.")
    sys.exit(0)


if __name__ == "__main__":
    main()
