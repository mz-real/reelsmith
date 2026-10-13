"""Tests for hold push motion."""

from __future__ import annotations

import shutil
import subprocess

import numpy as np
import pytest

from reelsmith.compose.hold_motion import (
    centered_zoom_filter,
    eased_hold_amount,
    hold_center,
    hold_push_chain,
    hold_scale_expr,
)
from reelsmith.models import ClipModel
from reelsmith.qa.image import judder_frames

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def test_hold_center_uses_last_event_position() -> None:
    clip = ClipModel.model_validate(
        {
            "id": "c",
            "video": "video.mp4",
            "width": 100,
            "height": 100,
            "fps": 30.0,
            "duration": 10.0,
            "events": [
                {"id": "e1", "t": 1.0, "type": "click", "x": 0.2, "y": 0.3},
                {"id": "e2", "t": 4.0, "type": "click", "x": 0.7, "y": 0.8},
            ],
        }
    )
    assert hold_center(clip, 5.0) == (0.7, 0.8)


def test_hold_ease_ends_at_full_push() -> None:
    amount = 0.025
    assert eased_hold_amount(0.0, 2.0, amount) == 1.0
    assert abs(eased_hold_amount(2.0, 2.0, amount) - (1.0 + amount)) < 1e-6


def _render_push(chain: str, width: int, height: int, seconds: float) -> np.ndarray:
    """Frames (n, h, w) of a textured still pushed in by chain."""
    graph = (
        f"testsrc2=s={width}x{height}:r=30,trim=end_frame=1,setpts=PTS-STARTPTS,"
        f"tpad=stop_mode=clone:stop_duration={seconds},trim=duration={seconds},{chain},"
        "format=gray"
    )
    done = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", graph, "-f", "rawvideo", "-"],
        capture_output=True,
        check=True,
    )
    raw = np.frombuffer(done.stdout, dtype=np.uint8)
    return raw.reshape(-1, height, width).astype(np.float64)


def _old_whole_pixel_chain(width: int, height: int, seconds: float) -> str:
    scale = hold_scale_expr(seconds)
    return (
        f"scale=w='2*trunc(iw*({scale})/2)':h='2*trunc(ih*({scale})/2)':eval=frame,"
        f"crop={width}:{height}"
    )


@needs_ffmpeg
def test_a_still_pushed_two_and_a_half_percent_moves_on_every_frame() -> None:
    width, height, seconds = 640, 360, 3.0
    chain = hold_push_chain(width, height, seconds, 0.5, 0.5)

    frames = _render_push(chain, width, height, seconds)

    assert len(frames) == 90
    steps = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    assert float(steps[:70].min()) > 0.0
    assert len(judder_frames(frames)) <= 2


@needs_ffmpeg
def test_the_old_whole_pixel_push_stuttered_on_the_same_still() -> None:
    width, height, seconds = 640, 360, 3.0

    frames = _render_push(_old_whole_pixel_chain(width, height, seconds), width, height, seconds)

    steps = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    assert float(steps[:70].min()) == 0.0


@needs_ffmpeg
def test_a_push_off_centre_stays_inside_the_frame_and_keeps_its_size() -> None:
    width, height, seconds = 640, 360, 1.0
    chain = hold_push_chain(width, height, seconds, 0.95, 0.05)

    frames = _render_push(chain, width, height, seconds)

    assert frames.shape[1:] == (height, width)
    assert float(frames[-1].mean()) > 0.0


@needs_ffmpeg
def test_the_slide_zoom_moves_on_every_frame_too() -> None:
    width, height, seconds = 640, 360, 3.0
    chain = centered_zoom_filter("(1+0.04*T/3)")

    frames = _render_push(chain, width, height, seconds)

    steps = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    assert float(steps.min()) > 0.0
