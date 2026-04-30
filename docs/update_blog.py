"""Update the Tulsa Gays blog with current event data.

Reads event JSON from data/events/, uses Jinja2 templates to regenerate
index.html with current events, and updates the archive with previous weeks.
"""

import sys
import os
import json
import shutil
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Jinja2 not installed. Run: pip install jinja2")
    sys.exit(1)


# ── Paths ────────────────────────────────────────────────────────────────
BLOG_DIR = config.BLOG_DIR
TEMPLATES_DIR = os.path.join(BLOG_DIR, "templates")
EVENTS_DIR = config.EVENTS_DIR
ARCHIVE_DIR = os.path.join(BLOG_DIR, "archive")


def ensure_dirs():
    """Create required directories."""
    for d in [TEMPLATES_DIR, ARCHIVE_DIR, EVENTS_DIR]:
        os.makedirs(d, exist_ok=True)


def load_current_events():
    """Load the current week's events from JSON files in data/events/.

    Looks for a file matching the current week key (e.g., 2026-W13.json)
    or falls back to the most recent events file.

    Returns:
        dict: Event data with keys like 'featured', 'community',
              'arts_culture', 'nightlife', and metadata.
    """
    week_key = config.current_week_key()
    week_file = os.path.join(EVENTS_DIR, f"{week_key}.json")

    if os.path.exists(week_file):
        with open(week_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fall back to the most recent events file
    json_files = sorted(
        [f for f in os.listdir(EVENTS_DIR) if f.endswith(".json")],
        reverse=True,
    )
    if json_files:
        latest = os.path.join(EVENTS_DIR, json_files[0])
        with open(latest, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def load_archive_index():
    """Load the archive index (list of past weeks).

    Returns:
        list[dict]: Each dict has 'week_key', 'date_range', 'filename'.
    """
    index_file = os.path.join(ARCHIVE_DIR, "index.json")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive_index(archive_entries):
    """Save the archive index."""
    index_file = os.path.join(ARCHIVE_DIR, "index.json")
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(archive_entries, f, indent=2)


def get_week_date_range(week_key=None):
    """Get a human-readable date range for a given week key.

    Args:
        week_key: e.g. '2026-W13'. Defaults to current week.

    Returns:
        str: e.g. 'March 24 - March 30, 2026'
    """
    if week_key is None:
        week_key = config.current_week_key()

    year, week_num = week_key.split("-W")
    year = int(year)
    week_num = int(week_num)

    # Monday of that ISO week
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week_num - 1)
    sunday = monday + timedelta(days=6)

    if monday.month == sunday.month:
        return f"{monday.strftime('%B')} {monday.day} - {sunday.day}, {year}"
    else:
        return f"{monday.strftime('%B')} {monday.day} - {sunday.strftime('%B')} {sunday.day}, {year}"


def categorize_events(events_data):
    """Organize raw events into display categories.

    Args:
        events_data: dict with 'events' list, each event having a 'category' field.

    Returns:
        dict with keys: featured, community, arts_culture, nightlife
    """
    categorized = {
        "featured": [],
        "community": [],
        "arts_culture": [],
        "nightlife": [],
    }

    if not events_data or "events" not in events_data:
        return categorized

    for event in events_data["events"]:
        cat = event.get("category", "community").lower()
        if cat == "featured":
            categorized["featured"].append(event)
        elif cat in ("arts", "arts_culture", "arts & culture"):
            categorized["arts_culture"].append(event)
        elif cat == "nightlife":
            categorized["nightlife"].append(event)
        else:
            categorized["community"].append(event)

    return categorized


def create_jinja_templates():
    """Create Jinja2 template files if they don't exist."""
    ensure_dirs()

    index_template = os.path.join(TEMPLATES_DIR, "index.html.j2")
    if not os.path.exists(index_template):
        with open(index_template, "w", encoding="utf-8") as f:
            f.write(INDEX_TEMPLATE)

    archive_template = os.path.join(TEMPLATES_DIR, "archive.html.j2")
    if not os.path.exists(archive_template):
        with open(archive_template, "w", encoding="utf-8") as f:
            f.write(ARCHIVE_TEMPLATE)


def render_index(events_data, date_range):
    """Render index.html with current event data.

    Args:
        events_data: Categorized events dict.
        date_range: Human-readable date range string.
    """
    create_jinja_templates()
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("index.html.j2")

    html = template.render(
        date_range=date_range,
        featured=events_data.get("featured", []),
        community=events_data.get("community", []),
        arts_culture=events_data.get("arts_culture", []),
        nightlife=events_data.get("nightlife", []),
        year=datetime.now().year,
    )

    output_path = os.path.join(BLOG_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[blog] Updated index.html with events for {date_range}")


def render_archive(archive_entries):
    """Render archive.html with past weeks list.

    Args:
        archive_entries: List of dicts with week_key, date_range, filename.
    """
    create_jinja_templates()
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("archive.html.j2")

    html = template.render(
        weeks=archive_entries,
        year=datetime.now().year,
    )

    output_path = os.path.join(BLOG_DIR, "archive.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[blog] Updated archive.html with {len(archive_entries)} weeks")


def archive_current_week():
    """Move current index.html to the archive before updating.

    Copies the current index.html to archive/{week_key}.html and
    updates the archive index.
    """
    ensure_dirs()
    week_key = config.current_week_key()
    date_range = get_week_date_range(week_key)

    current_index = os.path.join(BLOG_DIR, "index.html")
    if not os.path.exists(current_index):
        return

    archive_file = f"{week_key}.html"
    archive_path = os.path.join(ARCHIVE_DIR, archive_file)
    shutil.copy2(current_index, archive_path)

    archive_entries = load_archive_index()

    # Don't add duplicate entries
    existing_keys = {e["week_key"] for e in archive_entries}
    if week_key not in existing_keys:
        archive_entries.insert(0, {
            "week_key": week_key,
            "date_range": date_range,
            "filename": archive_file,
        })
        save_archive_index(archive_entries)
        print(f"[blog] Archived week {week_key} to {archive_file}")


def update_blog():
    """Main entry point: update the blog with current events.

    1. Archives the current index.html
    2. Loads new event data from data/events/
    3. Renders a fresh index.html
    4. Updates the archive page

    Returns:
        bool: True if successful, False otherwise.
    """
    ensure_dirs()

    # Load events
    events_data = load_current_events()
    if events_data is None:
        print("[blog] No event data found in data/events/. Skipping update.")
        return False

    week_key = events_data.get("week_key", config.current_week_key())
    date_range = events_data.get("date_range", get_week_date_range(week_key))

    # Archive previous content
    archive_current_week()

    # Categorize and render
    categorized = categorize_events(events_data)
    render_index(categorized, date_range)

    # Update archive page
    archive_entries = load_archive_index()
    render_archive(archive_entries)

    return True


# ── Jinja2 Templates (embedded) ─────────────────────────────────────────

INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tulsa Gays - Your Weekly LGBTQ+ Event Guide for Tulsa</title>
    <meta name="description" content="Tulsa Gays is your weekly LGBTQ+ event guide for Tulsa, Oklahoma. Find queer events, pride happenings, drag shows, community gatherings, and more.">
    <meta name="keywords" content="Tulsa LGBTQ events, Tulsa gay events, Tulsa pride, queer Tulsa, Tulsa drag shows, LGBTQ Oklahoma, Tulsa nightlife, Homo Hotel Happy Hour, OKEQ events">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="Tulsa Gays - Weekly LGBTQ+ Events">
    <meta property="og:description" content="Your weekly guide to LGBTQ+ events in Tulsa, Oklahoma. Community gatherings, nightlife, arts, and more.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://tulsagays.github.io">
    <meta property="og:site_name" content="Tulsa Gays">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Tulsa Gays - Weekly LGBTQ+ Events">
    <meta name="twitter:description" content="Your weekly guide to LGBTQ+ events in Tulsa, Oklahoma.">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header class="site-header">
        <div class="header-inner">
            <a href="index.html" class="logo-area">
                <div>
                    <div class="logo-text">Tulsa Gays</div>
                    <div class="logo-tagline">Your Weekly LGBTQ+ Event Guide</div>
                </div>
            </a>
            <button class="nav-toggle" aria-label="Toggle navigation" onclick="document.querySelector('nav').classList.toggle('open')">&#9776;</button>
            <nav>
                <ul>
                    <li><a href="index.html" class="active">This Week</a></li>
                    <li><a href="archive.html">Archive</a></li>
                    <li><a href="about.html">About</a></li>
                    <li><a href="https://instagram.com/tulsagays" target="_blank" rel="noopener">Instagram</a></li>
                </ul>
            </nav>
        </div>
    </header>
    <main class="container">
        <div class="week-header">
            <h1>This Week's Events</h1>
            <p class="date-range">{{ date_range }}</p>
            <div class="rainbow-bar rainbow-gradient"></div>
        </div>
        {% if featured %}
        <section class="events-section">
            <h2 class="section-title"><span class="emoji">&#11088;</span> Featured</h2>
            <div class="events-grid">
                {% for event in featured %}
                <article class="event-card featured">
                    <span class="event-badge badge-featured">Featured</span>
                    <h3 class="event-name">{{ event.name }}</h3>
                    <div class="event-meta">
                        <span class="event-datetime">{{ event.datetime }}</span>
                        <span class="event-venue">{{ event.venue }}</span>
                    </div>
                    <p class="event-description">{{ event.description }}</p>
                    {% if event.url %}<a href="{{ event.url }}" class="event-link" target="_blank" rel="noopener">More Info &rarr;</a>{% endif %}
                </article>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        {% if community %}
        <section class="events-section">
            <h2 class="section-title"><span class="emoji">&#129309;</span> Community</h2>
            <div class="events-grid">
                {% for event in community %}
                <article class="event-card">
                    <span class="event-badge badge-community">Community</span>
                    <h3 class="event-name">{{ event.name }}</h3>
                    <div class="event-meta">
                        <span class="event-datetime">{{ event.datetime }}</span>
                        <span class="event-venue">{{ event.venue }}</span>
                    </div>
                    <p class="event-description">{{ event.description }}</p>
                    {% if event.url %}<a href="{{ event.url }}" class="event-link" target="_blank" rel="noopener">Details &rarr;</a>{% endif %}
                </article>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        {% if arts_culture %}
        <section class="events-section">
            <h2 class="section-title"><span class="emoji">&#127912;</span> Arts &amp; Culture</h2>
            <div class="events-grid">
                {% for event in arts_culture %}
                <article class="event-card">
                    <span class="event-badge badge-arts">Arts &amp; Culture</span>
                    <h3 class="event-name">{{ event.name }}</h3>
                    <div class="event-meta">
                        <span class="event-datetime">{{ event.datetime }}</span>
                        <span class="event-venue">{{ event.venue }}</span>
                    </div>
                    <p class="event-description">{{ event.description }}</p>
                    {% if event.url %}<a href="{{ event.url }}" class="event-link" target="_blank" rel="noopener">Details &rarr;</a>{% endif %}
                </article>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        {% if nightlife %}
        <section class="events-section">
            <h2 class="section-title"><span class="emoji">&#127878;</span> Nightlife</h2>
            <div class="events-grid">
                {% for event in nightlife %}
                <article class="event-card">
                    <span class="event-badge badge-nightlife">Nightlife</span>
                    <h3 class="event-name">{{ event.name }}</h3>
                    <div class="event-meta">
                        <span class="event-datetime">{{ event.datetime }}</span>
                        <span class="event-venue">{{ event.venue }}</span>
                    </div>
                    <p class="event-description">{{ event.description }}</p>
                    {% if event.url %}<a href="{{ event.url }}" class="event-link" target="_blank" rel="noopener">Details &rarr;</a>{% endif %}
                </article>
                {% endfor %}
            </div>
        </section>
        {% endif %}
        {% if not featured and not community and not arts_culture and not nightlife %}
        <p class="no-events">No events listed for this week yet. Check back soon!</p>
        {% endif %}
    </main>
    <footer class="site-footer">
        <div class="footer-inner">
            <p>Follow us on Instagram: <a href="https://instagram.com/tulsagays" target="_blank" rel="noopener">@tulsagays</a></p>
            <p>Updated weekly &middot; Your guide to LGBTQ+ Tulsa</p>
            <p style="font-size:0.75em;opacity:0.55;margin-top:0.5em">&copy; 2026 Tulsa Gays&#8482; &middot; Homo Hotel Happy Hour&#8482;</p>
        </div>
    </footer>
</body>
</html>"""

ARCHIVE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Event Archive - Tulsa Gays</title>
    <meta name="description" content="Archive of past LGBTQ+ events in Tulsa, Oklahoma.">
    <meta property="og:title" content="Event Archive - Tulsa Gays">
    <meta property="og:description" content="Browse past weeks' LGBTQ+ event guides for Tulsa, Oklahoma.">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header class="site-header">
        <div class="header-inner">
            <a href="index.html" class="logo-area">
                <div>
                    <div class="logo-text">Tulsa Gays</div>
                    <div class="logo-tagline">Your Weekly LGBTQ+ Event Guide</div>
                </div>
            </a>
            <button class="nav-toggle" aria-label="Toggle navigation" onclick="document.querySelector('nav').classList.toggle('open')">&#9776;</button>
            <nav>
                <ul>
                    <li><a href="index.html">This Week</a></li>
                    <li><a href="archive.html" class="active">Archive</a></li>
                    <li><a href="about.html">About</a></li>
                    <li><a href="https://instagram.com/tulsagays" target="_blank" rel="noopener">Instagram</a></li>
                </ul>
            </nav>
        </div>
    </header>
    <main class="container">
        <div class="week-header">
            <h1>Event Archive</h1>
            <p class="date-range">Browse past weeks' LGBTQ+ events in Tulsa</p>
            <div class="rainbow-bar rainbow-gradient"></div>
        </div>
        <div class="archive-list">
            <h2>Past Weeks</h2>
            {% if weeks %}
                {% for week in weeks %}
                <a href="archive/{{ week.filename }}" class="archive-week">
                    <span class="week-label">Week of {{ week.date_range }}</span>
                    <span class="week-date">{{ week.week_key }}</span>
                </a>
                {% endfor %}
            {% else %}
                <p class="no-events">No archived weeks yet. Check back after the first week!</p>
            {% endif %}
        </div>
    </main>
    <footer class="site-footer">
        <div class="footer-inner">
            <p>Follow us on Instagram: <a href="https://instagram.com/tulsagays" target="_blank" rel="noopener">@tulsagays</a></p>
            <p>Updated weekly &middot; Your guide to LGBTQ+ Tulsa</p>
            <p style="font-size:0.75em;opacity:0.55;margin-top:0.5em">&copy; 2026 Tulsa Gays&#8482; &middot; Homo Hotel Happy Hour&#8482;</p>
        </div>
    </footer>
</body>
</html>"""


if __name__ == "__main__":
    success = update_blog()
    if success:
        print("[blog] Blog update complete.")
    else:
        print("[blog] Blog update skipped (no event data).")
