"""Tests for reelsmith.text.normalise_word: British/American spelling match."""

from __future__ import annotations

import pytest

from reelsmith.text import normalise_word

EQUIVALENT_PAIRS = [
    ("colour", "color"),
    ("favour", "favor"),
    ("favourites", "favorites"),
    ("behaviour", "behavior"),
    ("honour", "honor"),
    ("neighbour", "neighbor"),
    ("organise", "organize"),
    ("organising", "organizing"),
    ("organised", "organized"),
    ("organisation", "organization"),
    ("realise", "realize"),
    ("recognise", "recognize"),
    ("customise", "customize"),
    ("optimise", "optimize"),
    ("prioritise", "prioritize"),
    ("summarise", "summarize"),
    ("finalise", "finalize"),
    ("personalise", "personalize"),
    ("visualise", "visualize"),
    ("minimise", "minimize"),
    ("maximise", "maximize"),
    ("categorise", "categorize"),
    ("synchronise", "synchronize"),
    ("analyse", "analyze"),
    ("analysing", "analyzing"),
    ("analysed", "analyzed"),
    ("centre", "center"),
    ("metre", "meter"),
    ("theatre", "theater"),
    ("catalogue", "catalog"),
    ("dialogue", "dialog"),
    ("travelled", "traveled"),
    ("travelling", "traveling"),
    ("cancelled", "canceled"),
    ("labelled", "labeled"),
    ("modelled", "modeled"),
]


@pytest.mark.parametrize(("british", "american"), EQUIVALENT_PAIRS)
def test_british_and_american_spellings_match(british: str, american: str) -> None:
    assert normalise_word(british) == normalise_word(american)


@pytest.mark.parametrize(("british", "american"), EQUIVALENT_PAIRS)
def test_the_american_spelling_is_left_unchanged(british: str, american: str) -> None:
    assert normalise_word(american) == american


OUR_WHOLE_SOUND_WORDS = [
    "your",
    "four",
    "hour",
    "pour",
    "tour",
    "flour",
    "sour",
    "our",
    "dour",
    "yours",
    "fours",
    "hours",
    "tours",
]


@pytest.mark.parametrize("word", OUR_WHOLE_SOUND_WORDS)
def test_short_our_words_are_not_changed(word: str) -> None:
    assert normalise_word(word) == word


ISE_FIXED_SPELLING_WORDS = [
    "rise",
    "wise",
    "otherwise",
    "likewise",
    "raise",
    "praise",
    "noise",
    "poise",
    "promise",
    "surprise",
    "exercise",
    "advertise",
    "compromise",
    "expertise",
    "enterprise",
    "premise",
    "precise",
    "concise",
    "paradise",
    "franchise",
    "merchandise",
    "televise",
    "supervise",
    "revise",
    "advise",
    "devise",
    "comprise",
    "despise",
    "disguise",
    "improvise",
]


@pytest.mark.parametrize("word", ISE_FIXED_SPELLING_WORDS)
def test_fixed_ise_spellings_are_not_changed(word: str) -> None:
    assert normalise_word(word) == word


def test_case_is_folded_before_matching() -> None:
    assert normalise_word("COLOUR") == normalise_word("color")
    assert normalise_word("Favourites") == normalise_word("Favorites")


def test_an_unrelated_word_is_left_unchanged() -> None:
    assert normalise_word("kitchen") == "kitchen"


def test_a_plain_plural_is_left_unchanged() -> None:
    assert normalise_word("recipes") == "recipes"
