"""
EPUB generation module for creating ebook files from parsed stories.
"""

import os
import uuid
from datetime import datetime

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from .parser import Story


# CSS for styling preservation
EPUB_CSS = """
* {
    box-sizing: border-box;
    max-width: 100%;
}

body {
    font-family: Georgia, serif;
    line-height: 1.6;
    margin: 1em;
}

h1 {
    font-size: 1.8em;
    margin-top: 1em;
    margin-bottom: 0.5em;
    text-align: center;
}

h2 {
    font-size: 1.4em;
    margin-top: 1em;
    margin-bottom: 0.5em;
}

h3 {
    font-size: 1.2em;
    margin-top: 0.8em;
    margin-bottom: 0.4em;
}

p {
    margin: 0.5em 0;
}

em, i {
    font-style: italic;
}

strong, b {
    font-weight: bold;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 2em auto;
    width: 50%;
}

.scene-break {
    text-align: center;
    margin: 2em 0;
    font-size: 1.2em;
    letter-spacing: 0.5em;
}

ul, ol {
    margin: 1em 0;
    padding-left: 2em;
}

li {
    margin: 0.3em 0;
}

blockquote {
    margin: 1em 2em;
    padding-left: 1em;
    border-left: 3px solid #ccc;
    font-style: italic;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}

.image-caption {
    text-align: center;
    font-size: 0.9em;
    font-style: italic;
    color: #666;
    margin-top: 0.5em;
}

.chapter-header {
    text-align: center;
    margin-bottom: 2em;
}

.chapter-title {
    font-size: 1.8em;
    margin-bottom: 0.3em;
}

.chapter-author {
    font-size: 1em;
    color: #666;
    text-align: center;
}

.chapter-date {
    font-size: 0.9em;
    color: #888;
    text-align: center;
}

a {
    color: #0066cc;
    text-decoration: none;
}

pre, code {
    font-family: monospace;
    background: #f5f5f5;
    padding: 0.2em 0.4em;
}

pre {
    padding: 1em;
    overflow-x: auto;
    white-space: pre-wrap;
}

table {
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 0.85em;
    table-layout: fixed;
    background: #1a1a1a !important;
    color: #fff;
}

th, td {
    border: 1px solid #444;
    padding: 0.4em;
    text-align: left;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

th {
    background: #333;
    font-weight: bold;
}

pre {
    background: #1a1a1a !important;
    color: #fff;
    font-size: 0.8em;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}
"""


def create_epub(stories: list[Story], set_name: str, output_dir: str, cover_image_path: str | None = None) -> str:
    """
    Create an EPUB file from a list of stories.

    Args:
        stories: List of Story objects, should be sorted by publication date.
        set_name: Name of the story set (used for title).
        output_dir: Directory to save the EPUB file.
        cover_image_path: Optional path to cover image.

    Returns:
        Path to the created EPUB file.
    """
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(f"mtg-stories-{uuid.uuid4().hex[:8]}")
    book.set_title(set_name)
    book.set_language("en")

    # Set primary author (first story's author)
    primary_author = None
    for story in stories:
        if story.author and story.author != "Unknown Author":
            primary_author = story.author
            break

    if primary_author:
        book.add_author(primary_author)
    else:
        book.add_author("Wizards of the Coast")

    # Add cover image if provided
    if cover_image_path and os.path.exists(cover_image_path):
        _add_cover_image(book, cover_image_path, set_name)

    # Add CSS
    css = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=EPUB_CSS
    )
    book.add_item(css)

    # Collect all images from all stories
    all_images = {}
    for story in stories:
        for img in story.images:
            if img["local_path"] and os.path.exists(img["local_path"]):
                all_images[img["filename"]] = img["local_path"]

    # Add images to the book (convert to JPEG for Kindle compatibility)
    image_items = {}
    for filename, local_path in all_images.items():
        try:
            content, new_filename, media_type = _convert_image_for_kindle(local_path, filename)
            img_item = epub.EpubItem(
                uid=f"img_{filename}",
                file_name=f"images/{new_filename}",
                media_type=media_type,
                content=content
            )
            book.add_item(img_item)
            image_items[filename] = new_filename  # Map original filename to new filename
        except Exception as e:
            print(f"Failed to add image {filename}: {e}")

    # Create chapters (pass image mapping for filename updates)
    chapters = []
    for i, story in enumerate(stories):
        chapter = _create_chapter(story, i + 1, css, image_items)
        book.add_item(chapter)
        chapters.append(chapter)

    # Create table of contents
    book.toc = [(chapter, []) for chapter in chapters]

    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define spine (reading order)
    book.spine = ["nav"] + chapters

    # Save the book
    os.makedirs(output_dir, exist_ok=True)
    safe_filename = "".join(c if c.isalnum() or c in " -_" else "_" for c in set_name)
    output_path = os.path.join(output_dir, f"{safe_filename}.epub")

    epub.write_epub(output_path, book)

    return output_path


def _add_cover_image(book: epub.EpubBook, image_path: str, title: str = ""):
    """Add a cover image to the book with standard book aspect ratio and title text."""
    import io

    # Target dimensions (Kindle recommended: 1600x2560, ratio 1:1.6)
    TARGET_WIDTH = 1600
    TARGET_HEIGHT = 2560
    TARGET_RATIO = TARGET_HEIGHT / TARGET_WIDTH  # 1.6

    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            orig_width, orig_height = img.size
            orig_ratio = orig_height / orig_width

            # Crop to target aspect ratio (center crop)
            if orig_ratio < TARGET_RATIO:
                # Image is too wide, crop width
                new_width = int(orig_height / TARGET_RATIO)
                left = (orig_width - new_width) // 2
                img = img.crop((left, 0, left + new_width, orig_height))
            elif orig_ratio > TARGET_RATIO:
                # Image is too tall, crop height
                new_height = int(orig_width * TARGET_RATIO)
                top = (orig_height - new_height) // 2
                img = img.crop((0, top, orig_width, top + new_height))

            # Resize to target dimensions
            img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)

            # Add title text overlay
            if title:
                img = _add_title_to_cover(img, title)

            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            cover_content = buffer.getvalue()

        book.set_cover("cover.jpg", cover_content)

    except Exception as e:
        print(f"Failed to add cover image: {e}")


def _add_title_to_cover(img: Image.Image, title: str) -> Image.Image:
    """Add title text to the cover image in a rectangular box with margins."""
    img_width, img_height = img.size

    # 15% margins on left, right, and bottom
    margin = int(img_width * 0.15)
    margin_bottom = int(img_height * 0.08)  # Slightly less on bottom

    # Box dimensions - positioned in bottom third with margins
    box_height = img_height // 3
    box_left = margin
    box_right = img_width - margin
    box_bottom = img_height - margin_bottom
    box_top = box_bottom - box_height
    box_width = box_right - box_left

    # Create semi-transparent overlay for the box
    overlay = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Draw semi-transparent dark box with rounded appearance
    overlay_draw.rectangle(
        [(box_left, box_top), (box_right, box_bottom)],
        fill=(20, 20, 20, 220)  # Near-black with ~85% opacity
    )

    # Composite the overlay onto the image
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    # Now draw text on the composited image
    draw = ImageDraw.Draw(img)

    # Try to load a nice font with larger size
    font_size = 160
    font = None

    # Try common font paths (prefer bold fonts)
    font_paths = [
        "C:/Windows/Fonts/georgiab.ttf",  # Georgia Bold
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/timesbd.ttf",  # Times Bold
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/arialbd.ttf",  # Arial Bold
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/System/Library/Fonts/Times.ttc",
    ]

    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        font = ImageFont.load_default()
        font_size = 20

    # Word wrap the title to fit in the box (with padding inside box)
    text_padding = 40
    max_text_width = box_width - (text_padding * 2)
    lines = _wrap_text(title, font, max_text_width, draw)

    # Calculate total text block height
    line_height = font_size + 30
    total_text_height = len(lines) * line_height

    # Center text vertically within the box
    text_start_y = box_top + (box_height - total_text_height) // 2

    # Draw each line centered horizontally within the box
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = box_left + (box_width - text_width) // 2

        # Draw text in white
        draw.text((x_position, text_start_y), line, font=font, fill=(255, 255, 255))

        text_start_y += line_height

    return img


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def _create_chapter(story: Story, chapter_num: int, css: epub.EpubItem, image_mapping: dict[str, str] | None = None) -> epub.EpubHtml:
    """Create an EPUB chapter from a story."""
    # Create chapter header
    date_str = story.publication_date.strftime("%B %d, %Y") if story.publication_date else ""

    header_html = f"""
    <div class="chapter-header">
        <h1 class="chapter-title">{_escape_html(story.title)}</h1>
        <p class="chapter-author">by {_escape_html(story.author)}</p>
        {f'<p class="chapter-date">{date_str}</p>' if date_str else ''}
    </div>
    <hr />
    """

    # Process the story content
    content = _process_content(story.content_html, image_mapping)

    # Combine into full chapter (simple HTML for ebooklib compatibility)
    chapter_html = f"""<html>
<head>
    <title>{_escape_html(story.title)}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
{header_html}
{content}
</body>
</html>
"""

    # Create the chapter item
    safe_title = "".join(c if c.isalnum() else "_" for c in story.title)[:30]
    chapter = epub.EpubHtml(
        title=story.title,
        file_name=f"chapter_{chapter_num:02d}_{safe_title}.xhtml",
        lang="en"
    )
    chapter.set_content(chapter_html)
    chapter.add_item(css)

    return chapter


def _process_content(html: str, image_mapping: dict[str, str] | None = None) -> str:
    """Process HTML content to ensure EPUB compatibility."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Convert scene breaks (*** or * * *) to styled divs
    for text in soup.find_all(string=True):
        if text.strip() in ["***", "* * *", "* * * *"]:
            new_div = soup.new_tag("div")
            new_div["class"] = "scene-break"
            new_div.string = "* * *"
            text.replace_with(new_div)

    # Ensure all img tags are properly closed and have alt text
    # Also update image src to use converted filenames
    for img in soup.find_all("img"):
        if not img.get("alt"):
            img["alt"] = "Story illustration"

        # Update image src if we have a mapping (webp -> jpg conversion)
        if image_mapping and img.get("src"):
            src = img["src"]
            if src.startswith("images/"):
                original_filename = src[7:]  # Remove "images/" prefix
                if original_filename in image_mapping:
                    img["src"] = f"images/{image_mapping[original_filename]}"

    # Remove any remaining script or style tags
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Get just the body content if there's a body tag
    body = soup.find("body")
    if body:
        return "".join(str(child) for child in body.children)

    # Otherwise return the processed content
    article = soup.find("article")
    if article:
        return str(article)

    return str(soup)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _convert_image_for_kindle(local_path: str, original_filename: str) -> tuple[bytes, str, str]:
    """
    Convert image to JPEG for Kindle compatibility.

    Returns:
        Tuple of (image_bytes, new_filename, media_type)
    """
    import io

    ext = os.path.splitext(local_path)[1].lower()

    # JPEG and GIF can be used as-is
    if ext in (".jpg", ".jpeg"):
        with open(local_path, "rb") as f:
            return f.read(), original_filename, "image/jpeg"
    if ext == ".gif":
        with open(local_path, "rb") as f:
            return f.read(), original_filename, "image/gif"

    # Convert webp, png, and other formats to JPEG
    try:
        with Image.open(local_path) as img:
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparent images
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Save as JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)

            # Create new filename with .jpg extension
            new_filename = os.path.splitext(original_filename)[0] + ".jpg"

            return buffer.getvalue(), new_filename, "image/jpeg"
    except Exception as e:
        print(f"Failed to convert image {original_filename}, using original: {e}")
        # Fall back to original file
        with open(local_path, "rb") as f:
            return f.read(), original_filename, _get_image_media_type(local_path)


def _get_image_media_type(filepath: str) -> str:
    """Get the MIME type for an image file."""
    ext = os.path.splitext(filepath)[1].lower()
    types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    return types.get(ext, "image/jpeg")
