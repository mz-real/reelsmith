"""Tests for the transcriber wrapper used by the transcript vs script check."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.qa.transcribe import Word, get_transcriber


def test_falls_back_to_local_whisper_wrapper_when_voice_module_is_absent() -> None:
    # reelsmith.voice does not exist yet (T3 has not merged), so this must
    # return a callable instead of raising at import time.
    transcriber = get_transcriber()
    assert callable(transcriber)


def test_local_wrapper_raises_a_clear_error_without_faster_whisper(tmp_path: Path) -> None:
    transcriber = get_transcriber()
    audio = tmp_path / "line.wav"
    audio.write_bytes(b"")

    with pytest.raises(ReelsmithError) as info:
        transcriber(audio)

    assert "faster-whisper" in str(info.value)
    assert info.value.fix is not None
    assert "faster-whisper" in info.value.fix


def test_word_is_a_plain_text_start_end_record() -> None:
    word = Word(text="hello", start=0.0, end=0.4)
    assert word.text == "hello"
    assert word.end > word.start
