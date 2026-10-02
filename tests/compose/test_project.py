"""Tests for composing a project with a fake ffmpeg: cache, preview, warnings."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reelsmith.compose.project import PREVIEW, compose_project, final_settings
from reelsmith.compose.scene import step_times
from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.timing import Placement


class FakeFfmpeg:
    """Records each call and writes a small file where ffmpeg would."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> None:
        self.calls.append(args)
        Path(args[-1]).write_bytes(b"video")


def edit_yaml(path: Path, change: object) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)  # type: ignore[operator]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_first_compose_renders_every_scene_and_the_master(ready: Path) -> None:
    fake = FakeFfmpeg()
    report = compose_project(DemoPaths.at(ready), final_settings(SpecModel()), fake)
    fmt = report.formats[0]
    assert fmt.rendered == ["intro", "search"]
    assert fmt.reused == []
    assert fmt.master == ready / "build" / "master_16x9.mp4"
    assert fmt.master.is_file()
    assert len(fake.calls) == 3
    assert not list((ready / "build" / "scenes").glob("*.partial.mp4"))
    assert len(list((ready / "build" / "scenes").glob("*.mp4"))) == 2


def test_second_compose_reuses_unchanged_scenes(ready: Path) -> None:
    compose_project(DemoPaths.at(ready), final_settings(SpecModel()), FakeFfmpeg())
    fake = FakeFfmpeg()
    report = compose_project(DemoPaths.at(ready), final_settings(SpecModel()), fake)
    assert report.formats[0].reused == ["intro", "search"]
    assert len(fake.calls) == 1  # only the master


def test_a_changed_scene_is_rendered_again(ready: Path) -> None:
    compose_project(DemoPaths.at(ready), final_settings(SpecModel()), FakeFfmpeg())

    def new_caption(data: dict) -> None:  # type: ignore[type-arg]
        data["scenes"][1]["caption"] = "Search in a second"

    edit_yaml(ready / "script.yaml", new_caption)
    report = compose_project(DemoPaths.at(ready), final_settings(SpecModel()), FakeFfmpeg())
    assert report.formats[0].rendered == ["search"]
    assert report.formats[0].reused == ["intro"]


def test_changed_audio_renders_the_scene_again(ready: Path) -> None:
    compose_project(DemoPaths.at(ready), final_settings(SpecModel()), FakeFfmpeg())
    (ready / "voice" / "intro__l1.wav").write_bytes(b"new take")
    report = compose_project(DemoPaths.at(ready), final_settings(SpecModel()), FakeFfmpeg())
    assert report.formats[0].rendered == ["intro"]


def test_preview_ignores_the_cache_and_renders_small(ready: Path) -> None:
    compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    fake = FakeFfmpeg()
    report = compose_project(DemoPaths.at(ready), PREVIEW, fake)
    assert report.formats[0].rendered == ["intro", "search"]
    assert report.formats[0].master == ready / "build" / "master_16x9_preview.mp4"
    search_graph = fake.calls[1][fake.calls[1].index("-filter_complex") + 1]
    assert "s=960x540" in search_graph
    assert fake.calls[1][fake.calls[1].index("-preset") + 1] == "ultrafast"


def test_every_format_gets_a_master(ready: Path) -> None:
    edit_yaml(ready / "spec.yaml", lambda d: d.update(formats=["16:9", "9:16"]))
    report = compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert [f.master.name for f in report.formats] == [
        "master_16x9_preview.mp4",
        "master_9x16_preview.mp4",
    ]


def test_timing_conflicts_become_warnings(ready: Path) -> None:
    def no_holds(data: dict) -> None:  # type: ignore[type-arg]
        data["options"] = {"allow_holds": False}

    def pin_both(data: dict) -> None:  # type: ignore[type-arg]
        data["scenes"][1]["lines"][0]["phrases"][1]["pin"] = "e1"

    edit_yaml(ready / "spec.yaml", no_holds)
    edit_yaml(ready / "script.yaml", pin_both)
    report = compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert len(report.warnings) == 1
    assert "Scene 'search', line 'l1'" in report.warnings[0]
    assert "s over" in report.warnings[0]


def test_missing_slide_says_to_render_slides(ready: Path) -> None:
    (ready / "slides" / "intro.png").unlink()
    with pytest.raises(ReelsmithError) as info:
        compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert info.value.fix == "reelsmith slides"


def test_missing_wav_says_to_generate_voice(ready: Path) -> None:
    (ready / "voice" / "search__l1.wav").unlink()
    with pytest.raises(
        ReelsmithError, match="search.*l1.*no audio file voice/search__l1.wav"
    ) as info:
        compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert info.value.fix == "reelsmith voice generate --only search/l1"


def test_step_times_follow_phrases_then_spread() -> None:
    placements = [Placement(0, 0.0, 1.0), Placement(1, 1.2, 2.0)]
    assert step_times(1, placements, 5.0) == [0.0]
    assert step_times(2, placements, 5.0) == [0.0, 1.2]
    times = step_times(4, placements, 5.0)
    assert times[:2] == [0.0, 1.2]
    assert times[1] < times[2] < times[3] < 5.0
