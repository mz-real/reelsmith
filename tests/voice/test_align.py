"""Tests for reelsmith.voice.align."""

from __future__ import annotations

import numpy as np

from reelsmith.voice.align import phrase_bounds
from reelsmith.voice.base import Audio
from reelsmith.voice.transcribe import Word


def _audio_with_quiet_gap(sample_rate: int = 24000) -> Audio:
    """Loud, then a quiet dip around 0.9 to 1.1s, then loud again."""
    loud_a = np.full(int(0.9 * sample_rate), 0.5, dtype=np.float32)
    quiet = np.zeros(int(0.2 * sample_rate), dtype=np.float32)
    loud_b = np.full(int(0.9 * sample_rate), 0.5, dtype=np.float32)
    samples = np.concatenate([loud_a, quiet, loud_b])
    return Audio(samples=samples, sample_rate=sample_rate)


def _words() -> list[Word]:
    return [
        Word(text="Type", start=0.0, end=0.2),
        Word(text="fast.", start=0.2, end=0.85),
        Word(text="Results", start=1.1, end=1.3),
        Word(text="update.", start=1.3, end=1.9),
    ]


def test_phrase_bounds_splits_words_by_phrase_word_count() -> None:
    audio = _audio_with_quiet_gap()

    bounds = phrase_bounds(["Type fast.", "Results update."], _words(), audio)

    assert len(bounds) == 2
    assert bounds[0][0] == 0.0
    assert bounds[1][1] == 2.0  # the last phrase runs to the end of the audio


def test_phrase_bounds_moves_the_cut_to_the_quiet_gap() -> None:
    audio = _audio_with_quiet_gap()

    bounds = phrase_bounds(["Type fast.", "Results update."], _words(), audio)

    cut = bounds[0][1]
    assert cut == bounds[1][0]
    # The raw word timestamps put the boundary at 0.85 or 1.1. The quiet
    # dip is between 0.9 and 1.1, so a real cut should land inside it.
    assert 0.9 <= cut <= 1.1


def test_phrase_bounds_single_phrase_returns_full_span() -> None:
    audio = _audio_with_quiet_gap()
    words = [Word(text="Hello", start=0.0, end=0.5)]

    bounds = phrase_bounds(["Hello"], words, audio)

    assert bounds == [(0.0, 2.0)]  # a one phrase line keeps the whole audio


def test_phrase_bounds_empty_phrases_returns_empty_list() -> None:
    audio = _audio_with_quiet_gap()

    assert phrase_bounds([], [], audio) == []


def test_phrase_bounds_tolerates_fewer_words_than_expected() -> None:
    audio = _audio_with_quiet_gap()
    words = [Word(text="Type", start=0.0, end=0.2)]

    bounds = phrase_bounds(["Type fast.", "Results update."], words, audio)

    assert len(bounds) == 2
    assert bounds[0] == (0.0, 0.2)
    assert bounds[1] == (0.0, 0.0)


def test_line_edges_keep_the_whole_audio_so_no_sound_is_clipped() -> None:
    # Whisper's first start can be late and its last end early. Cutting there
    # clips the first sound and the last syllable ("marker" heard as "mark").
    sample_rate = 24000
    audio = Audio(
        samples=np.full(int(3.8 * sample_rate), 0.1, dtype=np.float32), sample_rate=sample_rate
    )
    words = [
        Word(text="Saved", start=0.12, end=0.6),
        Word(text="with", start=0.6, end=0.9),
        Word(text="a", start=0.9, end=1.0),
        Word(text="marker.", start=1.0, end=3.5),
    ]

    bounds = phrase_bounds(["Saved with a marker."], words, audio)

    assert bounds == [(0.0, 3.8)]


def test_inner_cuts_stay_between_words_while_edges_cover_the_line() -> None:
    audio = _audio_with_quiet_gap()
    bounds = phrase_bounds(["Type fast.", "Results update."], _words(), audio)

    assert bounds[0][0] == 0.0
    assert bounds[-1][1] == len(audio.samples) / audio.sample_rate
    assert 0.85 <= bounds[0][1] <= 1.1
