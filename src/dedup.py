"""
Shared helpers for deduplicating stories across the three data sources
(Contentful storyGroups, Contentful articles, mtg.wiki).

Each source builds a set of string "keys" for the stories it knows about.
A story from a lower-priority source is dropped when any of its own keys
is already in that set.

Key kinds:
  - URL slug          "march-of-the-machine-episode-1"
  - URL path          "/en/news/magic-story/march-of-the-machine-episode-1"
  - scoped title      "marchofthemachine::episode-1"   (set name + title)
  - bare title        "the-gathering-storm"           (only for specific titles)

Bare title keys are only produced for titles that are unlikely to recur
across unrelated sets. Generic titles such as "Prologue", "Epilogue" or
"Chapter 3" are matched only when the set name matches as well.
"""

import re
from urllib.parse import urlparse

# Titles that appear in many unrelated story sets. Matched case-insensitively
# against the whole title after whitespace normalisation.
_GENERIC_WORD = (
    r"(?:the\s+)?(?:prologue|epilogue|interlude|introduction|intro|finale|aftermath|"
    r"conclusion|coda|prelude|preface|foreword|afterword|postscript|beginning|end|ending)"
)
_GENERIC_NUMBERED = (
    r"(?:chapter|part|episode|installment|section|act|book|volume|vol\.?)\s*[\divxlc]+"
    r"(?:\s+of\s+[\divxlc]+)?"
)
_SEP = r"\s*[:.,\-–—]?\s*"

# Matches "Prologue", "Chapter 3", "Part II", "Epilogue, Part 2", "Chapter 1: Prologue", ...
_GENERIC_TITLE_RE = re.compile(
    rf"^(?:{_GENERIC_WORD}|{_GENERIC_NUMBERED})"
    rf"(?:{_SEP}(?:{_GENERIC_WORD}|{_GENERIC_NUMBERED}|[\divxlc]+))*$",
    re.IGNORECASE,
)

# A title with fewer words than this is treated as generic regardless of pattern.
_MIN_SPECIFIC_WORDS = 3


def title_to_slug(title: str) -> str:
    """Convert a title to a URL-safe slug ("Return to Dominaria, Episode 1" -> "return-to-dominaria-episode-1")."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-")


def normalize_set_name(name: str | None) -> str:
    """
    Normalise a set name for loose comparison: lowercase, letters and digits only.
    "Theros: Beyond Death" and "Theros Beyond Death" both become "therosbeyonddeath".
    """
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_generic_title(title: str) -> bool:
    """True when a title is too generic to identify a story on its own."""
    if not title:
        return True
    cleaned = re.sub(r"\s+", " ", title).strip()
    if _GENERIC_TITLE_RE.match(cleaned):
        return True
    return len(title_to_slug(cleaned).split("-")) < _MIN_SPECIFIC_WORDS


def url_path_key(url: str | None) -> str:
    """
    Normalised URL path for matching. For archive.org URLs the original page
    URL is unwrapped first, so an archived copy matches the live page.
    """
    if not url:
        return ""
    if "web.archive.org" in url:
        match = re.search(r"web\.archive\.org/web/\d+[a-z_]*/(.*)", url)
        if match:
            url = match.group(1)
    return urlparse(url).path.rstrip("/").lower()


def title_keys(title: str | None, set_names: list[str | None]) -> set[str]:
    """
    Dedup keys derived from a story's title.

    Always includes a scoped key per non-empty set name. Includes the bare
    title slug only when the title is specific enough to stand alone.
    """
    keys: set[str] = set()
    if not title:
        return keys
    slug = title_to_slug(title)
    if not slug:
        return keys
    for name in set_names:
        norm = normalize_set_name(name)
        if norm:
            keys.add(f"{norm}::{slug}")
    if not is_generic_title(title):
        keys.add(slug)
    return keys


def story_keys(story: dict, set_names: list[str | None]) -> set[str]:
    """
    All dedup keys for one story dict (as produced by any of the scrapers).

    Args:
        story: dict with optional "slug", "url", "title".
        set_names: names this story is filed under (set name, wiki "Set" column, ...).
    """
    keys: set[str] = set()
    slug = (story.get("slug") or "").lower().strip()
    if slug:
        keys.add(slug)
    path = url_path_key(story.get("url"))
    if path:
        keys.add(path)
    keys |= title_keys(story.get("title"), set_names)
    return keys
