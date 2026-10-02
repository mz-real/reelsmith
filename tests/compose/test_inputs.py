"""Tests for reading timings.json and building scene timelines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from reelsmith.compose.inputs import load_project, read_timings, slide_images
from reelsmith.errors import ReelsmithError
from reelsmith.paths import DemoPaths


def test_read_timings(demo: Path) -> None:
    timings = read_timings(demo / "voice" / "timings.json")
    line = timings.line("search", "l1")
    assert line is not None
    assert line.file == "search__l1.wav"
    assert [(p.start, p.end) for p in line.phrases] == [(0.0, 1.6), (1.8, 4.0)]
    assert timings.line("search", "nope") is None


def test_missing_timings_tells_you_to_generate_voice(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as info:
        read_timings(tmp_path / "timings.json")
    assert info.value.fix == "reelsmith voice generate"


def test_broken_timings_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "timings.json"
    path.write_text(json.dumps({"lines": [{"scene": "a"}]}), encoding="utf-8")
    with pytest.raises(ReelsmithError, match="timings.json"):
        read_timings(path)


def test_load_project_builds_phrases_and_timelines(demo: Path) -> None:
    project = load_project(DemoPaths.at(demo))
    intro, search = project.scenes
    assert intro.clip is None
    assert [p.text for p in intro.phrases][0].startswith("Recipe Box")
    first = search.phrases[0]
    assert first.pin_time == 1.0
    assert first.wav == demo / "voice" / "search__l1.wav"
    assert (first.audio_start, first.audio_end) == (0.0, 1.6)
    assert search.phrases[1].duration == pytest.approx(2.2)
    assert len(search.timeline.placements) == 2
    assert search.timeline.duration >= 5.0
    assert intro.timeline.duration == pytest.approx(1.9 + 0.15 + 1.9 + 0.35)


def test_engine_none_uses_caption_durations_and_no_audio(demo: Path) -> None:
    spec = yaml.safe_load((demo / "spec.yaml").read_text(encoding="utf-8"))
    spec["voice"] = {"engine": "none"}
    (demo / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (demo / "voice" / "timings.json").unlink()
    project = load_project(DemoPaths.at(demo))
    assert all(p.wav is None for scene in project.scenes for p in scene.phrases)
    assert project.scenes[0].phrases[0].duration >= 1.5


def test_line_without_voice_is_an_error(demo: Path) -> None:
    timings = json.loads((demo / "voice" / "timings.json").read_text(encoding="utf-8"))
    timings["lines"] = timings["lines"][:1]
    (demo / "voice" / "timings.json").write_text(json.dumps(timings), encoding="utf-8")
    with pytest.raises(ReelsmithError, match="search") as info:
        load_project(DemoPaths.at(demo))
    assert info.value.fix == "reelsmith voice generate"


def test_phrase_count_mismatch_is_an_error(demo: Path) -> None:
    timings = json.loads((demo / "voice" / "timings.json").read_text(encoding="utf-8"))
    timings["lines"][1]["phrases"] = timings["lines"][1]["phrases"][:1]
    (demo / "voice" / "timings.json").write_text(json.dumps(timings), encoding="utf-8")
    with pytest.raises(ReelsmithError, match="phrase"):
        load_project(DemoPaths.at(demo))


def test_missing_clip_is_an_error(demo: Path) -> None:
    (demo / "capture" / "clips" / "search" / "clip.json").unlink()
    with pytest.raises(ReelsmithError, match="clip.json"):
        load_project(DemoPaths.at(demo))


def test_slide_images_prefer_numbered_steps(tmp_path: Path) -> None:
    for name in ("flow.png", "flow_step2.png", "flow_step10.png", "flow_step1.png"):
        (tmp_path / name).write_bytes(b"png")
    assert [p.name for p in slide_images(tmp_path, "flow")] == [
        "flow_step1.png",
        "flow_step2.png",
        "flow_step10.png",
    ]
    (tmp_path / "solo.png").write_bytes(b"png")
    assert [p.name for p in slide_images(tmp_path, "solo")] == ["solo.png"]
    assert slide_images(tmp_path, "missing") == []
