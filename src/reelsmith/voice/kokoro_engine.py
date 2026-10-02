"""The Kokoro text to speech engine behind VoiceEngine."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.models_dl import KOKORO_INT8, KOKORO_VOICES, ensure_model

_kokoro_singleton: Any = None

# The int8 model quantizes the generator's source phase, which holds a few NaN
# values (atan of 0/0). onnxruntime's DynamicQuantizeLinear drops them when it
# finds the min and max in parallel, but a single threaded run keeps them, so
# the scale and then the whole waveform become NaN. onnxruntime's own default
# ends up single threaded on the 3 core macOS GitHub runner, so the thread
# count is always set, and never below two.
_MIN_INTRA_OP_THREADS = 2


def _session_options() -> Any:
    import onnxruntime as rt

    options = rt.SessionOptions()
    options.intra_op_num_threads = max(_MIN_INTRA_OP_THREADS, os.cpu_count() or 1)
    return options


def _load_kokoro() -> Any:
    global _kokoro_singleton
    if _kokoro_singleton is None:
        try:
            import onnxruntime as rt
            from kokoro_onnx import Kokoro
            from kokoro_onnx.session import resolve_providers
        except ImportError as exc:
            raise ReelsmithError(
                "kokoro-onnx is not installed.",
                fix="uv pip install kokoro-onnx",
            ) from exc
        model_path = ensure_model(KOKORO_INT8.filename)
        voices_path = ensure_model(KOKORO_VOICES.filename)
        session = rt.InferenceSession(
            str(model_path),
            sess_options=_session_options(),
            providers=resolve_providers(),
        )
        _kokoro_singleton = Kokoro.from_session(session, str(voices_path))
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
        try:
            samples, sample_rate = kokoro.create(
                text, voice=self.voice, speed=effective_speed, lang=self.lang
            )
        except ValueError as exc:
            raise ReelsmithError(
                f"Kokoro could not synthesize {text!r}: {exc}",
                fix="reelsmith doctor",
            ) from exc
        audio = np.asarray(samples, dtype=np.float32)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise ReelsmithError(
                f"Kokoro produced silent or invalid audio for {text!r}.",
                fix="reelsmith doctor",
            )
        return Audio(samples=audio, sample_rate=int(sample_rate))
