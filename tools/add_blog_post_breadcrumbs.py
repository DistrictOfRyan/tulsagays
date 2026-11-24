"""Inject BreadcrumbList JSON-LD into every individual docs/blog/*.html post.

Found 2026-11-24 (tulsa-gays-ai-schema audit): the blog INDEX got CollectionPage +
BreadcrumbList on 2026-11-10 (tools/add_blog_index_schema.py), but every individual
post under docs/blog/ still carries only BlogPosting + FAQPage, with no BreadcrumbList.
Guide pages (tools/gen_topic_pages.py) and org profiles (tools/gen_org_profiles.py)
have always had BreadcrumbList; blog posts were the one indexed content template
missing it. Headline is pulled from each post's own BlogPosting schema, never
re-derived from the filename or <title>, so the breadcrumb label always matches
what's actually published.

Usage:
    python tools/add_blog_post_breadcrumbs.py             # writes every docs/blog/*.html post
    python tools/add_blog_post_breadcrumbs.py --dry-run    # prints what would change, no write
    python tools/add_blog_post_breadcrumbs.py --selftest   # proves extraction + injection
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO / "docs" / "blog"
BASE = "https://www.tulsagays.com"
MARKER_START = "<!-- blog-post-breadcrumbs:start -->"
MARKER_END = "<!-- blog-post-breadcrumbs:end -->"


def _headline(html, slug):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(block)
        except Exception:
            continue
        if d.get("@type") == "BlogPosting" and d.get("headline"):
            return d["headline"]
    return None


def build_schema(headline, url):
    block = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{BASE}/blog/index.html"},
            {"@type": "ListItem", "position": 3, "name": headline, "item": url},
        ],
    }
    return f'{MARKER_START}\n<script type="application/ld+json">{json.dumps(block, ensure_ascii=False)}</script>\n{MARKER_END}'


def inject(html, schema_html):
    if MARKER_START in html:
        return re.sub(re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
                       schema_html, html, flags=re.S)
    return html.replace("</head>", schema_html + "\n</head>", 1)


def posts():
    return sorted(p for p in BLOG_DIR.glob("*.html") if p.name != "index.html")


def main():
    dry = "--dry-run" in sys.argv
    changed, skipped = [], []
    for path in posts():
        html = path.read_text(encoding="utf-8")
        slug = path.name
        headline = _headline(html, slug)
        if not headline:
            skipped.append(slug)
            continue
        url = f"{BASE}/blog/{slug}"
        schema_html = build_schema(headline, url)
        already = MARKER_START in html
        new_html = inject(html, schema_html)
        if new_html == html:
            continue
        changed.append((slug, "updated" if already else "added"))
        if not dry:
            path.write_text(new_html, encoding="utf-8")
    for slug, action in changed:
        print(f"{action}: {slug}")
    if skipped:
        print(f"SKIPPED (no BlogPosting headline found): {skipped}")
    print(f"{'would change' if dry else 'wrote'} {len(changed)} of {len(posts())} posts")
    return 0


def _selftest():
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs" / "blog").mkdir(parents=True)
    global BLOG_DIR
    real = BLOG_DIR
    BLOG_DIR = tmp / "docs" / "blog"
    try:
        block = json.dumps({"@type": "BlogPosting", "headline": "Test Post Headline",
                             "datePublished": "2026-01-01"})
        sample = f'<html><head><title>x</title><script type="application/ld+json">{block}</script></head><body></body></html>'
        (BLOG_DIR / "test-post.html").write_text(sample, encoding="utf-8")
        headline = _headline(sample, "test-post.html")
        assert headline == "Test Post Headline", headline
        schema = build_schema(headline, f"{BASE}/blog/test-post.html")
        assert "BreadcrumbList" in schema and "Test Post Headline" in schema
        out1 = inject(sample, schema)
        assert out1.count(MARKER_START) == 1
        out2 = inject(out1, build_schema(headline, f"{BASE}/blog/test-post.html"))
        assert out2.count(MARKER_START) == 1, "re-running must replace, not duplicate"
        no_headline_html = "<html><head></head></html>"
        assert _headline(no_headline_html, "x.html") is None
        print("SELFTEST PASS")
    finally:
        BLOG_DIR = real
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(main())
