"""Tests for the contact sheets check."""

from __future__ import annotations

from pathlib import Path

from media_fixtures import build_silent_video

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.checks import CheckStatus, QAContext, check_contact_sheets
from reelsmith.qa.timeline import PlacementOut, SceneOut, Timeline


def test_contact_sheets_are_written_for_scenes_events_and_transitions(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_silent_video(master, duration=3.0)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=3.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.5, out_end=1.0, pin_event_out=1.2)
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=3.0, scenes=[scene], transitions=[2.0])
    sheets_dir = tmp_path / "sheets"
    ctx = QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=master,
        master_duration=3.0,
        sheets_dir=sheets_dir,
        work_dir=tmp_path,
        transcriber=lambda path: [],
    )

    row = check_contact_sheets(ctx)

    assert row.status == CheckStatus.PASS
    assert (sheets_dir / "scenes.jpg").is_file()
    assert (sheets_dir / "events.jpg").is_file()
    assert (sheets_dir / "transitions.jpg").is_file()
    assert any("scenes.jpg" in d for d in row.details)


def test_contact_sheets_pass_even_with_nothing_to_sheet(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_silent_video(master, duration=1.0)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=1.0,
        segments=None,
        placements=None,
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=1.0, scenes=[scene], transitions=[])
    sheets_dir = tmp_path / "sheets"
    ctx = QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=master,
        master_duration=1.0,
        sheets_dir=sheets_dir,
        work_dir=tmp_path,
        transcriber=lambda path: [],
    )

    row = check_contact_sheets(ctx)

    assert row.status == CheckStatus.PASS
    assert (sheets_dir / "scenes.jpg").is_file()
    assert not (sheets_dir / "events.jpg").exists()
    assert not (sheets_dir / "transitions.jpg").exists()
