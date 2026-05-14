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
# size: "full" = full-width hero, "right" = float right ~45%, "left" = float left ~45%
# alt text: naturally keyword-stuffed for SEO without being obvious

ARTICLE_IMAGES = {
    "gay-bars-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/c/c2/Downtown_Tulsa_Skyline.jpg",
            "alt": "Gay bars Tulsa Oklahoma downtown Boston Avenue nightlife LGBTQ scene",
            "caption": "Photo: Jordan Michael Winn / CC0 (Wikimedia Commons) — Club Majestic sits two blocks off this skyline at 124 N Boston Ave",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Woody_Guthrie_Center_Tulsa_OK20220414_150921835.jpg",
                "alt": "Brady Arts District Tulsa 3rd Street gay bar Tulsa Eagle neighborhood",
                "caption": "Photo: bobistraveling / CC BY 2.0 (Wikimedia Commons) — Brady Arts District, 3rd Street — the Tulsa Eagle is a short walk from here",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Downtown_Tulsa_At_Night_From_Chandler_Park.jpg",
                "alt": "Tulsa Oklahoma nightlife downtown LGBTQ bars gay nightlife after dark",
                "caption": "Photo: Jordan Michael Winn / CC0 (Wikimedia Commons) — Tulsa after dark",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/e/ea/Tulsa_Oklahoma_Downtown_Buildings.jpg",
                "alt": "Tulsa Oklahoma downtown Cherry Street 15th Street gay bar Yellow Brick Road neighborhood",
                "caption": "Photo: Tim Morgan / CC BY-SA 3.0 (Wikimedia Commons) — Tulsa's Cherry Street district, home of Yellow Brick Road",
                "size": "full"
            }
        ]
    },
    "bruce-goff-gay-architect-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/1/15/Tulsa_Club_building_front_360_photo_Tulsa_OK_2025-10-23_13-34-28_1.jpg",
            "alt": "Tulsa Club Hotel 124 West 5th Street downtown Tulsa Oklahoma Bruce Goff architect 1927 LGBTQ history",
            "caption": "Photo: G. Edward Johnson / CC BY 4.0 (Wikimedia Commons) — The Tulsa Club Hotel, designed by Bruce Goff in 1927 at age 23",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/9/9a/Tulsa_Club_Hotel_ballroom_looking_down_Tulsa_OK_2024-11-09_11-51-37.jpg",
                "alt": "Tulsa Club Hotel ballroom interior Art Deco architecture Oklahoma historic landmark LGBTQ travel stay",
                "caption": "Photo: G. Edward Johnson / CC BY 4.0 (Wikimedia Commons) — The ballroom inside the Tulsa Club Hotel — you can stay here",
                "size": "full"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/3/3e/Boston_Avenue_Methodist_Episcopal_Church_Tulsa_78002270.jpg",
                "alt": "Boston Avenue Methodist Church Tulsa Oklahoma Art Deco architecture LGBTQ affirming congregation National Historic Landmark",
                "caption": "Photo: Joseph Zdanowski / CC BY-SA 4.0 (Wikimedia Commons) — Boston Avenue Methodist Church, another Goff-era Tulsa landmark",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/4/46/AdahRobinsonHouse3.jpg",
                "alt": "Adah Robinson House Tulsa Oklahoma Bruce Goff 1923 residential architecture queer history",
                "caption": "Photo: David Stapleton / CC BY-SA 3.0 (Wikimedia Commons) — The Adah Robinson House, 1923 — one of Goff's earliest Tulsa commissions",
                "size": "right"
            }
        ]
    },
    "gay-tulsa-travel-guide": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Tulsa_River_Skyline.jpg",
            "alt": "Gay Tulsa travel guide LGBTQ friendly city Oklahoma Arkansas River skyline visit",
            "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — Tulsa from the river — more than you'd expect",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/6/65/Gathering_Place_-_45581648835.jpg",
                "alt": "Gathering Place Tulsa Oklahoma riverside park LGBTQ friendly free admission community events",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place: 66 acres on the Arkansas River, free, and genuinely world-class",
                "size": "full"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/2/28/Philbrook_Museum_of_Art_entrance_Tulsa_Oklahoma_DSC_0897.jpg",
                "alt": "Philbrook Museum of Art Tulsa Oklahoma LGBTQ friendly cultural destination Waite Phillips mansion",
                "caption": "Photo: Adavyd / CC BY 4.0 (Wikimedia Commons) — Philbrook Museum of Art, housed in a 1920s villa with 23 acres of gardens",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c3/Mayo_Hotel_Tulsa.jpg",
                "alt": "Mayo Hotel downtown Tulsa Oklahoma LGBTQ travel accommodation historic Art Deco landmark",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — The Mayo Hotel — stay here if you want to feel the city's 1920s energy",
                "size": "right"
            }
        ]
    },
    "new-to-tulsa-queer-starter-pack": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/4/47/Tulsa%2C_Oklahoma.jpg",
            "alt": "Tulsa Oklahoma aerial view LGBTQ community new resident queer starter pack guide",
            "caption": "Photo: Caleb Long / CC BY-SA 2.5 (Wikimedia Commons) — Your new city, from above",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/f/f3/Woody_Guthrie_Center.jpg",
                "alt": "Brady Arts District Tulsa Oklahoma 3rd Street LGBTQ nightlife gay bars queer community hub",
                "caption": "Photo: Peter Greenberg / CC BY-SA 3.0 (Wikimedia Commons) — Brady Arts District — your first stop for getting plugged in",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Tulsa%27s_Gathering_Place_-_46443394242.jpg",
                "alt": "Gathering Place Tulsa Oklahoma free park Arkansas River LGBTQ community events new resident guide",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place — free, beautiful, and exactly where you'll meet people",
                "size": "full"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/b/b7/Boston_Avenue_Methodist_Episcopal_Church%2C_Tulsa%2C_OK%2C_Exterior%2C_North_07.JPG",
                "alt": "Boston Avenue Methodist Church Tulsa Oklahoma affirming LGBTQ welcoming congregation queer community",
                "caption": "Photo: Sarah J Malerich / CC BY-SA 3.0 (Wikimedia Commons) — Boston Avenue UMC: affirming, historic, and worth knowing about",
                "size": "right"
            }
        ]
    },
    "date-night-queer-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/2/28/Philbrook_Museum_of_Art_entrance_Tulsa_Oklahoma_DSC_0897.jpg",
            "alt": "Philbrook Museum of Art Tulsa Oklahoma queer date night LGBTQ couples romantic evening cultural destination",
            "caption": "Photo: Adavyd / CC BY 4.0 (Wikimedia Commons) — Philbrook Museum of Art — a date night that actually impresses",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/2/2e/Philbrook_Museum_of_Art_garden_Tulsa_Oklahoma_DSC_0916.jpg",
                "alt": "Philbrook Museum garden Tulsa Oklahoma romantic outdoor space queer couples date night stroll",
                "caption": "Photo: Adavyd / CC BY 4.0 (Wikimedia Commons) — The Philbrook garden at golden hour is one of Tulsa's genuinely great date moves",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/8/83/The_Gathering_Place_-_46426790372.jpg",
                "alt": "Gathering Place Tulsa Oklahoma sunset riverside walk LGBTQ friendly date night outdoor activity",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place at sunset — free, beautiful, and deeply underrated as a date",
                "size": "full"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Downtown_Tulsa_At_Night_From_Chandler_Park.jpg",
                "alt": "Tulsa Oklahoma downtown rooftop bar nightlife LGBTQ queer couples evening date night skyline",
                "caption": "Photo: Jordan Michael Winn / CC0 (Wikimedia Commons) — Tulsa rooftop bars with this exact backdrop",
                "size": "right"
            }
        ]
    },
    "lgbtq-sports-tulsa": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/2/25/Sunday_morning_kickball_game_on_the_Active_Oval_at_Piedmont_Park_in_early_March.jpg",
            "alt": "LGBTQ kickball league Tulsa Oklahoma queer sports outdoor recreation HotMess community team",
            "caption": "Photo: Marc Merlin / CC BY-SA 4.0 (Wikimedia Commons) — HotMess kickball brings this exact energy every week in Tulsa",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/9/90/Sunset_Lanes_bowling_alley_-_Beaverton%2C_OR_%282015%29.jpg",
                "alt": "LGBTQ bowling league Tulsa Oklahoma Lambda Unity queer community sports recreation",
                "caption": "Photo: Steve Morgan / CC BY-SA 3.0 (Wikimedia Commons) — Lambda bowling has been a queer Tulsa staple for decades",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Tulsa%27s_Gathering_Place_-_46443394242.jpg",
                "alt": "Gathering Place Tulsa Oklahoma outdoor recreation LGBTQ sports leagues fields Arkansas River park",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place and the riverside trail host dozens of outdoor league games per season",
                "size": "full"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Tulsa_River_Skyline.jpg",
                "alt": "Tulsa Oklahoma Arkansas River trail running queer LGBTQ outdoor recreation community",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — The river trail is prime territory for the queer running crowd",
                "size": "right"
            }
        ]
    },
    "gilcrease-uncrease-free-arts-series": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/d/d1/New_Gilcrease_Museum_rendering_in_Tulsa%2C_OK.jpg",
            "alt": "Gilcrease Museum Tulsa Oklahoma free arts series UnCrease LGBTQ friendly cultural event community",
            "caption": "Photo: Mara3229 / CC0 (Wikimedia Commons) — Gilcrease Museum, renovated and running one of Tulsa's best free arts programs",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/4/47/Tulsa%2C_Oklahoma.jpg",
                "alt": "Tulsa Oklahoma aerial city arts culture LGBTQ community events free programming",
                "caption": "Photo: Caleb Long / CC BY-SA 2.5 (Wikimedia Commons) — Tulsa's arts scene is bigger than most people realize until they live here",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/a2/Woody_Guthrie_Center_Tulsa_OK20220414_150921835.jpg",
                "alt": "Woody Guthrie Center Brady Arts District Tulsa Oklahoma LGBTQ arts community cultural venue",
                "caption": "Photo: bobistraveling / CC BY 2.0 (Wikimedia Commons) — Brady Arts District, where Tulsa's arts community lives",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/ca/Philbrook_Museum_of_Art.jpg",
                "alt": "Philbrook Museum of Art Tulsa Oklahoma LGBTQ friendly cultural institution queer art community",
                "caption": "Photo: Cwfordo / CC BY-SA 3.0 (Wikimedia Commons) — Philbrook is another Tulsa institution that takes art seriously",
                "size": "full"
            }
        ]
    },
    "how-we-find-every-queer-event": {
        "hero": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/c/c2/Downtown_Tulsa_Skyline.jpg",
            "alt": "Tulsa Oklahoma downtown LGBTQ events weekly queer guide city coverage comprehensive",
            "caption": "Photo: Jordan Michael Winn / CC0 (Wikimedia Commons) — Every corner of this city, every week",
            "size": "full"
        },
        "inline": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/6/65/Gathering_Place_-_45581648835.jpg",
                "alt": "Gathering Place Tulsa Oklahoma event source LGBTQ community programming weekly calendar",
                "caption": "Photo: Paul Sableman / CC BY 2.0 (Wikimedia Commons) — Gathering Place alone generates dozens of events per season we track",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c3/Mayo_Hotel_Tulsa.jpg",
                "alt": "Mayo Hotel Tulsa Oklahoma downtown venue event source LGBTQ community gathering",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — Venues like the Mayo Hotel are regular sources for the weekly guide",
                "size": "right"
            },
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Tulsa_River_Skyline.jpg",
                "alt": "Tulsa Oklahoma city skyline Arkansas River queer community events guide weekly coverage LGBTQ",
                "caption": "Photo: Camerafiend / CC BY-SA 3.0 (Wikimedia Commons) — The whole city, tracked every Monday",
                "size": "full"
            }
        ]
    }
}

# ── CSS to inject into each article's <style> block ───────────────────────────
FIGURE_CSS = """
        .post-figure {
            margin: 1.5rem 0;
            overflow: hidden;
        }
        .post-figure.pf-full { clear: both; }
        .post-figure.pf-right {
            float: right;
            width: 46%;
            margin: 0.25rem 0 1rem 1.5rem;
        }
        .post-figure.pf-left {
            float: left;
            width: 46%;
            margin: 0.25rem 1.5rem 1rem 0;
        }
        .post-figure img {
            width: 100%;
            border-radius: 6px;
            max-height: 320px;
            object-fit: cover;
            display: block;
        }
        .post-figure.pf-full img { max-height: 420px; }
        .post-figure figcaption {
            font-size: 0.75rem;
            color: var(--text-muted, #888);
            margin-top: 0.4rem;
            text-align: center;
            font-style: italic;
            line-height: 1.4;
            white-space: normal;
            overflow: visible;
        }
        .post-figure.pf-right figcaption,
        .post-figure.pf-left figcaption { text-align: left; }
        .post-clearfix { clear: both; }
        @media (max-width: 600px) {
            .post-figure.pf-right,
            .post-figure.pf-left {
                float: none;
                width: 100%;
                margin: 1.5rem 0;
            }
        }
"""

def _size_class(size):
    return {"full": "pf-full", "right": "pf-right", "left": "pf-left"}.get(size, "pf-full")

def make_figure(img_data):
    cls = _size_class(img_data.get("size", "full"))
    return (
        f'<figure class="post-figure {cls}">\n'
        f'    <img src="{img_data["url"]}" alt="{img_data["alt"]}" loading="lazy">\n'
        f'    <figcaption>{img_data["caption"]}</figcaption>\n'
        f'</figure>'
    )

def make_hero(img_data):
    return (
        f'<figure class="post-figure pf-full" style="margin-top:0;">\n'
        f'    <img src="{img_data["url"]}" alt="{img_data["alt"]}" loading="eager" '
        f'style="max-height:460px;">\n'
        f'    <figcaption>{img_data["caption"]}</figcaption>\n'
        f'</figure>\n'
        f'<div class="post-clearfix"></div>'
    )

def add_images_to_article(slug, images):
    path = BLOG_DIR / f"{slug}.html"
    if not path.exists():
        print(f"[SKIP] {slug}.html not found")
        return

    html = path.read_text(encoding="utf-8")

    # Skip if images already added (idempotent)
    if 'class="post-figure"' in html:
        print(f"[SKIP] {slug}.html already has images — removing duplicates first")
        soup = BeautifulSoup(html, "html.parser")
        for fig in soup.find_all("figure", class_="post-figure"):
            fig.decompose()
        html = str(soup)

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
