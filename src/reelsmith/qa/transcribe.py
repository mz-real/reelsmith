"""Get a transcriber for the transcript vs script check.

QA reuses the voice step's faster-whisper transcriber, which takes
decoded audio. This adapter reads a wav file into that form, so the
check can work on file paths and tests can inject a fake.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from reelsmith.voice import transcribe as voice_transcribe
from reelsmith.voice.base import Audio


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


class Transcriber(Protocol):
    """Transcribe a short audio file into timed words."""

    def __call__(self, audio_path: Path) -> list[Word]: ...


def load_audio(path: Path) -> Audio:
    """Read a wav file as float32 mono."""
    samples, rate = sf.read(path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1).astype(np.float32)
    return Audio(samples=samples, sample_rate=int(rate))


def get_transcriber(vocabulary: Sequence[str] = ()) -> Transcriber:
    """Return a transcriber that takes a wav path.

    vocabulary is passed on as speech model hints, the same ones the
    voice step uses (see voice/transcribe.py).
    """
    hints = list(vocabulary)

    def _transcribe(audio_path: Path) -> list[Word]:
        audio = load_audio(audio_path)
        if hints:
            words = voice_transcribe.transcribe(audio, vocabulary=hints)
        else:
            words = voice_transcribe.transcribe(audio)
        return [Word(text=w.text, start=w.start, end=w.end) for w in words]

    return _transcribe
