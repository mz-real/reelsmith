"""The Kokoro text to speech engine behind VoiceEngine."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.models_dl import KOKORO_INT8, KOKORO_VOICES, ensure_model

_kokoro_singleton: Any = None
_tokenizer_singleton: Any = None

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


def _load_tokenizer() -> Any:
    global _tokenizer_singleton
    if _tokenizer_singleton is None:
        try:
            from kokoro_onnx.tokenizer import Tokenizer
        except ImportError as exc:
            raise ReelsmithError(
                "kokoro-onnx is not installed.",
                fix="uv pip install kokoro-onnx",
            ) from exc
        _tokenizer_singleton = Tokenizer()
    return _tokenizer_singleton


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


def _word_pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)


def _phoneme_boundary_pattern(phonemes: str) -> re.Pattern[str]:
    """A pattern matching phonemes only on a word boundary.

    Python's regex treats IPA letters and stress marks as word characters,
    the same as plain letters, so \\b marks a boundary around a word's
    phonemes correctly, including when punctuation follows with no space
    ("ɹˈiːlsmɪθ." still matches on a boundary before the full stop). This
    keeps a short word's phonemes from being replaced when they are only
    part of a longer one embedded in the line.
    """
    return re.compile(rf"\b{re.escape(phonemes)}\b")


@dataclass
class KokoroEngine:
    """Synthesizes narration with a Kokoro stock voice."""

    voice: str
    speed: float = 1.0
    lang: str = "en-us"
    # A word (case insensitive, whole word) to the phonemes it should be
    # read as. See voice.pronounce in spec.yaml.
    pronounce: Mapping[str, str] = field(default_factory=dict)
    name: str = "kokoro"
    _word_phonemes: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def _matched_words(self, text: str) -> list[str]:
        """The pronounce keys (lower case) that appear as whole words in text."""
        return [word for word in self.pronounce if _word_pattern(word).search(text)]

    def _phonemes_for_word(self, tokenizer: Any, word: str) -> str:
        cached = self._word_phonemes.get(word)
        if cached is None:
            cached = str(tokenizer.phonemize(word, self.lang))
            self._word_phonemes[word] = cached
        return cached

    def _phonemized_line(self, tokenizer: Any, text: str, matched: list[str]) -> tuple[str, str]:
        """Replace each matched word's phonemes in the line with its mapping.

        Returns the resulting phonemes and the word whose phonemes could
        not be found in context, or an empty string when every word was
        replaced.
        """
        line_phonemes = str(tokenizer.phonemize(text, self.lang))
        for word in matched:
            word_phonemes = self._phonemes_for_word(tokenizer, word)
            pattern = _phoneme_boundary_pattern(word_phonemes)
            line_phonemes, count = pattern.subn(self.pronounce[word], line_phonemes)
            if count == 0:
                return line_phonemes, word
        return line_phonemes, ""

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        kokoro = _load_kokoro()
        effective_speed = speed if speed is not None else _jittered_speed(self.speed, seed)
        matched = self._matched_words(text) if self.pronounce else []

        synth_text = text
        is_phonemes = False
        warning: str | None = None
        if matched:
            tokenizer = _load_tokenizer()
            phonemes, unresolved_word = self._phonemized_line(tokenizer, text, matched)
            if unresolved_word:
                warning = (
                    f"WARN: could not place the pronunciation for '{unresolved_word}' in "
                    f"{text!r}; it was read from plain text instead."
                )
            else:
                synth_text = phonemes
                is_phonemes = True

        try:
            samples, sample_rate = kokoro.create(
                synth_text,
                voice=self.voice,
                speed=effective_speed,
                lang=self.lang,
                is_phonemes=is_phonemes,
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
        return Audio(samples=audio, sample_rate=int(sample_rate), warning=warning)
