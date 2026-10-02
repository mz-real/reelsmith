"""Tests for reelsmith.voice.reference, on synthetic speech like audio."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.reference import (
    pick_reference,
    score_window,
    syllable_rate,
)

SR = 24000


def speechlike(
    seconds: float, rate: float = 4.0, amp: float = 0.4, seed: int = 0, pauses: bool = True
) -> np.ndarray:
    """Voiced bursts at `rate` syllables a second over a very quiet floor.

    Every fourth syllable is left out, like the gaps between phrases.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    carrier = (
        np.sin(2 * np.pi * 140 * t)
        + 0.5 * np.sin(2 * np.pi * 280 * t)
        + 0.25 * np.sin(2 * np.pi * 560 * t)
    ) / 1.75
    lobes = np.sin(np.pi * rate * t) ** 2
    if pauses:
        syllable = np.floor(t * rate).astype(int)
        lobes = np.where(syllable % 4 == 3, 0.0, lobes)
    floor = rng.normal(0.0, 1e-4, t.size)
    return (amp * carrier * lobes + floor).astype(np.float32)


def noisy(seconds: float, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (speechlike(seconds) + rng.normal(0.0, 0.06, int(seconds * SR))).astype(np.float32)


def clipped(seconds: float) -> np.ndarray:
    return np.clip(speechlike(seconds, amp=1.6), -1.0, 1.0).astype(np.float32)


def test_syllable_rate_tracks_the_burst_rate() -> None:
    assert syllable_rate(speechlike(10, rate=4.0, pauses=False), SR) == pytest.approx(4.0, abs=0.5)
    assert syllable_rate(speechlike(10, rate=8.0, pauses=False), SR) == pytest.approx(8.0, abs=1.0)


def test_clean_window_scores_well() -> None:
    score = score_window(speechlike(12), SR, start=0.0)
    assert score.clipped_samples == 0
    assert score.noise_floor_db < -60
    assert 0.4 < score.speech_ratio < 0.95
    assert score.pace_score == pytest.approx(1.0)
    assert score.total > 0.8


def test_noise_lowers_the_noise_and_speech_scores() -> None:
    clean = score_window(speechlike(12), SR, start=0.0)
    hiss = score_window(noisy(12), SR, start=0.0)
    assert hiss.noise_floor_db > clean.noise_floor_db + 20
    assert hiss.noise_score < clean.noise_score
    assert hiss.total < clean.total


def test_clipping_is_counted_at_099() -> None:
    samples = speechlike(12)
    samples[1000] = 0.99
    assert score_window(samples, SR, start=0.0).clipped_samples == 1
    assert score_window(clipped(12), SR, start=0.0).clip_score == 0.0


def test_a_fast_window_loses_on_pace() -> None:
    steady = score_window(speechlike(12, rate=4.0), SR, start=0.0)
    rushed = score_window(speechlike(12, rate=9.0), SR, start=0.0)
    assert rushed.pace_score < steady.pace_score


def test_pick_reference_finds_the_clean_stretch() -> None:
    recording = np.concatenate([noisy(14), clipped(14), speechlike(14, seed=5), noisy(14, 7)])
    pick = pick_reference(Audio(recording, SR), seconds=12)

    assert 28.0 <= pick.best.start <= 30.0
    assert pick.best.end == pytest.approx(pick.best.start + 12)
    assert pick.best.clipped_samples == 0
    assert pick.audio.sample_rate == SR
    assert pick.audio.samples.size == 12 * SR
    assert any("clipping" in reason for reason in pick.reasons)
    assert any("noise floor" in reason for reason in pick.reasons)
    assert pick.windows > 10


def test_pick_reference_resamples_to_24k() -> None:
    sr = 16000
    t = np.arange(13 * sr) / sr
    lobes = np.sin(np.pi * 4 * t) ** 2
    samples = (0.4 * np.sin(2 * np.pi * 140 * t) * lobes).astype(np.float32)
    pick = pick_reference(Audio(samples, sr), seconds=12)
    assert pick.audio.sample_rate == 24000
    assert pick.audio.samples.size == 12 * 24000


def test_a_short_recording_uses_all_of_it_with_a_note() -> None:
    pick = pick_reference(Audio(speechlike(8), SR), seconds=12)
    assert pick.best.start == 0.0
    assert pick.best.end == pytest.approx(8.0)
    assert any("shorter" in note for note in pick.notes)


def test_a_tiny_recording_is_an_error() -> None:
    with pytest.raises(ReelsmithError, match="too short"):
        pick_reference(Audio(speechlike(2), SR), seconds=12)


def test_pick_reference_cli_writes_24k_mono(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from reelsmith.cli import app

    source = tmp_path / "my voice note.wav"
    stereo = np.stack([speechlike(16), speechlike(16)], axis=1)
    sf.write(source, stereo, 48000 // 2)
    out = tmp_path / "ref.wav"
    out.write_bytes(b"old")

    result = CliRunner().invoke(
        app, ["voice", "pick-reference", str(source), "--out", str(out), "--seconds", "12"]
    )

    assert result.exit_code == 0, result.output
    assert "[OK]" in result.output
    data, rate = sf.read(out)
    assert rate == 24000
    assert data.ndim == 1
    assert data.size == 12 * 24000
    assert list(tmp_path.glob("ref.wav.bak-*")), "the old file is backed up, not overwritten"
    assert "Picked" in result.output
    assert " to " in result.output


def test_pick_reference_cli_rejects_odd_lengths(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from reelsmith.cli import app

    source = tmp_path / "a.wav"
    sf.write(source, speechlike(16), SR)
    result = CliRunner().invoke(app, ["voice", "pick-reference", str(source), "--seconds", "2"])
    assert result.exit_code != 0
