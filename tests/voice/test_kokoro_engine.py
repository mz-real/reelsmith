"""Tests for the Kokoro engine's seed to speed jitter.

Kokoro has no seed parameter, so a "new seed" retry is approximated with a
small speed jitter instead. See _jittered_speed in kokoro_engine.py.
"""

from __future__ import annotations

from typing import Any

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


class _RecordingKokoro:
    """Records every call to create, instead of actually synthesizing."""

    def __init__(self, samples: np.ndarray, sample_rate: int = 24000) -> None:
        self.samples = samples
        self.sample_rate = sample_rate
        self.calls: list[dict[str, object]] = []

    def create(self, text: str, **kwargs: object) -> tuple[np.ndarray, int]:
        self.calls.append({"text": text, **kwargs})
        return self.samples, self.sample_rate


class _FakeTokenizer:
    """Returns canned phonemes for known text, as espeak would."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def phonemize(self, text: str, lang: str) -> str:
        return self.mapping[text]


def _samples() -> np.ndarray:
    return np.linspace(-0.1, 0.1, 2400, dtype=np.float32)


def test_pronounce_replaces_the_word_phonemes_on_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kokoro = _RecordingKokoro(_samples())
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: kokoro)
    tokenizer = _FakeTokenizer(
        {
            "Made with reelsmith.": "mˈeɪd wɪð ɹˈiːlsmɪθ.",
            "reelsmith": "ɹˈiːlsmɪθ",
        }
    )
    monkeypatch.setattr(kokoro_engine, "_load_tokenizer", lambda: tokenizer)
    engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})

    audio = engine.synthesize("Made with reelsmith.", seed=0)

    call = kokoro.calls[0]
    assert call["is_phonemes"] is True
    assert call["text"] == "mˈeɪd wɪð ɹˈiːl smɪθ."
    assert audio.warning is None


def test_pronounce_does_not_touch_a_longer_word_sharing_the_same_phonemes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "reelsmithy" embeds the same phonemes as "reelsmith" without a
    # boundary around them, so they must not be replaced.
    kokoro = _RecordingKokoro(_samples())
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: kokoro)
    tokenizer = _FakeTokenizer(
        {
            "Say reelsmith here.": "sˈeɪ ɹˈiːlsmɪθ hˈɪɹ.",
            "reelsmith": "ɹˈiːlsmɪθ",
        }
    )
    monkeypatch.setattr(kokoro_engine, "_load_tokenizer", lambda: tokenizer)
    engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})

    engine.synthesize("Say reelsmith here.", seed=0)

    call = kokoro.calls[0]
    assert call["text"] == "sˈeɪ ɹˈiːl smɪθ hˈɪɹ."


def test_pronounce_is_case_insensitive_on_the_word(monkeypatch: pytest.MonkeyPatch) -> None:
    kokoro = _RecordingKokoro(_samples())
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: kokoro)
    tokenizer = _FakeTokenizer(
        {
            "Made with Reelsmith.": "mˈeɪd wɪð ɹˈiːlsmɪθ.",
            "reelsmith": "ɹˈiːlsmɪθ",
        }
    )
    monkeypatch.setattr(kokoro_engine, "_load_tokenizer", lambda: tokenizer)
    engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})

    engine.synthesize("Made with Reelsmith.", seed=0)

    assert kokoro.calls[0]["text"] == "mˈeɪd wɪð ɹˈiːl smɪθ."


def test_pronounce_falls_back_to_plain_text_when_context_changes_the_phonemes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kokoro = _RecordingKokoro(_samples())
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: kokoro)
    # espeak phonemizes "reelsmith" differently in this sentence than it
    # does alone, so the expected substring is not found in the line.
    tokenizer = _FakeTokenizer(
        {
            "Made with reelsmith.": "mˈeɪd wɪð ɹˈiːlsmɪθz.",
            "reelsmith": "ɹˈiːlsmɪθ",
        }
    )
    monkeypatch.setattr(kokoro_engine, "_load_tokenizer", lambda: tokenizer)
    engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})

    audio = engine.synthesize("Made with reelsmith.", seed=0)

    call = kokoro.calls[0]
    assert call["is_phonemes"] is False
    assert call["text"] == "Made with reelsmith."
    assert audio.warning is not None
    assert "reelsmith" in audio.warning


def test_pronounce_leaves_a_line_without_the_word_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kokoro = _RecordingKokoro(_samples())
    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: kokoro)

    def _boom(*args: object, **kwargs: object) -> Any:
        raise AssertionError("should not phonemize a line without a mapped word")

    monkeypatch.setattr(kokoro_engine, "_load_tokenizer", _boom)
    engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})

    audio = engine.synthesize("Hello there.", seed=0)

    call = kokoro.calls[0]
    assert call["is_phonemes"] is False
    assert call["text"] == "Hello there."
    assert audio.warning is None
