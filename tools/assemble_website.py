"""Inject generated day-sections into docs/index.html.

Run after tools/gen_website_html.py. Replaces everything between
<!-- MONDAY --> and </main> with the fresh C:/tmp/day_sections.html output.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECTIONS_FILE = "C:/tmp/day_sections.html"
INDEX_FILE    = "docs/index.html"

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
