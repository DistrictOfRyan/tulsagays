"""Discover new LGBTQ+ event sources in Tulsa.

Searches the web for potential event sources, evaluates them,
and tracks new discoveries for review.
"""

import sys
import os
import json
import re
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


DISCOVERED_SOURCES_FILE = os.path.join(config.DATA_DIR, "discovered_sources.json")

# Date-related patterns that suggest event content
DATE_PATTERNS = [
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}\b",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\b",
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
]

# Words that suggest event listings
EVENT_KEYWORDS = [
    "event", "events", "calendar", "schedule", "show", "performance",
    "meetup", "meet-up", "gathering", "workshop", "class", "party",
    "drag", "pride", "lgbtq", "queer", "community", "happy hour",
    "open mic", "bingo", "trivia", "karaoke", "brunch",
]


def _load_discovered():
    """Load previously discovered sources."""
    if os.path.exists(DISCOVERED_SOURCES_FILE):
        with open(DISCOVERED_SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_discovered(sources):
    """Save discovered sources list."""
    config.ensure_dirs()
    with open(DISCOVERED_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2)


def _get_known_domains():
    """Get set of domains we already know about."""
    known = set()
    for source in config.SOURCES.values():
        url = source.get("url", "")
        if url:
            parsed = urlparse(url)
            known.add(parsed.netloc.lower().replace("www.", ""))
    # Also include previously discovered sources
    for source in _load_discovered():
        parsed = urlparse(source.get("url", ""))
        known.add(parsed.netloc.lower().replace("www.", ""))
    return known


def _search_google(query, num_results=10):
    """Search Google for a query and return result URLs.

    Args:
        query: Search query string.
        num_results: Number of results to request.

    Returns:
        list[str]: URLs from search results.
    """
    if requests is None:
        print("[discovery] requests library not installed.")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    urls = []
    try:
        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": num_results},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.startswith("/url?q="):
                url = href.split("/url?q=")[1].split("&")[0]
                if not any(skip in url for skip in [
                    "google.com", "youtube.com", "facebook.com",
                    "twitter.com", "instagram.com", "yelp.com",
                    "tripadvisor.com", "wikipedia.org",
                ]):
                    urls.append(url)
    except Exception as e:
        print(f"[discovery] Search error for '{query}': {e}")

    return urls[:num_results]


def discover_new_sources():
    """Search for new LGBTQ+ event sources in Tulsa.

    Searches Google with various queries from config.SEARCH_QUERIES,
    filters out known sources, and saves new discoveries.

    Returns:
        list[str]: URLs of newly discovered sources.
    """
    if requests is None or BeautifulSoup is None:
        print("[discovery] Install requests and beautifulsoup4: "
              "pip install requests beautifulsoup4")
        return []

    known_domains = _get_known_domains()
    discovered = _load_discovered()
    new_urls = []

    for query in config.SEARCH_QUERIES:
        print(f"[discovery] Searching: {query}")
        urls = _search_google(query)

        for url in urls:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")

            if domain in known_domains:
                continue

            # Skip generic/irrelevant sites
            if any(skip in domain for skip in [
                "eventbrite.com", "meetup.com", "patch.com",
                "tulsaworld.com", "news",
            ]):
                continue

            known_domains.add(domain)
            new_urls.append(url)

            discovered.append({
                "url": url,
                "domain": domain,
                "discovered_at": datetime.now().isoformat(),
                "discovered_via": query,
                "evaluated": False,
                "score": None,
            })

    _save_discovered(discovered)

    if new_urls:
        print(f"[discovery] Found {len(new_urls)} new potential sources.")
    else:
        print("[discovery] No new sources found this time.")

    return new_urls


def evaluate_source(url):
    """Visit a URL and evaluate whether it contains event-like content.

    Checks for dates, event names, and signs of regular updates.

    Args:
        url: The URL to evaluate.

    Returns:
        int: Score from 0-100 indicating likelihood of being a good event source.
    """
    if requests is None or BeautifulSoup is None:
        print("[discovery] Install requests and beautifulsoup4.")
        return 0

    score = 0
    details = []

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()

        # Check for date patterns (max 25 points)
        date_count = 0
        for pattern in DATE_PATTERNS:
            date_count += len(re.findall(pattern, text, re.IGNORECASE))
        if date_count > 0:
            date_score = min(25, date_count * 5)
            score += date_score
            details.append(f"dates_found={date_count}")

        # Check for event keywords (max 25 points)
        keyword_count = 0
        for keyword in EVENT_KEYWORDS:
            keyword_count += text.count(keyword)
        if keyword_count > 0:
            keyword_score = min(25, keyword_count * 3)
            score += keyword_score
            details.append(f"event_keywords={keyword_count}")

        # Check for LGBTQ+ relevance (max 20 points)
        lgbtq_terms = ["lgbtq", "lgbt", "gay", "queer", "pride",
                       "drag", "trans", "lesbian", "bisexual", "nonbinary"]
        lgbtq_count = sum(text.count(term) for term in lgbtq_terms)
        if lgbtq_count > 0:
            lgbtq_score = min(20, lgbtq_count * 5)
            score += lgbtq_score
            details.append(f"lgbtq_terms={lgbtq_count}")

        # Check for Tulsa relevance (max 15 points)
        tulsa_count = text.count("tulsa")
        if tulsa_count > 0:
            tulsa_score = min(15, tulsa_count * 5)
            score += tulsa_score
            details.append(f"tulsa_mentions={tulsa_count}")

        # Check for structured event data (max 15 points)
        has_schema = "schema.org" in resp.text.lower()
        has_ical = any(ext in resp.text.lower() for ext in [".ics", "icalendar", "vcalendar"])
        has_event_markup = soup.find_all(attrs={"class": re.compile(r"event", re.I)})

        if has_schema:
            score += 5
            details.append("has_schema_org")
        if has_ical:
            score += 5
            details.append("has_ical")
        if has_event_markup:
            score += 5
            details.append(f"event_css_classes={len(has_event_markup)}")

    except Exception as e:
        details.append(f"error={e}")
        print(f"[discovery] Error evaluating {url}: {e}")

    # Update the discovered sources file with the score
    discovered = _load_discovered()
    for source in discovered:
        if source["url"] == url:
            source["evaluated"] = True
            source["score"] = score
            source["evaluation_details"] = details
            source["evaluated_at"] = datetime.now().isoformat()
            break
    _save_discovered(discovered)

    print(f"[discovery] {url} scored {score}/100 ({', '.join(details)})")
    return score


if __name__ == "__main__":
    print("=== Tulsa Gays Source Discovery ===")
    new_sources = discover_new_sources()
    for url in new_sources:
        evaluate_source(url)
    print("=== Discovery complete ===")
