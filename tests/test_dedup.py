from src import dedup


GENERIC = [
    "Prologue", "Epilogue", "The Epilogue", "Interlude", "Aftermath", "Finale",
    "The End", "Chapter 3", "Part II", "Episode 12", "Chapter 1: Prologue",
    "Epilogue, Part 2", "Part 1 of 3",
]
SPECIFIC = [
    "Return to Dominaria, Episode 1", "The Gathering Storm", "Blood of the Ancients",
    "March of the Machine Epilogue", "Chapter 1: The Sword", "Unbowed, Part 1",
]


def test_generic_titles_are_generic():
    assert [t for t in GENERIC if not dedup.is_generic_title(t)] == []


def test_specific_titles_are_specific():
    assert [t for t in SPECIFIC if dedup.is_generic_title(t)] == []


def test_title_to_slug():
    assert dedup.title_to_slug("Return to Dominaria, Episode 1") == "return-to-dominaria-episode-1"
    assert dedup.title_to_slug("  Weird -- Spacing  ") == "weird----spacing"


def test_normalize_set_name_ignores_punctuation_and_case():
    assert dedup.normalize_set_name("Theros: Beyond Death") == dedup.normalize_set_name("theros beyond death")
    assert dedup.normalize_set_name(None) == ""


def test_url_path_key_unwraps_archive_urls():
    live = "https://magic.wizards.com/en/news/magic-story/some-story"
    archived = "https://web.archive.org/web/20200101000000/https://magic.wizards.com/en/news/magic-story/some-story/"
    assert dedup.url_path_key(live) == "/en/news/magic-story/some-story"
    assert dedup.url_path_key(archived) == dedup.url_path_key(live)
    assert dedup.url_path_key(None) == ""


def test_generic_title_only_matches_within_same_set():
    contentful = {"title": "Epilogue", "slug": "theros-beyond-death-epilogue",
                  "url": "https://magic.wizards.com/en/news/magic-story/theros-beyond-death-epilogue"}
    known = dedup.story_keys(contentful, ["Theros: Beyond Death"])

    other_set = {"title": "Epilogue", "slug": "epilogue", "url": "https://web.archive.org/web/2015/http://x/epilogue"}
    same_set = dict(other_set)

    assert not dedup.story_keys(other_set, ["Zendikar"]) & known
    assert dedup.story_keys(same_set, ["Theros Beyond Death"]) & known


def test_specific_title_matches_across_sets():
    a = dedup.story_keys({"title": "The Gathering Storm", "slug": "", "url": ""}, ["Set A"])
    b = dedup.story_keys({"title": "The Gathering Storm", "slug": "", "url": ""}, ["Set B"])
    assert a & b


def test_real_slug_matches_regardless_of_title_or_set():
    a = dedup.story_keys({"title": "Whatever", "slug": "a-real-slug", "url": ""}, ["A"])
    b = dedup.story_keys({"title": "Different", "slug": "a-real-slug", "url": ""}, ["B"])
    assert "a-real-slug" in a & b
