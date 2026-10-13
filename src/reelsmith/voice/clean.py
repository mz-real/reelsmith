"""Per-line narration cleanup after synthesis and tail trim."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from reelsmith.voice.base import Audio
from reelsmith.voice.quality import transcript_matches_any
from reelsmith.voice.transcribe import Word

_HIGHPASS_HZ = 75.0
_FADE_IN_S = 0.015
_FADE_OUT_S = 0.045
_LEAD_PAD_S = 0.10
_TAIL_PAD_S = 0.10
_STFT_SIZE = 2048
_STFT_HOP = 512
_NR_STRENGTH = 0.35
_GATE_FLOOR_DB = -55.0
_GATE_THRESHOLD_DB = -42.0
_GATE_RATIO = 3.0
_GATE_ATTACK_S = 0.008
_GATE_RELEASE_S = 0.060
_TAIL_QUIET_DB = -40.0
_TAIL_MIN_QUIET_S = 0.04
_TAIL_KEEP_S = 0.02


@dataclass(frozen=True)
class CleanSettings:
    enabled: bool = True


def _highpass(samples: np.ndarray, sample_rate: int, cutoff: float) -> np.ndarray:
    """Single-pole high-pass filter."""
    if samples.size == 0:
        return samples
    rc = 1.0 / (2.0 * np.pi * cutoff)
    alpha = rc / (rc + 1.0 / sample_rate)
    out = np.empty_like(samples)
    prev_y = 0.0
    prev_x = float(samples[0])
    for index, value in enumerate(samples):
        x = float(value)
        prev_y = alpha * (prev_y + x - prev_x)
        prev_x = x
        out[index] = prev_y
    return out


def _spectral_denoise(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Gentle spectral noise reduction for speech."""
    if samples.size < _STFT_SIZE:
        return samples
    window = np.hanning(_STFT_SIZE).astype(np.float32)
    noise_frames = max(1, int(0.2 * sample_rate / _STFT_HOP))
    spec_chunks: list[np.ndarray] = []
    positions: list[int] = []
    for start in range(0, samples.size - _STFT_SIZE + 1, _STFT_HOP):
        frame = samples[start : start + _STFT_SIZE] * window
        spec_chunks.append(np.fft.rfft(frame))
        positions.append(start)
    if not spec_chunks:
        return samples
    magnitudes = np.abs(np.stack(spec_chunks, axis=0))
    noise_profile = np.median(magnitudes[:noise_frames], axis=0)
    output = np.zeros(samples.size + _STFT_SIZE, dtype=np.float32)
    weight = np.zeros_like(output)
    for start, spec in zip(positions, spec_chunks, strict=True):
        mag = np.abs(spec)
        gain = 1.0 - _NR_STRENGTH * (noise_profile / (mag + 1e-8))
        gain = np.clip(gain, 0.15, 1.0)
        cleaned = np.fft.irfft(spec * gain, n=_STFT_SIZE) * window
        output[start : start + _STFT_SIZE] += cleaned
        weight[start : start + _STFT_SIZE] += window**2
    weight = np.maximum(weight, 1e-8)
    return (output[: samples.size] / weight[: samples.size]).astype(np.float32)


def _frame_rms_db(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= 1e-10:
        return -120.0
    return 20.0 * math.log10(rms)


def _soft_gate(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Bring sub-speech regions down without chopping word onsets."""
    if samples.size == 0:
        return samples
    frame = max(1, int(0.020 * sample_rate))
    attack = max(1, int(_GATE_ATTACK_S * sample_rate))
    release = max(1, int(_GATE_RELEASE_S * sample_rate))
    gain = np.ones(samples.size, dtype=np.float32)
    envelope = 0.0
    for start in range(0, samples.size, frame):
        chunk = samples[start : start + frame]
        level_db = _frame_rms_db(chunk)
        if level_db < _GATE_THRESHOLD_DB:
            target = _GATE_FLOOR_DB + (level_db - _GATE_THRESHOLD_DB) / _GATE_RATIO
            target_gain = 10 ** ((target - level_db) / 20.0)
        else:
            target_gain = 1.0
        for offset in range(chunk.size):
            index = start + offset
            if target_gain < envelope:
                step = max(envelope - target_gain, 0.0) / attack
                envelope = max(target_gain, envelope - step)
            else:
                step = (target_gain - envelope) / release
                envelope = min(target_gain, envelope + step)
            gain[index] = envelope
    return (samples * gain).astype(np.float32)


def _apply_fade(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    out = samples.copy()
    fade_in = min(out.size, max(1, int(_FADE_IN_S * sample_rate)))
    fade_out = min(out.size, max(1, int(_FADE_OUT_S * sample_rate)))
    ramp_in = np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    out[:fade_in] *= ramp_in
    ramp_out = np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
    out[-fade_out:] *= ramp_out
    return out


def _pad_lead(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    lead = int(round(_LEAD_PAD_S * sample_rate))
    if lead <= 0:
        return samples
    return np.concatenate([np.zeros(lead, dtype=np.float32), samples])


def _trim_after_last_word(samples: np.ndarray, sample_rate: int, words: list[Word]) -> np.ndarray:
    """Cut after the first sustained quiet stretch after the last word."""
    if not words or samples.size == 0:
        return samples
    last_end = int(round(words[-1].end * sample_rate))
    last_end = min(max(last_end, 0), samples.size)
    threshold = 10 ** (_TAIL_QUIET_DB / 20.0)
    min_quiet = max(1, int(_TAIL_MIN_QUIET_S * sample_rate))
    keep = max(1, int(_TAIL_KEEP_S * sample_rate))
    quiet_run = 0
    cut = samples.size
    for index in range(last_end, samples.size):
        if abs(float(samples[index])) <= threshold:
            quiet_run += 1
            if quiet_run >= min_quiet:
                cut = index - quiet_run + 1 + keep
                break
        else:
            quiet_run = 0
    cut = min(max(cut, last_end + 1), samples.size)
    tail_pad = int(round(_TAIL_PAD_S * sample_rate))
    trimmed = samples[:cut]
    if tail_pad <= 0:
        return trimmed
    return np.concatenate([trimmed, np.zeros(tail_pad, dtype=np.float32)])


def process_body(audio: Audio) -> Audio:
    """High-pass, denoise, gate and edge fades before transcription."""
    samples = audio.samples.astype(np.float32, copy=False)
    if samples.size == 0:
        return audio
    samples = _highpass(samples, audio.sample_rate, _HIGHPASS_HZ)
    samples = _spectral_denoise(samples, audio.sample_rate)
    samples = _soft_gate(samples, audio.sample_rate)
    samples = _pad_lead(samples, audio.sample_rate)
    samples = _apply_fade(samples, audio.sample_rate)
    return Audio(samples=samples, sample_rate=audio.sample_rate, warning=audio.warning)


def finish_tail(
    audio: Audio,
    words: list[Word],
    expected: Sequence[str],
    vocabulary: Sequence[str],
) -> tuple[Audio, list[Word], bool]:
    """Trim breaths after the last word and confirm the transcript still matches."""
    samples = _trim_after_last_word(audio.samples, audio.sample_rate, words)
    samples = _apply_fade(samples, audio.sample_rate)
    trimmed = Audio(samples=samples, sample_rate=audio.sample_rate, warning=audio.warning)
    end = trimmed.samples.size / trimmed.sample_rate
    clipped = [Word(w.text, w.start, min(w.end, end)) for w in words if w.start < end]
    ok, _ = transcript_matches_any(expected, clipped, vocabulary)
    return trimmed, clipped, ok


def clean_line(
    audio: Audio,
    settings: CleanSettings,
    words: list[Word] | None,
    expected: Sequence[str],
    vocabulary: Sequence[str],
) -> tuple[Audio, list[Word] | None, bool]:
    """Run the full cleanup path when enabled."""
    if not settings.enabled:
        return audio, words, True
    body = process_body(audio)
    if words is None:
        return body, None, True
    finished, clipped, ok = finish_tail(body, words, expected, vocabulary)
    return finished, clipped, ok


__all__ = ["CleanSettings", "clean_line", "finish_tail", "process_body"]
