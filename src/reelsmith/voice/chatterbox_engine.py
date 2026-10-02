"""The Chatterbox own voice engine behind VoiceEngine.

Cloning a voice is opt in. The engine refuses to run unless consent is
"own" or "permission" and the voice sample exists, even if spec.yaml was
built without validation. Chatterbox's built in watermark stays on: there
is no setting to turn it off, and a model without its watermarker is
refused.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import typer

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio

CONSENT_VALUES = ("own", "permission")
CLONE_FIX = 'uv tool install "reelsmith[clone]"'
CPU_WARNING = (
    "WARN: no GPU found, so Chatterbox runs on the CPU. Expect it to be slow, "
    "often a minute or more per line."
)
PRONOUNCE_WARNING = (
    "WARN: Chatterbox cannot read phonemes, so voice.pronounce is ignored. "
    "Spell the word the way it sounds in the phrase's say instead."
)

_models: dict[str, Any] = {}


def check_consent(consent: str | None, sample: Path) -> None:
    """Raise unless consent is own or permission and the sample exists."""
    if consent not in CONSENT_VALUES:
        raise ReelsmithError(
            "Own voice cloning needs consent. Set voice.consent in spec.yaml to own "
            "or permission, and only if that is true.",
            fix="Edit voice.consent in spec.yaml",
        )
    if not sample.is_file():
        raise ReelsmithError(
            f"The voice sample {sample} was not found.",
            fix="reelsmith voice pick-reference <recording> --out ref.wav",
        )


def _import_chatterbox() -> tuple[Any, Any]:
    if sys.version_info >= (3, 13):
        raise ReelsmithError(
            "Own voice cloning needs Python 3.11 or 3.12. Chatterbox does not run on 3.13 yet.",
            fix='uv tool install --python 3.12 "reelsmith[clone]"',
        )
    try:
        torch = importlib.import_module("torch")
        tts = importlib.import_module("chatterbox.tts")
    except ImportError as exc:
        raise ReelsmithError("Own voice cloning needs the clone extra.", fix=CLONE_FIX) from exc
    return torch, tts.ChatterboxTTS


def pick_device(torch: Any) -> str:
    """CUDA if there is one, else Apple MPS, else the CPU."""
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def _load_model(torch: Any, tts_class: Any) -> Any:
    device = pick_device(torch)
    model = _models.get(device)
    if model is None:
        if device == "cpu":
            typer.echo(CPU_WARNING, err=True)
        model = tts_class.from_pretrained(device=device)
        if getattr(model, "watermarker", None) is None:
            raise ReelsmithError(
                "This Chatterbox build has no watermarker, so reelsmith will not use it. "
                "Cloned narration must stay watermarked.",
                fix=f"Reinstall the official package: {CLONE_FIX}",
            )
        _models[device] = model
    return model


def _to_mono_float32(wav: Any) -> np.ndarray:
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    return np.asarray(wav, dtype=np.float32).reshape(-1)


def _sample_digest(sample: Path) -> str:
    return hashlib.sha256(sample.read_bytes()).hexdigest()[:12]


@dataclass
class ChatterboxEngine:
    """Reads narration in a cloned voice from a short reference sample."""

    sample: Path
    consent: str | None
    # Accepted for a common interface with KokoroEngine. Chatterbox cannot
    # take phonemes, so this is ignored, with a warning, by synthesize.
    pronounce: Mapping[str, str] = field(default_factory=dict)
    name: str = "chatterbox"
    voice_id: str = field(init=False, default="")

    def __post_init__(self) -> None:
        check_consent(self.consent, self.sample)
        self.voice_id = f"{self.sample.name}:{_sample_digest(self.sample)}"
        if self.pronounce:
            typer.echo(PRONOUNCE_WARNING, err=True)

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        # Chatterbox has no setting for how fast it reads a cloned voice,
        # so speed is accepted for a common interface with other engines
        # and otherwise ignored.
        check_consent(self.consent, self.sample)
        torch, tts_class = _import_chatterbox()
        model = _load_model(torch, tts_class)
        torch.manual_seed(seed)
        wav = model.generate(text, audio_prompt_path=str(self.sample))
        return Audio(samples=_to_mono_float32(wav), sample_rate=int(model.sr))
