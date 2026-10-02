"""Tests for the word level transcript comparison."""

from __future__ import annotations

from reelsmith.qa.text import compare_words, normalize_words


def test_normalize_words_lowercases_and_drops_punctuation() -> None:
    assert normalize_words("Type a dish into the search box.") == [
        "type",
        "a",
        "dish",
        "into",
        "the",
        "search",
        "box",
    ]


def test_identical_text_has_no_missing_or_changed_words() -> None:
    missing, changed = compare_words("Results update as you type.", "results update as you type")
    assert missing == []
    assert changed == []


def test_dropped_word_is_reported_as_missing() -> None:
    missing, changed = compare_words(
        "Type a dish into the search box.", "type a into the search box"
    )
    assert missing == ["dish"]
    assert changed == []


def test_slurred_word_is_reported_as_changed() -> None:
    missing, changed = compare_words("Click the search button.", "click the search bitten")
    assert missing == []
    assert changed == [("button", "bitten")]


def test_extra_heard_words_are_not_reported() -> None:
    missing, changed = compare_words("Save the recipe.", "um save the recipe okay")
    assert missing == []
    assert changed == []


def test_spelling_variant_is_not_reported_as_missing() -> None:
    missing, changed = compare_words("Browse your saved favourites.", "browse your saved favorites")
    assert missing == []
    assert changed == []
