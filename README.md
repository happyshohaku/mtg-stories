# MTG Stories to EPUB Converter

[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/happyshohaku/mtg-stories/releases)

A Python GUI application that scrapes Magic: The Gathering stories from the official Wizards of the Coast website and generates EPUB files for e-reader devices like Kindle.

## Features

- Three data sources for comprehensive story coverage:
  - **Contentful storyGroups** — official curated story sets (2014+)
  - **Contentful articles** — individual magic-story articles not in any storyGroup
  - **mtg.wiki** — archive stories including pre-2014 content
- 3-layer deduplication prevents duplicate stories across sources
- Real-time search bar to filter by set name or story title
- Details panel showing story titles, authors, and dates on selection
- Story sets grouped by year with newest first
- Generate EPUB files with all episodes and side stories
- Multi-select story sets to combine into a single EPUB
- Drag-and-drop reorder dialog with date sorting for combined EPUBs
- Table of contents with chapter links (nested sections for multi-set EPUBs)
- Preserved original styling (headers, italics, lists, tables)
- Embedded images converted to Kindle-compatible format (SVG pass-through)
- Professional cover image with title overlay (1600x2560, standard book ratio)
- Direct links to external e-books (Amazon, etc.) for e-book only entries

## Setup

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd mtg-stories
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

### From Source

```bash
python -m src.main
```

### Standalone Executable

Build a standalone `.exe` (no Python required):

```bash
# Double-click build_exe.bat, or run manually:
pip install pyinstaller
pyinstaller mtg_stories.spec
```

The executable is created at `dist/MTG to EPUB.exe`.

### Using the Application

1. The application will automatically fetch available story sets on startup (results appear progressively as each source loads)
2. Click "Refresh Sets" to reload the story list from the website
3. Select one or more story sets from the list (Ctrl+click or Shift+click to multi-select; year headers are not selectable)
4. Choose an output directory using "Browse..."
5. Click "Generate EPUB" to create the e-book
   - For a single set with only an external e-book link, the button shows "Open Link"
   - For multiple sets, a dialog lets you edit the EPUB title and reorder sets via drag-and-drop
6. Once complete, you'll be prompted to open the output folder

### Output

EPUB files are saved to `~/Documents/MTG-Stories/` by default. The filename matches the story set name.

## Project Structure

```
mtg-stories/
├── src/
│   ├── __init__.py       # Package marker + version constant
│   ├── main.py           # Entry point
│   ├── gui.py            # Tkinter GUI application
│   ├── scraper.py        # Contentful API (storyGroups + articles)
│   ├── wiki_scraper.py   # mtg.wiki archive scraper
│   ├── parser.py         # HTML parsing & content extraction
│   ├── epub_builder.py   # EPUB file generation
│   ├── net.py            # HTTP session, cancellable retries, offline detection
│   ├── dedup.py          # Cross-source dedup keys
│   ├── dates.py          # Shared date parsing
│   └── log.py            # File logging (%LOCALAPPDATA%\MTG-Stories\mtg-stories.log)
├── docs/                 # Documentation SOPs
├── run.py                # PyInstaller entry point
├── mtg_stories.spec      # PyInstaller build config
├── build_exe.bat         # One-click build script
├── requirements.txt      # Python dependencies
├── .gitignore
└── README.md
```

## Documentation

Detailed documentation for developers is available in the `docs/` folder:

- [Architecture Overview](docs/architecture.md) - High-level system design and data flow
- [Contentful API & Token](docs/contentful-api.md) - How the magic-story API works and token details
- [Scraper Module](docs/scraper.md) - Web scraping implementation details
- [Parser Module](docs/parser.md) - HTML parsing and content extraction
- [EPUB Builder Module](docs/epub-builder.md) - EPUB generation and styling
- [GUI Module](docs/gui.md) - Tkinter interface implementation

## Dependencies

| Package | Purpose |
|---------|---------|
| requests | HTTP requests to fetch web pages and API data |
| beautifulsoup4 | HTML parsing and content extraction |
| ebooklib | EPUB file creation |
| Pillow | Image processing, cover generation, and text rendering |

## License

This project is for personal use. Magic: The Gathering stories are copyright Wizards of the Coast.
