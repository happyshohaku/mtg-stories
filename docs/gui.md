# GUI Module Documentation

## File: `src/gui.py`

## Purpose

The GUI module provides a Tkinter-based graphical interface for:
- Browsing available story sets from three data sources
- Real-time search filtering by set name or story title
- Viewing story details (title, author, date) in a details panel
- Multi-select story sets for combined EPUB generation
- Drag-and-drop reorder dialog for multi-set EPUBs with date sorting
- Grouped table of contents when combining multiple sets
- File-exists detection with save-as dialog
- Selecting output directory
- Triggering EPUB generation
- Displaying progress and status

## Class: MTGStoriesApp

### Initialization

```python
def __init__(self, root: tk.Tk):
    self.root = root
    self.root.title(f"MTG Stories to EPUB v{__version__}")
    self.root.geometry("600x650")
    self.root.minsize(500, 550)

    # Data
    self.story_sets_by_year: dict[int, list[dict]] = {}
    self.listbox_items: list[dict | None] = []  # None for year headers
    self.output_dir = os.path.join(os.path.expanduser("~"), "Documents", "MTG-Stories")
    self.selection_order: list[int] = []  # Track click order for multi-select

    self._create_widgets()
    self.root.after(100, self._refresh_sets)  # Auto-fetch on startup
```

### Window Layout

```
┌─────────────────────────────────────────────────────┐
│  MTG Stories to EPUB v1.1.0             (Header)    │
├─────────────────────────────────────────────────────┤
│  Story Sets (by Year)                               │
│  Search: [________________________]                 │
│  ┌───────────────────────────────────────────────┐  │
│  │ ──── 2026 ────                                │  │
│  │   Secrets of Strixhaven (1 stories) [articles]│  │
│  │ ──── 2025 ────                                │  │
│  │   Edge of Eternities (5 stories)              │  │
│  │   Lorwyn Eclipsed (4 stories)                │  │
│  │   The Magic Story Podcast (3 stories) [wiki] │▼ │
│  └───────────────────────────────────────────────┘  │
│  [Refresh Sets]                                     │
├─────────────────────────────────────────────────────┤
│  Details                                            │
│  ┌───────────────────────────────────────────────┐  │
│  │ Edge of Eternities  (official)                │  │
│  │   Episode 1 — by Author — (2025-01-15)        │  │
│  │   Episode 2 — by Author — (2025-01-22)        │  │
│  └───────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│  Output Directory                                   │
│  ┌─────────────────────────────────────┐ [Browse]   │
│  │ C:\Users\...\Documents\MTG-Stories  │            │
│  └─────────────────────────────────────┘            │
├─────────────────────────────────────────────────────┤
│  [          Generate EPUB / Open Link          ]    │
├─────────────────────────────────────────────────────┤
│  ████████████████░░░░░░░░░░░░░░░░  45%              │
│  Fetching story 3/7: Edge of Eternities...          │
└─────────────────────────────────────────────────────┘
```

### Widget Hierarchy

```
root (Tk)
└── main_frame (Frame)
    ├── header_frame (Frame)
    │   └── Label "MTG Stories to EPUB v{__version__}"
    ├── list_frame (LabelFrame "Story Sets")
    │   ├── search_frame (Frame)
    │   │   ├── Label "Search:"
    │   │   └── Entry (search_var, real-time filtering)
    │   ├── list_container (Frame)
    │   │   ├── listbox (Listbox)
    │   │   └── scrollbar (Scrollbar)
    │   └── Button "Refresh Sets"
    ├── info_frame (LabelFrame "Details")
    │   └── Text (info_text, disabled, styled tags)
    ├── output_frame (LabelFrame "Output Directory")
    │   ├── Entry (readonly, shows path)
    │   └── Button "Browse..."
    ├── generate_btn (Button "Generate EPUB")
    ├── progress_bar (Progressbar)
    └── status_label (Label)
```

## Methods

### Search

#### _on_search(*args)
Triggered on every keystroke in the search entry. Filters `story_sets_by_year` by matching the query against set names and individual story titles (case-insensitive). Calls `_update_sets_list()` with `preserve_search=True` to avoid overwriting the master data.

Empty search restores the full list.

---

### Details Panel

#### _show_info(story_set: dict)
Populates the details Text widget with story set info using styled tags:
- **bold** — set name
- **story** — per-story line with title, author, date (indented 20px)

Shown for single-selection only.

#### _show_multi_info(story_sets: list[dict])
Shows a combined summary when multiple sets are selected: count of sets, total story count, and per-set name/count/source.

#### _clear_info()
Clears the details panel.

---

### UI Update Methods

#### _set_status(message: str)
Updates the status label text. Calls `root.update_idletasks()` to refresh immediately.

#### _set_progress(value: float)
Updates the progress bar (0-100 scale). Calls `root.update_idletasks()`.

---

### Data Methods

#### _refresh_sets()
Fetches story sets from all three sources in a background thread. Uses an indeterminate progress bar and progressive loading (listbox updates after each phase).

**Flow:**
```
Disable generate button
Start indeterminate progress bar (50ms interval)
Set status "Fetching..."
       │
       ▼
Background thread (wrapped in try/finally for progress bar cleanup):
  ├── scraper.fetch_all_story_sets()        → contentful_sets
  │     └── _update_sets_list() ← progressive update
  ├── scraper.fetch_article_story_sets()    → raw_article_sets
  │     ├── Build article_metadata lookup (slug → author/excerpt)
  │     ├── Enrich contentful_sets stories with article metadata
  │     ├── filter_article_sets() against storyGroup slugs
  │     └── _update_sets_list() ← progressive update
  └── wiki_scraper.fetch_wiki_story_sets()  → raw_wiki_sets
        ├── filter_wiki_sets() against storyGroup + article slugs
        └── _update_sets_list() ← final update
       │
       ▼
finally: stop progress bar, reset to determinate mode
```

#### _merge_story_sets(contentful_sets, article_sets, wiki_sets)
Merges all three sources into a single dict by year. Order per year: storyGroups first, then articles, then wiki.

#### _update_sets_list(sets_by_year, preserve_search=False)
Populates the listbox with story sets grouped by year.

**Display Format:**
```
──── 2025 ────                              (Year header, not selectable)
  Edge of Eternities (5 stories)            (Official storyGroup — black)
  New Set Name (2 stories) [articles]       (Article source — teal)
  Archive Set (3 stories) [mtg.wiki]        (Wiki source — saddle brown)
  Set Name (e-book only)                    (Grayed out, opens link)
```

**Source Colors:**
| Source | Color | Hex |
|--------|-------|-----|
| storyGroups | Default (black) | — |
| articles | Teal | `#1E6F8C` |
| mtg.wiki | Saddle brown | `#8B4513` |
| e-book only | Gray | `#999999` |

**Status bar** shows counts by source: "Found 150 story sets (80 official, 40 from articles, 30 from archive)"

**Listbox Items Tracking:**
```python
self.listbox_items: list[dict | None]
# None = year header (not selectable)
# dict = story set (selectable)
```

---

### Event Handlers

#### _on_select(event)
Handles listbox selection changes. Supports multi-select (EXTENDED mode).

**Behavior:**
- Year headers are automatically deselected
- Tracks selection order via `self.selection_order` (click order, not index order)
- Single selection: shows details panel, button shows "Generate EPUB" or "Open Link"
- Multiple selection: shows combined summary via `_show_multi_info()`, button shows "Generate EPUB"

#### _browse_output()
Opens a folder browser dialog and updates the output directory.

---

### Selection Methods

#### _get_selected_story_sets() -> list[dict]
Returns all currently selected story sets in click order, filtering out year headers. Replaces the old `_get_selected_story_set()` method.

#### _show_multi_info(story_sets: list[dict])
Shows a combined summary in the details panel when multiple sets are selected: total count, per-set name/count/source.

---

### Generation Methods

#### _generate_epub()
Main generation entry point. Handles single-select (direct generation or link opening) and multi-select (shows reorder dialog first).

#### _show_generate_dialog(story_sets: list[dict]) -> tuple[str, list[dict]] | None
Modal dialog for multi-set EPUB generation. Returns `(title, ordered_story_sets)` or `None` if cancelled.

**Features:**
- Editable EPUB title (defaults to "Set A + Set B + ...")
- Drag-and-drop reorderable list of selected sets
- "Date ↑" / "Date ↓" sort buttons (by earliest story date)
- Generate / Cancel buttons

#### _do_generate(story_sets: list[dict], epub_name: str, output_path: str | None) -> str
Performs the actual EPUB generation in a background thread. Accepts one or more story sets.

**Multi-set behavior:**
- Fetches/parses stories preserving set grouping as `(set_name, [Story, ...])` tuples
- Passes groups to `epub_builder.create_epub()` for nested TOC (multi-set only)
- Single-set uses flat TOC as before
- If output file already exists, prompts with save-as dialog before starting

**Progress Updates:**
| Progress | Action |
|----------|--------|
| 0% | Start |
| 10% | Found stories |
| 10-85% | Fetching/parsing stories across all sets |
| 90% | Building EPUB |
| 100% | Complete |

---

## Threading Pattern

All long-running operations use this pattern:

```python
def _some_operation(self):
    self.generate_btn.config(state="disabled")
    self._set_status("Working...")

    def work():
        try:
            result = do_long_operation()
            self.root.after(0, lambda: self._handle_result(result))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(str(e)))

    threading.Thread(target=work, daemon=True).start()
```

**Key Points:**
- `daemon=True` - Thread exits when main thread exits
- `root.after(0, callback)` - Schedules callback on main thread
- Never update Tkinter widgets from background threads directly

## Entry Point

### run()

```python
def run():
    root = tk.Tk()

    # Try to set modern theme (optional)
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except Exception:
        pass  # Fall back to default

    app = MTGStoriesApp(root)
    root.mainloop()
```

## Maintenance Notes

### Adding new data sources:
1. Add fetch call in `_refresh_sets()` background thread
2. Add dedup step against existing slugs
3. Pass to `_merge_story_sets()`
4. Add source tag/color in `_update_sets_list()`

### Modifying the listbox display:
Update `_update_sets_list()` to change how items are formatted.

### Modifying the details panel:
Update `_show_info()` to change what info is displayed per story.

### Theming:
The app tries to load `azure.tcl` for a modern look. If not available, uses default Tkinter theme.
