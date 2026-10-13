"""Tests for per-line narration cleanup."""

from __future__ import annotations

import numpy as np
import pytest

from reelsmith.voice import clean
from reelsmith.voice.base import Audio
from reelsmith.voice.clean import (
    _LEAD_PAD_S,
    _downward_expander,
    _level_to_target,
    _spectral_denoise,
    _trim_after_last_word,
    finish_tail,
    process_body,
)
from reelsmith.voice.transcribe import Word


def _tone_with_noise(seconds: float, sample_rate: int, freq: float, noise: float) -> np.ndarray:
    count = int(seconds * sample_rate)
    t = np.arange(count, dtype=np.float32) / sample_rate
    tone = 0.4 * np.sin(2 * np.pi * freq * t)
    hiss = noise * np.random.default_rng(0).standard_normal(count).astype(np.float32)
    return (tone + hiss).astype(np.float32)


def test_process_body_adds_lead_pad_and_fade_in() -> None:
    sample_rate = 24000
    raw = _tone_with_noise(0.4, sample_rate, 440.0, 0.03)
    cleaned = process_body(Audio(raw, sample_rate))
    lead = int(0.10 * sample_rate)
    assert cleaned.samples.size > raw.size
    assert float(np.max(np.abs(cleaned.samples[:lead]))) < 1e-5
    assert float(np.abs(cleaned.samples[lead])) < float(np.abs(cleaned.samples[lead + 500]))


def test_finish_tail_cuts_a_click_after_the_last_word() -> None:
    sample_rate = 1000
    speech = np.full(500, 0.4, dtype=np.float32)
    click = np.full(100, 0.9, dtype=np.float32)
    tail = np.zeros(200, dtype=np.float32)
    samples = np.concatenate([speech, click, tail])
    words = [Word("hello", 0.0, 0.5)]
    trimmed, clipped, ok = finish_tail(Audio(samples, sample_rate), words, ["hello"], [])
    assert ok is True
    assert trimmed.samples.size < samples.size
    assert clipped[-1].end <= 0.55


def test_trim_after_last_word_leaves_audio_uncut_without_quiet_run() -> None:
    sample_rate = 1000
    samples = np.full(800, 0.4, dtype=np.float32)
    words = [Word("hello", 0.0, 0.5)]
    trimmed = _trim_after_last_word(samples, sample_rate, words)
    assert np.allclose(trimmed[: samples.size], samples)


RATE = 24000


def _bursts(amplitude: float, noise: float, seconds: float = 2.4) -> np.ndarray:
    """Speech-like bursts (0.3 to 0.8 s and 1.2 to 1.8 s) over steady broadband noise."""
    count = int(seconds * RATE)
    t = np.arange(count, dtype=np.float32) / RATE
    voice = amplitude * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 660 * t))
    mask = np.zeros(count, dtype=np.float32)
    for start, end in ((0.3, 0.8), (1.2, 1.8)):
        mask[int(start * RATE) : int(end * RATE)] = 1.0
    hiss = noise * np.random.default_rng(1).standard_normal(count).astype(np.float32)
    return (voice * mask + hiss).astype(np.float32)


def _window_db(samples: np.ndarray, start: float, end: float) -> np.ndarray:
    """Level in dB of each 20 ms window between start and end seconds."""
    size = int(0.020 * RATE)
    part = samples[int(start * RATE) : int(end * RATE)]
    part = part[: part.size // size * size].reshape(-1, size).astype(np.float64)
    rms = np.sqrt(np.mean(np.square(part), axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-12))


def test_between_bursts_the_line_is_never_digital_silence_and_the_floor_drops() -> None:
    raw = _bursts(0.2, 0.01)
    lead = int(round(_LEAD_PAD_S * RATE))

    cleaned = process_body(Audio(raw, RATE)).samples[lead:]

    before = _window_db(raw, 0.9, 1.1)
    after = _window_db(cleaned, 0.9, 1.1)
    assert float(after.min()) > -100.0
    assert float(np.median(after)) < float(np.median(before)) - 6.0


def test_the_floor_between_words_stays_steady_instead_of_switching() -> None:
    raw = _bursts(0.2, 0.01)
    lead = int(round(_LEAD_PAD_S * RATE))

    cleaned = process_body(Audio(raw, RATE)).samples[lead:]

    gap_a = _window_db(cleaned, 0.9, 1.1)
    gap_b = _window_db(cleaned, 1.9, 2.3)
    assert abs(float(np.median(gap_a)) - float(np.median(gap_b))) < 6.0


def test_the_expander_never_reduces_by_more_than_its_limit() -> None:
    raw = _bursts(0.2, 0.00001)

    expanded = _downward_expander(raw, RATE)

    before = _window_db(raw, 0.05, 0.25)
    after = _window_db(expanded, 0.05, 0.25)
    assert float(np.max(before - after)) <= 15.0
    assert float(np.max(before - after)) > 8.0


def test_the_expander_keeps_word_onsets() -> None:
    raw = _bursts(0.2, 0.0005)

    expanded = _downward_expander(raw, RATE)

    onset = slice(int(0.300 * RATE), int(0.306 * RATE))
    assert float(np.sqrt(np.mean(expanded[onset] ** 2))) > 0.9 * float(
        np.sqrt(np.mean(raw[onset] ** 2))
    )


def test_the_expander_closes_slowly_after_a_word() -> None:
    raw = _bursts(0.2, 0.0005)

    expanded = _downward_expander(raw, RATE)

    just_after = _window_db(raw, 0.81, 0.85) - _window_db(expanded, 0.81, 0.85)
    later = _window_db(raw, 1.0, 1.15) - _window_db(expanded, 1.0, 1.15)
    assert float(np.max(just_after)) < 6.0
    assert float(np.median(later)) > 9.0


def test_process_body_runs_the_expander(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def spy(samples: np.ndarray, sample_rate: int) -> np.ndarray:
        calls.append(sample_rate)
        return samples

    monkeypatch.setattr(clean, "_downward_expander", spy)

    process_body(Audio(_bursts(0.2, 0.01), RATE))

    assert calls == [RATE]


def test_levelling_stops_at_the_peak_ceiling() -> None:
    quiet = np.full(RATE, 0.02, dtype=np.float32)
    quiet[1000] = 0.6

    out = _level_to_target(quiet, RATE, -10.0)

    assert 0.88 <= float(np.max(np.abs(out))) <= 0.89 + 1e-6


def test_quiet_and_loud_takes_end_up_at_the_same_speech_level() -> None:
    quiet = process_body(Audio(_bursts(0.06, 0.001), RATE), -16.0).samples
    loud = process_body(Audio(_bursts(0.4, 0.001), RATE), -16.0).samples

    quiet_db = float(np.percentile(_window_db(quiet, 0.0, 2.5), 90))
    loud_db = float(np.percentile(_window_db(loud, 0.0, 2.5), 90))
    assert abs(quiet_db - loud_db) < 1.5


def test_levelling_does_not_clip_a_hot_take() -> None:
    hot = process_body(Audio(_bursts(0.9, 0.001), RATE), -10.0).samples

    assert float(np.max(np.abs(hot))) <= 0.9


def test_a_line_without_pauses_is_not_denoised_into_mush() -> None:
    t = np.arange(RATE, dtype=np.float32) / RATE
    tone = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

    out = _spectral_denoise(tone, RATE)

    assert np.array_equal(out, tone)
