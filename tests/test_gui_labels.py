from src.gui import KIND_COLORS, KIND_DESCRIPTIONS, KIND_LEGEND, _count_label, _plural, _set_kind


def _set(count, source=None, external_links=None):
    s = {"name": "X", "stories": [{"title": str(i)} for i in range(count)]}
    if source:
        s["source"] = source
    if external_links:
        s["external_links"] = external_links
    return s


def test_plural():
    assert _plural(1, "story") == "1 story"
    assert _plural(10, "story") == "10 stories"
    assert _plural(0, "story") == "0 stories"
    assert _plural(1, "e-book") == "1 e-book"
    assert _plural(2, "e-book") == "2 e-books"


def test_count_label_names_articles_as_articles():
    assert _count_label(_set(1)) == "1 story"
    assert _count_label(_set(13)) == "13 stories"
    assert _count_label(_set(1, source="articles")) == "1 article"
    assert _count_label(_set(3, source="articles")) == "3 articles"
    assert _count_label(_set(4, source="wiki")) == "4 stories"


def test_set_kind():
    assert _set_kind(_set(2)) == "official"
    assert _set_kind(_set(2, source="articles")) == "articles"
    assert _set_kind(_set(2, source="wiki")) == "wiki"
    assert _set_kind(_set(0, external_links=["https://example.com"])) == "ebook"
    # Stories plus an e-book link is still a convertible set
    assert _set_kind(_set(2, external_links=["https://example.com"])) == "official"


def test_every_kind_has_colour_legend_and_description():
    assert set(KIND_COLORS) == set(KIND_LEGEND) == set(KIND_DESCRIPTIONS)
