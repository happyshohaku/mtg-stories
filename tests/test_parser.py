from datetime import datetime

from src import parser

PAGE = """
<html><head>
<title>The Gathering Storm | MAGIC: THE GATHERING</title>
<meta property="article:published_time" content="2025-06-20T14:00:00Z">
<script type="application/ld+json">{"@type": "Article", "author": {"@type": "Person", "name": "Jane Writer"}}</script>
</head><body>
<header><nav>Site nav</nav></header>
<article>
  <h1 class="article-title">The Gathering Storm</h1>
  <div class="article-body">
    <p>By the time the storm broke, nothing was left.</p>
    <img src="/images/story/pic1.webp" srcset="/x 2x" loading="lazy">
    <img data-src="https://cdn.example.com/pic2.png">
    <p>See <a href="https://magic.wizards.com/en/news/other">this other story</a> and
       <a href="https://en.wikipedia.org/wiki/Storm">Wikipedia</a> and <a href="#top">top</a>.</p>
    <p>* * *</p>
    <iframe src="https://youtube.com/embed/x"></iframe>
    <script>alert(1)</script>
  </div>
</article>
<footer>Footer</footer>
</body></html>
"""

ARCHIVED = """
<html><head><title>Old Story - Magic: The Gathering</title>
<script src="https://web.archive.org/static/js/wombat.js"></script>
</head><body>
<!-- BEGIN WAYBACK TOOLBAR INSERT --><div id="wm-ipp-base">toolbar</div><!-- END WAYBACK TOOLBAR INSERT -->
<div id="bodycontent"><p>By Old Author</p><p>Once upon a time.</p><img src="/images/old.jpg"></div>
</body></html>
"""


def test_parse_story_extracts_metadata_and_content():
    story = parser.parse_story(PAGE, "https://magic.wizards.com/en/news/magic-story/the-gathering-storm")
    assert story.title == "The Gathering Storm"
    assert story.author == "Jane Writer"                      # JSON-LD wins over "By the time..."
    assert story.publication_date == datetime(2025, 6, 20, 14, 0, 0)
    assert "nothing was left" in story.content_html
    assert "alert(1)" not in story.content_html
    assert "<iframe" not in story.content_html
    assert "Site nav" not in story.content_html


def test_images_are_collected_and_rewritten_to_local_paths():
    story = parser.parse_story(PAGE, "https://magic.wizards.com/en/news/magic-story/x")
    urls = [i["url"] for i in story.images]
    assert urls == ["https://magic.wizards.com/images/story/pic1.webp", "https://cdn.example.com/pic2.png"]
    for img in story.images:
        assert img["filename"].endswith((".webp", ".png"))
        assert f'src="images/{img["filename"]}"' in story.content_html
    assert "srcset" not in story.content_html and "loading=" not in story.content_html


def test_wizards_links_unwrapped_external_links_and_anchors_kept():
    story = parser.parse_story(PAGE, "https://magic.wizards.com/en/news/magic-story/x")
    assert 'href="https://magic.wizards.com/en/news/other"' not in story.content_html
    assert "this other story" in story.content_html
    assert 'href="https://en.wikipedia.org/wiki/Storm"' in story.content_html
    assert 'href="#top"' in story.content_html


def test_archived_page_strips_toolbar_resolves_relative_to_original_url():
    url = "https://web.archive.org/web/20150101000000/http://www.wizards.com/magic/story/old"
    story = parser.parse_story(ARCHIVED, url)
    assert story.title == "Old Story"
    assert story.author == "Old Author"
    assert "toolbar" not in story.content_html
    assert story.images[0]["url"] == "http://www.wizards.com/images/old.jpg"


def test_fallbacks_used_when_page_lacks_metadata():
    story = parser.parse_story("<html><body><div><p>text</p></div></body></html>", "https://x/y",
                               fallback_author="Wiki Author", fallback_date=datetime(2010, 1, 2),
                               fallback_title="Wiki Title")
    assert (story.title, story.author, story.publication_date) == ("Wiki Title", "Wiki Author", datetime(2010, 1, 2))


def test_url_to_filename_is_safe_and_unique_per_url():
    a = parser._url_to_filename("https://cdn.example.com/a/pic.jpg")
    b = parser._url_to_filename("https://cdn.example.com/b/pic.jpg")
    assert a != b and a.endswith("_pic.jpg")
    assert parser._url_to_filename("https://x/y/no-extension").endswith(".jpg")
    assert "/" not in parser._url_to_filename("https://x/we ird?name=1.png")


CARDS_PAGE = """
<html><body><article><div class="article-body">
<p>Jace</p>
<div style="text-align: center;">
<responsive-grid slide-view-if="(min-width:10px)">
  <grid-item><cig-card entry="AAA">0216_MTGFRA_MainPair: Jace, Reality Sculptor</cig-card></grid-item>
  <grid-item><cig-card entry="BBB">0300_MTGFRA_BdlsDipt: Two-Faced Card</cig-card></grid-item>
</responsive-grid>
</div>
<div><cig-card entry="GONE">0001_MTGFRA_CommBord: Jace, Multiverse Architect</cig-card></div>
</div></article></body></html>
"""


def test_card_placeholders_become_images():
    asked = []

    def lookup(ids):
        asked.extend(ids)
        return {
            "AAA": {"name": "Jace, Reality Sculptor", "face": "https://media.example.com/jace.webp", "back": None},
            "BBB": {"name": "Two-Faced Card", "face": "https://media.example.com/front.webp",
                    "back": "https://media.example.com/back.webp"},
        }

    story = parser.parse_story(CARDS_PAGE, "https://magic.wizards.com/en/news/magic-story/x", card_lookup=lookup)
    assert asked == ["AAA", "BBB", "GONE"]
    assert [i["url"] for i in story.images] == [
        "https://media.example.com/jace.webp",
        "https://media.example.com/front.webp",
        "https://media.example.com/back.webp",
    ]
    assert 'alt="Jace, Reality Sculptor"' in story.content_html
    # Internal labels and site-only tags never reach the book
    assert "MTGFRA" not in story.content_html
    assert "cig-card" not in story.content_html and "grid-item" not in story.content_html
    # A card that cannot be resolved is reduced to its name
    assert "Jace, Multiverse Architect" in story.content_html


def test_card_placeholders_fall_back_to_names_without_lookup():
    story = parser.parse_story(CARDS_PAGE, "https://magic.wizards.com/en/news/magic-story/x")
    assert story.images == []
    assert "Jace, Reality Sculptor" in story.content_html
    assert "MTGFRA" not in story.content_html and "cig-card" not in story.content_html
