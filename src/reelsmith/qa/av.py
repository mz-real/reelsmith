"""ffmpeg backed audio and frame extraction helpers used by the QA checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import require_ffmpeg, run_ffmpeg

_NUMBER = r"(-?(?:\d+\.?\d*|inf))"
_INTEGRATED_RE = re.compile(rf"\bI:\s*{_NUMBER}\s*LUFS")
_TRUE_PEAK_RE = re.compile(rf"Peak:\s*{_NUMBER}\s*dBFS")


def extract_audio_window(master: Path, start: float, end: float, out_wav: Path) -> None:
    """Write the master's audio between start and end (seconds) to a wav file."""
    start = max(0.0, start)
    duration = max(0.0, end - start)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(master),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{max(duration, 0.02):.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(out_wav),
        ]
    )


def rms_of_window(master: Path, start: float, end: float, work_dir: Path) -> float:
    """The root mean square amplitude of the master's audio in a time window."""
    wav_path = work_dir / f"rms-{start:.3f}-{end:.3f}.wav"
    extract_audio_window(master, start, end, wav_path)
    samples, _ = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def ebur128_loudness(master: Path) -> tuple[float, float]:
    """Return (integrated loudness in LUFS, true peak in dBTP) for the master."""
    require_ffmpeg()
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "info",
        "-i",
        str(master),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ReelsmithError(f"ffmpeg loudness analysis failed: {_tail(completed.stderr)}")
    integrated = _last_match(_INTEGRATED_RE, completed.stderr)
    true_peak = _last_match(_TRUE_PEAK_RE, completed.stderr)
    if integrated is None or true_peak is None:
        raise ReelsmithError("Could not read loudness from ffmpeg's ebur128 output.")
    return integrated, true_peak


_FRAME_RETRY_STEP = 0.2
_FRAME_RETRIES = 5


def extract_frame(master: Path, time: float, out_png: Path) -> None:
    """Write a single frame at the given master time to a PNG file.

    A time right at the end of the master can land after the last frame
    and produce no output, so this steps a little earlier and retries
    rather than leaving no file behind.
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    seek = max(0.0, time)
    for attempt in range(_FRAME_RETRIES):
        run_ffmpeg(
            [
                "-i",
                str(master),
                "-ss",
                f"{seek:.3f}",
                "-frames:v",
                "1",
                str(out_png),
            ]
        )
        if out_png.is_file():
            return
        seek = max(0.0, seek - _FRAME_RETRY_STEP)
        if attempt > 0 and seek <= 0.0:
            break
    raise ReelsmithError(f"Could not extract a frame near {time:.2f}s from {master}.")


def _last_match(pattern: re.Pattern[str], text: str) -> float | None:
    matches = pattern.findall(text)
    return float(matches[-1]) if matches else None


def _tail(text: str, limit: int = 400) -> str:
    flat = " ".join(text.split())
    return flat[-limit:] if flat else "no error output"
