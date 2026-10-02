"""Checks on generated narration: pace, dropped words, and tail trimming."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from reelsmith.text import reconcile_joins, sounds_alike, tokens, vocabulary_tokens
from reelsmith.voice.base import Audio
from reelsmith.voice.transcribe import Word


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
    return Audio(
        samples=samples[:cut_at].astype(np.float32),
        sample_rate=audio.sample_rate,
        warning=audio.warning,
    )


def transcript_matches(
    expected: str, words: list[Word], vocabulary: Sequence[str] = ()
) -> tuple[bool, list[str]]:
    """Check a transcript against the expected line text.

    Both sides go through reelsmith.text first, so case, punctuation,
    small numbers, a few abbreviations, British/American spelling and
    words heard joined or split all match. A vocabulary word heard as a
    word with the same sound (realsmith for reelsmith) counts as heard.
    Returns whether every expected word was heard, and the list of words
    that were not.
    """
    vocab = vocabulary_tokens(vocabulary)
    expected_tokens = tokens(expected)
    heard_tokens = reconcile_joins(expected_tokens, tokens(" ".join(w.text for w in words)), vocab)
    heard = set(heard_tokens)

    def was_heard(token: str) -> bool:
        if token in heard:
            return True
        return token in vocab and any(sounds_alike(token, other) for other in heard)

    missing = [token for token in expected_tokens if not was_heard(token)]
    return (len(missing) == 0, missing)
