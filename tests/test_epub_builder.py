import re
import zipfile
from datetime import datetime

from src import epub_builder
from src.parser import Story


def _story(n, content="<p>Body</p>", images=None):
    return Story(url=f"https://x/{n}", title=f"Story {n}", author="Author", publication_date=datetime(2024, 1, n),
                 content_html=content, images=images or [])


def test_process_content_drops_images_not_in_book_and_maps_converted_ones():
    html = '<p>a</p><img src="images/keep.webp"><img src="images/gone.jpg"><p>b</p>'
    out = epub_builder._process_content(html, {"keep.webp": "keep.jpg"})
    assert 'src="images/keep.jpg"' in out
    assert "gone.jpg" not in out
    assert 'alt="Story illustration"' in out


def test_process_content_scene_breaks_and_scripts():
    out = epub_builder._process_content("<p>x</p><p>***</p><script>bad()</script>", {})
    assert 'class="scene-break"' in out and "bad()" not in out


def test_create_epub_is_deterministic_and_structured(tmp_path):
    stories = [_story(1), _story(2)]
    p1 = epub_builder.create_epub(stories, "My Set", str(tmp_path / "a"))
    p2 = epub_builder.create_epub(stories, "my set ", str(tmp_path / "b"))

    def read(path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}

    a, b = read(p1), read(p2)
    ident = lambda files: re.search(r"<dc:identifier[^>]*>([^<]+)<", files["EPUB/content.opf"]).group(1)
    assert ident(a) == ident(b) and ident(a).startswith("urn:uuid:")
    chapters = sorted(n for n in a if "chapter_" in n)
    assert len(chapters) == 2
    assert "Story 1" in a[chapters[0]] and "by Author" in a[chapters[0]]
    assert "!important" not in a["EPUB/style/main.css"]


def test_grouped_toc_nests_multi_story_groups(tmp_path):
    s = [_story(1), _story(2), _story(3)]
    path = epub_builder.create_epub(s, "Combined", str(tmp_path),
                                    groups=[("Set A", s[:2]), ("Set B", s[2:])])
    with zipfile.ZipFile(path) as z:
        nav = z.read("EPUB/nav.xhtml").decode()
    assert "Set A" in nav            # section header for the 2-story group
    assert "Set B" not in nav        # single-story group is flat
    assert nav.index("Story 1") < nav.index("Story 2") < nav.index("Story 3")


def test_unknown_author_falls_back_to_wizards(tmp_path):
    s = _story(1); s.author = "Unknown Author"
    path = epub_builder.create_epub([s], "Anon", str(tmp_path))
    with zipfile.ZipFile(path) as z:
        assert "Wizards of the Coast" in z.read("EPUB/content.opf").decode()
