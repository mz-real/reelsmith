"""Tests for reelsmith.voice.quality."""

from __future__ import annotations

import numpy as np

from reelsmith.voice.base import Audio
from reelsmith.voice.quality import pace_ok, transcript_matches, trim_tail, words_per_minute
from reelsmith.voice.transcribe import Word


def _tone(seconds: float, sample_rate: int = 24000, amplitude: float = 0.5) -> np.ndarray:
    return np.full(int(seconds * sample_rate), amplitude, dtype=np.float32)


def _silence(seconds: float, sample_rate: int = 24000) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


def test_words_per_minute_basic() -> None:
    assert words_per_minute("one two three four five", 60.0) == 5.0


def test_words_per_minute_zero_duration_is_zero() -> None:
    assert words_per_minute("hello world", 0.0) == 0.0


def test_pace_ok_within_window() -> None:
    assert pace_ok(170.0) is True


def test_pace_ok_outside_window() -> None:
    assert pace_ok(100.0) is False
    assert pace_ok(250.0) is False


def test_pace_ok_respects_custom_bounds() -> None:
    assert pace_ok(220.0, low=100.0, high=250.0) is True


def test_trim_tail_cuts_after_sustained_silence() -> None:
    sample_rate = 24000
    tone = _tone(1.0, sample_rate)
    tail_silence = _silence(1.0, sample_rate)
    audio = Audio(samples=np.concatenate([tone, tail_silence]), sample_rate=sample_rate)

    trimmed = trim_tail(audio, silence_db=-45.0, min_silence=0.25, keep_tail=0.06)

    expected_length = tone.size + int(round(0.06 * sample_rate))
    assert trimmed.samples.size == expected_length
    assert trimmed.sample_rate == sample_rate


def test_trim_tail_keeps_audio_without_sustained_silence() -> None:
    sample_rate = 24000
    tone = _tone(1.0, sample_rate)
    audio = Audio(samples=tone, sample_rate=sample_rate)

    trimmed = trim_tail(audio, min_silence=0.25)

    assert trimmed.samples.size == tone.size


def test_trim_tail_ignores_a_short_pause_shorter_than_min_silence() -> None:
    sample_rate = 24000
    tone = _tone(1.0, sample_rate)
    short_gap = _silence(0.1, sample_rate)
    audio = Audio(samples=np.concatenate([tone, short_gap]), sample_rate=sample_rate)

    trimmed = trim_tail(audio, min_silence=0.25)

    assert trimmed.samples.size == audio.samples.size


def test_trim_tail_handles_fully_silent_audio() -> None:
    sample_rate = 24000
    audio = Audio(samples=_silence(0.5, sample_rate), sample_rate=sample_rate)

    trimmed = trim_tail(audio)

    assert trimmed.samples.size == audio.samples.size


def test_trim_tail_handles_empty_audio() -> None:
    audio = Audio(samples=np.zeros(0, dtype=np.float32), sample_rate=24000)

    trimmed = trim_tail(audio)

    assert trimmed.samples.size == 0


def test_transcript_matches_true_when_everything_heard() -> None:
    words = [Word(text="Hello,", start=0.0, end=0.4), Word(text="world.", start=0.4, end=0.8)]

    ok, missing = transcript_matches("Hello world", words)

    assert ok is True
    assert missing == []


def test_transcript_matches_reports_missing_words() -> None:
    words = [Word(text="Hello", start=0.0, end=0.4)]

    ok, missing = transcript_matches("Hello world", words)

    assert ok is False
    assert missing == ["world"]


def test_transcript_matches_normalises_case_and_punctuation() -> None:
    words = [Word(text="HELLO", start=0.0, end=0.4), Word(text="world!!", start=0.4, end=0.8)]

    ok, missing = transcript_matches("hello, world.", words)

    assert ok is True
    assert missing == []


def test_transcript_matches_normalises_numbers_to_words() -> None:
    words = [Word(text="step", start=0.0, end=0.2), Word(text="two", start=0.2, end=0.4)]

    ok, missing = transcript_matches("step 2", words)

    assert ok is True
    assert missing == []
