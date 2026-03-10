"""
Wiki scraper module for fetching MTG story metadata from mtg.wiki.

Parses the Magic Story wiki page to get a catalog of all stories
(including pre-2014 stories not available via the Contentful API),
with links to original pages (often via web.archive.org).
"""

import re
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup, Tag

WIKI_URL = "https://mtg.wiki/page/Magic_Story"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_wiki_story_sets() -> dict[int, list[dict]]:
    """
    Fetch story sets from mtg.wiki, grouped by year.

    Returns:
        Dict mapping year -> list of story set dicts.
        Each story set has: name, year, stories, external_links, image_url, source.
        Format matches scraper.py output for GUI compatibility.
    """
    try:
        response = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch wiki page: {e}")
        return {}

    stories_by_set = _parse_wiki_page(html)

    # Sections to skip (incomplete/placeholder arcs)
    SKIP_SECTIONS = {"To Be Named Arc"}

    # Sections to split into sub-groups by title and place at the end
    MISC_SECTIONS = {"Other Magic Story articles"}

    # Group story sets by year
    sets_by_year: dict[int, list[dict]] = {}
    misc_groups: list[dict] = []  # Collected separately, added at end

    for set_name, stories in stories_by_set.items():
        if not stories:
            continue

        if set_name in SKIP_SECTIONS:
            continue

        if set_name in MISC_SECTIONS:
            # Split into sub-groups by title prefix, then add at end
            misc_groups.extend(_group_stories_by_title(stories))
            continue

        # Determine year from the earliest story date in the set
        dates = [s["published_date"] for s in stories if s.get("published_date")]
        if dates:
            year = min(dates).year
        else:
            year = 0  # Unknown year

        story_set = {
            "name": set_name,
            "year": year,
            "source": "wiki",
            "stories": stories,
            "external_links": [],
            "image_url": None,
        }

        if year not in sets_by_year:
            sets_by_year[year] = []
        sets_by_year[year].append(story_set)

    # Add misc groups under a special year key (-1) so they sort last
    if misc_groups:
        sets_by_year[-1] = misc_groups

    return sets_by_year


def _parse_wiki_page(html: str) -> dict[str, list[dict]]:
    """
    Parse the wiki page HTML to extract story metadata grouped by set/section.

    Returns:
        Dict mapping section_name -> list of story dicts.
    """
    soup = BeautifulSoup(html, "html.parser")

    stories_by_section: dict[str, list[dict]] = {}

    # Find all wikitables on the page
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        # Determine which section this table belongs to
        section_name = _find_section_for_table(table)

        # Parse the table rows
        stories = _parse_story_table(table)

        if stories:
            if section_name in stories_by_section:
                stories_by_section[section_name].extend(stories)
            else:
                stories_by_section[section_name] = stories

    return stories_by_section


def _find_section_for_table(table: Tag) -> str:
    """
    Find the section heading that precedes this table.
    Walks backwards through siblings and parents to find h2/h3/h4.
    """
    # Walk backwards through preceding siblings
    elem = table.previous_sibling
    while elem:
        if isinstance(elem, Tag):
            if elem.name in ("h2", "h3", "h4"):
                # Extract text, strip any [edit] links
                text = elem.get_text(strip=True)
                # Remove common wiki artifacts like "[edit]"
                text = re.sub(r'\[edit\]', '', text).strip()
                return text
            # If we hit another table, stop looking
            if elem.name == "table":
                break
        elem = elem.previous_sibling

    # Try parent's preceding siblings
    parent = table.parent
    if parent:
        elem = parent.previous_sibling
        while elem:
            if isinstance(elem, Tag) and elem.name in ("h2", "h3", "h4"):
                text = elem.get_text(strip=True)
                text = re.sub(r'\[edit\]', '', text).strip()
                return text
            elem = elem.previous_sibling

    return "Unknown Section"


def _parse_story_table(table: Tag) -> list[dict]:
    """
    Parse a single wiki table to extract story rows.

    Expected columns: Title | Author | Publishing date | Set | Setting | Featuring
    """
    stories = []

    # Find header row to determine column indices
    headers = []
    header_row = table.find("tr")
    if header_row:
        for th in header_row.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True).lower())

    # Map column names to indices
    col_map = {}
    for i, header in enumerate(headers):
        if "title" in header:
            col_map["title"] = i
        elif "author" in header:
            col_map["author"] = i
        elif "date" in header or "publishing" in header:
            col_map["date"] = i
        elif "set" in header and "setting" not in header:
            col_map["set"] = i
        elif "setting" in header or "plane" in header:
            col_map["setting"] = i
        elif "content" in header:
            col_map["content"] = i

    # If we couldn't find a title column, this probably isn't a story table
    if "title" not in col_map:
        return []

    # Parse data rows
    rows = table.find_all("tr")
    for row in rows[1:]:  # Skip header row
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        story = _parse_story_row(cells, col_map)
        if story:
            stories.append(story)

    return stories


def _parse_story_row(cells: list[Tag], col_map: dict[str, int]) -> dict | None:
    """
    Parse a single table row into a story dict.

    Returns:
        Story dict with title, url, author, published_date, slug, or None if invalid.
    """
    try:
        # Extract title and URL
        title_idx = col_map.get("title", 0)
        if title_idx >= len(cells):
            return None

        title_cell = cells[title_idx]
        title, url = _extract_title_and_url(title_cell)

        if not title:
            return None

        # Extract author
        author = "Unknown Author"
        author_idx = col_map.get("author")
        if author_idx is not None and author_idx < len(cells):
            author_text = cells[author_idx].get_text(strip=True)
            if author_text:
                author = author_text

        # Extract publication date
        pub_date = None
        date_idx = col_map.get("date")
        if date_idx is not None and date_idx < len(cells):
            date_text = cells[date_idx].get_text(strip=True)
            pub_date = _parse_wiki_date(date_text)

        # Extract set name
        set_name = None
        set_idx = col_map.get("set")
        if set_idx is not None and set_idx < len(cells):
            set_name = cells[set_idx].get_text(strip=True)

        # Extract content/description (used for grouping in "Other" section)
        content_desc = None
        content_idx = col_map.get("content")
        if content_idx is not None and content_idx < len(cells):
            content_desc = cells[content_idx].get_text(strip=True)

        if not url:
            return None

        return {
            "title": title,
            "url": url,
            "author": author,
            "slug": _title_to_slug(title),
            "published_date": pub_date,
            "set_name": set_name,
            "content_desc": content_desc,
        }

    except (IndexError, AttributeError):
        return None


def _extract_title_and_url(cell: Tag) -> tuple[str, str | None]:
    """
    Extract story title and URL from a table cell.

    Handles multiple link formats:
    - Direct link: <a href="https://web.archive.org/...">Title</a>
    - Wiki page link: <a href="/page/Story_Name">Title</a>
    - Multi-part: "Story Name, Part 1 (link), Part 2 (link)" — takes first link
    """
    # Find all links in the cell
    links = cell.find_all("a", href=True)

    if not links:
        # No links, just text — can't use this story
        return cell.get_text(strip=True), None

    # Find the first external link (archive.org or wizards.com)
    best_url = None
    best_title = None

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Skip internal wiki links (to wiki pages about the story, not the story itself)
        if _is_story_url(href):
            if not best_url:
                best_url = _normalize_url(href)
                best_title = text
        elif href.startswith("/page/") and not best_url:
            # Wiki internal link — might be the only link available
            # We can't use these directly, but record the title
            if not best_title:
                best_title = text

    # Use the cell text as title if we didn't get one from links
    if not best_title:
        best_title = cell.get_text(strip=True)
        # Clean up — remove stuff like ", Part 1, Part 2"
        best_title = re.sub(r',\s*(Part|Chapter)\s+\d+.*$', '', best_title).strip()

    return best_title, best_url


def _is_story_url(url: str) -> bool:
    """Check if a URL points to an actual story page (not a wiki page)."""
    if not url:
        return False

    # External URLs are story pages
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Known story host domains
        story_domains = [
            "web.archive.org",
            "magic.wizards.com",
            "www.wizards.com",
            "wizards.com",
            "mtgstory.com",
            "mtglore.com",
        ]
        return any(d in domain for d in story_domains)

    return False


def _normalize_url(url: str) -> str:
    """
    Normalize a story URL for consistency.
    Ensures https, handles archive.org URLs.
    """
    if not url:
        return url

    # Ensure https
    if url.startswith("http://") and "web.archive.org" not in url:
        url = "https://" + url[7:]

    return url


def _group_stories_by_title(stories: list[dict]) -> list[dict]:
    """
    Group a flat list of stories into sub-groups using multiple strategies:

    1. Title prefix: "Planeswalker's Guide to Theros, Part 1/2/3" → one group
    2. Content description: stories sharing a series description
       (e.g., "Episode N of the Forgotten Realms D&D campaign") → one group
    3. Same author + consecutive dates with no title prefix match → group together

    Returns:
        List of story_set dicts (same format as fetch_wiki_story_sets output).
    """
    # Step 1: Extract a "series key" for each story from its content description
    def _series_from_content(desc: str | None) -> str | None:
        if not desc:
            return None
        # Match patterns like "Episode N of the X" or "Recapitulating the X"
        # Strip the episode/part number to get the series name
        m = re.match(
            r'(?:Episode|Part|Chapter)\s+\d+\s+of\s+(?:the\s+)?(.+?)\.?$',
            desc, re.IGNORECASE
        )
        if m:
            # Clean up wiki markup artifacts (missing spaces around links)
            name = m.group(1).strip()
            name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # "RealmsD&D" → "Realms D&D"
            # Also fix "theForgotten" → "the Forgotten"
            name = re.sub(r'\b(the|a|an|of|in|to|and|for)([A-Z])', r'\1 \2', name)
            # Capitalize first letter
            if name:
                name = name[0].upper() + name[1:]
            return name
        return None

    # Step 2: Strip part/chapter suffixes from title, and collapse "X: Y" series
    def _base_title(title: str) -> str:
        base = re.sub(
            r'[\s,:]+\s*(?:Part|Chapter|Episode|Vol\.?|Volume)\s*\d+\s*$',
            '', title, flags=re.IGNORECASE
        ).strip()
        base = re.sub(r'\s*\(\d{4}\)\s*$', '', base).strip()
        # Collapse "The Magic Story Podcast: X" → "The Magic Story Podcast"
        # and similar "Series Name: Individual Title" patterns for known series
        for prefix in ["The Magic Story Podcast"]:
            if base.startswith(prefix + ":") or base.startswith(prefix + " -"):
                return prefix
        return base

    # Step 3: Assign each story a group key
    # Priority: content-based series > title prefix
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []

    for story in stories:
        title = story.get("title", "")
        content = story.get("content_desc")

        # Try content-based grouping first
        series = _series_from_content(content)
        if series:
            key = series
        else:
            key = _base_title(title) or title

        if not key:
            key = title or "Unknown"

        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(story)

    # Step 4: Second pass — merge single-story groups that share author + close dates
    # Only merges 3+ consecutive singletons by the same author within 7 days of each other
    # (catches series like the Kamigawa recaps or Forgotten Realms episodes)
    merged_order: list[str] = []
    merged_groups: dict[str, list[dict]] = {}
    skip: set[str] = set()

    for i, key in enumerate(group_order):
        if key in skip:
            continue
        stories_in_group = groups[key]

        # Only try merging singletons
        if len(stories_in_group) == 1:
            story = stories_in_group[0]
            author = story.get("author", "")
            date = story.get("published_date")

            # Skip generic/staff authors for proximity-based grouping
            generic_authors = {"the magic creative team", "wizards of the coast", "wotc staff"}

            # Look ahead for consecutive singletons by the same author within 7 days
            if author and date and author.lower() not in generic_authors:
                cluster = [story]
                cluster_keys = [key]
                for j in range(i + 1, len(group_order)):
                    next_key = group_order[j]
                    if next_key in skip or len(groups[next_key]) != 1:
                        break
                    next_story = groups[next_key][0]
                    next_author = next_story.get("author", "")
                    next_date = next_story.get("published_date")
                    if next_author == author and next_date and date:
                        delta = abs((next_date - date).days)
                        if delta <= 7:
                            cluster.append(next_story)
                            cluster_keys.append(next_key)
                            date = next_date  # Extend the window
                        else:
                            break
                    else:
                        break

                # Only merge if 3+ stories (avoids false positives with pairs)
                if len(cluster) >= 3:
                    for ck in cluster_keys[1:]:
                        skip.add(ck)
                    # Use content description to name the group
                    series_name = None
                    for s in cluster:
                        sn = _series_from_content(s.get("content_desc"))
                        if sn:
                            series_name = sn
                            break
                    if not series_name:
                        series_name = f"{author} stories"
                    # Ensure unique key
                    unique_name = series_name
                    counter = 2
                    while unique_name in merged_groups:
                        unique_name = f"{series_name} ({counter})"
                        counter += 1
                    merged_groups[unique_name] = cluster
                    merged_order.append(unique_name)
                    continue

        # Ensure unique key for non-merged groups too
        unique_key = key
        counter = 2
        while unique_key in merged_groups:
            unique_key = f"{key} ({counter})"
            counter += 1
        merged_groups[unique_key] = stories_in_group
        merged_order.append(unique_key)

    # Convert to story_set dicts
    result = []
    for group_name in merged_order:
        group_stories = merged_groups[group_name]

        dates = [s["published_date"] for s in group_stories if s.get("published_date")]
        year = min(dates).year if dates else 0

        result.append({
            "name": group_name,
            "year": year,
            "source": "wiki",
            "stories": group_stories,
            "external_links": [],
            "image_url": None,
        })

    return result


def _parse_wiki_date(date_str: str) -> datetime | None:
    """
    Parse a date string from the wiki.

    Handles formats like:
    - "2004-08-18"
    - "2004-08-18 (original), 2015-05-06 (republished)"
    - "August 18, 2004"
    """
    if not date_str:
        return None

    # Take the first date if there are multiple (e.g., "original, republished")
    date_str = date_str.split("(")[0].strip().rstrip(",").strip()

    formats = [
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    # Try to extract a date pattern from the string
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            pass

    return None


def _title_to_slug(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = slug.strip('-')
    return slug


def get_contentful_slugs(contentful_sets: dict[int, list[dict]]) -> set[str]:
    """
    Extract all story slugs/URLs from Contentful results for deduplication.

    Args:
        contentful_sets: The result of scraper.fetch_all_story_sets()

    Returns:
        Set of normalized slugs and URLs.
    """
    slugs = set()
    for year, sets in contentful_sets.items():
        for story_set in sets:
            for story in story_set.get("stories", []):
                # Add the slug
                if story.get("slug"):
                    slugs.add(story["slug"].lower().strip())

                # Add normalized URL path
                if story.get("url"):
                    parsed = urlparse(story["url"])
                    path = parsed.path.rstrip("/").lower()
                    slugs.add(path)

                # Add title-based slug
                if story.get("title"):
                    slugs.add(_title_to_slug(story["title"]))

    return slugs


def filter_wiki_sets(
    wiki_sets: dict[int, list[dict]],
    contentful_slugs: set[str]
) -> dict[int, list[dict]]:
    """
    Remove stories from wiki sets that already exist in Contentful results.

    Args:
        wiki_sets: Wiki story sets from fetch_wiki_story_sets()
        contentful_slugs: Set from get_contentful_slugs()

    Returns:
        Filtered wiki sets with duplicates removed.
    """
    filtered: dict[int, list[dict]] = {}

    for year, sets in wiki_sets.items():
        filtered_sets = []
        for story_set in sets:
            filtered_stories = []
            for story in story_set.get("stories", []):
                # Check if this story already exists in Contentful
                slug = story.get("slug", "")
                title_slug = _title_to_slug(story.get("title", ""))
                url_path = ""
                if story.get("url"):
                    # For archive.org URLs, extract the original URL path
                    url = story["url"]
                    if "web.archive.org" in url:
                        # Extract original URL from archive URL
                        match = re.search(r'web\.archive\.org/web/\d+/(.*)', url)
                        if match:
                            original = match.group(1)
                            url_path = urlparse(original).path.rstrip("/").lower()
                    else:
                        url_path = urlparse(url).path.rstrip("/").lower()

                # Check all possible matches
                is_duplicate = (
                    (slug and slug in contentful_slugs) or
                    (title_slug and title_slug in contentful_slugs) or
                    (url_path and url_path in contentful_slugs)
                )

                if not is_duplicate:
                    filtered_stories.append(story)

            if filtered_stories:
                filtered_set = dict(story_set)
                filtered_set["stories"] = filtered_stories
                filtered_sets.append(filtered_set)

        if filtered_sets:
            filtered[year] = filtered_sets

    return filtered
