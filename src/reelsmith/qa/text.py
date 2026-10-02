"""Compare a transcript against the script text it should match."""

from __future__ import annotations

import difflib
import re

from reelsmith.text import normalise_word

_WORD_RE = re.compile(r"[a-z0-9']+")


def normalize_words(text: str) -> list[str]:
    """Lowercase, split into bare words, drop punctuation, and fold
    British/American spelling variants to the same form."""
    return [normalise_word(word) for word in _WORD_RE.findall(text.lower())]


def compare_words(expected: str, actual: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Diff two pieces of text at the word level.

    Returns a list of words missing from ``actual`` and a list of
    ``(expected, heard)`` pairs for words that changed. Extra words that
    ``actual`` has but ``expected`` does not (filler the model heard) are
    not reported: they do not mean a word was dropped or slurred.
    """
    expected_words = normalize_words(expected)
    actual_words = normalize_words(actual)
    matcher = difflib.SequenceMatcher(a=expected_words, b=actual_words, autojunk=False)
    missing: list[str] = []
    changed: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        expected_slice = expected_words[i1:i2]
        actual_slice = actual_words[j1:j2]
        for index in range(max(len(expected_slice), len(actual_slice))):
            exp_word = expected_slice[index] if index < len(expected_slice) else None
            act_word = actual_slice[index] if index < len(actual_slice) else None
            if exp_word is None:
                continue
            if act_word is None:
                missing.append(exp_word)
            else:
                changed.append((exp_word, act_word))
    return missing, changed
