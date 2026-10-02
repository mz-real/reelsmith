"""Tests for scene start times and the xfade chain."""

from __future__ import annotations

import pytest

from reelsmith.compose.transitions import (
    XFADE,
    boundary_transitions,
    ffmpeg_transition,
    padded_lengths,
    scene_starts,
    xfade_filters,
)


def test_scene_starts_add_up_timeline_durations() -> None:
    assert scene_starts([3.0, 4.5, 2.0]) == [0.0, 3.0, 7.5]


def test_every_scene_but_the_last_is_padded_by_the_fade() -> None:
    assert padded_lengths([3.0, 4.5, 2.0], 0.4) == [
        pytest.approx(3.4),
        pytest.approx(4.9),
        pytest.approx(2.0),
    ]


def test_xfade_offsets_are_the_scene_starts() -> None:
    chains = xfade_filters([3.0, 4.5, 2.0], XFADE, "vout")
    assert chains == [
        "[0:v][1:v]xfade=transition=fade:duration=0.4:offset=3[x1]",
        "[x1][2:v]xfade=transition=fade:duration=0.4:offset=7.5[vout]",
    ]


def test_one_scene_needs_no_xfade() -> None:
    assert xfade_filters([5.0], XFADE, "vout") == ["[0:v]null[vout]"]


def test_ffmpeg_transition_names() -> None:
    assert ffmpeg_transition("fade") == "fade"
    assert ffmpeg_transition("slide") == "slideleft"
    assert ffmpeg_transition("push") == "smoothleft"
    assert ffmpeg_transition("zoom") == "zoomin"


def test_boundary_transitions_use_incoming_scene_or_default() -> None:
    names = boundary_transitions([None, "slide", "zoom"], "fade")
    assert names == ["slideleft", "zoomin"]
    assert boundary_transitions([None], "push") == []


def test_xfade_chain_uses_per_boundary_names() -> None:
    chains = xfade_filters(
        [2.0, 3.0, 1.0],
        XFADE,
        "vout",
        ["slideleft", "zoomin"],
    )
    assert "transition=slideleft" in chains[0]
    assert "transition=zoomin" in chains[1]
