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


def parse_story(html: str, url: str) -> Story:
    """
    Parse a story page and extract all relevant content.

    Args:
        html: The HTML content of the story page.
        url: The URL of the story (for resolving relative links).

    Returns:
        A Story object with all extracted data.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    author = _extract_author(soup)
    pub_date = _extract_publication_date(soup)
    content_html, images = _extract_content(soup, url)

    return Story(
        url=url,
        title=title,
        author=author,
        publication_date=pub_date,
        content_html=content_html,
        images=images
    )


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
        return title_tag.get_text(strip=True).split("|")[0].strip()

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
    content_selectors = [
        "article .article-body",
        "article .entry-content",
        ".article-content",
        ".story-content",
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
    for unwanted in content_elem.select("script, style, nav, header, footer, iframe, .social-share, .comments, .related-articles, .advertisement"):
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
        elif "magic.wizards.com" in href:
            # External link to MTG site - remove the link but keep text
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
