"""
Inject Featured Partners into docs/directory.html from data/featured_partners.json.

Run after adding a new sponsor to the JSON file.
Idempotent: rewrites the section each time; safe to run in CI or weekly.

Usage: python tools/inject_featured_partners.py
"""
import json, re, os, sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA_FILE = REPO / "data" / "featured_partners.json"
DIRECTORY_HTML = REPO / "docs" / "directory.html"
SECTION_START = "<!-- ══ FEATURED PARTNERS"
SECTION_END = "<!-- ══ CATEGORY SECTIONS"


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_partner_card(p):
    badge = '<span class="featured-partner-badge">Featured</span>'
    addr_line = ""
    if p.get("address"):
        addr_line = f'\n                <div class="biz-address">{esc(p["address"])}</div>'
    return (
        f'            <div class="biz-card featured-partner">\n'
        f'                <div class="biz-name"><a href="{esc(p["url"])}" target="_blank" rel="noopener">'
        f'{esc(p["name"])}</a> {badge}</div>{addr_line}\n'
        f'                <div class="biz-desc">{esc(p["description"])}</div>\n'
        f'            </div>'
    )


def build_section(partners):
    active = [p for p in partners if p.get("active", True)]
    display = "none" if not active else ""
    cards = "\n".join(render_partner_card(p) for p in active)
    cards_block = f"\n{cards}\n        " if active else "\n        "
    return (
        f"        <!-- ══ FEATURED PARTNERS ═══════════════════════════════════════════ -->\n"
        f"        <!-- Businesses listed here are paying Featured Partners ($50–75/mo).\n"
        f"             To add a partner: edit data/featured_partners.json and run\n"
        f"             python tools/inject_featured_partners.py\n"
        f"             Contact: hello@tulsagays.com -->\n"
        f'        <div class="featured-partners-section" id="featuredPartners" style="display:{display}">\n'
        f'            <div class="featured-partners-label">Featured Partners</div>{cards_block}'
        f"        </div>\n\n"
    )


def main():
    if not DATA_FILE.exists():
        print("No featured_partners.json found — creating empty one")
        DATA_FILE.write_text('{"partners": []}', encoding="utf-8")

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    partners = data.get("partners", [])
    active_count = sum(1 for p in partners if p.get("active", True))
    print(f"Partners in JSON: {len(partners)} total, {active_count} active")

    html = DIRECTORY_HTML.read_text(encoding="utf-8")

    # Find the section bounds
    start_idx = html.find(SECTION_START)
    end_idx = html.find(SECTION_END)
    if start_idx == -1 or end_idx == -1:
        print("ERROR: Could not find Featured Partners section markers in directory.html")
        sys.exit(1)

    new_section = build_section(partners)
    new_html = html[:start_idx] + new_section + "        " + html[end_idx:]
    DIRECTORY_HTML.write_text(new_html, encoding="utf-8")
    print(f"Updated directory.html — {active_count} featured partner(s) injected")

    if active_count == 0:
        print("(Section hidden — no active partners yet. Add one to data/featured_partners.json)")
    else:
        print("(Section visible)")


if __name__ == "__main__":
    main()
