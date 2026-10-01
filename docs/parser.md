# Parser Module Documentation

## File: `src/parser.py`

## Purpose

The parser module extracts structured data from story HTML pages:
- Title
- Author
- Publication date
- Story content (preserving HTML structure)
- Image URLs

## Data Classes

### Story

```python
@dataclass
class Story:
    url: str
    title: str
    author: str
    publication_date: datetime | None
    content_html: str
    images: list[dict]  # [{"url": ..., "local_path": ..., "filename": ..., "error": ...}]
```

## Functions

### parse_story(html, url, fallback_author=None, fallback_date=None, fallback_title=None, card_lookup=None) -> Story

**Purpose:** Main entry point - parse a story page and extract all content.

**Parameters:**
- `html` - HTML content of the story page
- `url` - URL of the story (for resolving relative links)
- `fallback_author`, `fallback_date`, `fallback_title` - used when the page yields "Unknown Author", no date, or "Untitled" (wiki rows and article metadata supply these)
- `card_lookup` - function that resolves `<cig-card>` entry ids to card images; the GUI passes `scraper.fetch_card_images`. Without it, cards show as their name

**archive.org pages:** the Wayback Machine toolbar and injected scripts are stripped first (`_strip_wayback_toolbar`), and relative links are resolved against the original URL rather than the archive URL (`_get_base_url_for_content`).

**Returns:** `Story` object with all extracted data.

**Flow:**
```
html ──► BeautifulSoup
           │
           ├──► _extract_title()
           ├──► _extract_author()
           ├──► _extract_publication_date()
           └──► _extract_content()
                     │
                     └──► (content_html, images)
           │
           ▼
        Story object
```

---

### _extract_title(soup: BeautifulSoup) -> str

**Purpose:** Extract the story title.

**Selectors tried (in order):**
1. `h1.article-title`
2. `h1.entry-title`
3. `article h1`
4. `.article-header h1`
5. `h1` (any)
6. `<title>` tag (split on `|`, take first part)

**Fallback:** `"Untitled"`

---

### _extract_author(soup: BeautifulSoup) -> str

**Purpose:** Extract the author name.

**Methods tried (in order):**

1. **JSON-LD Structured Data** (most reliable)
   ```html
   <script type="application/ld+json">
   {"@type": "Article", "author": {"name": "Seth Dickinson"}}
   </script>
   ```

   Handles various author formats:
   - `{"author": {"name": "Author Name"}}`
   - `{"author": [{"name": "Author Name"}]}`
   - `{"author": "Author Name"}`

2. **Author Archive Links** (MTG site pattern)
   ```html
   <a href="/en/news/archive?author=HwyLvN87TZgwLSiWpNgX7">
     <span>Seth Dickinson</span>
   </a>
   ```

3. **CSS Selectors:**
   - `.author-name`
   - `.article-author`
   - `[rel='author']`
   - `.byline`

4. **Text Pattern:** Look for "By Author Name" in page text

5. **Meta Tags:** `<meta name="author" content="...">`

**Fallback:** `"Unknown Author"`

**Code Snippet - JSON-LD Extraction:**
```python
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
```

---

### _extract_publication_date(soup: BeautifulSoup) -> datetime | None

**Purpose:** Extract the publication date.

**Methods tried:**

1. **Meta Tag:** `<meta property="article:published_time">`
2. **Time Element:** `<time datetime="...">`
3. **Date Patterns** in page text:
   - `Month DD, YYYY` (e.g., "Jun 20, 2025")
   - `YYYY-MM-DD` (e.g., "2025-06-20")

**Date parsing** is done by `dates.parse_date()`, shared with both scrapers. It accepts ISO 8601 with or without a timezone, Contentful's `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD`, and English month-name forms ("June 20, 2025", "Jun 20, 2025", "20 June 2025"). It always returns a naive `datetime` so dates from different sources sort together.

---

### _extract_content(soup: BeautifulSoup, base_url: str, card_lookup=None) -> tuple[str, list[dict]]

**Purpose:** Extract the main story content, preserving HTML structure.

**Returns:** Tuple of (content_html, image_list)

**Content Selectors (in order):**
1. `article .article-body`
2. `article .entry-content`
3. `.article-content`
4. `.story-content`
5. Older WotC and archive.org layouts: `#content-detail-page-of-an-article`, `.article-detail`, `#main-content`, `#article-body`, `td.article-body`, `#bodycontent`, `.main-content`
6. `article`
7. `main`
8. `body` (fallback)

**Processing Steps:**

1. **Find content container** using selectors
2. **Remove unwanted elements:**
   - `script`, `style`, `nav`, `header`, `footer`
   - `iframe` (not supported in EPUB)
   - `.social-share`, `.comments`, `.related-articles`, `.advertisement`
   - Wayback Machine elements (`#wm-ipp-base`, `[id^='wm-']`, ...) and old site chrome (`.breadcrumb`, `.site-footer`, ...)
3. **Replace card placeholders** (`_replace_card_placeholders`):
   - The site embeds cards as `<cig-card entry="ID">0001_MTGFRA_CommBord: Card Name</cig-card>` and fills in the picture with JavaScript
   - Entry ids are resolved in one batch through `card_lookup`; each placeholder becomes an `<img>` (plus a second one for a back face)
   - A card that cannot be resolved is reduced to its name, without the internal label prefix
   - `<responsive-grid>` and `<grid-item>` wrappers are unwrapped
4. **Process images:**
   - Get URL from `src` or `data-src`
   - Generate unique filename
   - Update `src` to local path (`images/filename`)
   - Remove `srcset`, `data-src`, `data-srcset`, `loading` attributes
5. **Process links:**
   - Keep internal anchor links (`#section`)
   - Remove magic.wizards.com and web.archive.org links (keep text)
   - Keep other external links
6. **Normalize whitespace**

**Image Dict Structure:**
```python
{
    "url": "https://media.wizards.com/image.jpg",
    "filename": "abc123_image.jpg",
    "local_path": None,  # Set when downloaded
    "error": None        # After download: None, "connection" or "http"
}
```

---

### _url_to_filename(url: str) -> str

**Purpose:** Convert a URL to a safe, unique filename.

**Algorithm:**
1. Extract path from URL
2. Get original filename from path
3. Create MD5 hash of full URL (first 8 chars)
4. Split the name into stem and extension (default extension `.jpg`)
5. Make both parts safe (replace non-alphanumeric chars)
6. Truncate the stem to 50 chars; the extension is never cut off
7. Combine: `{hash}_{safe_stem}{ext}`

**Example:**
```
Input:  https://media.wizards.com/2025/images/story-art.webp
Output: a1b2c3d4_story_art.webp
```

---

### download_image(url, output_dir, cancel=None) -> str | None

**Purpose:** Download a single image (used for the cover).

**Features:**
- Adds `Referer` header to avoid CDN blocking
- `net.get()` with `IMAGE_RETRIES` (1) and `IMAGE_TIMEOUT` `(5, 20)`
- Creates output directory if needed

**Returns:** Local file path, or `None` if failed. `net.Cancelled` propagates.

---

### download_images(images, output_dir, cancel=None, progress=None) -> list[dict]

**Purpose:** Download all images for one story and update their `local_path` and `error` fields.

**Parameters:**
- `images` - List of image dicts from `_extract_content()`
- `output_dir` - Directory to save images (the run's working folder inside the output directory)
- `cancel` - Optional event; `net.Cancelled` is raised promptly when set
- `progress` - Optional `callback(done, total)` called before each download

**Behaviour:**
- After `_HOST_FAILURE_LIMIT` (2) consecutive connection failures to one host, the remaining images on that host are skipped for this story. This keeps a dead image CDN from stalling every image in turn
- `net.Offline` (no internet at all) is not swallowed; it propagates so the run aborts
- Each image ends with `error` set to `None`, `"connection"` (host unreachable or skipped) or `"http"` (404, read timeout, disk error)

**Returns:** Updated list. Images that failed keep `local_path = None`; the EPUB builder removes their `<img>` tags.

## Error Handling

- **Missing elements:** Fallback values used, no exceptions
- **JSON parsing:** Caught and ignored, moves to next method
- **Image download failures:** Logged, `local_path` stays `None`, doesn't crash
- **Stop / no internet:** `net.Cancelled` and `net.Offline` propagate to the GUI

## Maintenance Notes

### If titles aren't extracted correctly:
Add new selector to the list in `_extract_title()`.

### If authors show as "Unknown Author":
1. Check JSON-LD structure on the page
2. Check if author link pattern changed
3. Add new selector to `_extract_author()`

### If content is missing:
1. Inspect page structure in browser DevTools
2. Add new selector to `_extract_content()`
3. Check if new unwanted elements need filtering

### If an internal label shows where a card image should be:
The page uses a placeholder tag filled in by JavaScript. Check the tag name and attribute in the raw HTML against `_replace_card_placeholders()`, and the `magicCard` fields (`face`, `back`) used by `scraper.fetch_card_images()`.
