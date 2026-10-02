"""Tiny synthetic masters, built with ffmpeg's lavfi sources, for the qa tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        check=True,
    )


def build_video(
    path: Path,
    audio_segments: list[str],
    duration: float,
    size: str = "320x240",
    rate: int = 10,
    color: str = "gray",
) -> None:
    """Build a tiny mp4 with a plain colour video and a concatenated audio track.

    Each entry in ``audio_segments`` is a full lavfi audio source spec,
    including its own ``duration=``, such as
    ``"sine=frequency=440:duration=1.0"``. The segments play back to back.
    """
    inputs: list[str] = []
    for segment in audio_segments:
        inputs += ["-f", "lavfi", "-i", segment]
    video_index = len(audio_segments)
    inputs += [
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:size={size}:rate={rate}:duration={duration}",
    ]
    concat = "".join(f"[{i}:a]" for i in range(len(audio_segments)))
    concat += f"concat=n={len(audio_segments)}:v=0:a=1[aout]"
    _ffmpeg(
        [
            *inputs,
            "-filter_complex",
            concat,
            "-map",
            f"{video_index}:v",
            "-map",
            "[aout]",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ]
    )


def build_silent_video(
    path: Path, duration: float, size: str = "320x240", rate: int = 10, color: str = "gray"
) -> None:
    build_video(
        path,
        [f"anullsrc=channel_layout=mono:sample_rate=44100:duration={duration}"],
        duration,
        size,
        rate,
        color,
    )


def build_blur_test_video(
    path: Path,
    duration: float,
    box: tuple[int, int, int, int],
    blurred: bool,
    size: str = "320x240",
) -> None:
    """A detailed (testsrc) video, blurred in ``box`` or left sharp there."""
    x, y, w, h = box
    if blurred:
        filter_complex = (
            f"[0:v]split=2[base][tocrop];"
            f"[tocrop]crop={w}:{h}:{x}:{y},boxblur=10:2[blurred];"
            f"[base][blurred]overlay={x}:{y}[v]"
        )
        _ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={size}:rate=10:duration={duration}",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=mono:sample_rate=44100:duration={duration}",
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "1:a",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(path),
            ]
        )
    else:
        _ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={size}:rate=10:duration={duration}",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=mono:sample_rate=44100:duration={duration}",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(path),
            ]
        )


def build_loudness_video(path: Path, duration: float, normalized: bool) -> None:
    """A tone track either loudnorm'd to -16 LUFS, or left at raw amplitude."""
    audio_filter = "loudnorm=I=-16:TP=-1.0:LRA=11" if normalized else "anull"
    _ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:size=320x240:rate=10:duration={duration}",
            "-filter:a",
            audio_filter,
            "-map",
            "1:v",
            "-map",
            "0:a",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ]
    )
