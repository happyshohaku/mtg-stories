"""
Web scraping module for fetching MTG stories from the official website.
Uses the Contentful API to get story sets and metadata.
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import dedup
from . import net

BASE_URL = "https://magic.wizards.com"
CONTENTFUL_API = "https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries"
CONTENTFUL_TOKEN = "CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo"

# Only sent to the Contentful API — never to story pages or other hosts.
HEADERS = {
    "Authorization": f"Bearer {CONTENTFUL_TOKEN}"
}

# Years to fetch from the archive
YEARS = list(range(datetime.now().year, 2013, -1))  # Current year down to 2014


def fetch_all_story_sets() -> dict[int, list[dict]]:
    """
    Fetch all story sets from all years.

    Returns:
        Dict mapping year to list of story set dicts.
        Each story set has: name, year, stories (list of story info), image_url
    """
    all_sets = {}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_story_sets_for_year, year): year for year in YEARS}
        for future in as_completed(futures):
            year = futures[future]
            try:
                sets = future.result()
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

    response = net.get(CONTENTFUL_API, params=params, headers=HEADERS, timeout=net.DEFAULT_TIMEOUT)
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


def fetch_story_page(url: str, cancel: "threading.Event | None" = None) -> str:
    """
    Download an individual story page.

    Handles both regular URLs and web.archive.org URLs (with longer timeout).

    Args:
        url: The full URL of the story.
        cancel: Optional event; raises net.Cancelled promptly when set.

    Returns:
        HTML content of the story page.
    """
    is_archive = "web.archive.org" in url

    # Add a small delay to be respectful to the server
    # Longer delay for archive.org which rate-limits more aggressively
    net.wait(1.0 if is_archive else 0.5, cancel)

    response = net.get(url, cancel=cancel)
    response.raise_for_status()
    return response.text


def fetch_article_story_sets() -> dict[int, list[dict]]:
    """
    Fetch individual magic-story articles from the Contentful API and group
    them into story sets by title prefix (text before " | ").

    This catches stories that exist on magic.wizards.com/en/news/magic-story
    but aren't part of any storyGroup entry.

    Returns:
        Dict mapping year -> list of story set dicts with source="articles".
    """
    articles = _fetch_all_articles()

    # Group articles by title prefix
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []

    for article in articles:
        title = article.get("title", "")
        if " | " in title:
            prefix, story_title = title.split(" | ", 1)
            set_name = prefix.strip()
            article["title"] = story_title.strip()
        else:
            set_name = title

        if set_name not in groups:
            groups[set_name] = []
            group_order.append(set_name)
        groups[set_name].append(article)

    # Build story sets grouped by year
    sets_by_year: dict[int, list[dict]] = {}

    for set_name in group_order:
        stories = groups[set_name]

        # Determine year from earliest publication date
        dates = [s["published_date"] for s in stories if s.get("published_date")]
        year = min(dates).year if dates else 0

        # Sort stories by publication date
        stories.sort(key=lambda s: s["published_date"] or datetime.min)

        story_set = {
            "name": set_name,
            "year": year,
            "source": "articles",
            "stories": stories,
            "external_links": [],
            "image_url": None,
        }

        if year not in sets_by_year:
            sets_by_year[year] = []
        sets_by_year[year].append(story_set)

    return sets_by_year


def _fetch_all_articles() -> list[dict]:
    """Fetch all magic-story articles from Contentful, handling pagination."""
    all_articles = []
    skip = 0
    limit = 100  # Contentful max per request

    while True:
        params = {
            "content_type": "article",
            "fields.category": "magic-story",
            "locale": "en",
            "order": "-sys.createdAt",
            "limit": str(limit),
            "skip": str(skip),
            "include": "1",
        }

        response = net.get(CONTENTFUL_API, params=params, headers=HEADERS, timeout=net.DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Build author lookup from included entries
        author_map = {}
        for inc in data.get("includes", {}).get("Entry", []):
            ct = inc.get("sys", {}).get("contentType", {}).get("sys", {}).get("id", "")
            if ct == "author":
                author_map[inc["sys"]["id"]] = inc.get("fields", {}).get("name", "")

        for item in data.get("items", []):
            fields = item.get("fields", {})
            title = fields.get("title", "")
            slug = fields.get("slug", "")

            if not slug:
                continue

            url = f"{BASE_URL}/en/news/magic-story/{slug}"

            pub_date = None
            pub_date_str = fields.get("publishedDate", "")
            if pub_date_str:
                try:
                    pub_date = datetime.strptime(pub_date_str[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        pub_date = datetime.strptime(pub_date_str[:10], "%Y-%m-%d")
                    except ValueError:
                        pass

            # Resolve author names
            author_names = []
            for author_link in fields.get("authors", []):
                author_id = author_link.get("sys", {}).get("id", "")
                if author_id in author_map:
                    author_names.append(author_map[author_id])
            author = ", ".join(author_names) if author_names else None

            # Get excerpt (strip HTML tags)
            excerpt = fields.get("excerpt", "") or fields.get("metaDescription", "")
            if excerpt:
                excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()

            all_articles.append({
                "title": title,
                "url": url,
                "slug": slug,
                "published_date": pub_date,
                "author": author,
                "excerpt": excerpt,
            })

        total = data.get("total", 0)
        skip += limit
        if skip >= total:
            break

    return all_articles


def get_storygroup_slugs(storygroup_sets: dict[int, list[dict]]) -> set[str]:
    """
    Extract all story slugs/URL paths from storyGroup results for deduplicating
    the article archive against them.

    Only URL-derived keys are used here: both sources come from Contentful with
    real slugs, so title matching is unnecessary and would risk false positives.
    """
    slugs = set()
    for sets in storygroup_sets.values():
        for story_set in sets:
            for story in story_set.get("stories", []):
                if story.get("slug"):
                    slugs.add(story["slug"].lower().strip())
                path = dedup.url_path_key(story.get("url"))
                if path:
                    slugs.add(path)
    return slugs


def filter_article_sets(
    article_sets: dict[int, list[dict]],
    known_slugs: set[str],
) -> dict[int, list[dict]]:
    """
    Remove articles whose slug already exists in known_slugs (from storyGroups).

    Returns:
        Filtered article sets with duplicates removed.
    """
    filtered: dict[int, list[dict]] = {}

    for year, sets in article_sets.items():
        filtered_sets = []
        for story_set in sets:
            filtered_stories = []
            for story in story_set.get("stories", []):
                slug = story.get("slug", "").lower().strip()
                url_path = dedup.url_path_key(story.get("url"))

                is_duplicate = (
                    (slug and slug in known_slugs) or
                    (url_path and url_path in known_slugs)
                )
                if not is_duplicate:
                    filtered_stories.append(story)

            if filtered_stories:
                filtered_set = dict(story_set)
                filtered_set["stories"] = filtered_stories
                filtered_set["story_count"] = len(filtered_stories)
                filtered_sets.append(filtered_set)

        if filtered_sets:
            filtered[year] = filtered_sets

    return filtered


def get_article_slugs(article_sets: dict[int, list[dict]]) -> set[str]:
    """
    Extract all dedup keys (slugs, URL paths, scoped/specific titles) from
    article sets for wiki deduplication. See dedup.story_keys().
    """
    keys: set[str] = set()
    for sets in article_sets.values():
        for story_set in sets:
            set_names = [story_set.get("name")]
            for story in story_set.get("stories", []):
                keys |= dedup.story_keys(story, set_names)
    return keys
