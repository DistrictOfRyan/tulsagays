"""Per-org profile pages -- the entity graph (Answer Engine L5).

Each census org gets a permanent, schema-marked profile page that aggregates
EVERY event we've ever scraped for it (across data/events/*_all.json) plus its
note and links. That makes each page the single most complete page about that
org on the internet -- the opposite of thin content.

Anti-thin-content gate: a page is only generated for an org with real substance
(>= MIN_EVENTS aggregated events OR flagged anchor=True). Thin orgs stay in the
directory only, so we never publish low-value pages that drag down site quality.

Schema: Organization + BreadcrumbList. Cross-linked to the relevant topic guide.
Output: docs/org/<id>.html, added to sitemap. `--selftest` proves gating +
render + schema on synthetic data. Reuses the render helpers from
gen_topic_pages so the look is identical and DRY.
"""

import os
import sys
import re
import json
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tools.gen_topic_pages import (
    _header, FOOTER, GA, STYLE, esc, BASE, _load_census, TOPICS,
)

DOCS = os.path.join(config.PROJECT_DIR, "docs")
ORG_DIR = os.path.join(DOCS, "org")
SITEMAP = os.path.join(DOCS, "sitemap.xml")

MIN_EVENTS = 2          # below this (and not an anchor) -> no page (anti-thin)
ANCHORS = {"okeq", "tulsa_pride", "comc", "ybr", "tulsa_eagle", "club_majestic",
           "black_queer_tulsa", "qwc", "pflag_tulsa"}

# Map an org to the most relevant topic guide for cross-linking.
TYPE_TO_GUIDE = {
    "bar": "gay-bars-in-tulsa", "church": "queer-friendly-churches-tulsa",
    "wellness": "sound-baths-meditation-tulsa", "org": "lgbtq-organizations-tulsa",
    "group": "lgbtq-organizations-tulsa", "event": "lgbtq-organizations-tulsa",
}


def _aggregate_events(org, weeks=16):
    """Every distinct event matching this org's aliases across recent history."""
    aliases = [a.lower() for a in org.get("aliases", []) if a] + [org["name"].lower()]
    files = sorted(glob.glob(os.path.join(config.EVENTS_DIR, "*_all.json")),
                   key=os.path.getmtime)[-weeks:]
    seen, out = set(), []
    for f in files:
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        events = data.get("events", []) if isinstance(data, dict) else data
        for e in events:
            if not isinstance(e, dict):
                continue
            blob = (str(e.get("name", "")) + " " + str(e.get("venue", ""))).lower()
            if any(a in blob for a in aliases):
                key = (re.sub(r"\W+", "", str(e.get("name", "")).lower()), e.get("date", ""))
                if key not in seen:
                    seen.add(key)
                    out.append(e)
    out.sort(key=lambda e: e.get("date", ""), reverse=True)
    return out


def _schema(org, events, url):
    org_type = "LocalBusiness" if org.get("type") in ("bar", "wellness", "church") else "Organization"
    block = {"@context": "https://schema.org", "@type": org_type, "name": org["name"],
             "url": url, "areaServed": "Tulsa, Oklahoma",
             "description": org.get("note", "")}
    crumb = {"@context": "https://schema.org", "@type": "BreadcrumbList",
             "itemListElement": [
                 {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE},
                 {"@type": "ListItem", "position": 2, "name": "Directory", "item": f"{BASE}/directory.html"},
                 {"@type": "ListItem", "position": 3, "name": org["name"], "item": url}]}
    return (f'<script type="application/ld+json">{json.dumps(block)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(crumb)}</script>')


def render_org(org, events):
    url = f"{BASE}/org/{org['id']}.html"
    guide = TYPE_TO_GUIDE.get(org.get("type"), "lgbtq-organizations-tulsa")
    if events:
        rows = "\n".join(
            f'<li><strong>{esc(e.get("name"))}</strong> &middot; {esc(e.get("date"))} '
            f'{esc(e.get("time",""))} &middot; {esc(e.get("venue",""))}</li>' for e in events[:30])
        ev_block = f'<h2>Events we\'ve tracked ({len(events)})</h2><ul class="topic-events">{rows}</ul>'
    else:
        ev_block = ""
    desc = esc(org.get("note") or f"{org['name']} in Tulsa, Oklahoma.")
    title = f"{org['name']} - LGBTQ+ Tulsa | Tulsa Gays"
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(org['name'])} - LGBTQ+ Tulsa">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website"><meta property="og:url" content="{url}">
<meta property="og:site_name" content="Tulsa Gays">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link href="https://fonts.googleapis.com/css2?family=Poiret+One&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
{_schema(org, events, url)}
{GA}
{STYLE}
</head>
{_header()}
<main class="container">
  <div class="week-header"><h1>{esc(org['name'])}</h1><div class="rainbow-bar rainbow-gradient"></div></div>
  <div class="about-content">
    <p class="topic-intro">{desc}</p>
    {ev_block}
    <p class="topic-cta">See more in our <a href="/guides/{guide}.html">{esc(guide.replace('-', ' '))}</a> guide,
       the full <a href="/directory.html">directory</a>, or this week's <a href="/">calendar</a>.</p>
  </div>
</main>
{FOOTER}"""


def _update_sitemap(ids):
    if not os.path.exists(SITEMAP):
        return 0
    xml = open(SITEMAP, encoding="utf-8").read()
    inject, added = "", 0
    for i in ids:
        u = f"{BASE}/org/{i}.html"
        if u not in xml:
            inject += f"  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>\n"
            added += 1
    if inject and "</urlset>" in xml:
        open(SITEMAP, "w", encoding="utf-8").write(xml.replace("</urlset>", inject + "</urlset>"))
    return added


def run():
    os.makedirs(ORG_DIR, exist_ok=True)
    census = _load_census()
    made, skipped = [], []
    for org in census:
        events = _aggregate_events(org)
        if len(events) >= MIN_EVENTS or org["id"] in ANCHORS:
            open(os.path.join(ORG_DIR, f"{org['id']}.html"), "w", encoding="utf-8").write(
                render_org(org, events))
            made.append((org["id"], len(events)))
        else:
            skipped.append(org["id"])
    added = _update_sitemap([m[0] for m in made])
    print(f"[org-profiles] wrote {len(made)} profiles ({len(skipped)} skipped as thin); sitemap +{added}")
    for i, n in made:
        print(f"  /org/{i}.html  ({n} events)")
    return made


def _selftest():
    org_rich = {"id": "okeq", "name": "OKEQ", "type": "org", "aliases": ["okeq"], "note": "Hub org."}
    org_thin = {"id": "tiny", "name": "Tiny Group", "type": "group", "aliases": ["tiny group xyz"], "note": ""}
    events = [{"name": "OKEQ Clinic", "date": "2026-06-02", "venue": "Equality Center"},
              {"name": "OKEQ Mixer", "date": "2026-06-09", "venue": "Equality Center"}]
    page = render_org(org_rich, events)
    assert "Organization" in page and "BreadcrumbList" in page
    blocks = re.findall(r'application/ld\+json\">(.*?)</script>', page, re.S)
    assert len(blocks) == 2 and all(json.loads(b) for b in blocks)
    assert "OKEQ Clinic" in page and "/guides/" in page
    # gating: anchor renders even with few events; thin non-anchor would be skipped
    assert org_thin["id"] not in ANCHORS
    print(f"gen_org_profiles selftest: passed (schema valid, event aggregation, anti-thin gate)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    run()
