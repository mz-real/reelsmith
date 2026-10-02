"""Tests for the blur check."""

from __future__ import annotations

from pathlib import Path

from media_fixtures import build_blur_test_video

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.checks import CheckStatus, QAContext, check_blur
from reelsmith.qa.timeline import BlurOut, SceneOut, Timeline

BOX = (20, 20, 80, 80)


def _context(master: Path, timeline: Timeline, work_dir: Path) -> QAContext:
    return QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=master,
        master_duration=timeline.duration or 0.0,
        sheets_dir=work_dir / "sheets",
        work_dir=work_dir,
        transcriber=lambda path: [],
    )


def test_blur_passes_when_the_region_stays_blurred(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_blur_test_video(master, duration=2.0, box=BOX, blurred=True)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=2.0,
        segments=None,
        placements=None,
        captions=None,
        blur=[
            BlurOut(
                box=(float(BOX[0]), float(BOX[1]), float(BOX[2]), float(BOX[3])),
                out_start=0.0,
                out_end=2.0,
            )
        ],
    )
    timeline = Timeline(format="16x9", duration=2.0, scenes=[scene], transitions=[])
    ctx = _context(master, timeline, tmp_path)

    row = check_blur(ctx)

    assert row.status == CheckStatus.PASS


def test_blur_fails_when_the_region_is_left_sharp(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_blur_test_video(master, duration=2.0, box=BOX, blurred=False)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=2.0,
        segments=None,
        placements=None,
        captions=None,
        blur=[
            BlurOut(
                box=(float(BOX[0]), float(BOX[1]), float(BOX[2]), float(BOX[3])),
                out_start=0.0,
                out_end=2.0,
            )
        ],
    )
    timeline = Timeline(format="16x9", duration=2.0, scenes=[scene], transitions=[])
    ctx = _context(master, timeline, tmp_path)

    row = check_blur(ctx)

    assert row.status == CheckStatus.FAIL
    assert "scene 'search'" in row.details[0]
    assert "still sharp" in row.details[0]


def test_blur_warns_when_blur_field_is_missing(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_blur_test_video(master, duration=1.0, box=BOX, blurred=True)
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
    ctx = _context(master, timeline, tmp_path)

    row = check_blur(ctx)

    assert row.status == CheckStatus.WARN
