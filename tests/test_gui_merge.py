from datetime import datetime

from src.gui import MTGStoriesApp, _first_story_date


def _set(name, *dates, source=None):
    s = {"name": name, "stories": [{"title": f"{name} {i}", "published_date": d} for i, d in enumerate(dates)]}
    if source:
        s["source"] = source
    return s


def merge(cf, art, wiki):
    # _merge_story_sets does not touch self
    return MTGStoriesApp._merge_story_sets(None, cf, art, wiki)


def test_sets_within_a_year_sorted_by_first_story_date_newest_first():
    cf = {2024: [_set("Early", datetime(2024, 1, 5), datetime(2024, 1, 12)),
                 _set("Late", datetime(2024, 9, 1))]}
    art = {2024: [_set("Middle", datetime(2024, 5, 20), datetime(2024, 4, 1), source="articles")]}
    wiki = {2024: [_set("Latest", datetime(2024, 11, 30), source="wiki")]}
    merged = merge(cf, art, wiki)
    assert [s["name"] for s in merged[2024]] == ["Latest", "Late", "Middle", "Early"]


def test_first_story_date_is_the_earliest_regardless_of_list_order():
    s = _set("X", datetime(2024, 5, 20), datetime(2024, 4, 1), datetime(2024, 6, 1))
    assert _first_story_date(s) == datetime(2024, 4, 1)


def test_undated_sets_go_last_in_source_order():
    cf = {2020: [_set("NoDates SG", None), _set("Dated", datetime(2020, 3, 3))]}
    art = {2020: [_set("NoDates Art", None, source="articles")]}
    wiki = {2020: [_set("NoDates Wiki", source="wiki")]}
    merged = merge(cf, art, wiki)
    assert [s["name"] for s in merged[2020]] == ["Dated", "NoDates SG", "NoDates Art", "NoDates Wiki"]


def test_years_with_no_sets_are_dropped_and_others_kept():
    merged = merge({2024: [_set("A", datetime(2024, 1, 1))]}, {2023: []}, {-1: [_set("Other", None, source="wiki")]})
    assert sorted(merged) == [-1, 2024]
