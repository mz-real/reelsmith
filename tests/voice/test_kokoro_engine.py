"""Tests for the Kokoro engine's seed to speed jitter.

Kokoro has no seed parameter, so a "new seed" retry is approximated with a
small speed jitter instead. See _jittered_speed in kokoro_engine.py.
"""

from __future__ import annotations

import pytest

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
