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


def test_transcript_window_does_not_reach_into_the_next_line(tmp_path: Path) -> None:
    """The transcribed window must stop short of the next line's audio.

    The window pads 0.1s before the first phrase and 0.35s after the last
    one, but never past 0.05s before the next placement starts. l1 ends at
    0.9s and l2 starts at 1.0s, so l1's window must stop at 0.95s, not
    0.9 + 0.35 = 1.25s (which would reach into l2's own speech).
    """
    master = tmp_path / "master.mp4"
    build_video(master, ["sine=frequency=440:duration=2.0"], duration=2.0)
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=2.0,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=0.9, pin_event_out=None),
            PlacementOut(line="l2", phrase=0, out_start=1.0, out_end=2.0, pin_event_out=None),
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=2.0, scenes=[scene], transitions=[])
    script = ScriptModel.model_validate(
        {
            "version": 1,
            "scenes": [
                {
                    "id": "search",
                    "lines": [
                        {"id": "l1", "phrases": [{"text": "Open the search box."}]},
                        {"id": "l2", "phrases": [{"text": "Type tomato in the search box."}]},
                    ],
                }
            ],
        }
    )
    seen_windows: list[str] = []

    def _transcriber(path: Path) -> list[Word]:
        seen_windows.append(path.name)
        return [Word(text="word", start=0.0, end=0.1)]

    ctx = QAContext(
        spec=SpecModel.model_validate({}),
        script=script,
        timeline=timeline,
        master=master,
        master_duration=timeline.duration or 0.0,
        sheets_dir=tmp_path / "sheets",
        work_dir=tmp_path,
        transcriber=_transcriber,  # type: ignore[arg-type]
    )

    check_transcript(ctx)

    assert "transcript-0.000-0.950.wav" in seen_windows
    assert "transcript-0.900-2.000.wav" in seen_windows


def test_transcript_warns_instead_of_failing_on_a_singular_plural_diff(tmp_path: Path) -> None:
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
    script = ScriptModel.model_validate(
        {
            "version": 1,
            "scenes": [
                {
                    "id": "search",
                    "lines": [{"id": "l1", "phrases": [{"text": "Save the results now."}]}],
                }
            ],
        }
    )
    ctx = QAContext(
        spec=SpecModel.model_validate({}),
        script=script,
        timeline=timeline,
        master=master,
        master_duration=timeline.duration or 0.0,
        sheets_dir=tmp_path / "sheets",
        work_dir=tmp_path,
        transcriber=_fake_transcriber("save the result now"),  # type: ignore[arg-type]
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.WARN
    assert "singular/plural only, not a failure" in row.details[0]
    assert "'results' heard as 'result'" in row.details[0]


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


def test_end_noise_skips_a_line_when_the_next_one_starts_too_soon(tmp_path: Path) -> None:
    """A line must not be judged noisy by hearing the start of the next one.

    l1 ends at 0.3s and is followed by silence, so there is no leftover
    noise to find. l2 (loud) starts at 0.55s, only 0.25s later. The old
    300ms window reached to 0.6s regardless, catching 50ms of l2's own
    speech and reporting it as noise left over from l1. The window must
    now stop 0.05s before l2 starts, leaving a clean, silent window.
    """
    master = tmp_path / "master.mp4"
    build_video(
        master,
        [
            "sine=frequency=440:duration=0.3,volume=0.3",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=0.25",
            "sine=frequency=2000:duration=0.5,volume=0.8",
        ],
        duration=1.05,
    )
    scene = SceneOut(
        id="search",
        out_start=0.0,
        out_end=1.05,
        segments=None,
        placements=[
            PlacementOut(line="l1", phrase=0, out_start=0.0, out_end=0.3, pin_event_out=None),
            PlacementOut(line="l2", phrase=0, out_start=0.55, out_end=1.05, pin_event_out=None),
        ],
        captions=None,
        blur=None,
    )
    timeline = Timeline(format="16x9", duration=1.05, scenes=[scene], transitions=[])
    ctx = _context(master, timeline, tmp_path, _fake_transcriber("unused"))

    row = check_end_noise(ctx)

    assert row.status == CheckStatus.PASS
    assert not any("l1" in detail and "loud" in detail for detail in row.details)


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


def _one_line_context(
    tmp_path: Path, phrase: dict[str, str], heard: str, vocabulary: list[str] | None = None
) -> QAContext:
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
    script = ScriptModel.model_validate(
        {"scenes": [{"id": "search", "lines": [{"id": "l1", "phrases": [phrase]}]}]}
    )
    return QAContext(
        spec=SpecModel.model_validate({"voice": {"vocabulary": vocabulary or []}}),
        script=script,
        timeline=timeline,
        master=master,
        master_duration=1.0,
        sheets_dir=tmp_path / "sheets",
        work_dir=tmp_path,
        transcriber=_fake_transcriber(heard),  # type: ignore[arg-type]
    )


def test_transcript_is_checked_against_say(tmp_path: Path) -> None:
    ctx = _one_line_context(
        tmp_path, {"text": "Run reelsmith qa.", "say": "Run reelsmith Q A."}, "run reelsmith q a"
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.PASS


def test_transcript_with_say_still_fails_on_a_dropped_word(tmp_path: Path) -> None:
    ctx = _one_line_context(
        tmp_path, {"text": "Run reelsmith qa.", "say": "Run reelsmith Q A."}, "run reelsmith q"
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.FAIL
    assert "missing word(s) ['a']" in row.details[0]


def test_transcript_warns_on_a_homophone_of_a_vocabulary_word(tmp_path: Path) -> None:
    ctx = _one_line_context(
        tmp_path,
        {"text": "This video was made with reelsmith."},
        "this video was made with realsmith",
        vocabulary=["reelsmith"],
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.WARN
    assert "sounds the same, not a failure" in row.details[0]
    assert "'reelsmith' heard as 'realsmith'" in row.details[0]


def test_transcript_fails_on_a_homophone_outside_the_vocabulary(tmp_path: Path) -> None:
    ctx = _one_line_context(
        tmp_path,
        {"text": "Save the recipe."},
        "safe the recipe",
        vocabulary=["reelsmith"],
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.FAIL
    assert "'save' heard as 'safe'" in row.details[0]


def test_transcript_accepts_digits_abbreviations_and_joins(tmp_path: Path) -> None:
    ctx = _one_line_context(
        tmp_path,
        {"text": "It runs nine checks. Script check and doctor need the plugin."},
        "it runs 9 checks scriptcheck and dr need the plug in",
    )

    row = check_transcript(ctx)

    assert row.status == CheckStatus.PASS
