"""Find the cleanest stretch of a recording to use as a cloning reference.

Chatterbox only uses about the first 10 seconds of a reference, so a long
voice note is cut down to its best window. Each window is scored on four
things, all with plain numpy:

- speech: the share of 10 ms frames clearly above the window's noise floor
- noise: the level of the quietest 10% of frames
- clipping: any sample at or above 0.99
- pace: syllables a second, counted as peaks in the energy envelope

A window with no clipping always beats one with clipping.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import run_ffmpeg
from reelsmith.voice.base import Audio

REFERENCE_RATE = 24000
FRAME_SECONDS = 0.01
STEP_SECONDS = 0.5
MIN_SECONDS = 3.0
CLIP_LEVEL = 0.99
SPEECH_ABOVE_FLOOR_DB = 15.0
QUIETEST_SHARE = 0.10

WEIGHTS = {"speech": 0.35, "noise": 0.30, "pace": 0.20, "clip": 0.15}


@dataclass(frozen=True)
class WindowScore:
    start: float
    end: float
    speech_ratio: float
    noise_floor_db: float
    clipped_samples: int
    syllables_per_second: float
    speech_score: float
    noise_score: float
    clip_score: float
    pace_score: float
    total: float


@dataclass(frozen=True)
class ReferencePick:
    best: WindowScore
    runner_up: WindowScore | None
    windows: int
    audio: Audio
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _frame_db(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    size = max(1, int(round(FRAME_SECONDS * sample_rate)))
    count = samples.size // size
    if count == 0:
        return np.full(1, -120.0)
    frames = samples[: count * size].astype(np.float64).reshape(count, size)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return np.asarray(20.0 * np.log10(rms + 1e-6))


def _noise_floor(frame_db: np.ndarray) -> float:
    quiet_count = max(1, int(frame_db.size * QUIETEST_SHARE))
    return float(np.mean(np.sort(frame_db)[:quiet_count]))


def _speech_threshold(noise_floor_db: float) -> float:
    return max(noise_floor_db + SPEECH_ABOVE_FLOOR_DB, -55.0)


def _count_peaks(envelope_db: np.ndarray, threshold_db: float) -> int:
    """Count envelope peaks above threshold, at least 4 dB deep and 80 ms apart."""
    min_gap = int(round(0.08 / FRAME_SECONDS))
    peaks = 0
    last_index = -min_gap
    last_peak: float | None = None
    valley = float("inf")
    for i in range(1, envelope_db.size - 1):
        value = float(envelope_db[i])
        valley = min(valley, value)
        is_peak = value >= envelope_db[i - 1] and value > envelope_db[i + 1]
        if not is_peak or value <= threshold_db:
            continue
        deep_enough = last_peak is None or min(value, last_peak) - valley >= 4.0
        if deep_enough and i - last_index >= min_gap:
            peaks += 1
            last_peak = value
            last_index = i
            valley = value
    return peaks


def _envelope(frame_db: np.ndarray) -> np.ndarray:
    linear = 10 ** (frame_db / 20.0)
    smooth = np.convolve(linear, np.ones(5) / 5.0, mode="same")
    return np.asarray(20.0 * np.log10(smooth + 1e-6))


def syllable_rate(samples: np.ndarray, sample_rate: int) -> float:
    """Syllables a second, from peaks in the smoothed energy envelope."""
    frame_db = _frame_db(samples, sample_rate)
    seconds = samples.size / sample_rate
    if seconds <= 0:
        return 0.0
    threshold = _speech_threshold(_noise_floor(frame_db))
    return _count_peaks(_envelope(frame_db), threshold) / seconds


def _ramp(value: float, zero: float, one: float) -> float:
    if one == zero:
        return 1.0
    return float(np.clip((value - zero) / (one - zero), 0.0, 1.0))


def _speech_score(ratio: float) -> float:
    # Real speech has pauses. Far too little is a weak sample, and sound
    # with no gaps at all is more likely music or hum than a voice.
    if ratio < 0.5:
        return _ramp(ratio, 0.15, 0.5)
    if ratio <= 0.85:
        return 1.0
    return 1.0 - 0.5 * _ramp(ratio, 0.85, 1.0)


def _pace_score(rate: float) -> float:
    # About 2.5 to 5 syllables a second is a calm presenting pace.
    if rate < 2.5:
        return _ramp(rate, 1.0, 2.5)
    if rate <= 5.0:
        return 1.0
    return 1.0 - _ramp(rate, 5.0, 7.5)


def score_window(samples: np.ndarray, sample_rate: int, start: float) -> WindowScore:
    """Score one window of mono audio that starts at `start` seconds."""
    frame_db = _frame_db(samples, sample_rate)
    floor = _noise_floor(frame_db)
    threshold = _speech_threshold(floor)
    ratio = float(np.mean(frame_db > threshold))
    clipped = int(np.count_nonzero(np.abs(samples) >= CLIP_LEVEL))
    seconds = samples.size / sample_rate
    rate = _count_peaks(_envelope(frame_db), threshold) / seconds if seconds > 0 else 0.0

    speech_score = _speech_score(ratio)
    noise_score = _ramp(-floor, 30.0, 70.0)
    clip_score = 1.0 if clipped == 0 else 0.0
    pace_score = _pace_score(rate)
    total = (
        WEIGHTS["speech"] * speech_score
        + WEIGHTS["noise"] * noise_score
        + WEIGHTS["pace"] * pace_score
        + WEIGHTS["clip"] * clip_score
    )
    return WindowScore(
        start=start,
        end=start + seconds,
        speech_ratio=ratio,
        noise_floor_db=floor,
        clipped_samples=clipped,
        syllables_per_second=rate,
        speech_score=speech_score,
        noise_score=noise_score,
        clip_score=clip_score,
        pace_score=pace_score,
        total=total,
    )


def resample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """A plain linear resample, fine for speech."""
    if from_rate == to_rate or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / from_rate
    length = max(1, int(round(duration * to_rate)))
    old_t = np.arange(samples.size) / from_rate
    new_t = np.arange(length) / to_rate
    return np.asarray(np.interp(new_t, old_t, samples), dtype=np.float32)


def _rank_key(score: WindowScore) -> tuple[bool, float]:
    return (score.clipped_samples == 0, score.total)


def _reasons(best: WindowScore, runner_up: WindowScore | None, windows: int) -> list[str]:
    reasons = [
        f"speech in {best.speech_ratio:.0%} of the window",
        f"noise floor {best.noise_floor_db:.0f} dB",
        "no clipping"
        if best.clipped_samples == 0
        else f"{best.clipped_samples} clipped samples, every window had some clipping",
        f"pace {best.syllables_per_second:.1f} syllables a second",
    ]
    if runner_up is not None:
        reasons.append(
            f"best of {windows} windows, the next best scored {runner_up.total:.2f}"
            f" at {runner_up.start:.1f} to {runner_up.end:.1f} s"
        )
    return reasons


def pick_reference(audio: Audio, seconds: float = 12.0) -> ReferencePick:
    """Score every window of `seconds` and return the best one at 24 kHz."""
    samples = resample(audio.samples.astype(np.float32), audio.sample_rate, REFERENCE_RATE)
    rate = REFERENCE_RATE
    total_seconds = samples.size / rate
    if total_seconds < MIN_SECONDS:
        raise ReelsmithError(
            f"The recording is too short ({total_seconds:.1f} s). "
            "Record at least 10 seconds of steady speech.",
        )

    notes: list[str] = []
    window = int(round(seconds * rate))
    if samples.size <= window:
        notes.append(
            f"The recording is shorter than {seconds:.0f} s, so all of it is used. "
            "A longer one gives more to choose from."
        )
        window = samples.size

    step = int(round(STEP_SECONDS * rate))
    starts = list(range(0, samples.size - window + 1, step))
    scores = [score_window(samples[s : s + window], rate, start=s / rate) for s in starts]
    ranked = sorted(scores, key=_rank_key, reverse=True)
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    begin = int(round(best.start * rate))
    clip = Audio(samples=samples[begin : begin + window].copy(), sample_rate=rate)
    return ReferencePick(
        best=best,
        runner_up=runner_up,
        windows=len(scores),
        audio=clip,
        reasons=_reasons(best, runner_up, len(scores)),
        notes=notes,
    )


def load_recording(path: Path) -> Audio:
    """Decode any audio or video file to 24 kHz mono float samples with ffmpeg."""
    if not path.is_file():
        raise ReelsmithError(f"{path} not found.")
    with tempfile.TemporaryDirectory() as tmp:
        decoded = Path(tmp) / "decoded.wav"
        run_ffmpeg(
            [
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(REFERENCE_RATE),
                "-c:a",
                "pcm_f32le",
                str(decoded),
            ]
        )
        data, rate = sf.read(decoded, dtype="float32", always_2d=False)
    return Audio(samples=np.asarray(data, dtype=np.float32).reshape(-1), sample_rate=int(rate))
