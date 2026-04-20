"""Slack channel event scraper for TulsaRemote workspace.

Scrapes event posts from:
- #events-local: Local Tulsa events posted by community members
- #unite-lgbtq-plus: LGBTQ+ specific events and gatherings
- #gradient: Community events and opportunities

Extracts event names, dates, times, locations, and links from message content.
"""

import sys
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# Slack channel IDs for TulsaRemote workspace
SLACK_CHANNELS = {
    "events-local": "CGV2YLJSG",
    "unite-lgbtq-plus": "C0262PQNUDD",
    "gradient": "CGV2YLJSG",  # Will need to update with actual ID
}

# Event date patterns to match in messages
DATE_PATTERNS = [
    r'(\w+day,?\s+\w+\s+\d+)',  # "Monday, March 31"
    r'(\w+\s+\d+(?:st|nd|rd|th)?)',  # "March 31st"
    r'(\d{1,2}/\d{1,2})',  # "3/31"
    r'(today|tomorrow|this week|next week)',  # Relative dates
]

# Time patterns to match
TIME_PATTERNS = [
    r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',  # "7:30 PM"
    r'(\d{1,2}(?:am|pm|AM|PM))',  # "7pm"
]

# Location indicators
LOCATION_PATTERNS = [
    r'@\s*([^,\n]+)',  # "@address"
    r'at\s+([^,\n]+?)(?:\s+\(|,|$)',  # "at place"
    r'location:\s*([^,\n]+)',  # "location: place"
]


class SlackScraper(BaseScraper):
    """Scraper for TulsaRemote Slack event channels."""

    source_name = "slack_events"

    def __init__(self):
        super().__init__()
        self.channels = ["events-local", "unite-lgbtq-plus", "gradient"]
        self.events = []

    def scrape(self) -> List[Dict]:
        """Scrape all Slack event channels."""
        self.events = []

        logger.info(f"[{self.source_name}] Scraping Slack channels: {self.channels}")

        for channel in self.channels:
            try:
                events = self._scrape_channel(channel)
                self.events.extend(events)
                logger.info(f"[{self.source_name}] Found {len(events)} events in #{channel}")
            except Exception as e:
                logger.error(f"[{self.source_name}] Failed to scrape #{channel}: {e}")
                continue

        logger.info(f"[{self.source_name}] Total events scraped: {len(self.events)}")
        return self.events

    def _scrape_channel(self, channel: str) -> List[Dict]:
        """Scrape a single Slack channel and extract events."""
        events = []

        # This will be implemented using Playwright or API integration
        # For now, return empty list - will be populated by automated browser scraping
        logger.debug(f"[{self.source_name}] Would scrape #{channel}")

        return events

    def extract_event_from_message(self,
                                  text: str,
                                  author: str = "",
                                  channel: str = "") -> Optional[Dict]:
        """Extract event details from a Slack message.

        Looks for patterns like:
        - "Event Name - Date, Time at Location"
        - "Event Name coming to Tulsa! March 31, 7:30 PM at venue"
        """

        if not text or len(text.strip()) < 10:
            return None

        text = text.strip()

        # Extract event name (usually first line or sentence)
        lines = text.split('\n')
        event_name = lines[0].strip()
        event_name = re.sub(r'https?://\S+', '', event_name)  # Remove URLs
        event_name = re.sub(r'<[^>]+>', '', event_name)  # Remove Slack formatting
        event_name = event_name.strip()

        if len(event_name) < 5:
            return None

        # Extract date
        date_str = self._extract_date(text)

        # Extract time
        time_str = self._extract_time(text)

        # Extract location
        venue = self._extract_location(text)

        # Extract URL if present
        url = self._extract_url(text)

        # Extract description (remaining text after name)
        description = text[len(lines[0]):].strip()
        description = description[:200] if description else ""

        if not date_str:
            # If no date found, skip this event
            return None

        event = self.make_event(
            name=event_name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=2,
        )

        return event

    def _extract_date(self, text: str) -> str:
        """Extract date from text using flexible patterns."""

        # Try common patterns
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                parsed = self.parse_date_flexible(date_str)
                if parsed and parsed != date_str:
                    return parsed

        return ""

    def _extract_time(self, text: str) -> str:
        """Extract time from text."""

        for pattern in TIME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return ""

    def _extract_location(self, text: str) -> str:
        """Extract venue/location from text."""

        for pattern in LOCATION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up extra whitespace and punctuation
                location = re.sub(r'\s+', ' ', location)
                return location[:100]  # Limit to 100 chars

        return ""

    def _extract_url(self, text: str) -> str:
        """Extract first URL from text."""

        urls = re.findall(r'https?://\S+', text)
        if urls:
            # Return first valid URL
            url = urls[0].rstrip('.,;:!)')  # Clean trailing punctuation
            return url

        return ""


# Standalone test
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    scraper = SlackScraper()
    events = scraper.safe_scrape()

    import json
    print(json.dumps(events, indent=2))
