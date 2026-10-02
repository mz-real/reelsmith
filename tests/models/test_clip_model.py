"""Tests for the clip.json model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from reelsmith.models import ClipModel, Event


def clip_data(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "search",
        "video": "video.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration": 12.4,
        "events": events,
    }


def test_the_documented_example_loads() -> None:
    clip = ClipModel.model_validate(
        clip_data(
            [{"id": "e1", "t": 2.10, "type": "click", "x": 0.42, "y": 0.18, "label": "Search box"}]
        )
    )
    assert clip.events[0] == Event(
        id="e1", t=2.10, type="click", x=0.42, y=0.18, label="Search box"
    )
    assert clip.event("e1") is clip.events[0]
    assert clip.event("nope") is None


def test_screen_and_key_events_have_no_position() -> None:
    clip = ClipModel.model_validate(
        clip_data(
            [
                {"id": "e1", "t": 1.0, "type": "screen"},
                {"id": "e2", "t": 2.0, "type": "key", "x": None, "y": None},
            ]
        )
    )
    assert clip.events[0].x is None


def test_taps_need_a_position() -> None:
    with pytest.raises(ValidationError, match="needs x and y"):
        ClipModel.model_validate(clip_data([{"id": "e1", "t": 1.0, "type": "tap"}]))


def test_event_ids_must_be_unique() -> None:
    events = [
        {"id": "e1", "t": 1.0, "type": "screen"},
        {"id": "e1", "t": 2.0, "type": "screen"},
    ]
    with pytest.raises(ValidationError, match="Event id 'e1' is used more than once"):
        ClipModel.model_validate(clip_data(events))


def test_positions_are_fractions() -> None:
    with pytest.raises(ValidationError):
        ClipModel.model_validate(
            clip_data([{"id": "e1", "t": 1.0, "type": "tap", "x": 420, "y": 0.2}])
        )


def test_events_must_be_inside_the_clip() -> None:
    with pytest.raises(ValidationError, match="after the end of the clip"):
        ClipModel.model_validate(clip_data([{"id": "e1", "t": 20.0, "type": "screen"}]))


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ClipModel.model_validate(clip_data([{"id": "e1", "t": 1.0, "type": "swipe"}]))
