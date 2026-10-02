"""Tests for the Kokoro engine's seed to speed jitter.

Kokoro has no seed parameter, so a "new seed" retry is approximated with a
small speed jitter instead. See _jittered_speed in kokoro_engine.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.voice import kokoro_engine
from reelsmith.voice.kokoro_engine import KokoroEngine, _jittered_speed


def test_seed_zero_keeps_the_original_speed() -> None:
    assert _jittered_speed(1.0, 0) == 1.0


def test_odd_seeds_speed_up() -> None:
    assert _jittered_speed(1.0, 1) == pytest.approx(1.03)


def test_even_seeds_slow_down() -> None:
    assert _jittered_speed(1.0, 2) == pytest.approx(0.97)


def test_jitter_grows_with_seed() -> None:
    assert _jittered_speed(1.0, 3) == pytest.approx(1.06)
    assert _jittered_speed(1.0, 4) == pytest.approx(0.94)


def test_jitter_scales_with_base_speed() -> None:
    assert _jittered_speed(2.0, 1) == pytest.approx(2.06)


def test_kokoro_engine_exposes_its_name() -> None:
    engine = KokoroEngine(voice="af_heart")
    assert engine.name == "kokoro"


class _FakeKokoro:
    def __init__(self, result: object) -> None:
        self.result = result

    def create(self, text: str, **kwargs: object) -> tuple[np.ndarray, int]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result, 24000  # type: ignore[return-value]


def test_session_uses_at_least_two_threads_on_a_single_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A single threaded run of the int8 model turns the whole waveform into
    # NaN, so even a one core machine must not get one intra op thread
    monkeypatch.setattr(kokoro_engine.os, "cpu_count", lambda: 1)
    assert kokoro_engine._session_options().intra_op_num_threads == 2


def test_session_uses_every_core_when_there_are_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_engine.os, "cpu_count", lambda: 8)
    assert kokoro_engine._session_options().intra_op_num_threads == 8


def test_nan_audio_raises_a_reelsmith_error(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = np.full(2400, np.nan, dtype=np.float32)
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: _FakeKokoro(samples))
    with pytest.raises(ReelsmithError, match="silent or invalid audio"):
        KokoroEngine(voice="af_heart").synthesize("Hello.", seed=0)


def test_empty_audio_raises_a_reelsmith_error(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = np.zeros(0, dtype=np.float32)
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: _FakeKokoro(samples))
    with pytest.raises(ReelsmithError, match="silent or invalid audio"):
        KokoroEngine(voice="af_heart").synthesize("Hello.", seed=0)


def test_a_kokoro_value_error_becomes_a_reelsmith_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = ValueError("zero-size array to reduction operation maximum")
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: _FakeKokoro(failure))
    with pytest.raises(ReelsmithError, match="Kokoro could not synthesize") as info:
        KokoroEngine(voice="af_heart").synthesize("Hello.", seed=0)
    assert info.value.__cause__ is failure


def test_good_audio_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = np.linspace(-0.1, 0.1, 2400, dtype=np.float32)
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: _FakeKokoro(samples))
    audio = KokoroEngine(voice="af_heart").synthesize("Hello.", seed=0)
    assert audio.sample_rate == 24000
    assert np.array_equal(audio.samples, samples)
