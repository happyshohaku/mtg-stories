"""
Tkinter GUI for the MTG Stories to EPUB converter.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import scraper, parser, epub_builder


class MTGStoriesApp:
    """Main application window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MTG Stories to EPUB")
        self.root.geometry("600x550")
        self.root.minsize(500, 450)

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
        list_frame.rowconfigure(0, weight=1)

        # Listbox with scrollbar
        list_container = ttk.Frame(list_frame)
        list_container.grid(row=0, column=0, sticky="nsew")
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
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        # Output directory
        output_frame = ttk.LabelFrame(main_frame, text="Output Directory", padding="5")
        output_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
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
        self.generate_btn.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        # Progress
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.grid(row=4, column=0, sticky="ew", pady=(0, 5))

        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9)
        )
        self.status_label.grid(row=5, column=0, sticky="w")

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
            else:
                # Update button text based on whether it's e-book only
                stories = item.get("stories", [])
                external_links = item.get("external_links", [])
                if not stories and external_links:
                    self.generate_btn.config(text="Open Link")
                else:
                    self.generate_btn.config(text="Generate EPUB")

    def _set_status(self, message: str):
        """Update the status message."""
        self.status_var.set(message)
        self.root.update_idletasks()

    def _set_progress(self, value: float):
        """Update the progress bar (0-100)."""
        self.progress_var.set(value)
        self.root.update_idletasks()

    def _refresh_sets(self):
        """Fetch story sets from the website."""
        self._set_status("Fetching story sets...")
        self.generate_btn.config(state="disabled")
        self.progress_var.set(0)

        def fetch():
            try:
                sets = scraper.fetch_all_story_sets()
                self.root.after(0, lambda: self._update_sets_list(sets))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(f"Failed to fetch story sets: {e}"))

        threading.Thread(target=fetch, daemon=True).start()

    def _update_sets_list(self, sets_by_year: dict[int, list[dict]]):
        """Update the listbox with fetched story sets grouped by year."""
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
            header = f"──── {year} ────"
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

                # Build display text
                if story_count > 0 and external_links:
                    display = f"  {name} ({story_count} stories, {len(external_links)} e-book)"
                elif story_count > 0:
                    display = f"  {name} ({story_count} stories)"
                elif external_links:
                    display = f"  {name} (e-book only)"
                else:
                    display = f"  {name} (no content)"

                self.listbox.insert(tk.END, display)
                self.listbox_items.append(story_set)

                # Gray out e-book only entries
                if story_count == 0:
                    idx = self.listbox.size() - 1
                    self.listbox.itemconfig(idx, fg="#999999")

                total_sets += 1

        self.generate_btn.config(state="normal")
        self._set_status(f"Found {total_sets} story sets across {len(sets_by_year)} years")
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
                story = parser.parse_story(html, info["url"])

                # Override publication date from API if available
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
