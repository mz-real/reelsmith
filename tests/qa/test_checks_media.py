"""Tests for the checks that read the master's real audio and video."""

from __future__ import annotations

from pathlib import Path

from media_fixtures import build_loudness_video, build_video

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.checks import (
    CheckStatus,
    QAContext,
    check_end_noise,
    check_loudness,
    check_transcript,
)
from reelsmith.qa.timeline import PlacementOut, SceneOut, Timeline
from reelsmith.qa.transcribe import Word

SCRIPT = {
    "version": 1,
    "scenes": [
        {
            "id": "search",
            "lines": [
                {"id": "l1", "phrases": [{"text": "Type a dish into the search box."}]},
            ],
        }
    ],
}


def _context(master: Path, timeline: Timeline, work_dir: Path, transcriber: object) -> QAContext:
    return QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate(SCRIPT),
        timeline=timeline,
        master=master,
        master_duration=timeline.duration or 0.0,
        sheets_dir=work_dir / "sheets",
        work_dir=work_dir,
        transcriber=transcriber,  # type: ignore[arg-type]
    )


def _fake_transcriber(text: str) -> object:
    def _transcribe(_path: Path) -> list[Word]:
        words = text.split()
        return [Word(text=word, start=0.0, end=0.1) for word in words]

    return _transcribe


def test_transcript_passes_when_audio_matches_the_script(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_video(master, ["sine=frequency=440:duration=1.0"], duration=1.0)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=1.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=1.0, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=1.0, scenes=[scene], transitions=[])
    ctx = _context(
        master,
        timeline,
        tmp_path,
        _fake_transcriber("type a dish into the search box"),
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.PASS


def test_transcript_fails_when_a_word_is_missing(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_video(master, ["sine=frequency=440:duration=1.0"], duration=1.0)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=1.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=1.0, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=1.0, scenes=[scene], transitions=[])
    ctx = _context(
        master,
        timeline,
        tmp_path,
        _fake_transcriber("type a into the search box"),
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.FAIL
    assert "scene 'search'" in row.details[0]
    assert "line 'l1'" in row.details[0]
    assert "dish" in row.details[0]


def test_end_noise_passes_when_it_is_quiet_after_the_line(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_video(
        master,
        [
            "sine=frequency=440:duration=1.0,volume=0.3",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=1.0",
        ],
        duration=2.0,
    )
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=2.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=1.0, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=2.0, scenes=[scene], transitions=[])
    ctx = _context(master, timeline, tmp_path, _fake_transcriber("unused"))

    row = check_end_noise(ctx)

    assert row.status == CheckStatus.PASS


def test_end_noise_fails_when_a_click_is_left_after_the_line(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_video(
        master,
        [
            "sine=frequency=440:duration=1.0,volume=0.3",
            "sine=frequency=2000:duration=0.3,volume=0.8",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=0.7",
        ],
        duration=2.0,
    )
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=2.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=1.0, pin_event_out=None)
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=2.0, scenes=[scene], transitions=[])
    ctx = _context(master, timeline, tmp_path, _fake_transcriber("unused"))

    row = check_end_noise(ctx)

    assert row.status == CheckStatus.FAIL
    assert "scene 'search'" in row.details[0]
    assert "line 'l1'" in row.details[0]


def test_loudness_passes_near_target(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_loudness_video(master, duration=3.0, normalized=True)
    timeline = Timeline(format="16x9", duration=3.0, scenes=[], transitions=[])
    ctx = _context(master, timeline, tmp_path, _fake_transcriber("unused"))

    row = check_loudness(ctx)

    assert row.status == CheckStatus.PASS


def test_loudness_fails_far_from_target(tmp_path: Path) -> None:
    master = tmp_path / "master.mp4"
    build_loudness_video(master, duration=3.0, normalized=False)
    timeline = Timeline(format="16x9", duration=3.0, scenes=[], transitions=[])
    ctx = _context(master, timeline, tmp_path, _fake_transcriber("unused"))

    row = check_loudness(ctx)

    assert row.status == CheckStatus.FAIL
    assert "LUFS" in row.details[0]
