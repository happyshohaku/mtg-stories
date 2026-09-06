from datetime import datetime

from src import wiki_scraper

MAIN_TABLE = """
<h2><span class="mw-headline">Theros block</span><span class="mw-editsection">[edit]</span></h2>
<table class="wikitable">
<tr><th>Title</th><th>Author</th><th>Publishing date</th><th>Set</th><th>Setting</th><th>Featuring</th></tr>
<tr>
  <td><a href="https://web.archive.org/web/20140101000000/http://www.wizards.com/magic/magazine/article.aspx?x=mtg/daily/ur/262">Ajani, Mentor of Heroes</a></td>
  <td>Kelly Digges</td><td>2014-04-23</td><td>Journey into Nyx</td><td>Theros</td><td>Ajani</td>
</tr>
<tr>
  <td><a href="/page/Some_Wiki_Page">Wiki-only row</a></td>
  <td>Someone</td><td>2014-05-01</td><td>Journey into Nyx</td><td>Theros</td><td></td>
</tr>
<tr>
  <td><a href="https://magic.wizards.com/en/articles/archive/uncharted-realms/epilogue">Epilogue</a></td>
  <td>Kelly Digges</td><td>2014-08-18 (original), 2015-05-06 (republished)</td><td>Journey into Nyx</td><td>Theros</td><td></td>
</tr>
</table>
"""

OTHER_TABLE = """
<h2><span class="mw-headline">Other Magic Story articles</span></h2>
<table class="wikitable">
<tr><th>Title</th><th>Author</th><th>Release Date</th><th>Content</th></tr>
<tr><td><a href="https://magic.wizards.com/en/x/1">Campaign One</a></td><td>A. Writer</td><td>2021-07-01</td><td>Episode 1 of theForgotten RealmsD&amp;D campaign.</td></tr>
<tr><td><a href="https://magic.wizards.com/en/x/2">Campaign Two</a></td><td>A. Writer</td><td>2021-07-08</td><td>Episode 2 of theForgotten RealmsD&amp;D campaign.</td></tr>
<tr><td><a href="https://magic.wizards.com/en/x/3">Planeswalker's Guide to Theros, Part 1</a></td><td>B. Writer</td><td>2013-09-04</td><td>Guide</td></tr>
<tr><td><a href="https://magic.wizards.com/en/x/4">Planeswalker's Guide to Theros, Part 2</a></td><td>B. Writer</td><td>2013-09-11</td><td>Guide</td></tr>
<tr><td><a href="https://magic.wizards.com/en/x/5">The Magic Story Podcast: Kaladesh</a></td><td>WotC</td><td>2016-09-01</td><td>Podcast</td></tr>
<tr><td><a href="https://magic.wizards.com/en/x/6">The Magic Story Podcast: Amonkhet</a></td><td>WotC</td><td>2017-04-01</td><td>Podcast</td></tr>
</table>
"""


def test_parse_main_table_extracts_rows_and_skips_wiki_only_links():
    sections = wiki_scraper._parse_wiki_page(MAIN_TABLE)
    assert list(sections) == ["Theros block"]
    stories = sections["Theros block"]
    assert [s["title"] for s in stories] == ["Ajani, Mentor of Heroes", "Epilogue"]

    ajani = stories[0]
    assert ajani["author"] == "Kelly Digges"
    assert ajani["published_date"] == datetime(2014, 4, 23)
    assert ajani["set_name"] == "Journey into Nyx"
    assert ajani["slug"] == "ajani-mentor-of-heroes"
    assert ajani["url"].startswith("https://web.archive.org/")


def test_wiki_date_takes_first_of_multiple():
    assert wiki_scraper._parse_wiki_date("2014-08-18 (original), 2015-05-06 (republished)") == datetime(2014, 8, 18)
    assert wiki_scraper._parse_wiki_date("August 18, 2014") == datetime(2014, 8, 18)
    assert wiki_scraper._parse_wiki_date("") is None


def test_other_section_groups_by_content_series_title_prefix_and_known_series():
    stories = wiki_scraper._parse_wiki_page(OTHER_TABLE)["Other Magic Story articles"]
    groups = wiki_scraper._group_stories_by_title(stories)
    by_name = {g["name"]: [s["title"] for s in g["stories"]] for g in groups}

    # Wiki markup drops spaces around links ("theForgotten RealmsD&D"); grouping repairs them
    assert by_name["The Forgotten Realms D&D campaign"] == ["Campaign One", "Campaign Two"]
    assert by_name["Planeswalker's Guide to Theros"] == [
        "Planeswalker's Guide to Theros, Part 1", "Planeswalker's Guide to Theros, Part 2"]
    assert by_name["The Magic Story Podcast"] == [
        "The Magic Story Podcast: Kaladesh", "The Magic Story Podcast: Amonkhet"]
    assert all(g["source"] == "wiki" for g in groups)


def test_author_proximity_merges_three_consecutive_singletons():
    mk = lambda i, day, author="Solo Author": {
        "title": f"Unique Title Number {i}", "url": f"https://magic.wizards.com/en/x/{i}",
        "author": author, "published_date": datetime(2020, 1, day), "slug": f"u{i}", "content_desc": None,
    }
    groups = wiki_scraper._group_stories_by_title([mk(1, 1), mk(2, 5), mk(3, 9)])
    assert len(groups) == 1 and groups[0]["name"] == "Solo Author stories"

    # Only two: stays as two groups (avoids false positives)
    assert len(wiki_scraper._group_stories_by_title([mk(1, 1), mk(2, 5)])) == 2
    # Generic staff author: never merged
    staff = [mk(i, d, "The Magic Creative Team") for i, d in ((1, 1), (2, 3), (3, 5))]
    assert len(wiki_scraper._group_stories_by_title(staff)) == 3


def test_filter_wiki_sets_keeps_generic_title_in_different_set():
    contentful = {2020: [{"name": "Theros: Beyond Death", "stories": [
        {"title": "Epilogue", "slug": "theros-beyond-death-epilogue",
         "url": "https://magic.wizards.com/en/news/magic-story/theros-beyond-death-epilogue"},
    ]}]}
    wiki = {2014: [{"name": "Theros block", "source": "wiki", "stories": [
        {"title": "Epilogue", "slug": "epilogue", "set_name": "Journey into Nyx",
         "url": "https://web.archive.org/web/2014/http://www.wizards.com/x/epilogue"},
        {"title": "Epilogue", "slug": "epilogue", "set_name": "Theros Beyond Death",
         "url": "https://web.archive.org/web/2020/http://www.wizards.com/x/epilogue2"},
    ]}]}
    known = wiki_scraper.get_contentful_slugs(contentful)
    kept = wiki_scraper.filter_wiki_sets(wiki, known)
    assert [s["set_name"] for s in kept[2014][0]["stories"]] == ["Journey into Nyx"]


def test_filter_wiki_sets_drops_archived_copy_of_live_url():
    contentful = {2020: [{"name": "X", "stories": [
        {"title": "Some Long Specific Title", "slug": "some-long-specific-title",
         "url": "https://magic.wizards.com/en/news/magic-story/some-long-specific-title"}]}]}
    wiki = {2020: [{"name": "X block", "source": "wiki", "stories": [
        {"title": "Different Wording Here", "slug": "different-wording-here", "set_name": None,
         "url": "https://web.archive.org/web/2021/https://magic.wizards.com/en/news/magic-story/some-long-specific-title"}]}]}
    assert wiki_scraper.filter_wiki_sets(wiki, wiki_scraper.get_contentful_slugs(contentful)) == {}
