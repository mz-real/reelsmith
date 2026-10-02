"""Tests for export: srt timing, file names, backups and ffmpeg arguments."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reelsmith.compose.inputs import load_project
from reelsmith.errors import ReelsmithError
from reelsmith.export import (
    SrtCue,
    demo_name,
    export_project,
    format_srt,
    narration_args,
    silent_args,
    srt_cues,
    srt_time,
    voiced_args,
)
from reelsmith.paths import DemoPaths


def test_srt_time_format() -> None:
    assert srt_time(0.0) == "00:00:00,000"
    assert srt_time(3725.4567) == "01:02:05,457"


def test_srt_cues_add_the_scene_start_to_each_placement(demo: Path) -> None:
    project = load_project(DemoPaths.at(demo))
    cues = srt_cues(project)
    intro, search = project.scenes
    assert len(cues) == 4
    assert cues[0] == SrtCue(0.0, pytest.approx(1.9), intro.phrases[0].text)  # type: ignore[arg-type]
    offset = intro.timeline.duration
    first = search.timeline.placements[0]
    assert cues[2].start == pytest.approx(offset + first.out_start)
    assert cues[2].end == pytest.approx(offset + first.out_end)
    assert cues[2].text == "Type a dish into the search box."


def test_format_srt_numbers_cues_and_wraps_long_text() -> None:
    text = format_srt(
        [
            SrtCue(0.0, 1.5, "Short."),
            SrtCue(2.0, 4.25, "A much longer phrase that will not fit on one subtitle line at all"),
        ]
    )
    blocks = text.strip().split("\n\n")
    assert blocks[0] == "1\n00:00:00,000 --> 00:00:01,500\nShort."
    lines = blocks[1].split("\n")
    assert lines[:2] == ["2", "00:00:02,000 --> 00:00:04,250"]
    assert all(len(line) <= 42 for line in lines[2:])
    assert len(lines[2:]) == 2


def test_demo_name_is_file_safe() -> None:
    assert demo_name(Path("/x/My Demo é!")) == "my-demo-é"
    assert demo_name(Path("/x/---")) == "demo"


def test_export_args() -> None:
    master = Path("build/master_16x9.mp4")
    assert voiced_args(master, Path("out/a.mp4")) == [
        "-i",
        str(Path("build/master_16x9.mp4")),
        "-map",
        "0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(Path("out/a.mp4")),
    ]
    silent = silent_args(master, Path("out/a_silent.mp4"))
    assert "-an" in silent and silent[silent.index("-c:v") + 1] == "copy"
    narration = narration_args(master, Path("out/a_narration.wav"))
    assert "-vn" in narration and "pcm_s16le" in narration


class FakeFfmpeg:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> None:
        self.calls.append(args)
        Path(args[-1]).write_bytes(b"data")


def test_export_writes_every_file_and_backs_up_old_ones(demo: Path) -> None:
    (demo / "build").mkdir()
    (demo / "build" / "master_16x9.mp4").write_bytes(b"master")
    out = demo / "out"
    out.mkdir()
    (out / "recipes_16x9.mp4").write_bytes(b"old video")
    fake = FakeFfmpeg()
    report = export_project(DemoPaths.at(demo), "recipes", fake)
    names = sorted(p.name for p in report.written)
    assert names == [
        "recipes.srt",
        "recipes_16x9.mp4",
        "recipes_16x9_silent.mp4",
        "recipes_narration.wav",
    ]
    assert len(report.backups) == 1
    assert report.backups[0].read_bytes() == b"old video"
    assert (out / "recipes.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")
    assert len(fake.calls) == 3


def test_export_skips_silent_copy_and_narration_when_voice_is_none(demo: Path) -> None:
    spec = yaml.safe_load((demo / "spec.yaml").read_text(encoding="utf-8"))
    spec["voice"] = {"engine": "none"}
    (demo / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (demo / "build").mkdir()
    (demo / "build" / "master_16x9.mp4").write_bytes(b"master")
    fake = FakeFfmpeg()

    report = export_project(DemoPaths.at(demo), "recipes", fake)

    names = sorted(p.name for p in report.written)
    assert names == ["recipes.srt", "recipes_16x9.mp4"]
    assert len(fake.calls) == 1
    assert any("skipped" in note for note in report.notes)


def test_export_without_a_master_says_to_compose(demo: Path) -> None:
    with pytest.raises(ReelsmithError) as info:
        export_project(DemoPaths.at(demo), "recipes", FakeFfmpeg())
    assert info.value.fix == "reelsmith compose"


def test_export_reports_progress_per_file(demo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from reelsmith import progress

    (demo / "build").mkdir()
    (demo / "build" / "master_16x9.mp4").write_bytes(b"master")
    progress.configure(force=True)
    try:
        export_project(DemoPaths.at(demo), "recipes", FakeFfmpeg())
    finally:
        progress.reset()
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "Export file 1/4: recipes_16x9.mp4"
    assert lines[-1] == "Export file 4/4: recipes.srt"
