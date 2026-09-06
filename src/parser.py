"""
HTML parsing module for extracting story content and metadata.
"""

import logging
import re
import os
import hashlib
import threading
from typing import Callable
from datetime import datetime
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from . import net
from .dates import parse_date

log = logging.getLogger(__name__)


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
        parsed = parse_date(date_meta["content"])
        if parsed:
            return parsed

    # Try time element
    time_elem = soup.find("time")
    if time_elem:
        parsed = parse_date(time_elem.get("datetime")) or parse_date(time_elem.get_text(strip=True))
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
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed

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

    # Split extension so truncation never cuts it off; default to .jpg when
    # the URL has none (the conversion step turns the bytes into JPEG anyway)
    stem, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".jpg"

    safe_stem = re.sub(r'[^\w\-]', '_', stem)[:50] or "image"
    safe_ext = re.sub(r'[^\w.]', '_', ext)[:10]

    return f"{url_hash}_{safe_stem}{safe_ext}"


def _fetch_image(url: str, output_dir: str, cancel: "threading.Event | None" = None) -> str:
    """Download one image to output_dir. Raises requests exceptions (or net.Cancelled) on failure."""
    # Add Referer header to avoid CDN blocking
    headers = {"Referer": "https://magic.wizards.com/"}
    response = net.get(
        url, headers=headers, retries=net.IMAGE_RETRIES, timeout=net.IMAGE_TIMEOUT, cancel=cancel
    )
    response.raise_for_status()

    filename = _url_to_filename(url)
    filepath = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(response.content)
    return filepath


def download_image(url: str, output_dir: str, cancel: "threading.Event | None" = None) -> str | None:
    """
    Download an image and save it to the output directory.

    Args:
        url: The URL of the image.
        output_dir: Directory to save the image.
        cancel: Optional event; net.Cancelled propagates when set.

    Returns:
        The local file path, or None if download failed.
    """
    try:
        return _fetch_image(url, output_dir, cancel)
    except net.Cancelled:
        raise
    except requests.exceptions.RequestException as e:
        log.warning("Failed to download image %s: %s", url, e)
        return None
    except Exception as e:
        log.warning("Unexpected error downloading image %s: %s", url, e)
        return None


# After this many consecutive connection failures to one host, the remaining
# images on that host are skipped for the current story. Catches "offline"
# and "dead image host" without stalling on every image in turn.
_HOST_FAILURE_LIMIT = 2


def download_images(
    images: list[dict],
    output_dir: str,
    cancel: "threading.Event | None" = None,
    progress: "Callable[[int, int], None] | None" = None,
) -> list[dict]:
    """
    Download all images and update their local paths.

    Args:
        images: List of image dicts with 'url' and 'filename' keys.
        output_dir: Directory to save images.
        cancel: Optional event; when set, net.Cancelled is raised promptly
            (also interrupting an in-progress retry wait).
        progress: Optional callback(done, total) invoked before each download.

    Returns:
        Updated list of image dicts with 'local_path' populated (None on
        failure) and 'error' set to None, "connection" or "http".
    """
    consecutive_failures: dict[str, int] = {}
    total = len(images)

    for i, img in enumerate(images):
        img["local_path"] = None
        img["error"] = None  # None, "connection" (host unreachable) or "http" (bad response etc.)
        net.check_cancelled(cancel)

        host = urlparse(img["url"]).netloc.lower()
        if consecutive_failures.get(host, 0) >= _HOST_FAILURE_LIMIT:
            log.info("Skipping image on unreachable host %s: %s", host, img["url"])
            img["error"] = "connection"
            continue

        if progress:
            progress(i, total)

        try:
            img["local_path"] = _fetch_image(img["url"], output_dir, cancel)
            consecutive_failures[host] = 0
        except (net.Cancelled, net.Offline):
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            # DNS failure, refused, connect timeout: the host itself is unreachable
            consecutive_failures[host] = consecutive_failures.get(host, 0) + 1
            img["error"] = "connection"
            log.warning("Failed to download image %s: %s", img["url"], e)
        except Exception as e:
            # HTTP 404, read timeout, disk error: specific to this image
            img["error"] = "http"
            log.warning("Failed to download image %s: %s", img["url"], e)

    return images
