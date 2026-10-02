"""Compare a transcript against the script text it should match.

The rules live in reelsmith.text, shared with the voice step, so both
agree on what counts as the same word.
"""

from __future__ import annotations

from reelsmith.text import compare_text, tokens


def normalize_words(text: str) -> list[str]:
    """Lowercase, split into bare words, drop punctuation, spell out small
    numbers and abbreviations, and fold British/American spelling."""
    return tokens(text)


def compare_words(expected: str, actual: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Diff two pieces of text at the word level.

    Returns a list of words missing from ``actual`` and a list of
    ``(expected, heard)`` pairs for words that changed. Extra words that
    ``actual`` has but ``expected`` does not (filler the model heard) are
    not reported: they do not mean a word was dropped or slurred. No
    vocabulary is given here, so no homophone is forgiven.
    """
    result = compare_text(expected, actual)
    return result.missing, result.changed
