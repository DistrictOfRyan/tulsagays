"""Inject CollectionPage + ItemList + BreadcrumbList JSON-LD into docs/blog/index.html.

Found 2026-11-10 (tulsa-gays-ai-schema audit): every other page type on the site
(homepage, directory, blog posts, event share pages, topic guides, org profiles)
carries JSON-LD; the blog index had zero schema blocks, making it the one page an
AI assistant or Google rich-result crawler sees as untyped. The ItemList entries are
built from each live post's OWN BlogPosting schema (headline + datePublished), never
guessed from index HTML text, so a stale index can never drift from what's actually
published.

Usage:
    python tools/add_blog_index_schema.py            # writes docs/blog/index.html
    python tools/add_blog_index_schema.py --dry-run   # prints the block, no write
    python tools/add_blog_index_schema.py --selftest  # proves extraction + injection
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO / "docs" / "blog"
INDEX_PATH = BLOG_DIR / "index.html"
BASE = "https://www.tulsagays.com"
MARKER_START = "<!-- blog-index-schema:start -->"
MARKER_END = "<!-- blog-index-schema:end -->"


def _blog_post_links(index_html):
    """Relative hrefs to individual posts, in the order they appear on the index."""
    hrefs = re.findall(r'href="([a-z0-9][a-z0-9\-]*\.html)"', index_html)
    seen, out = set(), []
    for h in hrefs:
        if h not in seen and h != "index.html":
            seen.add(h)
            out.append(h)
    return out


def collect_posts(index_html=None):
    """Pull headline + datePublished + url straight from each post's own BlogPosting
    schema (never fabricated, never re-derived from index text)."""
    if index_html is None:
        index_html = INDEX_PATH.read_text(encoding="utf-8")
    posts, missing = [], []
    for link in _blog_post_links(index_html):
        path = BLOG_DIR / link
        if not path.is_file():
            missing.append(link)
            continue
        html = path.read_text(encoding="utf-8")
        headline = date = None
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                d = json.loads(block)
            except Exception:
                continue
            if d.get("@type") == "BlogPosting":
                headline, date = d.get("headline"), d.get("datePublished")
                break
        if headline and date:
            posts.append({"url": f"{BASE}/blog/{link}", "headline": headline, "datePublished": date})
        else:
            missing.append(f"{link} (no BlogPosting schema)")
    return posts, missing


def build_schema(posts):
    items = [
        {"@type": "ListItem", "position": i + 1,
         "item": {"@type": "BlogPosting", "headline": p["headline"],
                   "datePublished": p["datePublished"], "url": p["url"]}}
        for i, p in enumerate(posts)
    ]
    blocks = [
        {"@context": "https://schema.org", "@type": "CollectionPage",
         "name": "Blog - Tulsa Gays | LGBTQ+ Life in Tulsa",
         "description": "Stories, guides, and insider tips for LGBTQ+ life in Tulsa, Oklahoma.",
         "url": f"{BASE}/blog/index.html",
         "isPartOf": {"@type": "WebSite", "name": "Tulsa Gays", "url": BASE},
         "mainEntity": {"@type": "ItemList", "itemListElement": items}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE},
             {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{BASE}/blog/index.html"}]},
    ]
    body = "\n".join(f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks)
    return f"{MARKER_START}\n{body}\n{MARKER_END}"


def inject(index_html, schema_html):
    if MARKER_START in index_html:
        return re.sub(
            re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
            schema_html, index_html, flags=re.S)
    return index_html.replace("</head>", schema_html + "\n</head>")


def main():
    dry = "--dry-run" in sys.argv
    index_html = INDEX_PATH.read_text(encoding="utf-8")
    posts, missing = collect_posts(index_html)
    if not posts:
        print("ABORT: resolved 0 posts from live BlogPosting schema; refusing to write an empty ItemList")
        return 1
    schema_html = build_schema(posts)
    new_html = inject(index_html, schema_html)
    print(f"resolved {len(posts)} posts, {len(missing)} skipped (missing/no-schema): {missing}")
    if dry:
        print(schema_html)
        return 0
    INDEX_PATH.write_text(new_html, encoding="utf-8")
    print(f"wrote {INDEX_PATH}")
    return 0


def _selftest():
    sample = """<!DOCTYPE html><html><head><title>Blog</title></head><body>
    <a href="post-a.html">A</a><a href="post-b.html">B</a>
    </body></html>"""
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs" / "blog").mkdir(parents=True)
    global BLOG_DIR, INDEX_PATH
    real_blog_dir, real_index = BLOG_DIR, INDEX_PATH
    BLOG_DIR = tmp / "docs" / "blog"
    INDEX_PATH = BLOG_DIR / "index.html"
    try:
        INDEX_PATH.write_text(sample, encoding="utf-8")
        for slug, headline, date in [("post-a.html", "Post A Headline", "2026-01-01"),
                                      ("post-b.html", "Post B Headline", "2026-02-02")]:
            block = json.dumps({"@type": "BlogPosting", "headline": headline, "datePublished": date})
            (BLOG_DIR / slug).write_text(
                f'<html><head><script type="application/ld+json">{block}</script></head></html>',
                encoding="utf-8")
        posts, missing = collect_posts()
        assert len(posts) == 2 and not missing, (posts, missing)
        assert posts[0]["headline"] == "Post A Headline"
        schema = build_schema(posts)
        assert "CollectionPage" in schema and "BreadcrumbList" in schema
        out1 = inject(sample, schema)
        assert out1.count(MARKER_START) == 1
        out2 = inject(out1, build_schema(posts))
        assert out2.count(MARKER_START) == 1, "re-running must replace, not duplicate"
        empty_posts, _ = collect_posts("<html><head></head><body></body></html>")
        assert empty_posts == []
        print("SELFTEST PASS")
    finally:
        BLOG_DIR, INDEX_PATH = real_blog_dir, real_index
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(main())
