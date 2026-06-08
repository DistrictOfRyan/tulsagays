"""OBSOLETE — do not use in the weekly pipeline.

gen_website_html.py now self-injects the fresh, de-duped day-sections directly
into docs/index.html. This script re-injects C:/tmp/day_sections.html, which on
2026-06-08 was a 6-WEEK-OLD cache and silently CLOBBERED the good output with 21
repeated blurbs. It now refuses to run on a stale cache as a safety guard.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECTIONS_FILE = "C:/tmp/day_sections.html"
INDEX_FILE    = "docs/index.html"

# STALE-CACHE GUARD: never inject a day_sections file that wasn't regenerated
# today. This is what made the live site show 6-week-old repeated copy.
if not os.path.exists(SECTIONS_FILE):
    sys.exit(f"[obsolete] {SECTIONS_FILE} not found. gen_website_html.py already "
             f"self-injects into {INDEX_FILE} — you do not need this script.")
_age_h = (time.time() - os.path.getmtime(SECTIONS_FILE)) / 3600
if _age_h > 12:
    sys.exit(f"[obsolete/guard] {SECTIONS_FILE} is {_age_h:.0f}h old (stale). "
             f"Refusing to clobber {INDEX_FILE} with a stale cache. "
             f"gen_website_html.py already self-injects fresh cards.")

with open(INDEX_FILE, encoding="utf-8") as f:
    lines = f.readlines()

start = next((i for i, l in enumerate(lines) if "<!-- MONDAY -->" in l), None)
end   = next((i for i, l in enumerate(lines) if "</main>" in l), None)

if start is None or end is None:
    sys.exit(f"ERROR: Could not find <!-- MONDAY --> or </main> in {INDEX_FILE}")

with open(SECTIONS_FILE, encoding="utf-8") as f:
    new_sections = f.read()

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    f.write("".join(lines[:start]) + new_sections + "\n\n    " + "".join(lines[end:]))

print(f"Assembled {INDEX_FILE} ({len(lines)} -> {len(lines[:start]) + new_sections.count(chr(10)) + len(lines[end:])} lines)")
