"""Tests for tap ripples and Back badges."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reelsmith.compose.ripples import (
    RING_STEPS,
    back_cues,
    draw_back_badge,
    draw_ring,
    out_time,
    ripple_cues,
)
from reelsmith.models import Event
from reelsmith.timing import Segment

# Play 0..2, hold 1.5 s at 2, play 2..6 at double speed.
SEGMENTS = [
    Segment("play", 0.0, 2.0, 1.0, 0.0, 2.0),
    Segment("hold", 2.0, 2.0, 1.0, 2.0, 3.5),
    Segment("play", 2.0, 6.0, 2.0, 3.5, 5.5),
]


def event(t: float, kind: str = "tap", x: float | None = 0.5, y: float | None = 0.25) -> Event:
    return Event.model_validate({"id": f"e{t}", "t": t, "type": kind, "x": x, "y": y})


def test_out_time_inside_a_normal_segment() -> None:
    assert out_time(SEGMENTS, 1.0) == pytest.approx(1.0)


def test_out_time_after_a_hold_lands_after_the_hold() -> None:
    assert out_time(SEGMENTS, 2.0) == pytest.approx(3.5)


def test_out_time_in_a_sped_up_segment() -> None:
    assert out_time(SEGMENTS, 4.0) == pytest.approx(4.5)


def test_out_time_outside_the_clip_is_none() -> None:
    assert out_time(SEGMENTS, 9.0) is None


def test_ripple_cues_only_for_positioned_taps_and_clicks() -> None:
    events = [event(1.0), event(4.0, "click"), event(3.0, "key", None, None), event(5.0, "back")]
    cues = ripple_cues(events, SEGMENTS)
    assert [(c.t, c.x, c.y) for c in cues] == [
        (pytest.approx(1.0), 0.5, 0.25),
        (pytest.approx(4.5), 0.5, 0.25),
    ]


def test_back_cues_for_back_events() -> None:
    events = [event(1.0), event(5.0, "back", None, None)]
    assert [pytest.approx(c) for c in back_cues(events, SEGMENTS)] == [5.0]


def test_ring_and_badge_pngs(tmp_path: Path) -> None:
    assert RING_STEPS >= 3
    ring = draw_ring(40, "#38bdf8", 0.8, tmp_path / "ring.png")
    badge = draw_back_badge(1.0, None, tmp_path / "back.png")
    with Image.open(ring) as image:
        assert image.width == image.height >= 80
        assert image.mode == "RGBA"
    with Image.open(badge) as image:
        assert image.width > image.height > 0
