"""Checks on generated narration: pace, dropped words, and tail trimming."""

from __future__ import annotations

import re

import numpy as np

from reelsmith.text import normalise_word
from reelsmith.voice.base import Audio
from reelsmith.voice.transcribe import Word

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words_per_minute(text: str, seconds: float) -> float:
    """Words spoken per minute, for text read in the given duration."""
    word_count = len(text.split())
    if seconds <= 0:
        return 0.0
    minutes = seconds / 60.0
    return word_count / minutes


def speaking_seconds(words: list[Word], fallback: float) -> float:
    """Seconds of actual speech, from the first word's start to the last word's end.

    The whole audio file's length includes the engine's lead-in and the
    short tail kept after trim_tail, neither of which is time spent
    speaking the line. Whisper's own word timestamps mark where speech
    actually starts and stops, so they give a truer reading for words a
    minute than the file length does. When there are no words at all
    (nothing was transcribed), fallback is used instead.
    """
    if not words:
        return fallback
    return words[-1].end - words[0].start


def pace_ok(wpm: float, low: float = 130.0, high: float = 210.0) -> bool:
    """Whether a pace falls inside the comfortable narration window."""
    return low <= wpm <= high


def trim_tail(
    audio: Audio,
    silence_db: float = -45.0,
    min_silence: float = 0.25,
    keep_tail: float = 0.06,
) -> Audio:
    """Cut trailing silence from a line, keeping a short tail.

    Finds the last sample louder than silence_db. If what follows it is at
    least min_silence seconds of quiet, the audio is cut keep_tail seconds
    after that last loud sample. A line that never goes quiet for that long
    at the end, or that is silent throughout, is returned unchanged.
    """
    samples = audio.samples
    if samples.size == 0:
        return audio

    threshold = 10 ** (silence_db / 20.0)
    loud = np.nonzero(np.abs(samples) > threshold)[0]
    if loud.size == 0:
        return audio

    last_loud = int(loud[-1])
    trailing_seconds = (samples.size - 1 - last_loud) / audio.sample_rate
    if trailing_seconds < min_silence:
        return audio

    keep_samples = int(round(keep_tail * audio.sample_rate))
    cut_at = min(last_loud + 1 + keep_samples, samples.size)
    return Audio(samples=samples[:cut_at].astype(np.float32), sample_rate=audio.sample_rate)


def _number_to_words(value: int) -> str:
    if value < 0:
        return f"minus {_number_to_words(-value)}"
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        return _TENS[tens] if rest == 0 else f"{_TENS[tens]} {_ONES[rest]}"
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        prefix = f"{_ONES[hundreds]} hundred"
        return prefix if rest == 0 else f"{prefix} {_number_to_words(rest)}"
    return str(value)


def _normalise_tokens(text: str) -> list[str]:
    """Lower case, drop punctuation, spell out small numbers, and fold
    British/American spelling variants to the same form."""
    tokens: list[str] = []
    for raw in text.split():
        cleaned = re.sub(r"[^\w]", "", raw.lower())
        if not cleaned:
            continue
        if cleaned.isdigit():
            tokens.extend(_number_to_words(int(cleaned)).split())
        else:
            tokens.append(normalise_word(cleaned))
    return tokens


def transcript_matches(expected: str, words: list[Word]) -> tuple[bool, list[str]]:
    """Check a transcript against the expected line text.

    Case, punctuation and small numbers are normalised on both sides
    first, and spelling variants such as "favourites" and "Favorites"
    are treated as the same word. Returns whether every expected word
    was heard, and the list of words that were not.
    """
    expected_tokens = _normalise_tokens(expected)
    heard: set[str] = set()
    for word in words:
        heard.update(_normalise_tokens(word.text))

    missing = [token for token in expected_tokens if token not in heard]
    return (len(missing) == 0, missing)
