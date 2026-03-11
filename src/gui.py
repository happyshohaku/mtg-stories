"""
Tkinter GUI for the MTG Stories to EPUB converter.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
            selectmode=tk.SINGLE,
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
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index < len(self.listbox_items):
            item = self.listbox_items[index]
            if item is None:
                # This is a year header, deselect it
                self.listbox.selection_clear(0, tk.END)
                self.generate_btn.config(text="Generate EPUB")
                self._clear_info()
            else:
                # Update button text based on whether it's e-book only
                stories = item.get("stories", [])
                external_links = item.get("external_links", [])
                if not stories and external_links:
                    self.generate_btn.config(text="Open Link")
                else:
                    self.generate_btn.config(text="Generate EPUB")
                self._show_info(item)

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

        def fetch():
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

    def _get_selected_story_set(self) -> dict | None:
        """Get the currently selected story set, or None if a header is selected."""
        selection = self.listbox.curselection()
        if not selection:
            return None

        index = selection[0]
        if index < len(self.listbox_items):
            return self.listbox_items[index]
        return None

    def _generate_epub(self):
        """Generate EPUB for the selected story set."""
        import webbrowser

        story_set = self._get_selected_story_set()
        if not story_set:
            messagebox.showwarning("No Selection", "Please select a story set first (not a year header).")
            return

        # Check if this is an e-book only entry
        stories = story_set.get("stories", [])
        external_links = story_set.get("external_links", [])

        if not stories and external_links:
            # Open external link in browser
            link = external_links[0]
            self._set_status(f"Opening e-book link: {link['title']}")
            webbrowser.open(link["url"])
            return

        self.generate_btn.config(state="disabled")
        self._set_status(f"Generating EPUB for {story_set['name']}...")
        self._set_progress(0)

        def generate():
            try:
                result = self._do_generate(story_set)
                self.root.after(0, lambda: self._generation_complete(result))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(f"Generation failed: {e}"))

        threading.Thread(target=generate, daemon=True).start()

    def _do_generate(self, story_set: dict) -> str:
        """Perform the actual EPUB generation."""
        set_name = story_set["name"]
        stories_info = story_set.get("stories", [])

        if not stories_info:
            raise Exception(f"No stories found for {set_name}")

        total_stories = len(stories_info)
        self._update_status(f"Found {total_stories} stories")
        self._update_progress(10)

        # Fetch and parse each story
        parsed_stories = []
        temp_dir = os.path.join(self.output_dir, ".temp_images")
        os.makedirs(temp_dir, exist_ok=True)

        for i, info in enumerate(stories_info):
            progress = 10 + (70 * (i / total_stories))
            title = info.get("title", "Unknown")[:40]
            self._update_status(f"Fetching story {i+1}/{total_stories}: {title}...")
            self._update_progress(progress)

            try:
                html = scraper.fetch_story_page(info["url"])

                # For wiki-sourced stories, pass fallback metadata
                # (author and date from wiki catalog, in case page parsing fails)
                story = parser.parse_story(
                    html,
                    info["url"],
                    fallback_author=info.get("author"),
                    fallback_date=info.get("published_date"),
                    fallback_title=info.get("title"),
                )

                # Override publication date from API/wiki if available
                if info.get("published_date"):
                    story.publication_date = info["published_date"]

                # Download images
                if story.images:
                    parser.download_images(story.images, temp_dir)

                parsed_stories.append(story)
            except Exception as e:
                print(f"Failed to fetch story {info['url']}: {e}")
                continue

        if not parsed_stories:
            raise Exception("Failed to fetch any stories")

        # Sort by publication date
        self._update_status("Sorting stories by date...")
        self._update_progress(85)

        parsed_stories.sort(key=lambda s: s.publication_date or parser.datetime.min)

        # Find cover image
        cover_path = None
        if story_set.get("image_url"):
            self._update_status("Downloading cover image...")
            cover_path = parser.download_image(story_set["image_url"], temp_dir)

        # If no cover from set, use first story image
        if not cover_path:
            for story in parsed_stories:
                for img in story.images:
                    if img.get("local_path"):
                        cover_path = img["local_path"]
                        break
                if cover_path:
                    break

        # Generate EPUB
        self._update_status("Building EPUB...")
        self._update_progress(90)

        output_path = epub_builder.create_epub(
            stories=parsed_stories,
            set_name=set_name,
            output_dir=self.output_dir,
            cover_image_path=cover_path
        )

        # Clean up temp images folder
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        self._update_progress(100)
        return output_path

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
