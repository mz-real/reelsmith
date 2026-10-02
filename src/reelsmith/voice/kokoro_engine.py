"""The Kokoro text to speech engine behind VoiceEngine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.models_dl import KOKORO_INT8, KOKORO_VOICES, ensure_model

_kokoro_singleton: Any = None


def _load_kokoro() -> Any:
    global _kokoro_singleton
    if _kokoro_singleton is None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise ReelsmithError(
                "kokoro-onnx is not installed.",
                fix="uv pip install kokoro-onnx",
            ) from exc
        model_path = ensure_model(KOKORO_INT8.filename)
        voices_path = ensure_model(KOKORO_VOICES.filename)
        _kokoro_singleton = Kokoro(str(model_path), str(voices_path))
    return _kokoro_singleton


def _jittered_speed(base_speed: float, seed: int) -> float:
    """Approximate a "new seed" retry as a small speed jitter.

    Kokoro has no seed parameter, so there is no way to ask it for a
    genuinely different take of the same line. Instead, each retry nudges
    the speed by three percent per step, alternating slower and faster, so
    repeated synthesis of the same text is not bit for bit identical. seed
    0 is the caller's original speed, unchanged.
    """
    if seed <= 0:
        return base_speed
    sign = 1 if seed % 2 == 1 else -1
    step = (seed + 1) // 2
    return base_speed * (1 + sign * 0.03 * step)


@dataclass
class KokoroEngine:
    """Synthesizes narration with a Kokoro stock voice."""

    voice: str
    speed: float = 1.0
    lang: str = "en-us"
    name: str = "kokoro"

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        kokoro = _load_kokoro()
        effective_speed = speed if speed is not None else _jittered_speed(self.speed, seed)
        samples, sample_rate = kokoro.create(
            text, voice=self.voice, speed=effective_speed, lang=self.lang
        )
        return Audio(samples=np.asarray(samples, dtype=np.float32), sample_rate=int(sample_rate))
