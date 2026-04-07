# EPUB Builder Module Documentation

## File: `src/epub_builder.py`

## Purpose

The EPUB builder module creates valid EPUB files from parsed story content:
- Assembles chapters from Story objects
- Embeds and converts images
- Applies CSS styling
- Generates table of contents
- Handles cover images

## Dependencies

```python
from ebooklib import epub  # EPUB creation
from PIL import Image, ImageDraw, ImageFont  # Image processing and text rendering
```

## CSS Styling

The `EPUB_CSS` constant contains all styling for the EPUB. Key rules:

### Global Reset (Critical for Overflow Prevention)
```css
* {
    box-sizing: border-box;
    max-width: 100%;
}
```

**Why this matters:**
- `box-sizing: border-box` - Padding and border are included in width calculations
- `max-width: 100%` - Prevents any element from exceeding viewport width
- Preserves original inline styles while preventing overflow

### Typography
```css
body {
    font-family: Georgia, serif;
    line-height: 1.6;
}

p {
    margin: 0.5em 0;
    text-indent: 1.5em;
}

p:first-of-type {
    text-indent: 0;
}
```

### Tables (Dark Theme for Readability)
```css
table {
    width: 100% !important;
    max-width: 100% !important;
    background: #1a1a1a !important;
    color: #fff;
    table-layout: fixed;
}
```

### Scene Breaks
```css
.scene-break {
    text-align: center;
    margin: 2em 0;
    letter-spacing: 0.5em;
}
```

## Functions

### create_epub(stories, set_name, output_dir, cover_image_path, groups, output_path) -> str

**Purpose:** Main entry point - create an EPUB file from stories.

**Parameters:**
- `stories` - List of Story objects (flat list, used for image collection and author extraction)
- `set_name` - Name of the story set (used for title)
- `output_dir` - Directory to save the EPUB (used when `output_path` is not provided)
- `cover_image_path` - Optional path to cover image
- `groups` - Optional grouped structure for nested TOC. Each entry is `(group_name, [Story, ...])`. When provided, multi-story groups get a TOC section header; single-story groups get a flat entry.
- `output_path` - Optional explicit output file path. When provided, overrides `output_dir` and filename generation.

**Returns:** Path to the created EPUB file.

**Flow:**
```
Create EpubBook
       │
       ├──► Set metadata (ID, title, language, authors)
       │
       ├──► Add cover image (if provided)
       │
       ├──► Add CSS stylesheet
       │
       ├──► Collect and convert all images
       │
       ├──► Create chapters (one per story)
       │       │
       │       ├──► Flat mode (no groups): chapters in order, flat TOC
       │       └──► Grouped mode: chapters per group, nested TOC sections
       │
       ├──► Add navigation files (NCX, Nav)
       │
       ├──► Define spine (reading order)
       │
       └──► Write EPUB file
```

**Metadata:**
```python
book.set_identifier(f"mtg-stories-{uuid.uuid4().hex[:8]}")
book.set_title(set_name)
book.set_language("en")

# Collect unique authors
authors = set(s.author for s in stories if s.author != "Unknown Author")
for author in authors:
    book.add_author(author)
```

**File Naming:**
```python
# When output_path is not provided, generates filename from set_name:
safe_filename = "".join(c if c.isalnum() or c in " -_" else "_" for c in set_name)
output_path = os.path.join(output_dir, f"{safe_filename}.epub")

# When output_path is provided (e.g., from save-as dialog), uses it directly.
```

---

### _add_cover_image(book, image_path, title)

**Purpose:** Add and process cover image with standard book dimensions and title overlay.

**Parameters:**
- `book` - EpubBook instance
- `image_path` - Path to source image
- `title` - Story set name to display on cover

**Processing:**
1. Open image with Pillow
2. Convert RGBA/P modes to RGB
3. Crop to 1:1.6 aspect ratio (center crop)
4. Resize to 1600x2560 pixels (Kindle recommended)
5. Add title text overlay via `_add_title_to_cover()`
6. Save as JPEG (quality 85)
7. Add to book with `book.set_cover()`

**Cover Dimensions:**
```python
TARGET_WIDTH = 1600
TARGET_HEIGHT = 2560
TARGET_RATIO = 1.6  # Standard book aspect ratio
```

---

### _add_title_to_cover(img, title) -> Image

**Purpose:** Add title text in a semi-transparent box on the cover image.

**Layout:**
```
┌─────────────────────────────┐
│                             │
│      [Story artwork]        │
│                             │
│   ┌───────────────────┐     │ ← 15% margin left/right
│   │                   │     │
│   │   Story Title     │     │ ← Semi-transparent box
│   │                   │     │   (~85% opacity)
│   └───────────────────┘     │
│                             │ ← 8% margin bottom
└─────────────────────────────┘
```

**Features:**
- Box positioned in bottom third with 15% side margins, 8% bottom margin
- Semi-transparent dark background (RGBA: 20, 20, 20, 220)
- 160pt bold font (Georgia Bold preferred)
- Automatic word wrapping for long titles
- Text centered horizontally and vertically within box

**Font Loading:**
Tries fonts in order: Georgia Bold → Georgia → Times Bold → Times → Arial Bold → Arial → DejaVu Serif Bold → System default

---

### _wrap_text(text, font, max_width, draw) -> list[str]

**Purpose:** Word-wrap text to fit within a maximum pixel width.

**Parameters:**
- `text` - The text to wrap
- `font` - PIL ImageFont object
- `max_width` - Maximum width in pixels
- `draw` - PIL ImageDraw object (for measuring text)

**Returns:** List of lines that fit within max_width.

---

### _create_chapter(story, chapter_num, css, image_mapping) -> EpubHtml

**Purpose:** Create an EPUB chapter from a Story object.

**Chapter Structure:**
```html
<html>
<head>
    <title>Story Title</title>
    <link rel="stylesheet" href="style/main.css"/>
</head>
<body>
    <div class="chapter-header">
        <h1 class="chapter-title">Story Title</h1>
        <p class="chapter-author">by Author Name</p>
        <p class="chapter-date">January 15, 2025</p>
    </div>
    <hr />
    <!-- Story content here -->
</body>
</html>
```

**Filename Pattern:**
```python
f"chapter_{chapter_num:02d}_{safe_title}.xhtml"
# Example: chapter_01_Edge_of_Eternities_Episo.xhtml
```

---

### _process_content(html, image_mapping) -> str

**Purpose:** Process HTML content for EPUB compatibility.

**Processing Steps:**

1. **Convert scene breaks** - `***` or `* * *` becomes styled div
2. **Ensure image alt text** - Add "Story illustration" if missing
3. **Update image paths** - Map original filenames to converted filenames (webp → jpg)
4. **Remove scripts/styles** - Final cleanup
5. **Extract body content** - Return just the content, not full HTML wrapper

---

### _convert_image_for_kindle(local_path, original_filename) -> tuple

**Purpose:** Convert images to Kindle-compatible format.

**Returns:** Tuple of (bytes, new_filename, media_type)

**Conversion Rules:**
| Original Format | Action | Output Format |
|-----------------|--------|---------------|
| JPEG | Pass through | JPEG |
| GIF | Pass through | GIF |
| SVG | Pass through | SVG |
| WebP | Convert to JPEG | JPEG |
| PNG | Convert to JPEG | JPEG |
| PNG (transparent) | Convert with white background | JPEG |

**Transparency Handling:**
```python
if img.mode in ("RGBA", "P", "LA"):
    background = Image.new("RGB", img.size, (255, 255, 255))
    if img.mode == "P":
        img = img.convert("RGBA")
    background.paste(img, mask=img.split()[-1])
    img = background
```

---

### _get_image_media_type(filepath) -> str

**Purpose:** Get MIME type for an image file.

**Mapping:**
```python
{
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
```

---

### _escape_html(text) -> str

**Purpose:** Escape HTML special characters in text.

**Escapes:** `&`, `<`, `>`, `"`

## EPUB Structure

The generated EPUB contains:

```
book.epub/
├── META-INF/
│   └── container.xml
├── OEBPS/
│   ├── content.opf          # Package document
│   ├── toc.ncx              # Navigation (NCX)
│   ├── nav.xhtml            # Navigation (EPUB3)
│   ├── cover.jpg            # Cover image
│   ├── style/
│   │   └── main.css         # Stylesheet
│   ├── images/
│   │   ├── abc123_img1.jpg  # Story images
│   │   └── def456_img2.jpg
│   └── chapter_01_Title.xhtml
│   └── chapter_02_Title.xhtml
│   └── ...
└── mimetype
```

## Error Handling

- **Cover image failures:** Logged, book created without cover
- **Image conversion failures:** Falls back to original format
- **Missing images:** Skipped, chapter created without image

## Maintenance Notes

### Modifying styles:
Edit the `EPUB_CSS` constant. Test with multiple e-readers (Kindle, Calibre, Apple Books).

### Adding new chapter elements:
Modify `_create_chapter()` to include new HTML structure.

### Image format support:
Update `_convert_image_for_kindle()` to handle new formats.

### Kindle compatibility issues:
1. Ensure all images are JPEG or GIF
2. Keep CSS simple (no advanced features)
3. Test with Kindle Previewer or actual device
