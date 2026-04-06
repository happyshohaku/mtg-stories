"""
Tkinter GUI for the MTG Stories to EPUB converter.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from . import scraper, parser, epub_builder, wiki_scraper


class MTGStoriesApp:
    """Main application window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MTG Stories to EPUB")
        self.root.geometry("600x650")
        self.root.minsize(500, 550)

        # Data
        self.story_sets_by_year: dict[int, list[dict]] = {}
        self.listbox_items: list[dict | None] = []  # None for year headers
        self.output_dir = os.path.join(os.path.expanduser("~"), "Documents", "MTG-Stories")
        self.selection_order: list[int] = []  # Track click order for multi-select

        # Build UI
        self._create_widgets()

        # Initial load
        self.root.after(100, self._refresh_sets)

    def _create_widgets(self):
        """Create all UI widgets."""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(0, weight=1)

        ttk.Label(
            header_frame,
            text="MTG Stories to EPUB",
            font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, sticky="w")

        # Story sets list
        list_frame = ttk.LabelFrame(main_frame, text="Story Sets (by Year)", padding="5")
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)

        # Search bar
        search_frame = ttk.Frame(list_frame)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Search:").grid(row=0, column=0, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")

        # Listbox with scrollbar
        list_container = ttk.Frame(list_frame)
        list_container.grid(row=1, column=0, sticky="nsew")
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            font=("Segoe UI", 10),
            activestyle="dotbox"
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.config(yscrollcommand=scrollbar.set)

        # Refresh button
        ttk.Button(
            list_frame,
            text="Refresh Sets",
            command=self._refresh_sets
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))

        # Info panel — shows details when a story set is selected
        info_frame = ttk.LabelFrame(main_frame, text="Details", padding="5")
        info_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)

        self.info_text = tk.Text(
            info_frame,
            height=6,
            wrap="word",
            font=("Segoe UI", 9),
            state="disabled",
            relief="flat",
            bg=main_frame.winfo_toplevel().cget("bg"),
        )
        self.info_text.grid(row=0, column=0, sticky="nsew")

        # Output directory
        output_frame = ttk.LabelFrame(main_frame, text="Output Directory", padding="5")
        output_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        output_frame.columnconfigure(0, weight=1)

        self.output_var = tk.StringVar(value=self.output_dir)
        output_entry = ttk.Entry(output_frame, textvariable=self.output_var, state="readonly")
        output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ttk.Button(
            output_frame,
            text="Browse...",
            command=self._browse_output
        ).grid(row=0, column=1)

        # Generate button
        self.generate_btn = ttk.Button(
            main_frame,
            text="Generate EPUB",
            command=self._generate_epub,
            style="Accent.TButton"
        )
        self.generate_btn.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        # Progress
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.grid(row=5, column=0, sticky="ew", pady=(0, 5))

        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9)
        )
        self.status_label.grid(row=6, column=0, sticky="w")

    def _on_search(self, *args):
        """Filter the story sets list based on search text."""
        query = self.search_var.get().strip().lower()
        if not query:
            self._update_sets_list(self.story_sets_by_year)
            return

        filtered: dict[int, list[dict]] = {}
        for year, sets in self.story_sets_by_year.items():
            matching_sets = []
            for story_set in sets:
                name = story_set.get("name", "").lower()
                # Match against set name or individual story titles
                if query in name:
                    matching_sets.append(story_set)
                else:
                    for story in story_set.get("stories", []):
                        if query in story.get("title", "").lower():
                            matching_sets.append(story_set)
                            break
            if matching_sets:
                filtered[year] = matching_sets

        self._update_sets_list(filtered, preserve_search=True)

    def _on_select(self, event):
        """Handle listbox selection - prevent selecting year headers."""
        selection = set(self.listbox.curselection())
        if not selection:
            self.selection_order = []
            self._clear_info()
            self.generate_btn.config(text="Generate EPUB")
            return

        # Deselect any year headers
        for index in list(selection):
            if index < len(self.listbox_items) and self.listbox_items[index] is None:
                self.listbox.selection_clear(index)
                selection.discard(index)

        # Update click order: remove deselected, append newly selected
        self.selection_order = [i for i in self.selection_order if i in selection]
        for index in selection:
            if index not in self.selection_order:
                self.selection_order.append(index)

        # Get valid selected sets in click order
        selected = self._get_selected_story_sets()
        if not selected:
            self._clear_info()
            self.generate_btn.config(text="Generate EPUB")
            return

        if len(selected) == 1:
            item = selected[0]
            stories = item.get("stories", [])
            external_links = item.get("external_links", [])
            if not stories and external_links:
                self.generate_btn.config(text="Open Link")
            else:
                self.generate_btn.config(text="Generate EPUB")
            self._show_info(item)
        else:
            self.generate_btn.config(text="Generate EPUB")
            self._show_multi_info(selected)

    def _clear_info(self):
        """Clear the info panel."""
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", tk.END)
        self.info_text.config(state="disabled")

    def _show_info(self, story_set: dict):
        """Show details about the selected story set in the info panel."""
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", tk.END)

        # Configure text tags for styling
        # lmargin1 = first line indent, lmargin2 = wrapped line indent
        indent = 20  # pixels
        self.info_text.tag_configure("bold", font=("Segoe UI", 9, "bold"))
        self.info_text.tag_configure("story", font=("Segoe UI", 9),
                                     lmargin1=indent, lmargin2=indent)
        self.info_text.tag_configure("excerpt", font=("Segoe UI", 8, "italic"),
                                     foreground="#555555",
                                     lmargin1=indent, lmargin2=indent)

        name = story_set.get("name", "Unknown")
        stories = story_set.get("stories", [])
        source = story_set.get("source", "official")

        self.info_text.insert(tk.END, f"{name}", "bold")
        self.info_text.insert(tk.END, f"  ({source})\n")

        for story in stories:
            title = story.get("title", "Unknown")
            author = story.get("author", "")
            date = story.get("published_date")
            excerpt = story.get("excerpt", "")

            # Story title line
            date_str = date.strftime("%Y-%m-%d") if date else ""
            parts = [title]
            if author:
                parts.append(f"by {author}")
            if date_str:
                parts.append(f"({date_str})")
            self.info_text.insert(tk.END, " — ".join(parts) + "\n", "story")

        self.info_text.config(state="disabled")

    def _show_multi_info(self, story_sets: list[dict]):
        """Show combined summary when multiple story sets are selected."""
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", tk.END)

        indent = 20
        self.info_text.tag_configure("bold", font=("Segoe UI", 9, "bold"))
        self.info_text.tag_configure("story", font=("Segoe UI", 9),
                                     lmargin1=indent, lmargin2=indent)

        total_stories = sum(len(s.get("stories", [])) for s in story_sets)
        self.info_text.insert(tk.END, f"{len(story_sets)} sets selected", "bold")
        self.info_text.insert(tk.END, f"  ({total_stories} stories total)\n")

        for story_set in story_sets:
            name = story_set.get("name", "Unknown")
            count = len(story_set.get("stories", []))
            source = story_set.get("source", "official")
            self.info_text.insert(tk.END, f"{name} ({count} stories, {source})\n", "story")

        self.info_text.config(state="disabled")

    def _set_status(self, message: str):
        """Update the status message."""
        self.status_var.set(message)
        self.root.update_idletasks()

    def _set_progress(self, value: float):
        """Update the progress bar (0-100)."""
        self.progress_var.set(value)
        self.root.update_idletasks()

    def _refresh_sets(self):
        """Fetch story sets from Contentful storyGroups, articles, and mtg.wiki."""
        self._set_status("Fetching story sets...")
        self.generate_btn.config(state="disabled")
        self.progress_var.set(0)
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(50)

        def fetch():
            try:
                contentful_sets = {}
                article_sets = {}
                wiki_sets = {}

                # Fetch from Contentful API — storyGroups (official curated sets)
                try:
                    self.root.after(0, lambda: self._set_status("Fetching story groups..."))
                    contentful_sets = scraper.fetch_all_story_sets()
                except Exception as e:
                    print(f"Failed to fetch Contentful story sets: {e}")

                # Fetch from Contentful API — individual articles
                try:
                    self.root.after(0, lambda: self._set_status("Fetching article archive..."))
                    raw_article_sets = scraper.fetch_article_story_sets()

                    # Build slug->metadata lookup from raw articles (before dedup)
                    # to enrich storyGroup stories with excerpts and authors
                    article_metadata = {}
                    for year_sets in raw_article_sets.values():
                        for story_set in year_sets:
                            for story in story_set.get("stories", []):
                                slug = story.get("slug", "").lower().strip()
                                if slug:
                                    article_metadata[slug] = {
                                        "author": story.get("author"),
                                        "excerpt": story.get("excerpt"),
                                    }

                    # Enrich storyGroup stories with article metadata
                    for year_sets in contentful_sets.values():
                        for story_set in year_sets:
                            for story in story_set.get("stories", []):
                                slug = story.get("slug", "").lower().strip()
                                if slug and slug in article_metadata:
                                    meta = article_metadata[slug]
                                    if meta.get("author") and not story.get("author"):
                                        story["author"] = meta["author"]
                                    if meta.get("excerpt") and not story.get("excerpt"):
                                        story["excerpt"] = meta["excerpt"]

                    # Deduplicate: remove articles already in storyGroups
                    if contentful_sets:
                        sg_slugs = scraper.get_storygroup_slugs(contentful_sets)
                        article_sets = scraper.filter_article_sets(raw_article_sets, sg_slugs)
                    else:
                        article_sets = raw_article_sets
                except Exception as e:
                    print(f"Failed to fetch article story sets: {e}")

                # Fetch from mtg.wiki
                try:
                    self.root.after(0, lambda: self._set_status("Fetching archive stories from mtg.wiki..."))
                    raw_wiki_sets = wiki_scraper.fetch_wiki_story_sets()

                    # Deduplicate: remove wiki stories already in storyGroups or articles
                    known_slugs = set()
                    if contentful_sets:
                        known_slugs |= wiki_scraper.get_contentful_slugs(contentful_sets)
                    if article_sets:
                        known_slugs |= scraper.get_article_slugs(article_sets)
                    if known_slugs:
                        wiki_sets = wiki_scraper.filter_wiki_sets(raw_wiki_sets, known_slugs)
                    else:
                        wiki_sets = raw_wiki_sets
                except Exception as e:
                    print(f"Failed to fetch wiki story sets: {e}")

                # Merge all three sources
                merged = self._merge_story_sets(contentful_sets, article_sets, wiki_sets)
                self.root.after(0, lambda: self._update_sets_list(merged))
            finally:
                def _stop_progress():
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.progress_var.set(0)
                self.root.after(0, _stop_progress)

        threading.Thread(target=fetch, daemon=True).start()

    def _merge_story_sets(
        self,
        contentful_sets: dict[int, list[dict]],
        article_sets: dict[int, list[dict]],
        wiki_sets: dict[int, list[dict]],
    ) -> dict[int, list[dict]]:
        """
        Merge all three sources into a single dict by year.
        Order per year: storyGroups first, then articles, then wiki.
        """
        all_years = set(contentful_sets.keys()) | set(article_sets.keys()) | set(wiki_sets.keys())
        merged: dict[int, list[dict]] = {}

        for year in all_years:
            year_sets = []
            year_sets.extend(contentful_sets.get(year, []))
            year_sets.extend(article_sets.get(year, []))
            year_sets.extend(wiki_sets.get(year, []))
            if year_sets:
                merged[year] = year_sets

        return merged

    def _update_sets_list(self, sets_by_year: dict[int, list[dict]], preserve_search: bool = False):
        """Update the listbox with fetched story sets grouped by year."""
        if not preserve_search:
            self.story_sets_by_year = sets_by_year
        self.listbox.delete(0, tk.END)
        self.listbox_items = []

        total_sets = 0

        # Sort years descending (newest first)
        for year in sorted(sets_by_year.keys(), reverse=True):
            story_sets = sets_by_year[year]
            if not story_sets:
                continue

            # Add year header
            if year == -1:
                year_label = "Other"
            elif year == 0:
                year_label = "Unknown Year"
            else:
                year_label = str(year)
            header = f"──── {year_label} ────"
            self.listbox.insert(tk.END, header)
            self.listbox_items.append(None)  # None indicates a header

            # Style the header (make it look different)
            idx = self.listbox.size() - 1
            self.listbox.itemconfig(idx, fg="#666666", selectbackground="#ffffff", selectforeground="#666666")

            # Add story sets under this year
            for story_set in story_sets:
                name = story_set.get("name", "Unknown")
                story_count = len(story_set.get("stories", []))
                external_links = story_set.get("external_links", [])
                source = story_set.get("source", "")
                is_wiki = source == "wiki"
                is_articles = source == "articles"

                # Build display text — show source for non-storyGroup sets
                if is_wiki:
                    source_tag = " [mtg.wiki]"
                elif is_articles:
                    source_tag = " [articles]"
                else:
                    source_tag = ""
                if story_count > 0 and external_links:
                    display = f"  {name} ({story_count} stories, {len(external_links)} e-book){source_tag}"
                elif story_count > 0:
                    display = f"  {name} ({story_count} stories){source_tag}"
                elif external_links:
                    display = f"  {name} (e-book only)"
                else:
                    display = f"  {name} (no content)"

                self.listbox.insert(tk.END, display)
                self.listbox_items.append(story_set)

                idx = self.listbox.size() - 1
                # Gray out e-book only entries
                if story_count == 0:
                    self.listbox.itemconfig(idx, fg="#999999")
                # Give wiki/archive entries a distinct color
                elif is_wiki:
                    self.listbox.itemconfig(idx, fg="#8B4513")  # Saddle brown
                elif is_articles:
                    self.listbox.itemconfig(idx, fg="#1E6F8C")  # Teal

                total_sets += 1

        # Count sets by source
        wiki_count = sum(
            1 for items in sets_by_year.values()
            for s in items if s.get("source") == "wiki"
        )
        article_count = sum(
            1 for items in sets_by_year.values()
            for s in items if s.get("source") == "articles"
        )
        official_count = total_sets - wiki_count - article_count

        self.generate_btn.config(state="normal")
        parts = [f"{official_count} official"]
        if article_count > 0:
            parts.append(f"{article_count} from articles")
        if wiki_count > 0:
            parts.append(f"{wiki_count} from archive")
        self._set_status(f"Found {total_sets} story sets ({', '.join(parts)})")
        self._set_progress(0)

    def _browse_output(self):
        """Open a folder browser for output directory."""
        path = filedialog.askdirectory(
            initialdir=self.output_dir,
            title="Select Output Directory"
        )
        if path:
            self.output_dir = path
            self.output_var.set(path)

    def _get_selected_story_sets(self) -> list[dict]:
        """Get all currently selected story sets in click order, filtering out year headers."""
        sets = []
        for index in self.selection_order:
            if index < len(self.listbox_items):
                item = self.listbox_items[index]
                if item is not None:
                    sets.append(item)
        return sets

    def _show_generate_dialog(self, story_sets: list[dict]) -> tuple[str, list[dict]] | None:
        """Show a dialog to configure EPUB title and drag-and-drop reorder sets.
        Returns (title, ordered_story_sets) or None if cancelled."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Generate Combined EPUB")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.minsize(400, 300)

        frame = ttk.Frame(dialog, padding="15")
        frame.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        # Title
        ttk.Label(frame, text="EPUB Title:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        auto_name = " + ".join(s.get("name", "Unknown") for s in story_sets)
        title_var = tk.StringVar(value=auto_name)
        title_entry = ttk.Entry(frame, textvariable=title_var)
        title_entry.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        title_entry.select_range(0, tk.END)
        title_entry.focus_set()

        # Set order label + sort buttons
        order_header = ttk.Frame(frame)
        order_header.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(order_header, text="Set Order (drag to reorder):",
                  font=("Segoe UI", 9, "bold")).pack(side="left")

        def _get_earliest_date(s):
            """Get earliest story date for sorting."""
            dates = [st.get("published_date") for st in s.get("stories", [])
                     if st.get("published_date")]
            return min(dates) if dates else parser.datetime.min

        def sort_sets(reverse=False):
            ordered_sets.sort(key=_get_earliest_date, reverse=reverse)
            _refresh_drag_list()

        ttk.Button(order_header, text="Date \u2193", width=7,
                   command=lambda: sort_sets(reverse=True)).pack(side="right", padx=(5, 0))
        ttk.Button(order_header, text="Date \u2191", width=7,
                   command=lambda: sort_sets(reverse=False)).pack(side="right")

        # Drag-and-drop listbox
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 15))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        drag_list = tk.Listbox(list_frame, font=("Segoe UI", 10), activestyle="none",
                               selectmode=tk.SINGLE)
        drag_list.grid(row=0, column=0, sticky="nsew")
        drag_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=drag_list.yview)
        drag_scrollbar.grid(row=0, column=1, sticky="ns")
        drag_list.config(yscrollcommand=drag_scrollbar.set)

        # Backing data — mutable list in dialog scope
        ordered_sets = list(story_sets)

        def _refresh_drag_list():
            drag_list.delete(0, tk.END)
            for s in ordered_sets:
                count = len(s.get("stories", []))
                label = "story" if count == 1 else "stories"
                drag_list.insert(tk.END, f"  {s.get('name', 'Unknown')} ({count} {label})")

        _refresh_drag_list()

        # Drag-and-drop state
        drag_data = {"index": None}

        def drag_start(event):
            index = drag_list.nearest(event.y)
            if index >= 0:
                drag_data["index"] = index
                drag_list.selection_clear(0, tk.END)
                drag_list.selection_set(index)

        def drag_motion(event):
            if drag_data["index"] is None:
                return
            target = drag_list.nearest(event.y)
            current = drag_data["index"]
            if target != current and 0 <= target < len(ordered_sets):
                # Swap in backing list
                ordered_sets[current], ordered_sets[target] = ordered_sets[target], ordered_sets[current]
                # Update display
                text_current = drag_list.get(current)
                text_target = drag_list.get(target)
                drag_list.delete(current)
                drag_list.insert(current, text_target)
                drag_list.delete(target)
                drag_list.insert(target, text_current)
                # Update drag state
                drag_data["index"] = target
                drag_list.selection_clear(0, tk.END)
                drag_list.selection_set(target)

        def drag_end(event):
            drag_data["index"] = None

        drag_list.bind("<Button-1>", drag_start)
        drag_list.bind("<B1-Motion>", drag_motion)
        drag_list.bind("<ButtonRelease-1>", drag_end)

        # Result holder
        result = [None]

        def on_ok():
            title = title_var.get().strip()
            if title:
                result[0] = (title, list(ordered_sets))
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, sticky="e")
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).grid(row=0, column=0)
        ttk.Button(btn_frame, text="Generate", command=on_ok).grid(row=0, column=1, padx=(5, 0))

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_window()
        return result[0]

    def _generate_epub(self):
        """Generate EPUB for the selected story set(s)."""
        import webbrowser

        selected = self._get_selected_story_sets()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a story set first (not a year header).")
            return

        # Single selection: check for e-book only, then generate directly
        if len(selected) == 1:
            story_set = selected[0]
            stories = story_set.get("stories", [])
            external_links = story_set.get("external_links", [])

            if not stories and external_links:
                link = external_links[0]
                self._set_status(f"Opening e-book link: {link['title']}")
                webbrowser.open(link["url"])
                return

            epub_name = story_set["name"]
            ordered_sets = selected
        else:
            # Multi-select: show dialog for title and set order
            result = self._show_generate_dialog(selected)
            if result is None:
                return  # Cancelled
            epub_name, ordered_sets = result

        # Check if file already exists — prompt to overwrite or rename
        safe_filename = "".join(c if c.isalnum() or c in " -_" else "_" for c in epub_name)
        expected_path = os.path.join(self.output_dir, f"{safe_filename}.epub")
        output_path = None

        if os.path.exists(expected_path):
            output_path = filedialog.asksaveasfilename(
                initialdir=self.output_dir,
                initialfile=f"{safe_filename}.epub",
                title="File already exists — save as",
                filetypes=[("EPUB files", "*.epub")],
                defaultextension=".epub",
            )
            if not output_path:
                return  # Cancelled

        self.generate_btn.config(state="disabled")
        self._set_status(f"Generating EPUB for {epub_name}...")
        self._set_progress(0)

        def generate():
            try:
                result = self._do_generate(ordered_sets, epub_name, output_path)
                self.root.after(0, lambda: self._generation_complete(result))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(f"Generation failed: {e}"))

        threading.Thread(target=generate, daemon=True).start()

    def _do_generate(self, story_sets: list[dict], epub_name: str, output_path: str | None = None) -> str:
        """Perform the actual EPUB generation for one or more story sets."""
        # Count total stories across all sets
        total_stories = sum(len(s.get("stories", [])) for s in story_sets)
        if total_stories == 0:
            raise Exception(f"No stories found for {epub_name}")

        self._update_status(f"Found {total_stories} stories")
        self._update_progress(10)

        # Fetch and parse stories, preserving set grouping
        groups: list[tuple[str, list]] = []  # (set_name, [Story, ...])
        temp_dir = os.path.join(self.output_dir, ".temp_images")
        os.makedirs(temp_dir, exist_ok=True)

        story_num = 0
        for story_set in story_sets:
            set_name = story_set.get("name", "Unknown")
            parsed_in_group = []

            for info in story_set.get("stories", []):
                story_num += 1
                progress = 10 + (70 * (story_num / total_stories))
                title = info.get("title", "Unknown")[:40]
                self._update_status(f"Fetching story {story_num}/{total_stories}: {title}...")
                self._update_progress(progress)

                try:
                    html = scraper.fetch_story_page(info["url"])

                    story = parser.parse_story(
                        html,
                        info["url"],
                        fallback_author=info.get("author"),
                        fallback_date=info.get("published_date"),
                        fallback_title=info.get("title"),
                    )

                    if info.get("published_date"):
                        story.publication_date = info["published_date"]

                    if story.images:
                        parser.download_images(story.images, temp_dir)

                    parsed_in_group.append(story)
                except Exception as e:
                    print(f"Failed to fetch story {info['url']}: {e}")
                    continue

            if parsed_in_group:
                groups.append((set_name, parsed_in_group))

        all_stories = [story for _, stories in groups for story in stories]
        if not all_stories:
            raise Exception("Failed to fetch any stories")

        self._update_progress(85)

        # Find cover image — use first set with an image_url
        cover_path = None
        for story_set in story_sets:
            if story_set.get("image_url"):
                self._update_status("Downloading cover image...")
                cover_path = parser.download_image(story_set["image_url"], temp_dir)
                if cover_path:
                    break

        if not cover_path:
            for story in all_stories:
                for img in story.images:
                    if img.get("local_path"):
                        cover_path = img["local_path"]
                        break
                if cover_path:
                    break

        # Generate EPUB
        self._update_status("Building EPUB...")
        self._update_progress(90)

        # Use grouped TOC for multi-set, flat for single-set
        use_groups = groups if len(story_sets) > 1 else None

        final_path = epub_builder.create_epub(
            stories=all_stories,
            set_name=epub_name,
            output_dir=self.output_dir,
            cover_image_path=cover_path,
            groups=use_groups,
            output_path=output_path,
        )

        # Clean up temp images folder
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        self._update_progress(100)
        return final_path

    def _update_status(self, message: str):
        """Thread-safe status update."""
        self.root.after(0, lambda: self._set_status(message))

    def _update_progress(self, value: float):
        """Thread-safe progress update."""
        self.root.after(0, lambda: self._set_progress(value))

    def _generation_complete(self, output_path: str):
        """Handle successful EPUB generation."""
        self.generate_btn.config(state="normal")
        self._set_status(f"EPUB saved: {os.path.basename(output_path)}")

        result = messagebox.askquestion(
            "Success",
            f"EPUB created successfully!\n\n{output_path}\n\nOpen output folder?",
            icon="info"
        )
        if result == "yes":
            os.startfile(os.path.dirname(output_path))

    def _show_error(self, message: str):
        """Show an error message."""
        self.generate_btn.config(state="normal")
        self._set_status("Error")
        self._set_progress(0)
        messagebox.showerror("Error", message)


def run():
    """Run the application."""
    root = tk.Tk()

    # Try to set a modern theme
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except Exception:
        pass  # Fall back to default theme

    app = MTGStoriesApp(root)
    root.mainloop()
