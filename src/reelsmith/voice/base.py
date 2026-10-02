"""Shared voice types: the audio container and the engine protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel


@dataclass
class Audio:
    """Mono audio samples as float32, at the given sample rate."""

    samples: np.ndarray
    sample_rate: int


class VoiceEngine(Protocol):
    """A text to speech engine behind one interface.

    seed lets a caller ask for a different take of the same line. Not
    every engine has a real random seed: see kokoro_engine for how Kokoro
    approximates one.
    """

    name: str

    def synthesize(self, text: str, seed: int) -> Audio: ...


def get_engine(spec: SpecModel) -> VoiceEngine:
    """Build the voice engine named in spec.yaml."""
    engine_name = spec.voice.engine
    if engine_name == "kokoro":
        from reelsmith.voice.kokoro_engine import KokoroEngine

        return KokoroEngine(voice=spec.voice.kokoro_voice, speed=spec.voice.speed)
    if engine_name == "chatterbox":
        raise ReelsmithError(
            "Chatterbox voice cloning is not installed.",
            fix='uv tool install "reelsmith[clone]"',
        )
    if engine_name == "none":
        raise ReelsmithError(
            "spec.yaml sets voice.engine to none, so there is no narration to generate."
        )
    raise ReelsmithError(f"Unknown voice engine in spec.yaml: {engine_name}")
