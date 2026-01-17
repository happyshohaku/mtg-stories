# GUI Module Documentation

## File: `src/gui.py`

## Purpose

The GUI module provides a Tkinter-based graphical interface for:
- Browsing available story sets
- Selecting output directory
- Triggering EPUB generation
- Displaying progress and status

## Class: MTGStoriesApp

### Initialization

```python
def __init__(self, root: tk.Tk):
    self.root = root
    self.root.title("MTG Stories to EPUB")
    self.root.geometry("600x550")
    self.root.minsize(500, 450)

    # Data
    self.story_sets_by_year: dict[int, list[dict]] = {}
    self.listbox_items: list[dict | None] = []  # None for year headers
    self.output_dir = os.path.join(os.path.expanduser("~"), "Documents", "MTG-Stories")

    self._create_widgets()
    self.root.after(100, self._refresh_sets)  # Auto-fetch on startup
```

### Window Layout

```
┌─────────────────────────────────────────────────────┐
│  MTG Stories to EPUB                    (Header)    │
├─────────────────────────────────────────────────────┤
│  Story Sets (by Year)                               │
│  ┌───────────────────────────────────────────────┐  │
│  │ ──── 2025 ────                                │  │
│  │   Edge of Eternities (5 stories)              │  │
│  │   Lorwyn Eclipsed (4 stories)                │  │
│  │ ──── 2024 ────                                │  │
│  │   Outlaws of Thunder Junction (6 stories)    │  │
│  │   ...                                        │▼ │
│  └───────────────────────────────────────────────┘  │
│  [Refresh Sets]                                     │
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
    │   └── Label "MTG Stories to EPUB"
    ├── list_frame (LabelFrame "Story Sets")
    │   ├── list_container (Frame)
    │   │   ├── listbox (Listbox)
    │   │   └── scrollbar (Scrollbar)
    │   └── Button "Refresh Sets"
    ├── output_frame (LabelFrame "Output Directory")
    │   ├── Entry (readonly, shows path)
    │   └── Button "Browse..."
    ├── generate_btn (Button "Generate EPUB")
    ├── progress_bar (Progressbar)
    └── status_label (Label)
```

## Methods

### UI Update Methods

#### _set_status(message: str)
Updates the status label text. Calls `root.update_idletasks()` to refresh immediately.

#### _set_progress(value: float)
Updates the progress bar (0-100 scale). Calls `root.update_idletasks()`.

#### _update_status(message: str) / _update_progress(value: float)
Thread-safe versions using `root.after(0, callback)`.

---

### Data Methods

#### _refresh_sets()
Fetches story sets from the website in a background thread.

**Flow:**
```
Disable generate button
Set status "Fetching..."
       │
       ▼
Background thread:
  └── scraper.fetch_all_story_sets()
       │
       ▼
Main thread (via root.after):
  └── _update_sets_list(sets)
```

#### _update_sets_list(sets_by_year: dict)
Populates the listbox with story sets grouped by year.

**Display Format:**
```
──── 2025 ────                    (Year header, not selectable)
  Edge of Eternities (5 stories)  (Selectable story set)
  Set Name (e-book only)          (Grayed out, opens link)
```

**Listbox Items Tracking:**
```python
self.listbox_items: list[dict | None]
# None = year header (not selectable)
# dict = story set (selectable)
```

#### _get_selected_story_set() -> dict | None
Returns the currently selected story set, or None if a header is selected.

---

### Event Handlers

#### _on_select(event)
Handles listbox selection changes.

**Behavior:**
- If year header selected → deselect it
- If story set with stories → button shows "Generate EPUB"
- If e-book only entry → button shows "Open Link"

```python
def _on_select(self, event):
    selection = self.listbox.curselection()
    if not selection:
        return

    index = selection[0]
    item = self.listbox_items[index]

    if item is None:
        # Year header - deselect
        self.listbox.selection_clear(0, tk.END)
    else:
        stories = item.get("stories", [])
        external_links = item.get("external_links", [])
        if not stories and external_links:
            self.generate_btn.config(text="Open Link")
        else:
            self.generate_btn.config(text="Generate EPUB")
```

#### _browse_output()
Opens a folder browser dialog and updates the output directory.

---

### Generation Methods

#### _generate_epub()
Main generation entry point. Handles both EPUB generation and external link opening.

**E-book Only Handling:**
```python
if not stories and external_links:
    link = external_links[0]
    self._set_status(f"Opening e-book link: {link['title']}")
    webbrowser.open(link["url"])
    return
```

**EPUB Generation:**
Runs `_do_generate()` in a background thread.

#### _do_generate(story_set: dict) -> str
Performs the actual EPUB generation.

**Progress Updates:**
| Progress | Action |
|----------|--------|
| 0% | Start |
| 10% | Found stories |
| 10-80% | Fetching/parsing stories |
| 85% | Sorting stories |
| 90% | Building EPUB |
| 100% | Complete |

**Steps:**
1. Get story URLs from story set
2. For each story:
   - Fetch HTML page
   - Parse content
   - Download images
3. Sort stories by publication date
4. Download cover image (if available)
5. Build EPUB file
6. Clean up temp images folder

#### _generation_complete(output_path: str)
Shows success message and offers to open output folder.

#### _show_error(message: str)
Shows error dialog and resets UI state.

---

## Threading Pattern

All long-running operations use this pattern:

```python
def _some_operation(self):
    # Disable UI, show status
    self.generate_btn.config(state="disabled")
    self._set_status("Working...")

    def work():
        try:
            result = do_long_operation()
            # Update UI on main thread
            self.root.after(0, lambda: self._handle_result(result))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(str(e)))

    # Run in background
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

### Adding new UI elements:
1. Add widget in `_create_widgets()`
2. Configure grid placement
3. Add event handler if interactive

### Modifying the listbox display:
Update `_update_sets_list()` to change how items are formatted.

### Adding new generation options:
1. Add UI controls in `_create_widgets()`
2. Pass values to `_do_generate()`
3. Update `epub_builder.create_epub()` if needed

### Theming:
The app tries to load `azure.tcl` for a modern look. If not available, uses default Tkinter theme. To add a theme:
1. Download theme TCL file
2. Place in project root
3. Update the `root.tk.call("source", ...)` line
