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
