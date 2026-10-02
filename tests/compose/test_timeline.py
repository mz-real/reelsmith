"""Tests for build/timeline_<format>.json, the file QA reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.compose.inputs import load_project
from reelsmith.compose.project import PREVIEW, compose_project, final_settings
from reelsmith.compose.timeline import src_range_to_out
from reelsmith.models import SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.timing import Segment

SEGMENTS = [
    Segment("play", 0.0, 2.0, 1.0, 0.0, 2.0),
    Segment("hold", 2.0, 2.0, 1.0, 2.0, 3.5),
    Segment("play", 2.0, 6.0, 2.0, 3.5, 5.5),
]


def test_src_range_covers_holds_and_speed() -> None:
    assert src_range_to_out(SEGMENTS, 1.0, 4.0) == (pytest.approx(1.0), pytest.approx(4.5))
    assert src_range_to_out(SEGMENTS, 0.0, 6.0) == (0.0, 5.5)
    assert src_range_to_out(SEGMENTS, 7.0, 8.0) is None


class FakeFfmpeg:
    def __call__(self, args: list[str]) -> None:
        Path(args[-1]).write_bytes(b"video")


def read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_compose_writes_the_timeline_for_each_format(ready: Path) -> None:
    paths = DemoPaths.at(ready)
    compose_project(paths, final_settings(SpecModel()), FakeFfmpeg())
    doc = read(ready / "build" / "timeline_16x9.json")
    assert read(ready / "build" / "timeline.json") == doc
    project = load_project(paths)
    intro, search = project.scenes
    offset = intro.timeline.duration
    assert doc["format"] == "16x9"
    assert doc["duration"] == pytest.approx(offset + search.timeline.duration)
    assert doc["transitions"] == [pytest.approx(offset)]
    first, second = doc["scenes"]
    assert (first["id"], second["id"]) == ("intro", "search")
    assert second["out_start"] == pytest.approx(offset)
    assert second["out_end"] == pytest.approx(doc["duration"])
    seg = second["segments"][0]
    assert set(seg) == {"kind", "src_start", "src_end", "speed", "out_start", "out_end"}
    assert seg["out_start"] == pytest.approx(offset)
    placement = second["placements"][0]
    assert placement == {
        "line": "l1",
        "phrase": 0,
        "out_start": pytest.approx(offset + search.timeline.placements[0].out_start),
        "out_end": pytest.approx(offset + search.timeline.placements[0].out_end),
        "pin_event_out": pytest.approx(offset + 1.0),
    }
    assert second["placements"][1]["phrase"] == 1
    assert first["placements"][0]["pin_event_out"] is None
    heading = second["captions"][0]
    assert heading["text"] == "Find a recipe fast"
    assert heading["out_start"] == pytest.approx(offset)
    x, y, w, h = heading["box"]
    px, py, pw, ph = heading["panel"]
    assert px <= x and py <= y and x + w <= px + pw and y + h <= py + ph
    assert px + pw <= 1920 and py + ph <= 1080
    assert second["captions"][1]["out_start"] == pytest.approx(placement["out_start"])
    blur = second["blur"][0]
    assert blur["out_start"] == pytest.approx(offset)
    bx, by, bw, bh = blur["box"]
    assert bw > 0 and bh > 0 and bx + bw <= 1920 and by + bh <= 1080
    assert first["blur"] == []


def test_timeline_is_written_when_every_scene_is_cached(ready: Path) -> None:
    paths = DemoPaths.at(ready)
    compose_project(paths, final_settings(SpecModel()), FakeFfmpeg())
    (ready / "build" / "timeline_16x9.json").unlink()
    compose_project(paths, final_settings(SpecModel()), FakeFfmpeg())
    assert (ready / "build" / "timeline_16x9.json").is_file()


def test_preview_timeline_does_not_replace_the_final_one(ready: Path) -> None:
    compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert (ready / "build" / "timeline_16x9_preview.json").is_file()
    assert not (ready / "build" / "timeline.json").exists()
