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
- Triggering EPUB generation, stopping it, and reporting stories that could not be fetched
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
    self.generation_id = 0                # Bumped per run; stale callbacks are dropped
    self.cancel_event = threading.Event() # Set when the user presses Stop
    self.loading = False                  # True while the 3-source fetch is running

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
│  [      Generate EPUB / Open Link / Stop       ]    │
├─────────────────────────────────────────────────────┤
│  ████████████████░░░░░░░░░░░░░░░░  45%              │
│  Fetching story 3/7: Episode 3 (image 2/9)...       │
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

Empty search restores the full list. While a search is active the status reads "Showing N story sets"; the full list reads "Found N story sets". Searching during the initial fetch does not disturb the progress bar.

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
Starts the 3-source fetch in a background thread. Uses an indeterminate progress bar and progressive loading (listbox updates after each phase). The worker body is `_fetch_sources()`.

**Flow:**
```
Disable generate button, set loading = True
Start indeterminate progress bar (50ms interval)
Set status "Fetching..."
       │
       ▼
Background thread → _fetch_sources():
  ├── scraper.fetch_all_story_sets()        → contentful_sets
  │     └── _update_sets_list() ← progressive update
  ├── scraper.fetch_article_story_sets()    → raw_article_sets
  │     ├── Build article_metadata lookup (slug → author/excerpt)
  │     ├── Enrich contentful_sets stories with article metadata
  │     ├── filter_article_sets() against storyGroup slugs
  │     └── _update_sets_list() ← progressive update
  └── wiki_scraper.fetch_wiki_story_sets()  → raw_wiki_sets
        ├── filter_wiki_sets() against storyGroup + article keys
        └── _update_sets_list() ← final update
       │
       ▼
except: unexpected error → error dialog (never left stuck on "Fetching...")
finally: stop progress bar, reset to determinate mode, loading = False
```

Each source has its own `try/except`; a failed source is logged and skipped.

#### _merge_story_sets(contentful_sets, article_sets, wiki_sets)
Merges all three sources into a single dict by year.

Within a year, sets are sorted by the date of their **first** (earliest) story, newest first, matching the newest-first year headers. This puts single-story "Planeswalker's Guide" and "Legends of" articles next to the set they belong to. Sets with no dated stories go last, keeping source order (storyGroups, articles, wiki) among themselves. Ties keep source order too, so an official set comes before an article set that starts the same day.

Helpers: `_first_story_date(story_set)` and `_set_sort_key(story_set)` at module level.

#### _update_sets_list(sets_by_year, preserve_search=False)
Populates the listbox with story sets grouped by year.

Rebuilding the list clears the listbox selection, so this method also resets `selection_order`, clears the details panel and restores the "Generate EPUB" button label. Without that, stale indices would point at different rows after a search or a progressive update.

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
Main generation entry point. Handles single-select (direct generation or link opening) and multi-select (shows reorder dialog first). If the output file already exists, prompts with a save-as dialog before starting.

Starts a run: bumps `generation_id`, creates a fresh cancel event, turns the button into **Stop**, and launches the worker thread.

#### _show_generate_dialog(story_sets: list[dict]) -> tuple[str, list[dict]] | None
Modal dialog for multi-set EPUB generation. Returns `(title, ordered_story_sets)` or `None` if cancelled.

**Features:**
- Editable EPUB title (defaults to "Set A + Set B + ...")
- Drag-and-drop reorderable list of selected sets
- "Date ↑" / "Date ↓" sort buttons (by earliest story date)
- Generate / Cancel buttons

#### _do_generate(story_sets, epub_name, output_path, run_id, cancel) -> tuple[str, list[str]]
Performs the actual EPUB generation on the worker thread. Returns `(epub_path, failures)` where `failures` is a list of human-readable messages for stories left out of the book.

**Behaviour:**
- Creates the working folder `.mtg-stories-working-*` **inside the chosen output directory** and removes it in a `finally` block. The app never writes anywhere else (no system temp, no AppData, no log files)
- Fetches/parses stories preserving set grouping as `(set_name, [Story, ...])` tuples; passes groups to `epub_builder.create_epub()` for a nested TOC (multi-set only)
- Status shows per-image progress: "Fetching story 3/7: Title (image 2/9)..."
- A story that fails (404, site unreachable, parse error) is added to `failures` and the run continues
- `net.Offline` → raises `ConnectionLost`, the run aborts and no EPUB is written
- `net.Cancelled` → the run stops; if the EPUB had just been written it is deleted
- If every story fails, raises with the first few reasons

**Progress Updates:**
| Progress | Action |
|----------|--------|
| 0% | Start |
| 10% | Found stories |
| 10-85% | Fetching/parsing stories across all sets |
| 90% | Building EPUB |
| 100% | Complete |

#### _cancel_generate()
The Stop button. Sets the cancel event, bumps `generation_id`, and resets the UI immediately via `_generation_cancelled()`. It does not wait for the worker.

#### _post(run_id, fn)
Schedules `fn` on the main thread, but only runs it if `run_id` is still the current run. All worker-to-UI calls during generation go through this, which is what makes Stop instant: an abandoned worker's status updates and completion dialog are silently dropped.

#### Outcome handlers
| Handler | When | Result |
|---------|------|--------|
| `_generation_complete(path, failures)` | EPUB written | "Success" dialog, or "Completed with missing stories" listing up to 10 failures |
| `_generation_cancelled()` | Stop pressed | Status "Generation stopped. No EPUB was written." |
| `_generation_aborted(message)` | Internet lost | "Lost internet connection" warning naming the story being fetched |
| `_show_error(message)` | Anything else | Error dialog |

All four restore the Generate button through `_reset_generate_button()`.

---

## Threading Pattern

Workers are daemon threads and never touch widgets directly.

```python
def generate():
    try:
        path, failures = self._do_generate(sets, name, output_path, run_id, cancel)
        self._post(run_id, lambda: self._generation_complete(path, failures))
    except net.Cancelled:
        self._post(run_id, self._generation_cancelled)
    except ConnectionLost as e:
        message = str(e)
        self._post(run_id, lambda: self._generation_aborted(message))
    except Exception as e:
        message = f"Generation failed: {e}"
        self._post(run_id, lambda: self._show_error(message))

threading.Thread(target=generate, daemon=True).start()
```

**Key Points:**
- `daemon=True` - Thread exits when main thread exits
- `root.after(0, callback)` / `_post(run_id, callback)` - Schedules callback on main thread
- Never update Tkinter widgets from background threads directly
- Capture the exception text in a local before building the lambda. Python unbinds the `except ... as e` name when the block ends, and the lambda runs later (`NameError: free variable 'e' referenced before assignment`)
- Pass the `cancel` event to every network call made during generation

## Entry Point

### run()

```python
def run():
    setup_logging()                      # stderr only, never a file
    root = tk.Tk()
    icon = _icon_path()                  # assets/icon.ico, source checkout or PyInstaller bundle
    if icon:
        root.iconbitmap(icon)
    app = MTGStoriesApp(root)

    def on_close():
        app.cancel_event.set()           # stop any running generation
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    finally:
        cleanup_temp_dirs()              # remove the working folder of a run that was mid-download
```

Working folders of runs in progress are tracked in `_active_temp_dirs`. `cleanup_temp_dirs()` runs on window close and again via `atexit`, because closing the window kills the daemon worker before its own `finally` can run.

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

### Icon:
`assets/icon.ico` is embedded in the exe (`icon=` in `mtg_stories.spec`), bundled as data, and set as the window icon in `run()`. To change it, replace that file and rebuild.

### Adding network calls to generation:
Use `net.get(..., cancel=cancel)` and let `net.Cancelled` / `net.Offline` propagate. Do not call `requests` directly and do not use `time.sleep`; use `net.wait(seconds, cancel)`.
