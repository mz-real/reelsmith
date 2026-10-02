"""Tests for the tolerant voice/timings.json reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.qa.timings import load_timings

FULL_DOC = {
    "engine": "kokoro",
    "voice": "af_heart",
    "lines": [
        {
            "scene": "search",
            "line": "l1",
            "file": "search__l1.wav",
            "duration": 3.42,
            "hash": "abc123",
            "phrases": [{"index": 0, "start": 0.0, "end": 1.71}],
            "wpm": 168.0,
            "transcript_ok": True,
            "attempts": 1,
        }
    ],
}


def write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_full_document_parses_with_no_warnings(tmp_path: Path) -> None:
    path = write_json(tmp_path / "timings.json", FULL_DOC)

    timings = load_timings(path)

    assert timings.engine == "kokoro"
    assert timings.voice == "af_heart"
    assert timings.warnings == []
    line = timings.line("search", "l1")
    assert line is not None
    assert line.duration == 3.42
    assert line.phrases[0].end == 1.71
    assert line.transcript_ok is True


def test_missing_fields_are_warnings_not_crashes(tmp_path: Path) -> None:
    path = write_json(tmp_path / "timings.json", {"lines": [{"scene": "search", "line": "l1"}]})

    timings = load_timings(path)

    assert timings.engine is None
    assert timings.voice is None
    assert any("engine" in w for w in timings.warnings)
    line = timings.line("search", "l1")
    assert line is not None
    assert line.duration is None
    assert line.phrases == []


def test_missing_file_raises_with_a_fix(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as info:
        load_timings(tmp_path / "timings.json")
    assert info.value.fix == "reelsmith voice generate"
