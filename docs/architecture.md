# Architecture Overview

## System Design

The MTG Stories to EPUB Converter follows a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUI (gui.py)                            │
│                    Tkinter Application Window                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Story List  │  │  Controls   │  │   Progress/Status       │ │
│  │  (Listbox)  │  │  (Buttons)  │  │   (Bar + Label)         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Scraper (scraper.py)                         │
│                                                                 │
│  fetch_all_story_sets() ──► Contentful API ──► Story metadata  │
│  fetch_story_page()     ──► magic.wizards.com ──► Story HTML   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Parser (parser.py)                          │
│                                                                 │
│  parse_story() ──► Extract title, author, date, content        │
│  download_images() ──► Save images locally                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 EPUB Builder (epub_builder.py)                  │
│                                                                 │
│  create_epub() ──► Assemble chapters, images, CSS ──► .epub    │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Startup Flow
```
Application Start
       │
       ▼
GUI Initializes
       │
       ▼
Auto-fetch story sets (after 100ms delay)
       │
       ▼
Display grouped by year in listbox
```

### 2. EPUB Generation Flow
```
User clicks "Generate EPUB"
       │
       ▼
Get selected story set
       │
       ▼
For each story in set:
   │
   ├──► Fetch HTML page (scraper)
   │
   ├──► Parse content (parser)
   │
   └──► Download images (parser)
       │
       ▼
Sort stories by publication date
       │
       ▼
Build EPUB (epub_builder)
       │
       ▼
Save to output directory
       │
       ▼
Show success message
```

## Module Responsibilities

### gui.py
- Window layout and widgets
- User interaction handling
- Threading for background operations
- Progress and status updates
- File dialog for output directory

### scraper.py
- Contentful API communication
- Story set metadata retrieval
- Individual story page fetching
- Rate limiting (0.5s delay between requests)

### parser.py
- HTML content extraction
- Author name detection (multiple methods)
- Publication date parsing
- Image URL collection
- Image downloading

### epub_builder.py
- EPUB file structure creation
- CSS styling
- Chapter generation
- Image embedding and format conversion
- Table of contents generation

## Threading Model

The GUI uses Python's `threading` module to prevent UI freezing:

```python
# Pattern used throughout gui.py
def _long_operation(self):
    def work():
        try:
            result = do_something()
            self.root.after(0, lambda: self._handle_result(result))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(str(e)))

    threading.Thread(target=work, daemon=True).start()
```

Key points:
- Background threads are daemon threads (exit when main thread exits)
- UI updates use `root.after(0, callback)` to run on main thread
- Status/progress updates also use `root.after()` for thread safety

## Error Handling

Errors are handled at each layer:

1. **Scraper**: HTTP errors, API errors → Exception raised
2. **Parser**: Missing elements → Fallback values, continue
3. **EPUB Builder**: Image failures → Skip image, continue
4. **GUI**: All exceptions → Error dialog to user

## File Storage

```
~/Documents/MTG-Stories/
├── Set Name.epub          # Generated EPUB
└── .temp_images/          # Temporary (deleted after generation)
    ├── abc123_image1.jpg
    └── def456_image2.jpg
```

## Configuration

Currently hardcoded values (could be made configurable):

| Value | Location | Purpose |
|-------|----------|---------|
| `CONTENTFUL_TOKEN` | scraper.py | API authentication |
| `YEARS` | scraper.py | Years to fetch (2014-2025) |
| `output_dir` | gui.py | Default output path |
| `EPUB_CSS` | epub_builder.py | EPUB styling |
