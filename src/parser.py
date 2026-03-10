"""
HTML parsing module for extracting story content and metadata.
"""

import re
import os
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup, Tag

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


@dataclass
class Story:
    """Represents a parsed story with all its content."""
    url: str
    title: str
    author: str
    publication_date: datetime | None
    content_html: str
    images: list[dict] = field(default_factory=list)  # [{"url": ..., "local_path": ..., "filename": ...}]


def parse_story(
    html: str,
    url: str,
    fallback_author: str | None = None,
    fallback_date: datetime | None = None,
    fallback_title: str | None = None,
) -> Story:
    """
    Parse a story page and extract all relevant content.

    Args:
        html: The HTML content of the story page.
        url: The URL of the story (for resolving relative links).
        fallback_author: Author name to use if extraction fails (e.g., from wiki metadata).
        fallback_date: Publication date to use if extraction fails.
        fallback_title: Title to use if extraction fails.

    Returns:
        A Story object with all extracted data.
    """
    # Strip Wayback Machine toolbar if this is an archive.org page
    html = _strip_wayback_toolbar(html)

    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    if title in ("Untitled", "") and fallback_title:
        title = fallback_title

    author = _extract_author(soup)
    if author == "Unknown Author" and fallback_author:
        author = fallback_author

    pub_date = _extract_publication_date(soup)
    if pub_date is None and fallback_date:
        pub_date = fallback_date

    # Resolve base URL for archive.org pages (use original URL for relative links)
    base_url = _get_base_url_for_content(url)
    content_html, images = _extract_content(soup, base_url)

    return Story(
        url=url,
        title=title,
        author=author,
        publication_date=pub_date,
        content_html=content_html,
        images=images
    )


def _strip_wayback_toolbar(html: str) -> str:
    """
    Remove the Wayback Machine toolbar/banner from archived pages.
    The toolbar is injected by archive.org and interferes with content extraction.
    """
    # Remove the Wayback Machine toolbar comment block and elements
    # The toolbar is wrapped in <!-- BEGIN WAYBACK TOOLBAR INSERT --> comments
    html = re.sub(
        r'<!-- BEGIN WAYBACK TOOLBAR INSERT -->.*?<!-- END WAYBACK TOOLBAR INSERT -->',
        '',
        html,
        flags=re.DOTALL
    )

    # Remove the wm-ipp-base div (Wayback Machine toolbar container)
    html = re.sub(
        r'<div\s+id="wm-ipp-base"[^>]*>.*?</div>\s*</div>\s*</div>',
        '',
        html,
        flags=re.DOTALL
    )

    # Remove Wayback Machine script injections
    html = re.sub(
        r'<script\s+src="[^"]*web\.archive\.org[^"]*"[^>]*>.*?</script>',
        '',
        html,
        flags=re.DOTALL
    )

    # Remove _wm. prefixed scripts
    html = re.sub(
        r'<script[^>]*>\s*var\s+_wm\b.*?</script>',
        '',
        html,
        flags=re.DOTALL
    )

    return html


def _get_base_url_for_content(url: str) -> str:
    """
    Get the appropriate base URL for resolving relative links.
    For archive.org URLs, extract the original URL to use as base.
    """
    if "web.archive.org" in url:
        # Extract the original URL from archive.org URL
        # Format: https://web.archive.org/web/TIMESTAMP/ORIGINAL_URL
        match = re.search(r'web\.archive\.org/web/\d+/(https?://.*)', url)
        if match:
            return match.group(1)
        # Also handle without protocol
        match = re.search(r'web\.archive\.org/web/\d+/(.*)', url)
        if match:
            original = match.group(1)
            if not original.startswith("http"):
                original = "http://" + original
            return original
    return url


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract the story title."""
    # Try various selectors
    selectors = [
        "h1.article-title",
        "h1.entry-title",
        "article h1",
        ".article-header h1",
        "h1",
    ]

    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            return elem.get_text(strip=True)

    # Fallback to page title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True).split("|")[0].strip()
        # Clean common suffixes from old WotC pages
        for suffix in [
            " - Magic: The Gathering",
            " - Wizards of the Coast",
            " | MAGIC: THE GATHERING",
            " | Magic: The Gathering",
        ]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip(" -")
        return title

    return "Untitled"


def _extract_author(soup: BeautifulSoup) -> str:
    """Extract the author name."""
    import json

    # Try JSON-LD structured data first (most reliable)
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            script_content = script.string or script.get_text()
            if not script_content:
                continue
            data = json.loads(script_content)
            if isinstance(data, dict):
                author = data.get("author")
                if isinstance(author, list) and author:
                    author = author[0]
                if isinstance(author, dict) and author.get("name"):
                    return author["name"]
                if isinstance(author, str):
                    return author
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Try author archive link (MTG site pattern: /en/news/archive?author=...)
    for link in soup.find_all("a", href=True):
        if "archive?author=" in link["href"]:
            text = link.get_text(strip=True)
            if text:
                return text

    # Try various CSS selectors
    selectors = [
        ".author-name",
        ".article-author",
        "[rel='author']",
        ".byline",
    ]

    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            return elem.get_text(strip=True)

    # Look for "By Author Name" pattern in text
    for text in soup.stripped_strings:
        if text.lower().startswith("by "):
            return text[3:].strip()

    # Try meta tags
    meta_author = soup.find("meta", {"name": "author"})
    if meta_author and meta_author.get("content"):
        return meta_author["content"]

    return "Unknown Author"


def _extract_publication_date(soup: BeautifulSoup) -> datetime | None:
    """Extract the publication date."""
    # Try meta tags first
    date_meta = soup.find("meta", {"property": "article:published_time"})
    if date_meta and date_meta.get("content"):
        try:
            return datetime.fromisoformat(date_meta["content"].replace("Z", "+00:00"))
        except ValueError:
            pass

    # Try time element
    time_elem = soup.find("time")
    if time_elem:
        datetime_attr = time_elem.get("datetime")
        if datetime_attr:
            try:
                return datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Try parsing the text content
        date_text = time_elem.get_text(strip=True)
        parsed = _parse_date_string(date_text)
        if parsed:
            return parsed

    # Look for date patterns in the page
    date_patterns = [
        r"(\w+ \d{1,2}, \d{4})",  # "Jun 20, 2025"
        r"(\d{4}-\d{2}-\d{2})",    # "2025-06-20"
    ]

    page_text = soup.get_text()
    for pattern in date_patterns:
        match = re.search(pattern, page_text)
        if match:
            parsed = _parse_date_string(match.group(1))
            if parsed:
                return parsed

    return None


def _parse_date_string(date_str: str) -> datetime | None:
    """Try to parse a date string in various formats."""
    formats = [
        "%B %d, %Y",      # "June 20, 2025"
        "%b %d, %Y",      # "Jun 20, 2025"
        "%Y-%m-%d",       # "2025-06-20"
        "%d %B %Y",       # "20 June 2025"
        "%d %b %Y",       # "20 Jun 2025"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def _extract_content(soup: BeautifulSoup, base_url: str) -> tuple[str, list[dict]]:
    """
    Extract the main story content, preserving HTML structure.

    Returns:
        Tuple of (content_html, list of image dicts)
    """
    images = []

    # Find the main article content
    # Includes selectors for modern WotC site, older site layouts, and archive.org pages
    content_selectors = [
        "article .article-body",
        "article .entry-content",
        ".article-content",
        ".story-content",
        # Older WotC site layouts (pre-2015)
        "#content-detail-page-of-an-article",
        ".article-detail",
        "#main-content",
        "#article-body",
        "td.article-body",              # Very old WotC layout used tables
        "#bodycontent",                  # Old Wizards.com layout
        ".main-content",
        "article",
        "main",
    ]

    content_elem = None
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            break

    if not content_elem:
        content_elem = soup.body or soup

    # Make a copy to avoid modifying the original
    content_elem = BeautifulSoup(str(content_elem), "html.parser")

    # Remove unwanted elements (including iframes which EPUBs don't support)
    unwanted_selectors = [
        "script", "style", "nav", "header", "footer", "iframe",
        ".social-share", ".comments", ".related-articles", ".advertisement",
        # Wayback Machine / archive.org artifacts
        "#wm-ipp-base", "#wm-ipp", "#donato", "#wm-btm",
        "[id^='wm-']",
        # Old WotC site cruft
        ".header-search", ".site-footer", ".breadcrumb",
        ".article-footer", ".article-sidebar",
    ]
    for unwanted in content_elem.select(", ".join(unwanted_selectors)):
        unwanted.decompose()

    # Process images
    for img in content_elem.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            full_url = urljoin(base_url, src)
            filename = _url_to_filename(full_url)

            images.append({
                "url": full_url,
                "filename": filename,
                "local_path": None  # Will be set when downloaded
            })

            # Update the img src to use the local filename
            img["src"] = f"images/{filename}"
            # Remove srcset and other attributes that might cause issues
            for attr in ["srcset", "data-src", "data-srcset", "loading"]:
                if attr in img.attrs:
                    del img.attrs[attr]

    # Process internal anchor links - preserve them
    for link in content_elem.find_all("a", href=True):
        href = link["href"]
        if href.startswith("#"):
            # Internal anchor link - keep it
            pass
        elif "magic.wizards.com" in href or "wizards.com" in href:
            # External link to MTG/Wizards site - remove the link but keep text
            link.replace_with(link.get_text())
        elif "web.archive.org" in href:
            # Archive.org link - remove the link but keep text
            link.replace_with(link.get_text())
        else:
            # Other external links - keep them
            pass

    # Clean up the HTML
    content_html = str(content_elem)

    # Normalize whitespace but preserve structure
    content_html = re.sub(r'\n\s*\n\s*\n', '\n\n', content_html)

    return content_html, images


def _url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename."""
    parsed = urlparse(url)
    path = parsed.path

    # Get the original filename
    original_name = os.path.basename(path)

    # Create a hash of the full URL for uniqueness
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

    # Get extension
    _, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".jpg"  # Default extension

    # Create safe filename
    safe_name = re.sub(r'[^\w\-.]', '_', original_name)
    if len(safe_name) > 50:
        safe_name = safe_name[:50]

    return f"{url_hash}_{safe_name}"


def download_image(url: str, output_dir: str) -> str | None:
    """
    Download an image and save it to the output directory.

    Args:
        url: The URL of the image.
        output_dir: Directory to save the image.

    Returns:
        The local file path, or None if download failed.
    """
    try:
        # Add Referer header to avoid CDN blocking
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://magic.wizards.com/"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        filename = _url_to_filename(url)
        filepath = os.path.join(output_dir, filename)

        os.makedirs(output_dir, exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(response.content)

        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Failed to download image {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error downloading image {url}: {e}")
        return None


def download_images(images: list[dict], output_dir: str) -> list[dict]:
    """
    Download all images and update their local paths.

    Args:
        images: List of image dicts with 'url' and 'filename' keys.
        output_dir: Directory to save images.

    Returns:
        Updated list of image dicts with 'local_path' populated.
    """
    for img in images:
        local_path = download_image(img["url"], output_dir)
        img["local_path"] = local_path

    return images
