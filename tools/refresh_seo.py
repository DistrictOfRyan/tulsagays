"""Regenerate all programmatic SEO/GEO pages (Answer Engine L6: freshness machine).

One entry point the weekly pipeline calls so the long-tail guides and the per-org
profile pages re-render from the latest census + event data every week, with
zero manual touch. Idempotent: safe to run any number of times.

Wired into the Sunday source-growth task (tulsa-gays-site-discovery) after the
census/coverage step. Can also be run after the Monday scrape for max freshness.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run():
    from tools import gen_topic_pages, gen_org_profiles
    topics = gen_topic_pages.run()
    orgs = gen_org_profiles.run()
    print(f"[refresh_seo] done: {len(topics)} topic guides + {len(orgs)} org profiles regenerated.")
    return {"topics": len(topics), "orgs": len(orgs)}


if __name__ == "__main__":
    run()
