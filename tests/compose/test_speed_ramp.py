"""Tests for speed ramp expansion."""

from __future__ import annotations

import pytest

from reelsmith.compose.speed_ramp import (
    MAX_SPEED_STEP,
    check_segment_totals,
    expand_speed_ramps,
    max_speed_jump,
    max_step_speed_ratio,
)
from reelsmith.qa.checks import SPEED_JUMP_RATIO as QA_SPEED_JUMP
from reelsmith.qa.checks import SPEED_JUMP_WINDOW
from reelsmith.timing import Segment


def test_fast_segment_preserves_source_and_output_totals() -> None:
    original = Segment("play", 1.0, 5.0, 2.0, 1.0, 3.0)
    expanded = expand_speed_ramps([original])
    assert len(expanded) > 3
    assert check_segment_totals(original, expanded)


def test_each_step_speed_matches_its_spans() -> None:
    original = Segment("play", 1.0, 15.75, 3.75, 1.0, 4.4375)
    expanded = expand_speed_ramps([original])
    for seg in expanded:
        if seg.kind != "play":
            continue
        out_span = seg.out_end - seg.out_start
        if out_span <= 0:
            continue
        assert (seg.src_end - seg.src_start) / out_span == pytest.approx(seg.speed, rel=1e-4)


def test_step_ratio_stays_within_limit() -> None:
    original = Segment("play", 1.0, 15.75, 3.75, 1.0, 4.4375)
    expanded = expand_speed_ramps([original])
    assert max_step_speed_ratio(expanded) <= MAX_SPEED_STEP + 1e-3


def test_three_segment_375_ramp_passes_speed_jump_qa() -> None:
    stepped = [
        Segment("play", 0.0, 1.0, 1.0, 0.0, 1.0),
        Segment("play", 1.0, 15.75, 3.75, 1.0, 4.4375),
        Segment("play", 15.75, 16.0, 1.0, 4.4375, 4.5),
    ]
    expanded = expand_speed_ramps(stepped)
    for seg in stepped:
        part = [
            s
            for s in expanded
            if s.kind == "play"
            and s.out_start >= seg.out_start - 1e-6
            and s.out_end <= seg.out_end + 1e-4
        ]
        assert part, f"no pieces for {seg}"
        assert check_segment_totals(seg, part)
    jump = max_speed_jump(expanded, SPEED_JUMP_WINDOW)
    assert jump < QA_SPEED_JUMP + 1e-3


def test_max_speed_jump_drops_after_ramps() -> None:
    stepped = [
        Segment("play", 0.0, 1.0, 1.0, 0.0, 1.0),
        Segment("play", 1.0, 5.0, 2.0, 1.0, 3.0),
    ]
    jump = max_speed_jump(expand_speed_ramps(stepped), 0.2)
    assert jump < 1.5
