"""A real test that runs actual Kokoro synthesis and Whisper transcription.

This downloads the Kokoro and faster-whisper model files into the user
cache on first run, so it only runs when REELSMITH_TEST_MODELS=1 is set.
"""

from __future__ import annotations

import os

import pytest

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
