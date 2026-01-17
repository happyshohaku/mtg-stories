# Scraper Module Documentation

## File: `src/scraper.py`

## Purpose

The scraper module handles all external data fetching:
1. Retrieving story set metadata from the Contentful API
2. Downloading individual story HTML pages from the website

## Constants

```python
BASE_URL = "https://magic.wizards.com"
CONTENTFUL_API = "https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries"
CONTENTFUL_TOKEN = "CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Authorization": f"Bearer {CONTENTFUL_TOKEN}"
}

YEARS = list(range(2025, 2013, -1))  # 2025 down to 2014
```

## Functions

### fetch_all_story_sets()

**Purpose:** Fetch all story sets from all configured years.

**Returns:** `dict[int, list[dict]]` - Dictionary mapping year to list of story sets.

**Flow:**
```
For each year in YEARS:
   └──► _fetch_story_sets_for_year(year)
        └──► Returns list of story sets
   └──► Add to all_sets dict
Return all_sets
```

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

**Parameters:**
- `year` - The year to fetch (e.g., 2025)

**Returns:** `list[dict]` - List of story set dictionaries.

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

**Code Walkthrough - Story Processing:**

```python
for story_link in fields.get("stories", []):
    story_id = story_link.get("sys", {}).get("id")
    if story_id and story_id in entries_map:
        story_entry = entries_map[story_id]
        content_type = story_entry["sys"]["contentType"]["sys"]["id"]

        if content_type == "article":
            # Newer format: /en/news/{category}/{slug}
            category = story_fields.get("category", "magic-story")
            slug = story_fields.get("slug", "")
            url = f"{BASE_URL}/en/news/{category}/{slug}"

        elif content_type == "storyEntry":
            # Older format: URL in CTA link
            cta_link = story_fields.get("cta", {}).get("sys", {})
            cta_entry = entries_map.get(cta_link["id"])
            link = cta_entry["fields"]["link"]

            if "magic.wizards.com" in link:
                url = link
            else:
                # External link (e-book, Amazon)
                external_links.append({"title": title, "url": link})
```

### fetch_stories_for_set(story_set: dict)

**Purpose:** Get stories for a story set.

**Note:** Stories are already included in the story_set dict from `fetch_all_story_sets()`. This function simply returns `story_set.get("stories", [])`.

### fetch_story_page(url: str)

**Purpose:** Download an individual story page HTML.

**Parameters:**
- `url` - Full URL of the story page

**Returns:** `str` - HTML content of the page

**Features:**
- 0.5 second delay before each request (rate limiting)
- 30 second timeout
- Uses User-Agent header (no Authorization needed for public pages)

```python
def fetch_story_page(url: str) -> str:
    time.sleep(0.5)  # Be respectful to server

    response = requests.get(
        url,
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=30
    )
    response.raise_for_status()
    return response.text
```

## Error Handling

- **Year fetch failures:** Logged and skipped, other years continue
- **HTTP errors:** Raised via `response.raise_for_status()`
- **Missing data:** Returns empty lists/dicts, doesn't crash

## Maintenance Notes

### If stories stop loading:
1. Check if the Contentful token has changed (see contentful-api.md)
2. Check if content types have changed (`article`, `storyEntry`, `storyGroup`)
3. Check if URL patterns have changed

### Adding new years:
Update the `YEARS` constant:
```python
YEARS = list(range(2026, 2013, -1))  # Add 2026
```

### Adjusting rate limiting:
Modify the sleep duration in `fetch_story_page()`:
```python
time.sleep(1.0)  # Increase delay if getting rate limited
```
