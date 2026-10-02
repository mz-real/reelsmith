"""Local transcription with faster-whisper, used for the dropped word check.

Audio is passed to faster-whisper as a numpy array, not a file path. A file
path is decoded with PyAV, and the installed PyAV release often does not
match what faster-whisper expects, which raises a confusing TypeError. A
plain array is used as is and skips that decode step entirely.

The speech model gets a short list of vocabulary hints (faster-whisper's
hotwords): product names and other rare words from spec.yaml and the
script. It never gets the expected sentence. Given the sentence, Whisper
can write it out even when a word was not spoken, which would hide the
very dropped words this check exists to catch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.models import ScriptModel, SpecModel
from reelsmith.text import vocabulary_words
from reelsmith.voice.base import Audio
from reelsmith.voice.models_dl import models_dir

WHISPER_MODEL = "base.en"
_TARGET_SAMPLE_RATE = 16000
# Whisper's prompt holds about 220 tokens, so the hint list stays short.
MAX_HINTS = 40


def whisper_model_cache_dir() -> Path:
    """Folder faster-whisper creates under ``models_dir()`` for ``WHISPER_MODEL``."""
    return models_dir() / f"models--Systran--faster-whisper-{WHISPER_MODEL}"


_model_singleton: Any = None


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


def _load_model() -> Any:
    global _model_singleton
    if _model_singleton is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ReelsmithError(
                "faster-whisper is not installed.",
                fix="uv pip install faster-whisper",
            ) from exc
        model_dir = models_dir()
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            _model_singleton = WhisperModel(
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
                download_root=str(model_dir),
            )
        except Exception as exc:
            raise ReelsmithError(
                f"Could not load the {WHISPER_MODEL} speech model: {exc}",
                fix="Check your network connection, then run the command again.",
            ) from exc
    return _model_singleton


def _resample(samples: np.ndarray, orig_sample_rate: int, target_sample_rate: int) -> np.ndarray:
    """A plain linear resample, good enough for speech before transcription."""
    if orig_sample_rate == target_sample_rate or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / orig_sample_rate
    target_length = max(1, int(round(duration * target_sample_rate)))
    orig_times = np.linspace(0.0, duration, samples.size, endpoint=False)
    target_times = np.linspace(0.0, duration, target_length, endpoint=False)
    resampled = np.interp(target_times, orig_times, samples).astype(np.float32)
    return cast(np.ndarray, resampled)


def vocabulary_hints(spec: SpecModel, script: ScriptModel) -> list[str]:
    """voice.vocabulary from spec.yaml, then the uncommon words the voice reads.

    Words come from say where a phrase has one, since that is what is
    spoken. Repeats are dropped, ignoring case, and the list is capped.
    """
    spoken = [line.spoken_text for scene in script.scenes for line in scene.lines]
    hints: list[str] = []
    seen: set[str] = set()
    for word in [*spec.voice.vocabulary, *vocabulary_words(spoken)]:
        cleaned = word.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            hints.append(cleaned)
    return hints[:MAX_HINTS]


def transcribe(audio: Audio, vocabulary: Sequence[str] | None = None) -> list[Word]:
    """Transcribe narration audio and return each word with its timing.

    vocabulary is passed as hotwords, a comma separated list of words.
    A plain list keeps the model writing normal sentence case; it is
    never the expected sentence.
    """
    model = _load_model()
    samples = _resample(audio.samples, audio.sample_rate, _TARGET_SAMPLE_RATE)
    options: dict[str, Any] = {"word_timestamps": True}
    if vocabulary:
        options["hotwords"] = ", ".join(vocabulary)
    segments, _info = model.transcribe(samples, **options)
    words: list[Word] = []
    for segment in segments:
        for word in segment.words or []:
            words.append(Word(text=word.word.strip(), start=float(word.start), end=float(word.end)))
    return words
