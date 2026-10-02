"""A real test that runs actual Kokoro synthesis and Whisper transcription.

This downloads the Kokoro and faster-whisper model files into the user
cache on first run, so it only runs when REELSMITH_TEST_MODELS=1 is set.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from reelsmith.voice import kokoro_engine
from reelsmith.voice.kokoro_engine import KokoroEngine
from reelsmith.voice.quality import pace_ok, transcript_matches, trim_tail, words_per_minute
from reelsmith.voice.transcribe import transcribe

pytestmark = pytest.mark.skipif(
    os.environ.get("REELSMITH_TEST_MODELS") != "1",
    reason="set REELSMITH_TEST_MODELS=1 to run the real Kokoro and Whisper test",
)


@pytest.mark.models
def test_kokoro_line_is_read_back_correctly_by_whisper() -> None:
    text = "Type a dish into the search box."
    engine = KokoroEngine(voice="af_heart", speed=1.0)

    audio = engine.synthesize(text, seed=0)
    audio = trim_tail(audio)

    duration = audio.samples.size / audio.sample_rate
    wpm = words_per_minute(text, duration)
    # A wide window: this checks Kokoro and Whisper work together, not the
    # production pace policy, which is tested separately in test_quality.py.
    assert pace_ok(wpm, low=60.0, high=400.0)

    words = transcribe(audio)
    ok, missing = transcript_matches(text, words)
    assert ok, f"missing words: {missing}"


@pytest.mark.models
def test_pronounce_changes_the_phonemes_passed_to_kokoro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the map, Kokoro is asked to speak different phonemes for the line.

    This uses the real espeak backed tokenizer to phonemize "Made with
    reelsmith." with and without voice.pronounce, and only replaces the
    ONNX model call so the test does not need to judge the audio by ear.
    The fact that the two calls differ, and that the mapped one reads
    phonemes instead of text, is what makes the fix real.
    """
    text = "Made with reelsmith."
    captured: list[dict[str, object]] = []

    class _RecordingKokoro:
        def create(self, text: str, **kwargs: object) -> tuple[np.ndarray, int]:
            captured.append({"text": text, **kwargs})
            return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr(kokoro_engine, "_load_kokoro", lambda: _RecordingKokoro())

    plain_engine = KokoroEngine(voice="af_heart")
    plain_engine.synthesize(text, seed=0)

    mapped_engine = KokoroEngine(voice="af_heart", pronounce={"reelsmith": "ɹˈiːl smɪθ"})
    mapped_engine.synthesize(text, seed=0)

    assert captured[0]["is_phonemes"] is False
    assert captured[0]["text"] == text
    assert captured[1]["is_phonemes"] is True
    assert captured[1]["text"] != captured[0]["text"]
    assert "ɹˈiːl smɪθ" in str(captured[1]["text"])
