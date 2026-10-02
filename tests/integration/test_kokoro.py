"""Kokoro synthesis read back through Whisper."""

from __future__ import annotations

import os

import pytest

from reelsmith.voice.kokoro_engine import KokoroEngine
from reelsmith.voice.quality import pace_ok, transcript_matches, trim_tail, words_per_minute
from reelsmith.voice.transcribe import transcribe

pytestmark = [
    pytest.mark.integration,
    pytest.mark.models,
    pytest.mark.skipif(
        os.environ.get("REELSMITH_TEST_MODELS") != "1",
        reason="set REELSMITH_TEST_MODELS=1 to run model integration tests",
    ),
]


def test_kokoro_line_is_plausible_and_matches_whisper() -> None:
    text = "Type a dish into the search box."
    engine = KokoroEngine(voice="af_heart", speed=1.0)
    audio = trim_tail(engine.synthesize(text, seed=0))

    duration = audio.samples.size / audio.sample_rate
    assert 1.0 < duration < 8.0
    wpm = words_per_minute(text, duration)
    assert pace_ok(wpm, low=60.0, high=400.0)

    words = transcribe(audio)
    ok, missing = transcript_matches(text, words)
    assert ok, f"missing words: {missing}"
