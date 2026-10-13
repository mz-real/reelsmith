"""Blur enable window padding."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from reelsmith.compose.blur import _enable_window
from reelsmith.compose.layouts import Box, Layout, Size
from reelsmith.compose.speed_ramp import expand_speed_ramps
from reelsmith.compose.timeline import _blur, src_range_to_out
from reelsmith.models import BlurRegion
from reelsmith.timing import Segment


def test_enable_uses_frame_pad_at_window_start() -> None:
    assert _enable_window(1.0, 2.0) == "between(t,0.933,2.033)"


STEPPED = [
    Segment("play", 0.0, 1.0, 1.0, 0.0, 1.0),
    Segment("play", 1.0, 15.75, 3.75, 1.0, 4.9333333),
    Segment("play", 15.75, 20.0, 1.0, 4.9333333, 9.1833333),
]
FPS = 30
REGION = BlurRegion.model_validate(
    {"clip": "demo", "box": [0.1, 0.1, 0.5, 0.2], "start": 6.0, "end": 12.0}
)


def source_time(segments: list[Segment], out_time: float) -> float | None:
    for seg in segments:
        if seg.out_start - 1e-9 <= out_time < seg.out_end - 1e-9:
            if seg.kind == "hold":
                return seg.src_start
            return seg.src_start + (out_time - seg.out_start) * seg.speed
    return None


def blur_entry(segments: list[Segment]) -> dict[str, Any]:
    clip = SimpleNamespace(id="demo", width=1000, height=600, duration=20.0)
    scene = SimpleNamespace(clip=clip, timeline=SimpleNamespace(segments=segments))
    box = Box(0, 0, 1000, 600)
    layout = Layout(Size(1000, 600), box, None, None, None, None, False, 1.0)
    look = SimpleNamespace(blur=[REGION])
    entries = _blur(scene, layout, look, 0.0)  # type: ignore[arg-type]
    assert len(entries) == 1
    return entries[0]


def test_timeline_blur_window_follows_the_ramped_segments() -> None:
    rendered = expand_speed_ramps(STEPPED)
    assert len(rendered) > len(STEPPED)
    entry = blur_entry(STEPPED)
    expected = src_range_to_out(rendered, 6.0, 12.0)
    assert expected is not None
    assert entry["out_start"] == pytest.approx(expected[0], abs=1e-3)
    assert entry["out_end"] == pytest.approx(expected[1], abs=1e-3)


def test_every_output_frame_showing_the_region_is_inside_the_timeline_window() -> None:
    rendered = expand_speed_ramps(STEPPED)
    entry = blur_entry(STEPPED)
    inside = []
    for index in range(round(rendered[-1].out_end * FPS)):
        time = index / FPS
        src = source_time(rendered, time)
        if src is not None and 6.0 <= src <= 12.0:
            inside.append(time)
    assert inside
    for time in inside:
        assert entry["out_start"] - 1e-3 <= time <= entry["out_end"] + 1e-3, time
    assert math.ceil((entry["out_start"] - 1e-3) * FPS) / FPS == pytest.approx(inside[0])
