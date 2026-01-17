"""
Web scraping module for fetching MTG stories from the official website.
Uses the Contentful API to get story sets and metadata.
"""

import time
from datetime import datetime
import requests

BASE_URL = "https://magic.wizards.com"
CONTENTFUL_API = "https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries"
CONTENTFUL_TOKEN = "CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Authorization": f"Bearer {CONTENTFUL_TOKEN}"
}

# Years to fetch from the archive
YEARS = list(range(2025, 2013, -1))  # 2025 down to 2014


def fetch_all_story_sets() -> dict[int, list[dict]]:
    """
    Fetch all story sets from all years.

    Returns:
        Dict mapping year to list of story set dicts.
        Each story set has: name, year, stories (list of story info), image_url
    """
    all_sets = {}

    for year in YEARS:
        try:
            sets = _fetch_story_sets_for_year(year)
            if sets:
                all_sets[year] = sets
        except Exception as e:
            print(f"Failed to fetch year {year}: {e}")

    return all_sets


def _fetch_story_sets_for_year(year: int) -> list[dict]:
    """Fetch story sets for a specific year from the Contentful API."""
    params = {
        "content_type": "storyGroup",
        "locale": "en",
        "include": "10",
        "fields.firstStoryYear[in]": str(year)
    }

    response = requests.get(
        CONTENTFUL_API,
        params=params,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    # Build lookup maps for linked entries and assets
    entries_map = {}
    assets_map = {}

    for entry in data.get("includes", {}).get("Entry", []):
        entries_map[entry["sys"]["id"]] = entry

    for asset in data.get("includes", {}).get("Asset", []):
        assets_map[asset["sys"]["id"]] = asset

    # Process story sets
    story_sets = []

    for item in data.get("items", []):
        fields = item.get("fields", {})

        # Get story set name
        name = fields.get("name", "Unknown")

        # Get thumbnail image URL
        image_url = None
        thumbnail_link = fields.get("archiveThumbnail", {}).get("sys", {})
        if thumbnail_link.get("id"):
            asset = assets_map.get(thumbnail_link["id"])
            if asset:
                file_info = asset.get("fields", {}).get("file", {})
                image_url = file_info.get("url")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

        # Get stories
        stories = []
        external_links = []  # E-book/external links (Amazon, etc.)

        for story_link in fields.get("stories", []):
            story_id = story_link.get("sys", {}).get("id")
            if story_id and story_id in entries_map:
                story_entry = entries_map[story_id]
                story_fields = story_entry.get("fields", {})
                content_type = story_entry.get("sys", {}).get("contentType", {}).get("sys", {}).get("id", "")

                url = None
                title = story_fields.get("title", "")
                pub_date = None

                if content_type == "article":
                    # Newer format: has slug and category
                    category = story_fields.get("category", "magic-story")
                    slug = story_fields.get("slug", "")
                    url = f"{BASE_URL}/en/news/{category}/{slug}" if slug else None

                    # Parse publication date
                    pub_date_str = story_fields.get("publishedDate", "")
                    if pub_date_str:
                        try:
                            pub_date = datetime.strptime(pub_date_str[:19], "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            try:
                                pub_date = datetime.strptime(pub_date_str[:10], "%Y-%m-%d")
                            except ValueError:
                                pass

                elif content_type == "storyEntry":
                    # Older format: check CTA for URL
                    cta_link = story_fields.get("cta", {}).get("sys", {})
                    if cta_link.get("id") and cta_link["id"] in entries_map:
                        cta_entry = entries_map[cta_link["id"]]
                        cta_fields = cta_entry.get("fields", {})
                        link = cta_fields.get("link", "")
                        # Only use if it's a magic.wizards.com link (not Amazon, etc.)
                        if link and "magic.wizards.com" in link:
                            url = link
                        elif link:
                            # External link (e-book, Amazon, etc.)
                            external_links.append({"title": title, "url": link})

                if url:
                    stories.append({
                        "title": title,
                        "url": url,
                        "slug": story_fields.get("slug", ""),
                        "published_date": pub_date
                    })

        # Sort stories by publication date
        stories.sort(key=lambda s: s["published_date"] or datetime.min)

        story_sets.append({
            "name": name,
            "year": year,
            "stories": stories,
            "external_links": external_links,  # E-books/Amazon links
            "image_url": image_url
        })

    return story_sets


def fetch_stories_for_set(story_set: dict) -> list[dict]:
    """
    Get stories for a story set.
    The stories are already included in the story_set dict from fetch_all_story_sets().

    Args:
        story_set: A story set dict from fetch_all_story_sets()

    Returns:
        List of story dicts with url, title, published_date
    """
    return story_set.get("stories", [])


def fetch_story_page(url: str) -> str:
    """
    Download an individual story page.

    Args:
        url: The full URL of the story.

    Returns:
        HTML content of the story page.
    """
    # Add a small delay to be respectful to the server
    time.sleep(0.5)

    response = requests.get(
        url,
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=30
    )
    response.raise_for_status()
    return response.text
