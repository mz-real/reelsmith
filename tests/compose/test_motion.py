"""Tests for zoom and cursor keyframes and their ffmpeg expressions."""

from __future__ import annotations

import pytest

from reelsmith.compose.motion import (
    CURSOR_LEAD,
    FULL_VIEW,
    MAX_ZOOM,
    ZOOM_EASE,
    ZOOM_LEAD,
    Click,
    Key,
    clicks_of,
    cursor_keys,
    ease,
    track_expr,
    value_at,
    view_point,
    zoom_keys,
    zoom_moment,
    zoom_view,
    zoom_windows,
)
from reelsmith.models import ClipModel, ZoomSpec
from reelsmith.timing import Segment

# Play 0..2, hold 1.5 s at 2, play 2..6 at double speed.
SEGMENTS = [
    Segment("play", 0.0, 2.0, 1.0, 0.0, 2.0),
    Segment("hold", 2.0, 2.0, 1.0, 2.0, 3.5),
    Segment("play", 2.0, 6.0, 2.0, 3.5, 5.5),
]

CLIP = ClipModel.model_validate(
    {
        "id": "c",
        "video": "v.mp4",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "duration": 6.0,
        "events": [
            {"id": "e1", "t": 1.0, "type": "click", "x": 0.2, "y": 0.3},
            {"id": "e2", "t": 2.0, "type": "click", "x": 0.7, "y": 0.6},
            {"id": "e3", "t": 4.0, "type": "tap", "x": 0.5, "y": 0.5},
            {"id": "e4", "t": 5.0, "type": "key"},
        ],
    }
)


def zoom(
    at: str | float, box: tuple[float, ...] = (0.1, 0.1, 0.4, 0.4), hold: float = 1.5
) -> ZoomSpec:
    return ZoomSpec.model_validate({"box": list(box), "at": at, "hold": hold})


def evaluate(expr: str, t: float) -> float:
    """Evaluate the small subset of ffmpeg expressions track_expr writes."""

    def if_(cond: float, a: float, b: float) -> float:
        return a if cond else b

    names = {"if": if_, "lt": lambda a, b: float(a < b), "pow": pow, "t": t}
    return float(eval(expr.replace("if(", "if_("), {"if_": if_}, names))


def test_ease_runs_from_zero_to_one_and_is_symmetric() -> None:
    assert ease(0.0) == 0.0
    assert ease(1.0) == 1.0
    assert ease(0.5) == pytest.approx(0.5)
    assert ease(0.25) == pytest.approx(1 - ease(0.75))
    assert ease(-1) == 0.0 and ease(2) == 1.0


def test_zoom_view_keeps_the_footage_aspect_and_stays_inside() -> None:
    left, top, right, bottom = zoom_view((0.5, 0.8, 0.5, 0.2))
    assert right - left == pytest.approx(bottom - top)
    assert right - left == pytest.approx(0.5)  # the wider side of the box wins
    assert 0.0 <= left and right <= 1.0 and 0.0 <= top and bottom <= 1.0
    tiny = zoom_view((0.5, 0.5, 0.01, 0.01))
    assert tiny[2] - tiny[0] == pytest.approx(1 / MAX_ZOOM)


def test_an_event_id_maps_through_holds_and_speed_ups() -> None:
    assert zoom_moment(zoom("e1"), CLIP, SEGMENTS) == pytest.approx(1.0)
    assert zoom_moment(zoom("e2"), CLIP, SEGMENTS) == pytest.approx(3.5)  # after the hold
    assert zoom_moment(zoom(4.0), CLIP, SEGMENTS) == pytest.approx(4.5)  # sped up
    with pytest.raises(ValueError, match="no event 'e9'"):
        zoom_moment(zoom("e9"), CLIP, SEGMENTS)


def test_zoom_eases_in_before_the_moment_holds_then_eases_out() -> None:
    at = 3.5
    (window,) = zoom_windows([(at, zoom("e2", hold=1.0))], duration=8.0)
    assert window.full == pytest.approx(at - ZOOM_LEAD)
    assert window.start == pytest.approx(at - ZOOM_LEAD - ZOOM_EASE)
    assert window.release == pytest.approx(at + 1.0)
    assert window.end == pytest.approx(at + 1.0 + ZOOM_EASE)
    keys = zoom_keys([window])
    view = zoom_view((0.1, 0.1, 0.4, 0.4))
    assert value_at(keys, 0.0) == FULL_VIEW
    assert value_at(keys, window.start) == FULL_VIEW
    halfway = value_at(keys, window.start + ZOOM_EASE / 2)
    assert halfway[0] == pytest.approx(view[0] / 2)
    assert value_at(keys, at) == pytest.approx(view)  # the moment itself is zoomed in
    assert value_at(keys, window.release) == pytest.approx(view)
    assert value_at(keys, window.end + 0.01) == FULL_VIEW


def test_an_early_zoom_starts_at_the_scene_start() -> None:
    (window,) = zoom_windows([(0.2, zoom(0.2))], duration=5.0)
    assert window.start == 0.0
    assert window.full == pytest.approx(ZOOM_EASE)


def test_overlapping_zooms_move_from_box_to_box_without_zooming_out() -> None:
    first, second = (0.0, 0.0, 0.4, 0.4), (0.6, 0.6, 0.4, 0.4)
    windows = zoom_windows([(2.0, zoom(2.0, first)), (3.0, zoom(3.0, second))], duration=9.0)
    keys = zoom_keys(windows)
    times = [key.t for key in keys]
    assert times == sorted(times)
    a, b = zoom_view(first), zoom_view(second)
    assert value_at(keys, 2.0) == pytest.approx(a)
    assert value_at(keys, 3.0) == pytest.approx(b)
    between = [value_at(keys, 2.0 + n * 0.05) for n in range(21)]
    widths = [v[2] - v[0] for v in between]
    assert max(widths) < 0.5  # never back out to the full frame on the way


def test_track_expression_matches_python_values() -> None:
    windows = zoom_windows([(2.0, zoom(2.0)), (6.0, zoom(6.0, (0.5, 0.5, 0.5, 0.5)))], 10.0)
    keys = zoom_keys(windows)
    expr = track_expr(keys, lambda v: v[0])
    for n in range(0, 101):
        t = n * 0.1
        assert evaluate(expr, t) == pytest.approx(value_at(keys, t)[0], abs=2e-3), t


def test_view_point_maps_footage_into_the_zoomed_picture() -> None:
    assert view_point(FULL_VIEW, 0.3, 0.7) == (0.3, 0.7)
    x, y = view_point((0.2, 0.2, 0.6, 0.6), 0.4, 0.3)
    assert (x, y) == pytest.approx((0.5, 0.25))


def test_clicks_are_mapped_to_output_time_and_sorted() -> None:
    clicks = clicks_of(CLIP, SEGMENTS, ("click",))
    assert [(c.t, c.x) for c in clicks] == [(pytest.approx(1.0), 0.2), (pytest.approx(3.5), 0.7)]
    assert [c.t for c in clicks_of(CLIP, SEGMENTS, ("tap",))] == [pytest.approx(4.5)]


def test_cursor_arrives_before_each_click_and_rests_on_it() -> None:
    clicks = [Click(2.0, 0.2, 0.3), Click(4.0, 0.7, 0.6), Click(6.5, 0.4, 0.8)]
    keys = cursor_keys(clicks)
    for click in clicks:
        arrived = value_at(keys, click.t - CURSOR_LEAD)
        assert arrived == pytest.approx((click.x, click.y))
        assert value_at(keys, click.t) == pytest.approx((click.x, click.y))
    moving = value_at(keys, 3.4)
    assert moving != pytest.approx((0.2, 0.3)) and moving != pytest.approx((0.7, 0.6))
    assert keys[0].t == 0.0 and keys[0].v != (0.2, 0.3)  # starts at rest, off the first target


def test_cursor_handles_back_to_back_and_very_early_clicks() -> None:
    keys = cursor_keys([Click(0.1, 0.5, 0.5), Click(0.2, 0.6, 0.6)])
    times = [key.t for key in keys]
    assert times == sorted(times)
    assert value_at(keys, 0.2) == pytest.approx((0.6, 0.6))
    assert cursor_keys([]) == []


def test_a_single_key_track_is_constant() -> None:
    keys = [Key(0.0, (0.25,))]
    assert value_at(keys, 5.0) == (0.25,)
    assert evaluate(track_expr(keys, lambda v: v[0]), 3.0) == 0.25
