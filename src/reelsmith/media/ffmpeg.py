"""Thin wrappers around the ffmpeg and ffprobe command line tools."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from reelsmith.errors import ReelsmithError

_INSTALL_FIX = {
    "Darwin": "brew install ffmpeg",
    "Windows": "winget install ffmpeg",
    "Linux": "apt install ffmpeg",
}


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    rotation: int


def require_ffmpeg() -> None:
    """Raise a ReelsmithError with an install command if ffmpeg is missing."""
    if shutil.which("ffmpeg") is None:
        fix = _INSTALL_FIX.get(platform.system(), "install ffmpeg")
        raise ReelsmithError("ffmpeg was not found on the PATH.", fix=fix)
    if shutil.which("ffprobe") is None:
        fix = _INSTALL_FIX.get(platform.system(), "install ffmpeg")
        raise ReelsmithError("ffprobe was not found on the PATH.", fix=fix)


def run_ffmpeg(args: list[str]) -> None:
    """Run ffmpeg with the given arguments, always overwriting quietly.

    The caller passes only the arguments after the program name. A leading
    ``-y -hide_banner -loglevel error`` is always prepended.
    """
    require_ffmpeg()
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ReelsmithError(f"ffmpeg failed: {_tail(completed.stderr)}")


def _tail(text: str, limit: int = 400) -> str:
    """Return the last part of a tool's error output, on one line."""
    flat = " ".join(text.split())
    return flat[-limit:] if flat else "no error output"


def _parse_fps(rate: str) -> float:
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _rotation_of(stream: dict[str, object]) -> int:
    tags = stream.get("tags")
    if isinstance(tags, dict):
        raw = tags.get("rotate")
        if raw is not None:
            try:
                return int(raw) % 360
            except (TypeError, ValueError):
                pass
    side_data_list = stream.get("side_data_list")
    if isinstance(side_data_list, list):
        for side_data in side_data_list:
            if isinstance(side_data, dict) and "rotation" in side_data:
                try:
                    return int(float(side_data["rotation"])) % 360
                except (TypeError, ValueError):
                    pass
    return 0


def probe(path: Path) -> MediaInfo:
    """Inspect a media file and return its duration, size, fps and audio."""
    require_ffmpeg()
    command = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ReelsmithError(f"Could not read {path}: {_tail(completed.stderr)}")
    data = json.loads(completed.stdout)

    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not video_streams:
        raise ReelsmithError(f"No video stream found in {path}.")
    video = video_streams[0]

    duration_raw = data.get("format", {}).get("duration") or video.get("duration")
    duration = float(duration_raw) if duration_raw is not None else 0.0

    return MediaInfo(
        duration=duration,
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_parse_fps(str(video.get("avg_frame_rate", "0/1"))),
        has_audio=bool(audio_streams),
        rotation=_rotation_of(video),
    )
