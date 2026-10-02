"""Tests for the checks that only need the timeline, not real media.

Sync, cut off lines, hold limits and captions all work from numbers in
timeline.json alone, so these use a QAContext built directly from
dataclasses instead of real ffmpeg media.
"""

from __future__ import annotations

from pathlib import Path

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.checks import (
    CheckStatus,
    QAContext,
    check_captions,
    check_cutoff,
    check_holds,
    check_sync,
)
from reelsmith.qa.timeline import CaptionOut, PlacementOut, SceneOut, SegmentOut, Timeline
from reelsmith.qa.transcribe import Word


def make_context(
    scenes: list[SceneOut], transitions: list[float] | None = None, work_dir: Path | None = None
) -> QAContext:
    timeline = Timeline(format="16x9", duration=20.0, scenes=scenes, transitions=transitions or [])
    return QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=Path("unused.mp4"),
        master_duration=20.0,
        sheets_dir=Path("unused_sheets"),
        work_dir=work_dir or Path("unused_work"),
        transcriber=lambda path: [Word(text="unused", start=0.0, end=0.1)],
    )


def test_sync_passes_when_pinned_phrase_starts_in_window() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=1.9, out_end=2.5, pin_event_out=2.0)
        ],
        captions=None,
        blur=None,
    )
    row = check_sync(make_context([scene]))
    assert row.status == CheckStatus.PASS


def test_sync_fails_when_pinned_phrase_starts_too_late() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=3.0, out_end=3.5, pin_event_out=2.0)
        ],
        captions=None,
        blur=None,
    )
    row = check_sync(make_context([scene]))
    assert row.status == CheckStatus.FAIL
    assert "scene 'search'" in row.details[0]
    assert "line 'l1'" in row.details[0]
    assert "late" in row.details[0]


def test_sync_warns_when_placements_are_missing() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=None,
        captions=None,
        blur=None,
    )
    row = check_sync(make_context([scene]))
    assert row.status == CheckStatus.WARN


def test_cutoff_passes_when_lines_end_inside_their_scene() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=1.0, out_end=4.0, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    row = check_cutoff(make_context([scene]))
    assert row.status == CheckStatus.PASS


def test_cutoff_fails_when_a_line_runs_past_its_scene() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=4.5, out_end=5.5, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    row = check_cutoff(make_context([scene]))
    assert row.status == CheckStatus.FAIL
    assert "line 'l1'" in row.details[0]
    assert "past the end of its scene" in row.details[0]


def test_holds_passes_under_the_limit() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=[
            SegmentOut(
                kind="hold", src_start=5.0, src_end=5.0, speed=1.0, out_start=3.0, out_end=5.0
            )
        ],
        placements=None,
        captions=None,
        blur=None,
    )
    row = check_holds(make_context([scene]))
    assert row.status == CheckStatus.PASS


def test_holds_fails_over_the_limit() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=10.0,
        segments=[
            SegmentOut(
                kind="hold", src_start=5.0, src_end=5.0, speed=1.0, out_start=1.0, out_end=6.0
            )
        ],
        placements=None,
        captions=None,
        blur=None,
    )
    row = check_holds(make_context([scene]))
    assert row.status == CheckStatus.FAIL
    assert "scene 'search'" in row.details[0]
    assert "3" in row.details[0]


def test_captions_pass_when_box_fits_and_duration_is_enough() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=None,
        captions=[
            CaptionOut(
                text="Find a recipe fast",
                out_start=0.0,
                out_end=3.0,
                box=(10.0, 10.0, 100.0, 20.0),
                panel=(0.0, 0.0, 200.0, 50.0),
            )
        ],
        blur=None,
    )
    row = check_captions(make_context([scene]))
    assert row.status == CheckStatus.PASS


def test_captions_fail_when_box_overflows_the_panel() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=None,
        captions=[
            CaptionOut(
                text="Find a recipe fast",
                out_start=0.0,
                out_end=3.0,
                box=(150.0, 10.0, 100.0, 20.0),
                panel=(0.0, 0.0, 200.0, 50.0),
            )
        ],
        blur=None,
    )
    row = check_captions(make_context([scene]))
    assert row.status == CheckStatus.FAIL
    assert "overflows its panel" in row.details[0]


def test_captions_fail_when_on_screen_too_briefly() -> None:
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=5.0,
        segments=None,
        placements=None,
        captions=[
            CaptionOut(
                text="Find a recipe fast",
                out_start=0.0,
                out_end=0.5,
                box=(10.0, 10.0, 100.0, 20.0),
                panel=(0.0, 0.0, 200.0, 50.0),
            )
        ],
        blur=None,
    )
    row = check_captions(make_context([scene]))
    assert row.status == CheckStatus.FAIL
    assert "needs at least" in row.details[0]
