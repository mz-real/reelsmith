"""Aligns script phrases to the narration audio.

A line is spoken and saved as one audio file, but it is made of several
phrases, each pinned to an action in the video. This module splits the
line's word level timestamps across its phrases, then nudges the cut
between each pair of phrases to the quietest instant nearby, so the cut
never lands on a spoken syllable.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from reelsmith.voice.base import Audio
from reelsmith.voice.transcribe import Word

_SEARCH_WINDOW = 0.05  # seconds either side of a word gap to search for quiet
_ENERGY_WINDOW = 0.005  # seconds, the window used to measure local loudness


def _split_words(words: Sequence[Word], counts: list[int]) -> list[list[Word]]:
    blocks: list[list[Word]] = []
    index = 0
    for count in counts:
        blocks.append(list(words[index : index + count]))
        index += count
    return blocks


def _quietest_point(audio: Audio, start: float, end: float) -> float:
    """The quietest instant in and around the gap between start and end."""
    sample_rate = audio.sample_rate
    low = max(0, int((start - _SEARCH_WINDOW) * sample_rate))
    high = min(audio.samples.size, int((end + _SEARCH_WINDOW) * sample_rate))
    if high <= low:
        return (start + end) / 2.0

    window = max(1, int(_ENERGY_WINDOW * sample_rate))
    segment = audio.samples[low:high].astype(np.float64)
    span = max(1, segment.size - window + 1)

    best_offset = 0
    best_energy = float("inf")
    for offset in range(span):
        chunk = segment[offset : offset + window]
        energy = float(np.mean(chunk * chunk))
        if energy < best_energy:
            best_energy = energy
            best_offset = offset

    return (low + best_offset) / sample_rate


def phrase_bounds(
    phrases: Sequence[str], words: Sequence[Word], audio: Audio
) -> list[tuple[float, float]]:
    """Map each phrase to a (start, end) span in the line's audio."""
    if not phrases:
        return []

    counts = [max(len(phrase.split()), 1) for phrase in phrases]
    blocks = _split_words(words, counts)

    bounds: list[tuple[float, float]] = []
    for block in blocks:
        if block:
            bounds.append((block[0].start, block[-1].end))
        else:
            bounds.append((0.0, 0.0))

    for index in range(len(bounds) - 1):
        gap_start = bounds[index][1]
        gap_end = bounds[index + 1][0]
        if gap_end <= gap_start:
            continue
        cut = _quietest_point(audio, gap_start, gap_end)
        bounds[index] = (bounds[index][0], cut)
        bounds[index + 1] = (cut, bounds[index + 1][1])

    # The line's edges cover the whole file. Whisper's first start can be late
    # and its last end early, and cutting there clips the first sound or the
    # last syllable. The voice step has already trimmed the tail safely.
    duration = len(audio.samples) / audio.sample_rate
    if bounds[0][1] > 0.0:
        bounds[0] = (0.0, bounds[0][1])
    if bounds[-1][1] > 0.0:
        bounds[-1] = (bounds[-1][0], duration)
    return bounds
