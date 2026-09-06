from datetime import datetime

from src import scraper


def _article(title, slug, date, author="A"):
    return {"title": title, "url": f"https://magic.wizards.com/en/news/magic-story/{slug}", "slug": slug,
            "published_date": date, "author": author, "excerpt": ""}


def test_articles_grouped_by_title_prefix_and_year(monkeypatch):
    monkeypatch.setattr(scraper, "_fetch_all_articles", lambda: [
        _article("Bloomburrow | Episode 2: Later", "bb-2", datetime(2024, 7, 8)),
        _article("Bloomburrow | Episode 1: First", "bb-1", datetime(2024, 7, 1)),
        _article("Standalone Story", "solo", datetime(2023, 3, 3)),
    ])
    sets = scraper.fetch_article_story_sets()
    assert sorted(sets) == [2023, 2024]
    bb = sets[2024][0]
    assert bb["name"] == "Bloomburrow" and bb["source"] == "articles"
    assert [s["title"] for s in bb["stories"]] == ["Episode 1: First", "Episode 2: Later"]  # date order
    assert sets[2023][0]["name"] == "Standalone Story"


def test_filter_article_sets_removes_storygroup_duplicates():
    storygroups = {2024: [{"name": "Bloomburrow", "stories": [
        {"title": "Episode 1", "slug": "bb-1", "url": "https://magic.wizards.com/en/news/magic-story/bb-1"}]}]}
    articles = {2024: [{"name": "Bloomburrow", "source": "articles", "stories": [
        _article("Episode 1", "bb-1", datetime(2024, 7, 1)),
        _article("Episode 9", "bb-9", datetime(2024, 8, 1)),
    ]}]}
    kept = scraper.filter_article_sets(articles, scraper.get_storygroup_slugs(storygroups))
    assert [s["slug"] for s in kept[2024][0]["stories"]] == ["bb-9"]

    # Everything duplicated: the set disappears entirely
    only_dup = {2024: [{"name": "Bloomburrow", "source": "articles", "stories": [_article("Episode 1", "bb-1", None)]}]}
    assert scraper.filter_article_sets(only_dup, scraper.get_storygroup_slugs(storygroups)) == {}


def test_storygroup_year_parsing(monkeypatch):
    """_fetch_story_sets_for_year builds sets from Contentful's includes structure."""
    payload = {
        "items": [{"fields": {"name": "Set X", "archiveThumbnail": {"sys": {"id": "asset1"}},
                              "stories": [{"sys": {"id": "s1"}}, {"sys": {"id": "s2"}}, {"sys": {"id": "ebook"}}]}}],
        "includes": {
            "Entry": [
                {"sys": {"id": "s2", "contentType": {"sys": {"id": "article"}}},
                 "fields": {"title": "Second", "slug": "second", "category": "magic-story", "publishedDate": "2024-02-02 10:00:00"}},
                {"sys": {"id": "s1", "contentType": {"sys": {"id": "article"}}},
                 "fields": {"title": "First", "slug": "first", "publishedDate": "2024-01-01"}},
                {"sys": {"id": "ebook", "contentType": {"sys": {"id": "storyEntry"}}},
                 "fields": {"title": "Buy the novel", "cta": {"sys": {"id": "cta1"}}}},
                {"sys": {"id": "cta1", "contentType": {"sys": {"id": "cta"}}},
                 "fields": {"link": "https://www.amazon.com/dp/123"}},
            ],
            "Asset": [{"sys": {"id": "asset1"}, "fields": {"file": {"url": "//images.ctfassets.net/x.jpg"}}}],
        },
    }

    class Resp:
        def raise_for_status(self): pass
        def json(self): return payload

    monkeypatch.setattr(scraper.net, "get", lambda *a, **k: Resp())
    sets = scraper._fetch_story_sets_for_year(2024)
    assert len(sets) == 1
    s = sets[0]
    assert s["image_url"] == "https://images.ctfassets.net/x.jpg"
    assert [st["title"] for st in s["stories"]] == ["First", "Second"]
    assert s["stories"][1]["url"] == "https://magic.wizards.com/en/news/magic-story/second"
    assert s["stories"][1]["published_date"] == datetime(2024, 2, 2, 10, 0, 0)
    assert s["external_links"] == [{"title": "Buy the novel", "url": "https://www.amazon.com/dp/123"}]
