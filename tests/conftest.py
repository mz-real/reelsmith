"""Shared pytest fixtures for reelsmith tests."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tiny_video(tmp_path: Path) -> Iterator[Path]:
    """A tiny 2 second, 320x240 test video with a sine audio track.

    Built with ffmpeg's testsrc and sine sources, written once per test
    into an isolated temp directory.
    """
    video_path = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
    )
    yield video_path
