"""Tests for hold push motion."""

from __future__ import annotations

from reelsmith.compose.hold_motion import eased_hold_amount, hold_center
from reelsmith.models import ClipModel


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
