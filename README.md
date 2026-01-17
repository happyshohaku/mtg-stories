# MTG Stories to EPUB Converter

A Python GUI application that scrapes Magic: The Gathering stories from the official Wizards of the Coast website and generates EPUB files for e-reader devices like Kindle.

## Features

- Browse all available story sets from the MTG story archive (2014-2025)
- Story sets grouped by year with newest first
- Generate EPUB files with all episodes and side stories
- Stories automatically sorted by publication date
- Table of contents with chapter links
- Preserved original styling (headers, italics, lists, tables)
- Embedded images converted to Kindle-compatible format
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

### GUI Mode (Default)

```bash
python -m src.main
```

Or run directly:

```bash
cd src
python -m main
```

### Using the Application

1. The application will automatically fetch available story sets on startup
2. Click "Refresh Sets" to reload the story list from the website
3. Select a story set from the list (year headers are not selectable)
4. Choose an output directory using "Browse..."
5. Click "Generate EPUB" to create the e-book
   - For e-book only entries, the button shows "Open Link" and opens the external link in your browser
6. Once complete, you'll be prompted to open the output folder

### Output

EPUB files are saved to `~/Documents/MTG-Stories/` by default. The filename matches the story set name.

## Project Structure

```
mtg-stories/
├── src/
│   ├── __init__.py       # Package marker
│   ├── main.py           # Entry point
│   ├── gui.py            # Tkinter GUI application
│   ├── scraper.py        # Web scraping & Contentful API
│   ├── parser.py         # HTML parsing & content extraction
│   └── epub_builder.py   # EPUB file generation
├── docs/                 # Documentation SOPs
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
