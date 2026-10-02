"""Tests for the shared transcript comparison in reelsmith.text.

Every tolerance here is narrow. Each one has a negative case next to it
that must still be reported as a real error.
"""

from __future__ import annotations

import pytest

from reelsmith.text import (
    compare_text,
    phonetic_key,
    say_differs_much,
    sounds_alike,
    tokens,
    vocabulary_words,
)

# --- numbers ----------------------------------------------------------------

NUMBER_PAIRS = [
    ("nine checks", "9 checks"),
    ("zero errors", "0 errors"),
    ("ten lines", "10 lines"),
    ("twenty one steps", "21 steps"),
    ("twenty-one steps", "21 steps"),
    ("one hundred words", "100 words"),
    ("the first one", "the 1st one"),
    ("the third one", "the 3rd one"),
    ("the tenth one", "the 10th one"),
]


@pytest.mark.parametrize(("script", "heard"), NUMBER_PAIRS)
def test_number_words_and_digits_are_equal(script: str, heard: str) -> None:
    result = compare_text(script, heard)
    assert result.missing == []
    assert result.changed == []
    assert compare_text(heard, script).changed == []


def test_a_different_number_still_fails() -> None:
    result = compare_text("It runs nine checks.", "it runs 8 checks")
    assert result.changed == [("nine", "eight")]


def test_numbers_above_one_hundred_stay_digits() -> None:
    assert tokens("250 words") == ["250", "words"]


# --- abbreviations ----------------------------------------------------------

ABBREVIATION_PAIRS = [
    ("run reelsmith doctor", "run reelsmith dr"),
    ("Main Street", "main st"),
    ("cats versus dogs", "cats vs dogs"),
    ("and so on, et cetera", "and so on etc"),
]


@pytest.mark.parametrize(("script", "heard"), ABBREVIATION_PAIRS)
def test_abbreviations_match_their_full_form(script: str, heard: str) -> None:
    result = compare_text(script, heard)
    assert result.missing == []
    assert result.changed == []


def test_an_abbreviation_does_not_hide_a_different_word() -> None:
    result = compare_text("run reelsmith doctor", "run reelsmith director")
    assert result.changed == [("doctor", "director")]


# --- adjacent word joins ----------------------------------------------------

JOIN_PAIRS = [
    ("Script check runs on the demo.", "scriptcheck runs on the demo"),
    ("Run reelsmith Q A now.", "run reelsmith QA now"),
    ("Save it as an S R T file.", "save it as an SRT file"),
    ("then install the plugin.", "then install the plug in"),
    ("Open the set up page.", "open the setup page"),
]


@pytest.mark.parametrize(("script", "heard"), JOIN_PAIRS)
def test_joined_and_split_words_match(script: str, heard: str) -> None:
    result = compare_text(script, heard)
    assert result.missing == []
    assert result.changed == []


def test_a_join_never_hides_a_missing_word() -> None:
    result = compare_text("Script check runs on the demo.", "script runs on the demo")
    assert result.missing == ["check"]


def test_spelled_letters_still_fail_when_one_is_dropped() -> None:
    result = compare_text("Run reelsmith Q A now.", "run reelsmith q now")
    assert result.missing == ["a"]


def test_a_join_needs_the_exact_letters() -> None:
    result = compare_text("then install the plugin.", "then install the plug")
    assert result.changed == [("plugin", "plug")]


# --- spoken dots -----------------------------------------------------------


@pytest.mark.parametrize(
    ("script", "heard"),
    [
        ("First comes the plan, spec dot yaml.", "first comes the plan, spec .yaml."),
        ("First comes the plan, spec dot yaml.", "first comes the plan spec.yaml"),
        ("Open spec.yaml now.", "open spec dot yaml now"),
    ],
)
def test_a_dot_inside_a_word_is_the_spoken_word_dot(script: str, heard: str) -> None:
    result = compare_text(script, heard)
    assert result.missing == []
    assert result.changed == []


def test_dots_in_an_abbreviation_are_not_spoken() -> None:
    assert tokens("Q.A. checks, e.g. sync.") == ["q", "a", "checks", "e", "g", "sync"]


def test_a_full_stop_is_not_a_spoken_dot() -> None:
    assert tokens("It ends here. Next one.") == ["it", "ends", "here", "next", "one"]
    assert tokens("Version 3.5 is out.") == ["version", "three", "five", "is", "out"]


def test_a_dropped_dot_word_still_fails() -> None:
    result = compare_text("spec dot yaml", "spec yaml")
    assert result.missing == ["dot"]


# --- homophones of vocabulary words -----------------------------------------

HOMOPHONES = [
    ("reelsmith", "realsmith"),
    ("kokoro", "kakoro"),
    ("claude", "cloud"),
    ("codex", "codecs"),
]


@pytest.mark.parametrize(("word", "heard"), HOMOPHONES)
def test_known_homophones_have_the_same_key(word: str, heard: str) -> None:
    assert phonetic_key(word) == phonetic_key(heard)
    assert sounds_alike(word, heard)


@pytest.mark.parametrize(
    ("word", "heard"),
    [("save", "sale"), ("prints", "prince"), ("claude", "code"), ("doctor", "dr")],
)
def test_different_words_do_not_sound_alike(word: str, heard: str) -> None:
    assert not sounds_alike(word, heard)


def test_a_homophone_of_a_vocabulary_word_is_a_note_not_an_error() -> None:
    result = compare_text(
        "This video was made with reelsmith.",
        "this video was made with realsmith",
        vocabulary=["reelsmith"],
    )
    assert result.missing == []
    assert result.changed == []
    assert result.homophones == [("reelsmith", "realsmith")]


def test_a_vocabulary_word_heard_as_two_words_is_a_homophone() -> None:
    result = compare_text(
        "Run reelsmith Q A.",
        "run real smith q a",
        vocabulary=["reelsmith"],
    )
    assert result.missing == []
    assert result.changed == []
    assert result.homophones == [("reelsmith", "realsmith")]


def test_a_homophone_outside_the_vocabulary_still_fails() -> None:
    result = compare_text("Save the recipe.", "safe the recipe", vocabulary=["reelsmith"])
    assert result.changed == [("save", "safe")]
    assert result.homophones == []


def test_a_word_that_does_not_sound_alike_still_fails_in_the_vocabulary() -> None:
    result = compare_text(
        "First comes the plan, spec.yaml.",
        "first comes the plan back dot yaml",
        vocabulary=["spec.yaml"],
    )
    assert result.changed == [("spec", "back")]


def test_a_really_missing_word_still_fails_with_every_tolerance_on() -> None:
    result = compare_text(
        "In Claude Code, add the reelsmith marketplace.",
        "in cloud code add the marketplace",
        vocabulary=["Claude", "reelsmith"],
    )
    assert result.missing == ["reelsmith"]
    assert result.homophones == [("claude", "cloud")]


# --- vocabulary hints -------------------------------------------------------


def test_vocabulary_words_picks_only_uncommon_words() -> None:
    texts = [
        "In Claude Code, add the marketplace. Then open spec.yaml and voice_id.",
        "It runs 9 checks on GitHub. I think so.",
    ]
    assert vocabulary_words(texts) == [
        "Claude",
        "Code",
        "spec.yaml",
        "voice_id",
        "9",
        "GitHub",
    ]


def test_vocabulary_words_skips_the_first_word_of_a_sentence() -> None:
    assert vocabulary_words(["Save the file. Then close it! Done? Yes."]) == []


def test_vocabulary_words_skips_single_letters() -> None:
    assert vocabulary_words(["Pick option B, then press A."]) == []


def test_vocabulary_words_keeps_case_and_drops_repeats() -> None:
    assert vocabulary_words(["Use Kokoro. The voice is Kokoro, and kokoro."]) == ["Kokoro"]


# --- say versus text --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "say"),
    [
        ("Run reelsmith qa.", "Run reelsmith Q A."),
        ("Open spec.yaml.", "Open spec dot yaml."),
        ("Write an srt file.", "Write an S R T file."),
        ("reelsmith init makes the folder,", "reelsmith in it makes the folder,"),
    ],
)
def test_say_that_only_respells_text_is_not_flagged(text: str, say: str) -> None:
    assert not say_differs_much(text, say)


@pytest.mark.parametrize(
    ("text", "say"),
    [
        ("Save the recipe.", "Delete every file you own."),
        ("Run reelsmith qa.", "Run it."),
    ],
)
def test_say_that_changes_the_meaning_is_flagged(text: str, say: str) -> None:
    assert say_differs_much(text, say)
