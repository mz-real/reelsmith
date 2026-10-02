"""Tests for reading timings.json and building scene timelines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from reelsmith.compose.inputs import load_project, read_timings, resolve_slide_images, slide_images
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


def test_stale_timings_entry_not_in_script_is_ignored(demo: Path) -> None:
    timings = json.loads((demo / "voice" / "timings.json").read_text(encoding="utf-8"))
    timings["lines"].append(
        {
            "scene": "search",
            "line": "l3",
            "file": "search__l3.wav",
            "duration": 1.0,
            "hash": "old",
            "phrases": [{"index": 0, "start": 0.0, "end": 1.0}],
            "wpm": 150.0,
            "transcript_ok": True,
            "attempts": 1,
        }
    )
    (demo / "voice" / "timings.json").write_text(json.dumps(timings), encoding="utf-8")
    load_project(DemoPaths.at(demo))


def test_script_line_with_no_audio_timing_is_a_clear_error(demo: Path) -> None:
    timings = json.loads((demo / "voice" / "timings.json").read_text(encoding="utf-8"))
    timings["lines"] = [row for row in timings["lines"] if row["scene"] != "search"]
    (demo / "voice" / "timings.json").write_text(json.dumps(timings), encoding="utf-8")
    with pytest.raises(ReelsmithError, match="search.*l1.*no voice yet") as info:
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


def _fake_png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big")


def test_resolve_slide_images_prefers_format_subdirectory(tmp_path: Path) -> None:
    flat = tmp_path / "intro.png"
    flat.write_bytes(_fake_png_header(1920, 1080))
    per_format = tmp_path / "9x16" / "intro.png"
    per_format.parent.mkdir()
    per_format.write_bytes(_fake_png_header(1080, 1920))
    paths, warnings = resolve_slide_images(tmp_path, "intro", "9:16")
    assert warnings == []
    assert paths == [per_format]


def test_resolve_slide_images_warns_on_flat_fallback_with_wrong_aspect(tmp_path: Path) -> None:
    flat = tmp_path / "intro.png"
    flat.write_bytes(_fake_png_header(1920, 1080))
    paths, warnings = resolve_slide_images(tmp_path, "intro", "9:16")
    assert paths == [flat]
    assert len(warnings) == 1
    assert "intro" in warnings[0]
    assert "reelsmith slides" in warnings[0]
    assert "9x16" in warnings[0]
