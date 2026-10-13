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
_NR_NOISE_SHARE = 0.15
_NR_MIN_NOISE_FRAMES = 3
_NR_OVER_SUBTRACT = 1.5
_NR_GAIN_FLOOR = 0.18
_NR_MIN_DYNAMIC_DB = 15.0
_NR_TIME_SMOOTH = 5
_NR_FREQ_SMOOTH = 5
_EXPAND_HOP_S = 0.010
_EXPAND_THRESHOLD_BELOW_SPEECH_DB = 30.0
_EXPAND_RATIO = 2.0
_EXPAND_MAX_REDUCTION_DB = 12.0
_EXPAND_LOOKAHEAD_FRAMES = 2
_EXPAND_CLOSE_DB_PER_S = 40.0
_LEVEL_ACTIVE_BELOW_PEAK_DB = 20.0
_LEVEL_MAX_GAIN_DB = 12.0
_LEVEL_STEREO_DB = 3.0
_LEVEL_PEAK_CEILING = 0.89
_SILENCE_DB = -120.0
_TAIL_QUIET_DB = -40.0
_TAIL_MIN_QUIET_S = 0.04
_TAIL_KEEP_S = 0.02


@dataclass(frozen=True)
class CleanSettings:
    enabled: bool = True
    loudness: float = -16.0


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


def _smooth(values: np.ndarray, width: int, axis: int) -> np.ndarray:
    """Moving average of width samples along an axis, keeping the shape."""
    if width <= 1:
        return values
    kernel = np.ones(width, dtype=np.float32) / width
    pad = width // 2
    widths = [(0, 0)] * values.ndim
    widths[axis] = (pad, width - 1 - pad)
    padded = np.pad(values, widths, mode="edge")
    return np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), axis, padded)


def _spectral_denoise(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Spectral subtraction with a noise profile learned from the line's quietest frames.

    The profile is the mean spectrum of the quietest share of frames. The
    subtraction is conservative: it removes a little more than the average
    noise, never takes a bin below a floor, and the gains are smoothed over
    time and frequency so no isolated bins flicker as musical noise. A line
    with no real pauses has no clean noise to learn from, so it is left alone.
    """
    if samples.size < _STFT_SIZE:
        return samples
    window = np.hanning(_STFT_SIZE).astype(np.float32)
    pad = _STFT_SIZE
    padded = np.pad(samples.astype(np.float32), pad, mode="reflect")
    starts = range(0, padded.size - _STFT_SIZE + 1, _STFT_HOP)
    specs = np.stack([np.fft.rfft(padded[i : i + _STFT_SIZE] * window) for i in starts])
    mags = np.abs(specs)
    frame_db = 10.0 * np.log10(np.mean(np.square(mags), axis=1) + 1e-12)
    count = max(_NR_MIN_NOISE_FRAMES, int(len(frame_db) * _NR_NOISE_SHARE))
    if count >= len(frame_db):
        return samples
    quiet = np.argsort(frame_db)[:count]
    if float(np.percentile(frame_db, 95)) - float(np.mean(frame_db[quiet])) < _NR_MIN_DYNAMIC_DB:
        return samples
    profile = _smooth(np.mean(mags[quiet], axis=0), _NR_FREQ_SMOOTH, 0)
    steady = _smooth(mags, 3, 0)
    gain = 1.0 - _NR_OVER_SUBTRACT * profile / (steady + 1e-8)
    gain = np.clip(gain, _NR_GAIN_FLOOR, 1.0)
    gain = _smooth(_smooth(gain, _NR_TIME_SMOOTH, 0), _NR_FREQ_SMOOTH, 1)
    output = np.zeros(padded.size, dtype=np.float32)
    weight = np.zeros_like(output)
    for index, start in enumerate(starts):
        cleaned = np.fft.irfft(specs[index] * gain[index], n=_STFT_SIZE) * window
        output[start : start + _STFT_SIZE] += cleaned.astype(np.float32)
        weight[start : start + _STFT_SIZE] += window**2
    weight = np.maximum(weight, 1e-3)
    return (output / weight)[pad : pad + samples.size].astype(np.float32)


def _frame_db(samples: np.ndarray, hop: int) -> np.ndarray:
    """RMS level in dB of each hop-sized frame, with the last frame padded by zeros."""
    count = -(-samples.size // hop)
    padded = np.zeros(count * hop, dtype=np.float64)
    padded[: samples.size] = samples
    rms = np.sqrt(np.mean(np.square(padded.reshape(count, hop)), axis=1))
    return np.where(rms > 1e-10, 20.0 * np.log10(np.maximum(rms, 1e-10)), _SILENCE_DB)


def _downward_expander(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Lower what sits well under the speech by a limited amount, never to silence.

    Reduction grows gently below a threshold set from the line's own speech
    level and stops at a few dB. It opens at once (a little ahead of the
    sound, so word onsets are kept) and closes slowly, so it does not chatter.
    """
    if samples.size == 0:
        return samples
    hop = max(1, int(_EXPAND_HOP_S * sample_rate))
    levels = _frame_db(samples, hop)
    speech = float(np.percentile(levels, 90))
    threshold = speech - _EXPAND_THRESHOLD_BELOW_SPEECH_DB
    wanted = np.clip(
        (threshold - levels) * (1.0 - 1.0 / _EXPAND_RATIO), 0.0, _EXPAND_MAX_REDUCTION_DB
    )
    ahead = wanted.copy()
    for shift in range(1, _EXPAND_LOOKAHEAD_FRAMES + 1):
        ahead[:-shift] = np.minimum(ahead[:-shift], wanted[shift:])
    step = _EXPAND_CLOSE_DB_PER_S * _EXPAND_HOP_S
    reduction = ahead.copy()
    for index in range(1, reduction.size):
        reduction[index] = min(reduction[index], reduction[index - 1] + step)
    centres = (np.arange(reduction.size) + 0.5) * hop
    curve = np.interp(np.arange(samples.size), centres, reduction)
    return (samples * 10.0 ** (-curve / 20.0)).astype(np.float32)


def _level_to_target(samples: np.ndarray, sample_rate: int, loudness: float) -> np.ndarray:
    """Bring the speech of one line to the project loudness, without lifting its noise.

    Only the frames near the line's speech level count, so pauses do not pull
    the measure down. The gain is capped, and the peak is kept under the ceiling.
    """
    if samples.size == 0:
        return samples
    hop = max(1, int(_EXPAND_HOP_S * sample_rate))
    levels = _frame_db(samples, hop)
    active = levels > float(np.max(levels)) - _LEVEL_ACTIVE_BELOW_PEAK_DB
    if not bool(np.any(active)):
        return samples
    frames = -(-samples.size // hop)
    padded = np.zeros(frames * hop, dtype=np.float64)
    padded[: samples.size] = samples
    chosen = padded.reshape(frames, hop)[active]
    speech_db = 10.0 * math.log10(float(np.mean(np.square(chosen))) + 1e-12)
    gain_db = min(
        _LEVEL_MAX_GAIN_DB, max(-_LEVEL_MAX_GAIN_DB, loudness - _LEVEL_STEREO_DB - speech_db)
    )
    gain = float(10.0 ** (gain_db / 20.0))
    peak = float(np.max(np.abs(samples)))
    if peak * gain > _LEVEL_PEAK_CEILING:
        gain = _LEVEL_PEAK_CEILING / peak
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


def process_body(audio: Audio, loudness: float = -16.0) -> Audio:
    """High-pass, denoise, expand, level and edge fades before transcription."""
    samples = audio.samples.astype(np.float32, copy=False)
    if samples.size == 0:
        return audio
    samples = _highpass(samples, audio.sample_rate, _HIGHPASS_HZ)
    samples = _spectral_denoise(samples, audio.sample_rate)
    samples = _downward_expander(samples, audio.sample_rate)
    samples = _level_to_target(samples, audio.sample_rate, loudness)
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
    body = process_body(audio, settings.loudness)
    if words is None:
        return body, None, True
    finished, clipped, ok = finish_tail(body, words, expected, vocabulary)
    return finished, clipped, ok


__all__ = ["CleanSettings", "clean_line", "finish_tail", "process_body"]
