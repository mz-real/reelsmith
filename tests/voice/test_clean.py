"""Tests for per-line narration cleanup."""

from __future__ import annotations

import numpy as np

from reelsmith.voice.base import Audio
from reelsmith.voice.clean import _trim_after_last_word, finish_tail, process_body
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
