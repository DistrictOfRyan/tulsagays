"""Base scraper class with common functionality for all Tulsa Gays scrapers."""

import random
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
]


class BaseScraper:
    """Base class for all event scrapers."""

    source_name: str = "unknown"

    def __init__(self):
        self.session = requests.Session()
        self._rotate_user_agent()

    def _rotate_user_agent(self):
        """Set a random User-Agent header on the session."""
        ua = random.choice(USER_AGENTS)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        })

    def _random_delay(self):
        """Sleep for a random duration between 2 and 5 seconds to be polite."""
        delay = random.uniform(2.0, 5.0)
        logger.debug(f"[{self.source_name}] Sleeping {delay:.1f}s")
        time.sleep(delay)

    def fetch_page(self, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
        """Fetch a URL and return a BeautifulSoup object, or None on failure."""
        try:
            self._rotate_user_agent()
            logger.info(f"[{self.source_name}] Fetching {url}")
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            logger.error(f"[{self.source_name}] Failed to fetch {url}: {e}")
            return None

    def fetch_json(self, url: str, params: Optional[dict] = None, timeout: int = 15) -> Optional[dict]:
        """Fetch a URL expecting JSON response, or None on failure."""
        try:
            self._rotate_user_agent()
            logger.info(f"[{self.source_name}] Fetching JSON from {url}")
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.error(f"[{self.source_name}] Failed to fetch JSON from {url}: {e}")
            return None

    def make_event(
        self,
        name: str,
        date: str,
        time: str = "",
        venue: str = "",
        description: str = "",
        url: str = "",
        priority: int = 2,
    ) -> Dict:
        """Create a standardized event dict."""
        return {
            "name": name.strip() if name else "",
            "date": date.strip() if date else "",
            "time": time.strip() if time else "",
            "venue": venue.strip() if venue else "",
            "description": description.strip() if description else "",
            "url": url.strip() if url else "",
            "priority": priority,
            "source": self.source_name,
        }

    def scrape(self) -> List[Dict]:
        """Override in subclasses. Must return a list of event dicts."""
        raise NotImplementedError("Subclasses must implement scrape()")

    def safe_scrape(self) -> List[Dict]:
        """Run scrape() with full error handling. Returns empty list on any failure."""
        try:
            events = self.scrape()
            logger.info(f"[{self.source_name}] Scraped {len(events)} events")
            return events
        except Exception as e:
            logger.error(f"[{self.source_name}] Scraper crashed: {e}", exc_info=True)
            return []

    @staticmethod
    def parse_date_flexible(date_str: str) -> str:
        """Try multiple date formats and return YYYY-MM-DD or the original string."""
        if not date_str:
            return ""
        date_str = date_str.strip()
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%A, %B %d, %Y",
            "%A, %b %d, %Y",
            "%B %d",
            "%b %d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # If year is 1900 (no year in format), assume current year
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str
