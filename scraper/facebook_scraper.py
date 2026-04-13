"""Facebook scraper -- DISABLED.

Facebook blocks all unauthenticated scraping. Attempting to scrape Facebook
pages returns login walls or empty JS shells regardless of approach.

This module is kept as a stub so other modules that import from it
(e.g. bars.py) do not break. It always returns an empty list.

Manual alternative: check https://www.facebook.com/search/events/?q=lgbtq+tulsa
"""

import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


def scrape_facebook_page(page_url: str, source_name: str) -> List[Dict]:
    """Stub: Facebook scraping is not available."""
    logger.info(f"[facebook] Scraping not available for {source_name} ({page_url}) -- check manually")
    return []


class FacebookPageScraper:
    """Stub class for backward compatibility with bars.py."""

    source_name = "facebook"

    def __init__(self, pages: List[Tuple[str, str, int]]):
        self.pages = pages

    def safe_scrape(self) -> List[Dict]:
        logger.info("[facebook] Facebook scraping not available -- check pages manually")
        for page_url, source_name, _ in self.pages:
            logger.info(f"  Manual check: {page_url}")
        return []


def scrape() -> List[Dict]:
    """Module-level entry point -- always returns empty list."""
    logger.info("[facebook] Facebook scraping not available -- check manually")
    return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    print(f"Facebook scraping not available -- check manually. Events returned: {len(results)}")
