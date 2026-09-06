# Architecture Overview

## System Design

The MTG Stories to EPUB Converter follows a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUI (gui.py)                            │
│                    Tkinter Application Window                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐ │
│  │ Search   │ │ Story    │ │ Details  │ │ Progress/Status   │ │
│  │ Bar      │ │ List     │ │ Panel    │ │ (Bar + Label)     │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Scraper          │ │ Scraper          │ │ Wiki Scraper    │
│ (scraper.py)     │ │ (scraper.py)     │ │ (wiki_scraper)  │
│                  │ │                  │ │                 │
│ storyGroups      │ │ articles         │ │ mtg.wiki page   │
│ Contentful API   │ │ Contentful API   │ │ HTML tables     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
              │               │               │
              └───────┬───────┘───────────────┘
                      │  3-layer dedup + merge
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

## Data Sources

The application fetches stories from three sources, merged with deduplication:

| Source | Module | Priority | Content |
|--------|--------|----------|---------|
| **storyGroups** | `scraper.py` | Highest | Curated story sets from Contentful (2014+) |
| **articles** | `scraper.py` | Medium | Individual `magic-story` articles from Contentful |
| **mtg.wiki** | `wiki_scraper.py` | Lowest | Archive stories from wiki tables (all years) |

### 3-Layer Deduplication Chain

1. **storyGroups** — baseline, highest priority
2. **Articles** — deduped against storyGroup slugs
3. **Wiki** — deduped against storyGroup + article slugs (URL path + title-based matching)

### Metadata Enrichment

Before dedup, article metadata (author, excerpt) is applied to storyGroup stories via slug matching. This fills in author names and excerpts that storyGroup entries don't include.

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
Indeterminate progress bar starts
       │
       ├──► Fetch storyGroups from Contentful API (years fetched in parallel via ThreadPoolExecutor)
       │       └──► Display results immediately (progressive loading)
       ├──► Fetch articles from Contentful API
       │       ├──► Enrich storyGroup stories with article metadata
       │       ├──► Dedup articles against storyGroups
       │       └──► Display updated results (progressive loading)
       └──► Fetch stories from mtg.wiki
               ├──► Dedup wiki against storyGroups + articles
               └──► Display final results (progressive loading)
       │
       ▼
Progress bar stops
```

### 2. EPUB Generation Flow
```
User selects one or more story sets
       │
       ▼
Single set? ──► Generate directly
Multiple sets? ──► Show reorder dialog (title, drag-and-drop order, date sort)
       │
       ▼
Check if output file exists → save-as dialog if so
       │
       ▼
For each story set, for each story:
   │
   ├──► Fetch HTML page (scraper)
   │
   ├──► Parse content (parser)
   │
   └──► Download images (parser)
       │
       ▼
Build EPUB (epub_builder)
   │
   ├──► Single set: flat table of contents
   └──► Multiple sets: grouped TOC with section headers per set
       │
       ▼
Save to output directory
       │
       ▼
Show success message
```

## Module Responsibilities

### gui.py
- Window layout and widgets (search bar, listbox, details panel, controls)
- Real-time search filtering by set name and story titles
- Multi-select support with click-order tracking
- Details panel showing story info (single) or combined summary (multi)
- Reorder dialog with drag-and-drop and date sorting for combined EPUBs
- 3-source fetch, enrichment, dedup, and merge orchestration
- Generation runs with a per-run id and cancel event: Stop resets the UI immediately and abandons the worker; lost internet aborts the run; stories that fail are listed in the completion dialog
- File-exists detection with save-as dialog
- User interaction handling
- Threading for background operations
- Progress and status updates

### scraper.py
- Contentful API communication
- Story set metadata retrieval (storyGroups) — parallel year fetching via `ThreadPoolExecutor(max_workers=6)`
- Individual article fetching and title-prefix grouping
- Slug extraction and dedup utilities
- Individual story page downloading
- Rate limiting (0.5s for regular, 1.0s for archive.org)

### wiki_scraper.py
- Parses HTML tables from `https://mtg.wiki/page/Magic_Story`
- Extracts story metadata (title, author, date, URL, set)
- Groups "Other" stories by series, title prefix, and author proximity
- Slug extraction and dedup utilities for wiki content

### parser.py
- HTML content extraction
- Author name detection (multiple methods)
- Publication date extraction
- Image URL collection and downloading (per-host skip after repeated connection failures, records why each image failed)

### net.py
- Single entry point for all HTTP: `net.get()` on one pooled `requests.Session`
- Retries with exponential backoff on 429/5xx/connection errors, implemented in-process so the waits can be cancelled via a `threading.Event`
- `(connect, read)` timeouts: 5s connect everywhere, longer reads for archive.org
- On the first connection failure, probes a known-good host and raises `net.Offline` immediately when the internet is gone (generation aborts with a "Lost internet connection" dialog)

### dedup.py
- Dedup keys shared by the scrapers: URL slug, URL path (archive.org URLs unwrapped), set-scoped title, and bare title only for titles specific enough to stand alone
- Generic titles ("Prologue", "Chapter 3") only match within the same set, so wiki stories with common titles are not dropped

### dates.py
- `parse_date()` for every date format the sources use; always returns naive datetimes so sorting never mixes aware and naive values

### log.py
- `setup_logging()` sends all modules' logging to a rotating file (`%LOCALAPPDATA%\MTG-Stories\mtg-stories.log`, or `~/.mtg-stories/`) plus stderr when one exists
- The packaged .exe has no console, so this is where fetch and image failures can be found

### epub_builder.py
- EPUB file structure creation
- CSS styling
- Chapter generation
- Image embedding and format conversion
- Table of contents generation (flat or grouped/nested for multi-set EPUBs)
- Cover image with title overlay
- Custom output path support

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
- Fetch thread uses `try/finally` to guarantee progress bar cleanup
- Indeterminate progress bar animates during story fetch; determinate during EPUB generation
- Listbox updates progressively after each fetch phase (storyGroups → articles → wiki)

## Error Handling

Errors are handled at each layer:

1. **Scraper**: HTTP errors, API errors → Exception raised
2. **Wiki Scraper**: Fetch/parse errors → Logged, returns empty
3. **Parser**: Missing elements → Fallback values, continue
4. **EPUB Builder**: Image failures → Skip image, continue
5. **GUI**: All exceptions → Error dialog to user; source failures → skipped, other sources continue

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
| `YEARS` | scraper.py | Years to fetch (dynamic, current year down to 2014) |
| `output_dir` | gui.py | Default output path |
| `EPUB_CSS` | epub_builder.py | EPUB styling |
| Wiki URL | wiki_scraper.py | mtg.wiki story list page |
| `__version__` | __init__.py | App version (shown in title bar) |
