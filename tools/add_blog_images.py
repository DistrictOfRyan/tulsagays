"""
Add hero + inline images to all TulsaGays blog articles and thumbnails to blog index.
All images sourced from Wikimedia Commons (CC licensed). Run once, commit result.
"""

import os
import re
from bs4 import BeautifulSoup, Tag
from pathlib import Path

BLOG_DIR = Path(__file__).resolve().parent.parent / "docs" / "blog"

# ── Image data ────────────────────────────────────────────────────────────────
ARTICLE_IMAGES = {
    "gay-bars-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/c/c2/Downtown_Tulsa_Skyline.jpg",
            "alt": "Downtown Tulsa skyline near Boston Avenue",
            "caption": "Photo: Jordan Michael Winn / CC0 Public Domain (Wikimedia Commons)"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/f/f3/Woody_Guthrie_Center.jpg",
                "alt": "Woody Guthrie Center in Tulsa's Brady Arts District, near the Tulsa Eagle",
                "caption": "Photo: Peter Greenberg / CC BY-SA 3.0 (Wikimedia Commons) — Brady Arts District, home of the Tulsa Eagle"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Downtown_Tulsa_At_Night_From_Chandler_Park.jpg",
                "alt": "Downtown Tulsa at night from Chandler Park",
                "caption": "Photo: Jordan Michael Winn / CC0 Public Domain (Wikimedia Commons) — Tulsa nights run late when there's somewhere to be"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/e/ea/Tulsa_Oklahoma_Downtown_Buildings.jpg",
                "alt": "Buildings in downtown Tulsa, Oklahoma",
                "caption": "Photo: Tim Morgan / CC BY-SA 3.0 (Wikimedia Commons)"
            }
        ]
    },
    "bruce-goff-gay-architect-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/1/15/Tulsa_Club_building_front_360_photo_Tulsa_OK_2025-10-23_13-34-28_1.jpg",
            "alt": "The Tulsa Club building exterior, designed by Bruce Goff in 1927, now the Tulsa Club Hotel",
            "caption": "Photo: G. Edward Johnson / CC BY 4.0 (Wikimedia Commons) — The Tulsa Club building, designed by Bruce Goff at age 23"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/9/9a/Tulsa_Club_Hotel_ballroom_looking_down_Tulsa_OK_2024-11-09_11-51-37.jpg",
                "alt": "Interior of the Tulsa Club Hotel ballroom",
                "caption": "Photo: G. Edward Johnson / CC BY 4.0 (Wikimedia Commons) — The Tulsa Club Hotel ballroom. Sleep inside his masterpiece."
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/3/3e/Boston_Avenue_Methodist_Episcopal_Church_Tulsa_78002270.jpg",
                "alt": "Boston Avenue Methodist Church in Tulsa, an Art Deco landmark",
                "caption": "Photo: Joseph Zdanowski / CC BY-SA 4.0 (Wikimedia Commons) — Boston Avenue Methodist Church, a Goff-era masterwork"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/4/46/AdahRobinsonHouse3.jpg",
                "alt": "The Adah Robinson House in Tulsa, designed by Bruce Goff in 1923",
                "caption": "Photo: David Stapleton / CC BY-SA 3.0 (Wikimedia Commons) — The Adah Robinson House, one of Goff's earliest Tulsa commissions"
            }
        ]
    },
    "gay-tulsa-travel-guide": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Tulsa_River_Skyline.jpg",
            "alt": "Tulsa skyline viewed from the Arkansas River",
            "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons)"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/6/65/Gathering_Place_-_45581648835.jpg",
                "alt": "Gathering Place park along the Arkansas River in Tulsa",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place: 66 acres, free, and stunning"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/ca/Philbrook_Museum_of_Art.jpg",
                "alt": "Philbrook Museum of Art, housed in the former Waite Phillips mansion in Tulsa",
                "caption": "Photo: Cwfordo / CC BY-SA 3.0 (Wikimedia Commons) — Philbrook Museum of Art"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c3/Mayo_Hotel_Tulsa.jpg",
                "alt": "Mayo Hotel in downtown Tulsa, Oklahoma",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — The historic Mayo Hotel, a landmark Tulsa stay"
            }
        ]
    },
    "new-to-tulsa-queer-starter-pack": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/4/47/Tulsa%2C_Oklahoma.jpg",
            "alt": "Aerial view of Tulsa, Oklahoma",
            "caption": "Photo: Caleb Long / CC BY-SA 2.5 (Wikimedia Commons)"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Woody_Guthrie_Center_Tulsa_OK20220414_150921835.jpg",
                "alt": "Woody Guthrie Center exterior in Tulsa's Brady Arts District",
                "caption": "Photo: bobistraveling / CC BY 2.0 (Wikimedia Commons) — The Arts District is the heart of Tulsa's queer scene"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Tulsa%27s_Gathering_Place_-_46443394242.jpg",
                "alt": "Tulsa's Gathering Place park on the Arkansas River",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place: your first free afternoon sorted"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/3/3e/Boston_Avenue_Methodist_Episcopal_Church_Tulsa_78002270.jpg",
                "alt": "Boston Avenue Methodist Church, a Tulsa landmark and affirming congregation",
                "caption": "Photo: Joseph Zdanowski / CC BY-SA 4.0 (Wikimedia Commons) — Boston Avenue UMC: affirming and historic"
            }
        ]
    },
    "date-night-queer-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/2/28/Philbrook_Museum_of_Art_entrance_Tulsa_Oklahoma_DSC_0897.jpg",
            "alt": "Entrance to Philbrook Museum of Art in Tulsa, Oklahoma",
            "caption": "Photo: Adavyd / CC BY 4.0 (Wikimedia Commons) — Philbrook Museum: one of Tulsa's premier date-night destinations"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/2/2e/Philbrook_Museum_of_Art_garden_Tulsa_Oklahoma_DSC_0916.jpg",
                "alt": "Gardens at Philbrook Museum of Art in Tulsa",
                "caption": "Photo: Adavyd / CC BY 4.0 (Wikimedia Commons) — The Philbrook garden at sunset"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/8/83/The_Gathering_Place_-_46426790372.jpg",
                "alt": "The Gathering Place park along the Arkansas River at sunset",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place at golden hour is a genuinely good move"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Downtown_Tulsa_At_Night_From_Chandler_Park.jpg",
                "alt": "Tulsa downtown skyline at night from Chandler Park",
                "caption": "Photo: Jordan Michael Winn / CC0 Public Domain (Wikimedia Commons) — Rooftop bars with this view"
            }
        ]
    },
    "lgbtq-sports-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/2/25/Sunday_morning_kickball_game_on_the_Active_Oval_at_Piedmont_Park_in_early_March.jpg",
            "alt": "Kickball game in progress at a park on a sunny morning",
            "caption": "Photo: Marc Merlin / CC BY-SA 4.0 (Wikimedia Commons) — Queer kickball brings this exact energy every week"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/9/90/Sunset_Lanes_bowling_alley_-_Beaverton%2C_OR_%282015%29.jpg",
                "alt": "Interior of a bowling alley with colorful lanes",
                "caption": "Photo: Steve Morgan / CC BY-SA 3.0 (Wikimedia Commons) — Lambda bowling leagues have been a queer Tulsa staple for decades"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/6/65/Gathering_Place_-_45581648835.jpg",
                "alt": "Gathering Place park in Tulsa, a popular outdoor recreation spot",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Outdoor Tulsa venues host leagues and games all spring"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Tulsa_River_Skyline.jpg",
                "alt": "Tulsa skyline along the Arkansas River",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — The river trail is prime territory for queer runners and walkers"
            }
        ]
    },
    "gilcrease-uncrease-free-arts-series": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/d/d1/New_Gilcrease_Museum_rendering_in_Tulsa%2C_OK.jpg",
            "alt": "Rendering of the new Gilcrease Museum building in Tulsa, Oklahoma",
            "caption": "Photo: Mara3229 / CC0 Public Domain (Wikimedia Commons) — Gilcrease Museum after its recent renovation"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Woody_Guthrie_Center_Tulsa_OK20220414_150921835.jpg",
                "alt": "Woody Guthrie Center in Tulsa's Brady Arts District",
                "caption": "Photo: bobistraveling / CC BY 2.0 (Wikimedia Commons) — Tulsa's arts scene runs through the Brady District year-round"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/b/b7/Boston_Avenue_Methodist_Episcopal_Church%2C_Tulsa%2C_OK%2C_Exterior%2C_North_07.JPG",
                "alt": "Boston Avenue Methodist Church exterior in Tulsa",
                "caption": "Photo: Sarah J Malerich / CC BY-SA 3.0 (Wikimedia Commons) — Tulsa has always taken public art seriously"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c2/Downtown_Tulsa_Skyline.jpg",
                "alt": "Downtown Tulsa skyline",
                "caption": "Photo: Jordan Michael Winn / CC0 Public Domain (Wikimedia Commons)"
            }
        ]
    },
    "how-we-find-every-queer-event": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/4/47/Tulsa%2C_Oklahoma.jpg",
            "alt": "Aerial view of Tulsa, Oklahoma",
            "caption": "Photo: Caleb Long / CC BY-SA 2.5 (Wikimedia Commons) — Every corner of this city, every week"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Woody_Guthrie_Center_Tulsa_OK20220414_150921835.jpg",
                "alt": "Woody Guthrie Center, one of Tulsa's premier event venues",
                "caption": "Photo: bobistraveling / CC BY 2.0 (Wikimedia Commons) — Venues like this are regular sources for the weekly guide"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Tulsa%27s_Gathering_Place_-_46443394242.jpg",
                "alt": "Gathering Place park in Tulsa, site of many community events",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place alone generates dozens of events per season"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Downtown_Tulsa_At_Night_From_Chandler_Park.jpg",
                "alt": "Tulsa at night from Chandler Park",
                "caption": "Photo: Jordan Michael Winn / CC0 Public Domain (Wikimedia Commons) — Something is always happening"
            }
        ]
    }
}

# ── CSS to inject into each article's <style> block ───────────────────────────
FIGURE_CSS = """
        .post-figure {
            margin: 2rem 0;
        }
        .post-figure img {
            width: 100%;
            border-radius: 6px;
            max-height: 420px;
            object-fit: cover;
            display: block;
        }
        .post-figure figcaption {
            font-size: 0.8rem;
            color: var(--text-muted, #888);
            margin-top: 0.5rem;
            text-align: center;
            font-style: italic;
        }
        .post-hero-img {
            width: 100%;
            border-radius: 8px;
            max-height: 460px;
            object-fit: cover;
            display: block;
            margin-bottom: 2rem;
        }
"""

def make_figure(img_data):
    return (
        f'<figure class="post-figure">\n'
        f'    <img src="{img_data["url"]}" alt="{img_data["alt"]}" loading="lazy">\n'
        f'    <figcaption>{img_data["caption"]}</figcaption>\n'
        f'</figure>'
    )

def make_hero(img_data):
    return (
        f'<figure class="post-figure" style="margin-top:0;">\n'
        f'    <img src="{img_data["url"]}" alt="{img_data["alt"]}" '
        f'class="post-hero-img" loading="eager">\n'
        f'    <figcaption>{img_data["caption"]}</figcaption>\n'
        f'</figure>'
    )

def add_images_to_article(slug, images):
    path = BLOG_DIR / f"{slug}.html"
    if not path.exists():
        print(f"[SKIP] {slug}.html not found")
        return

    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Inject CSS into first <style> tag
    style_tag = soup.find("style")
    if style_tag and FIGURE_CSS not in style_tag.string:
        style_tag.string = (style_tag.string or "") + FIGURE_CSS

    # Find post-body (may be div or article)
    post_body = soup.find(class_="post-body")
    if not post_body:
        # Fallback: find main content div with style containing max-width:700px
        post_body = soup.find(style=lambda s: s and "max-width:700px" in s.replace(" ", ""))

    if not post_body:
        print(f"[WARN] Could not find post-body in {slug}.html — skipping")
        return

    # Add hero image at the very start of post-body
    hero_html = make_hero(images["hero"])
    hero_tag = BeautifulSoup(hero_html, "html.parser")
    first_child = post_body.find(True)  # first tag child
    if first_child:
        first_child.insert_before(hero_tag)
    else:
        post_body.append(hero_tag)

    # Find all h2 tags in post-body for inline image placement
    h2_tags = post_body.find_all("h2")
    inline_imgs = images.get("inline", [])

    # Place one inline image after each of the first N h2 sections
    for i, img_data in enumerate(inline_imgs[:len(h2_tags)]):
        target_h2 = h2_tags[i]
        # Find the next sibling that's a block element (p, ul, div)
        # Insert image after the first paragraph following this h2
        sibling = target_h2.find_next_sibling()
        insert_count = 0
        while sibling and insert_count < 2:
            if sibling.name in ("p", "ul", "div", "blockquote"):
                insert_count += 1
                if insert_count == 2:
                    break
            sibling = sibling.find_next_sibling()

        if sibling is None:
            # No good spot, insert after the h2 itself
            figure_tag = BeautifulSoup(make_figure(img_data), "html.parser")
            target_h2.insert_after(figure_tag)
        else:
            figure_tag = BeautifulSoup(make_figure(img_data), "html.parser")
            sibling.insert_after(figure_tag)

    # If fewer h2s than inline images, append remaining to end of post-body
    if len(inline_imgs) > len(h2_tags):
        for img_data in inline_imgs[len(h2_tags):]:
            figure_tag = BeautifulSoup(make_figure(img_data), "html.parser")
            post_body.append(figure_tag)

    path.write_text(str(soup), encoding="utf-8")
    print(f"[ok] {slug}.html — hero + {len(inline_imgs)} inline images added")


def add_thumbnails_to_index():
    index_path = BLOG_DIR / "index.html"
    html = index_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Add thumbnail CSS
    head = soup.find("head")
    thumb_css = BeautifulSoup(
        '<style>.blog-thumb{width:100%;height:200px;object-fit:cover;'
        'border-radius:8px 8px 0 0;display:block;}</style>', "html.parser"
    )
    if "blog-thumb" not in html:
        head.append(thumb_css)

    # Find all event-card links
    cards = soup.find_all("a", class_="event-card")
    for card in cards:
        href = card.get("href", "")
        slug = href.replace(".html", "").replace("./", "")
        if slug not in ARTICLE_IMAGES:
            continue
        # Skip if thumbnail already added
        if card.find("img"):
            continue
        hero_url = ARTICLE_IMAGES[slug]["hero"]["url"]
        hero_alt = ARTICLE_IMAGES[slug]["hero"]["alt"]
        img_tag = soup.new_tag("img", src=hero_url, alt=hero_alt,
                               loading="lazy", **{"class": "blog-thumb"})
        card.insert(0, img_tag)
        print(f"[ok] index thumbnail: {slug}")

    index_path.write_text(str(soup), encoding="utf-8")
    print("[ok] blog/index.html updated with thumbnails")


if __name__ == "__main__":
    print("Adding images to TulsaGays blog articles...")
    for slug, images in ARTICLE_IMAGES.items():
        add_images_to_article(slug, images)
    add_thumbnails_to_index()
    print("\nDone. Commit and push to deploy.")
