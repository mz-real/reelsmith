"""Get a transcriber for the transcript vs script check.

Voice (T3) owns ``reelsmith.voice.transcribe`` on main. Until that lands,
or if it is missing for any other reason, this falls back to a small
wrapper around faster-whisper behind the same one function, so tests can
inject a fake transcriber either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reelsmith.errors import ReelsmithError

WHISPER_MODEL = "base.en"


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


class Transcriber(Protocol):
    """Transcribe a short audio file into timed words."""

    def __call__(self, audio_path: Path) -> list[Word]: ...


def get_transcriber(model_name: str = WHISPER_MODEL) -> Transcriber:
    """Return the best available transcriber.

    Prefers ``reelsmith.voice.transcribe.transcribe`` if that module can
    be imported. Otherwise returns a local faster-whisper wrapper, which
    raises a ReelsmithError with the install command the first time it is
    actually used without the dependency installed.
    """
    adapted = _from_voice_module()
    if adapted is not None:
        return adapted
    return _local_whisper_transcriber(model_name)


def _from_voice_module() -> Transcriber | None:
    try:
        from reelsmith.voice import transcribe as voice_transcribe  # type: ignore[import-untyped]
    except ImportError:
        return None
    fn = getattr(voice_transcribe, "transcribe", None)
    if not callable(fn):
        return None

    def _adapt(audio_path: Path) -> list[Word]:
        words = fn(audio_path)
        return [Word(text=w.text, start=w.start, end=w.end) for w in words]

    return _adapt


def _local_whisper_transcriber(model_name: str) -> Transcriber:
    def _transcribe(audio_path: Path) -> list[Word]:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ReelsmithError(
                "faster-whisper is not installed, so narration cannot be transcribed.",
                fix="uv pip install faster-whisper",
            ) from exc
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), word_timestamps=True)
        words: list[Word] = []
        for segment in segments:
            for word in segment.words or []:
                words.append(Word(text=word.word.strip(), start=word.start, end=word.end))
        return words

    return _transcribe
