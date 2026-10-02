"""Tests for the tolerant build/timeline.json reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.qa.timeline import load_timeline

FULL_DOC = {
    "format": "16x9",
    "duration": 10.0,
    "scenes": [
        {
            "id": "search",
            "out_start": 0.0,
            "out_end": 5.0,
            "segments": [
                {
                    "kind": "play",
                    "src_start": 0.0,
                    "src_end": 5.0,
                    "speed": 1.0,
                    "out_start": 0.0,
                    "out_end": 5.0,
                }
            ],
            "placements": [
                {
                    "line": "l1",
                    "phrase": 0,
                    "out_start": 1.0,
                    "out_end": 2.0,
                    "pin_event_out": 1.1,
                }
            ],
            "captions": [
                {
                    "text": "hello",
                    "out_start": 0.0,
                    "out_end": 2.0,
                    "box": [0, 0, 100, 20],
                    "panel": [0, 0, 200, 40],
                }
            ],
            "blur": [{"box": [0, 0, 10, 10], "out_start": 0.0, "out_end": 5.0}],
        }
    ],
    "transitions": [5.0],
}


def write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_full_document_parses_with_no_warnings(tmp_path: Path) -> None:
    path = write_json(tmp_path / "timeline.json", FULL_DOC)

    timeline = load_timeline(path)

    assert timeline.format == "16x9"
    assert timeline.duration == 10.0
    assert timeline.warnings == []
    scene = timeline.scene("search")
    assert scene is not None
    assert scene.segments is not None and scene.segments[0].kind == "play"
    assert scene.placements is not None and scene.placements[0].line == "l1"
    assert scene.captions is not None and scene.captions[0].box == (0.0, 0.0, 100.0, 20.0)
    assert scene.blur is not None and scene.blur[0].box == (0.0, 0.0, 10.0, 10.0)
    assert timeline.transitions == [5.0]


def test_missing_scene_field_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    data = {
        "format": "16x9",
        "duration": 5.0,
        "scenes": [{"id": "search", "out_start": 0.0, "out_end": 5.0}],
        "transitions": [],
    }
    path = write_json(tmp_path / "timeline.json", data)

    timeline = load_timeline(path)

    scene = timeline.scene("search")
    assert scene is not None
    assert scene.segments is None
    assert scene.placements is None
    assert scene.captions is None
    assert scene.blur is None
    assert any("segments" in w for w in timeline.warnings)
    assert any("placements" in w for w in timeline.warnings)


def test_missing_top_level_fields_are_warnings(tmp_path: Path) -> None:
    path = write_json(tmp_path / "timeline.json", {"scenes": []})

    timeline = load_timeline(path)

    assert timeline.format is None
    assert timeline.duration is None
    assert timeline.transitions is None
    assert any("format" in w for w in timeline.warnings)
    assert any("duration" in w for w in timeline.warnings)
    assert any("transitions" in w for w in timeline.warnings)


def test_missing_file_raises_with_a_fix(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as info:
        load_timeline(tmp_path / "timeline.json")
    assert info.value.fix == "reelsmith compose"


def test_bad_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "timeline.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReelsmithError):
        load_timeline(path)
