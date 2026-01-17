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
    images: list[dict]  # [{"url": ..., "local_path": ..., "filename": ...}]
```

## Functions

### parse_story(html: str, url: str) -> Story

**Purpose:** Main entry point - parse a story page and extract all content.

**Parameters:**
- `html` - HTML content of the story page
- `url` - URL of the story (for resolving relative links)

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

**Date Formats Supported:**
```python
formats = [
    "%B %d, %Y",  # "June 20, 2025"
    "%b %d, %Y",  # "Jun 20, 2025"
    "%Y-%m-%d",   # "2025-06-20"
    "%d %B %Y",   # "20 June 2025"
    "%d %b %Y",   # "20 Jun 2025"
]
```

---

### _extract_content(soup: BeautifulSoup, base_url: str) -> tuple[str, list[dict]]

**Purpose:** Extract the main story content, preserving HTML structure.

**Returns:** Tuple of (content_html, image_list)

**Content Selectors (in order):**
1. `article .article-body`
2. `article .entry-content`
3. `.article-content`
4. `.story-content`
5. `article`
6. `main`
7. `body` (fallback)

**Processing Steps:**

1. **Find content container** using selectors
2. **Remove unwanted elements:**
   - `script`, `style`, `nav`, `header`, `footer`
   - `iframe` (not supported in EPUB)
   - `.social-share`, `.comments`, `.related-articles`, `.advertisement`
3. **Process images:**
   - Get URL from `src` or `data-src`
   - Generate unique filename
   - Update `src` to local path (`images/filename`)
   - Remove `srcset`, `data-src`, `data-srcset`, `loading` attributes
4. **Process links:**
   - Keep internal anchor links (`#section`)
   - Remove magic.wizards.com links (keep text)
   - Keep other external links
5. **Normalize whitespace**

**Image Dict Structure:**
```python
{
    "url": "https://media.wizards.com/image.jpg",
    "filename": "abc123_image.jpg",
    "local_path": None  # Set when downloaded
}
```

---

### _url_to_filename(url: str) -> str

**Purpose:** Convert a URL to a safe, unique filename.

**Algorithm:**
1. Extract path from URL
2. Get original filename from path
3. Create MD5 hash of full URL (first 8 chars)
4. Get file extension (default to `.jpg`)
5. Make filename safe (replace non-alphanumeric chars)
6. Truncate to 50 chars max
7. Combine: `{hash}_{safe_name}`

**Example:**
```
Input:  https://media.wizards.com/2025/images/story-art.webp
Output: a1b2c3d4_story_art.webp
```

---

### download_image(url: str, output_dir: str) -> str | None

**Purpose:** Download a single image.

**Features:**
- Adds `Referer` header to avoid CDN blocking
- 30 second timeout
- Creates output directory if needed

**Returns:** Local file path, or `None` if failed.

---

### download_images(images: list[dict], output_dir: str) -> list[dict]

**Purpose:** Download all images and update their `local_path` fields.

**Parameters:**
- `images` - List of image dicts from `_extract_content()`
- `output_dir` - Directory to save images

**Returns:** Updated list with `local_path` populated.

## Error Handling

- **Missing elements:** Fallback values used, no exceptions
- **JSON parsing:** Caught and ignored, moves to next method
- **Image download failures:** Logged, returns `None`, doesn't crash

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
