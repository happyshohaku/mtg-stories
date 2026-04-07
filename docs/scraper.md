# Scraper Module Documentation

## File: `src/scraper.py`

## Purpose

The scraper module handles all Contentful API communication:
1. Retrieving story set metadata from storyGroup entries
2. Fetching individual magic-story articles and grouping by title prefix
3. Deduplication utilities for slug/URL matching
4. Downloading individual story HTML pages

## Constants

```python
BASE_URL = "https://magic.wizards.com"
CONTENTFUL_API = "https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries"
CONTENTFUL_TOKEN = "CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Authorization": f"Bearer {CONTENTFUL_TOKEN}"
}

YEARS = list(range(datetime.now().year, 2013, -1))  # Current year down to 2014
```

## Functions

### fetch_all_story_sets()

**Purpose:** Fetch all story sets from all configured years via the `storyGroup` content type.

**Returns:** `dict[int, list[dict]]` - Dictionary mapping year to list of story sets.

**Flow:**
```
ThreadPoolExecutor(max_workers=6):
   For all years in YEARS (in parallel):
      └──► _fetch_story_sets_for_year(year)
           └──► Returns list of story sets
      └──► Add to all_sets dict
Return all_sets
```

**Performance:** Years are fetched in parallel (6 concurrent requests) using `concurrent.futures.ThreadPoolExecutor`, reducing total fetch time from ~13x a single request to roughly the time of the slowest single request.

**Story Set Dict Structure:**
```python
{
    "name": "Edge of Eternities",
    "year": 2025,
    "stories": [
        {
            "title": "Episode 1: ...",
            "url": "https://magic.wizards.com/en/news/magic-story/...",
            "slug": "edge-of-eternities-episode-1",
            "published_date": datetime(2025, 1, 15)
        }
    ],
    "external_links": [  # E-book/Amazon links
        {"title": "E-book", "url": "https://amazon.com/..."}
    ],
    "image_url": "https://images.ctfassets.net/..."
}
```

### _fetch_story_sets_for_year(year: int)

**Purpose:** Fetch story sets for a specific year from the Contentful API.

**API Query Parameters:**
```python
params = {
    "content_type": "storyGroup",
    "locale": "en",
    "include": "10",
    "fields.firstStoryYear[in]": str(year)
}
```

**Processing Steps:**

1. **Make API request** with authentication headers
2. **Build lookup maps** for linked entries and assets
3. **Process each story group:**
   - Extract name from fields
   - Get thumbnail image URL from linked asset
   - Process each story entry:
     - For `article` type: Build URL from category + slug
     - For `storyEntry` type: Get URL from CTA link
     - Store external links (non-wizards.com URLs) separately
4. **Sort stories** by publication date
5. **Return** list of processed story sets

---

### fetch_article_story_sets()

**Purpose:** Fetch individual magic-story articles from Contentful and group them into story sets by title prefix.

This catches stories that exist on `magic.wizards.com/en/news/magic-story` but aren't part of any `storyGroup` entry (e.g., "Secrets of Strixhaven | Off the Record").

**Returns:** `dict[int, list[dict]]` - Dictionary mapping year to list of story sets with `source="articles"`.

**Flow:**
```
_fetch_all_articles()
       │
       ▼
Group by title prefix (split on " | ")
  "Secrets of Strixhaven | Off the Record"
    → set "Secrets of Strixhaven", story "Off the Record"
  "Standalone Title" (no |)
    → set "Standalone Title"
       │
       ▼
Determine year from earliest published_date per group
       │
       ▼
Return dict[year → list of story sets]
```

**Article Story Set Dict Structure:**
```python
{
    "name": "Secrets of Strixhaven",
    "year": 2026,
    "source": "articles",
    "stories": [
        {
            "title": "Off the Record",
            "url": "https://magic.wizards.com/en/news/magic-story/secrets-of-strixhaven-off-the-record",
            "slug": "secrets-of-strixhaven-off-the-record",
            "published_date": datetime(2026, 3, 9),
            "author": "Author Name",
            "excerpt": "Story description text..."
        }
    ],
    "external_links": [],
    "image_url": None
}
```

### _fetch_all_articles()

**Purpose:** Fetch all magic-story articles from Contentful, handling pagination.

**API Query Parameters:**
```python
params = {
    "content_type": "article",
    "fields.category": "magic-story",
    "locale": "en",
    "order": "-sys.createdAt",
    "limit": "100",       # Contentful max per request
    "skip": str(skip),    # Pagination offset
    "include": "1",       # Resolve author entries
}
```

**Processing per page:**
1. Build author lookup from `includes.Entry` (content type `author`)
2. For each item: extract title, slug, publishedDate, resolve author names, extract excerpt
3. Paginate with `skip` until all articles fetched (~464 total)

---

### Deduplication Utilities

#### get_storygroup_slugs(storygroup_sets)

Extracts all story slugs and URL paths from storyGroup results for deduplication against articles.

**Returns:** `set[str]` of normalized slugs and URL paths.

#### filter_article_sets(article_sets, known_slugs)

Removes articles whose slug or URL path already exists in `known_slugs`. Filters out empty sets after removal.

**Returns:** Filtered `dict[int, list[dict]]`.

#### get_article_slugs(article_sets)

Extracts slugs from article sets for wiki deduplication. Includes:
- Raw slugs
- URL paths
- Title-based slugs (for fuzzy matching against wiki story titles)

**Returns:** `set[str]` of normalized slugs.

---

### fetch_stories_for_set(story_set: dict)

**Purpose:** Get stories for a story set.

**Note:** Stories are already included in the story_set dict from `fetch_all_story_sets()`. This function simply returns `story_set.get("stories", [])`.

### fetch_story_page(url: str)

**Purpose:** Download an individual story page HTML.

**Features:**
- 0.5 second delay for regular requests, 1.0 second for archive.org
- 30 second timeout (60 for archive.org)
- Uses User-Agent header (no Authorization needed for public pages)
- Follows redirects

## Error Handling

- **Year fetch failures:** Logged and skipped, other years continue
- **HTTP errors:** Raised via `response.raise_for_status()`
- **Missing data:** Returns empty lists/dicts, doesn't crash
- **Pagination:** Stops when `skip >= total`

## Maintenance Notes

### If stories stop loading:
1. Check if the Contentful token has changed (see contentful-api.md)
2. Check if content types have changed (`article`, `storyEntry`, `storyGroup`)
3. Check if URL patterns have changed

### Year range:
`YEARS` is now dynamic — `list(range(datetime.now().year, 2013, -1))` — no manual update needed.

### Adding new article grouping patterns:
Update `fetch_article_story_sets()` to handle new title formats beyond the `" | "` delimiter.

### Adjusting rate limiting:
Modify the sleep duration in `fetch_story_page()`:
```python
time.sleep(1.0)  # Increase delay if getting rate limited
```
