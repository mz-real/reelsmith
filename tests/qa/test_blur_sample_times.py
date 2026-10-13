"""Blur QA samples frames on master frame boundaries."""

from __future__ import annotations

import math

import pytest

from reelsmith.qa.checks import blur_sample_times


def test_first_sample_is_first_frame_at_or_after_window_start() -> None:
    fps = 30.0
    start = 36.112
    times = blur_sample_times(start, 40.0, fps)
    assert times[0] == pytest.approx(math.ceil(start * fps) / fps, rel=1e-6)


def test_last_sample_is_last_frame_at_or_before_window_end() -> None:
    fps = 30.0
    end = 40.017
    times = blur_sample_times(36.0, end, fps)
    assert times[-1] == pytest.approx(math.floor(end * fps) / fps, rel=1e-6)
