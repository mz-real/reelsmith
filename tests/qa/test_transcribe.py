"""Tests for the transcriber wrapper used by the transcript vs script check."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.qa.transcribe import Word


def test_word_is_a_plain_text_start_end_record() -> None:
    word = Word(text="hello", start=0.0, end=0.4)
    assert word.text == "hello"
    assert word.end > word.start


def test_voice_adapter_passes_audio_not_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    import soundfile as sf

    from reelsmith.qa import transcribe as qa_transcribe
    from reelsmith.voice import transcribe as voice_transcribe
    from reelsmith.voice.base import Audio

    wav = tmp_path / "line.wav"
    sf.write(wav, np.zeros((2400, 2), dtype="float32"), 24000)
    seen: list[object] = []

    def fake(audio: object) -> list[voice_transcribe.Word]:
        seen.append(audio)
        return [voice_transcribe.Word(text="hello", start=0.0, end=0.1)]

    monkeypatch.setattr(voice_transcribe, "transcribe", fake)
    words = qa_transcribe.get_transcriber()(wav)

    assert isinstance(seen[0], Audio)
    assert seen[0].samples.ndim == 1
    assert words[0].text == "hello"


def test_voice_adapter_passes_the_vocabulary_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    import soundfile as sf

    from reelsmith.qa import transcribe as qa_transcribe
    from reelsmith.voice import transcribe as voice_transcribe

    wav = tmp_path / "line.wav"
    sf.write(wav, np.zeros(2400, dtype="float32"), 24000)
    seen: list[object] = []

    def fake(audio: object, vocabulary: object = None) -> list[voice_transcribe.Word]:
        seen.append(vocabulary)
        return []

    monkeypatch.setattr(voice_transcribe, "transcribe", fake)
    qa_transcribe.get_transcriber(["reelsmith", "Kokoro"])(wav)

    assert seen == [["reelsmith", "Kokoro"]]
