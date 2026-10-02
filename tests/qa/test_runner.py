"""End to end tests for run_qa over a small synthetic demo folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from media_fixtures import build_video

from reelsmith.errors import ReelsmithError
from reelsmith.qa.runner import run_qa
from reelsmith.qa.transcribe import Word
from reelsmith.result import Status

SPEC = {"version": 1}
SCRIPT = {
    "version": 1,
    "scenes": [
        {
            "id": "search",
            "lines": [{"id": "l1", "phrases": [{"text": "Type a dish into the search box."}]}],
        }
    ],
}
TIMINGS = {
    "engine": "kokoro",
    "voice": "af_heart",
    "lines": [
        {
            "scene": "search",
            "line": "l1",
            "file": "search__l1.wav",
            "duration": 1.0,
            "hash": "abc123",
            "phrases": [{"index": 0, "start": 0.0, "end": 1.0}],
            "wpm": 160.0,
            "transcript_ok": True,
            "attempts": 1,
        }
    ],
}


def _timeline(pin_event_out: float) -> dict[str, object]:
    return {
        "format": "16x9",
        "duration": 2.0,
        "scenes": [
            {
                "id": "search",
                "out_start": 0.0,
                "out_end": 2.0,
                "segments": [
                    {
                        "kind": "play",
                        "src_start": 0.0,
                        "src_end": 2.0,
                        "speed": 1.0,
                        "out_start": 0.0,
                        "out_end": 2.0,
                    }
                ],
                "placements": [
                    {
                        "line": "l1",
                        "phrase": 0,
                        "out_start": 0.0,
                        "out_end": 1.0,
                        "pin_event_out": pin_event_out,
                    }
                ],
                "captions": [],
                "blur": [],
            }
        ],
        "transitions": [],
    }


def _fake_transcriber(path: Path) -> list[Word]:
    words = "type a dish into the search box".split()
    return [Word(text=word, start=0.0, end=0.1) for word in words]


def _build_demo(root: Path, pin_event_out: float = 0.0) -> None:
    (root / "build").mkdir(parents=True)
    (root / "voice").mkdir(parents=True)
    (root / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    (root / "voice" / "timings.json").write_text(json.dumps(TIMINGS), encoding="utf-8")
    (root / "build" / "timeline.json").write_text(
        json.dumps(_timeline(pin_event_out)), encoding="utf-8"
    )
    master = root / "build" / "master_16x9.mp4"
    build_video(
        master,
        [
            "sine=frequency=440:duration=1.0,loudnorm=I=-16:TP=-1.0:LRA=11",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=1.0",
        ],
        duration=2.0,
    )


def test_run_qa_passes_everything_and_writes_a_report(tmp_path: Path) -> None:
    _build_demo(tmp_path, pin_event_out=0.0)

    result = run_qa(tmp_path, "16x9", transcriber=_fake_transcriber)

    assert result.status == Status.OK
    report_path = tmp_path / "qa" / "report.md"
    assert report_path.is_file()
    text = report_path.read_text(encoding="utf-8")
    assert "Transcript vs script - PASS" in text
    assert "Sync - PASS" in text
    assert "Loudness - PASS" in text
    assert (tmp_path / "qa" / "sheets" / "scenes.jpg").is_file()


def test_run_qa_reports_error_when_sync_fails(tmp_path: Path) -> None:
    _build_demo(tmp_path, pin_event_out=5.0)

    result = run_qa(tmp_path, "16x9", transcriber=_fake_transcriber)

    assert result.status == Status.ERROR
    text = (tmp_path / "qa" / "report.md").read_text(encoding="utf-8")
    assert "Sync - FAIL" in text
    assert "Fix" in text


def test_run_qa_backs_up_an_existing_report(tmp_path: Path) -> None:
    _build_demo(tmp_path, pin_event_out=0.0)
    (tmp_path / "qa").mkdir()
    old_report = tmp_path / "qa" / "report.md"
    old_report.write_text("old report", encoding="utf-8")

    run_qa(tmp_path, "16x9", transcriber=_fake_transcriber)

    backups = list((tmp_path / "qa").glob("report.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old report"


def _build_preview_demo(root: Path, pin_event_out: float = 0.0) -> None:
    (root / "build").mkdir(parents=True)
    (root / "voice").mkdir(parents=True)
    (root / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    (root / "voice" / "timings.json").write_text(json.dumps(TIMINGS), encoding="utf-8")
    (root / "build" / "timeline_16x9_preview.json").write_text(
        json.dumps(_timeline(pin_event_out)), encoding="utf-8"
    )
    master = root / "build" / "master_16x9_preview.mp4"
    build_video(
        master,
        [
            "sine=frequency=440:duration=1.0,loudnorm=I=-16:TP=-1.0:LRA=11",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=1.0",
        ],
        duration=2.0,
    )


def test_run_qa_preview_checks_the_preview_master_and_timeline(tmp_path: Path) -> None:
    _build_preview_demo(tmp_path, pin_event_out=0.0)

    result = run_qa(tmp_path, "16x9", transcriber=_fake_transcriber, preview=True)

    assert result.status == Status.OK
    report = (tmp_path / "qa" / "report.md").read_text(encoding="utf-8")
    assert "# QA report (preview check)" in report
    assert "master_16x9_preview.mp4" in report


def test_run_qa_preview_raises_when_the_preview_master_is_missing(tmp_path: Path) -> None:
    (tmp_path / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (tmp_path / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")

    with pytest.raises(ReelsmithError) as info:
        run_qa(tmp_path, "16x9", preview=True)
    assert "--preview" in str(info.value.fix)


def test_run_qa_raises_when_master_is_missing(tmp_path: Path) -> None:
    (tmp_path / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (tmp_path / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")

    with pytest.raises(ReelsmithError) as info:
        run_qa(tmp_path, "16x9")
    assert "reelsmith compose" in str(info.value.fix)


def test_run_qa_raises_when_spec_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as info:
        run_qa(tmp_path, "16x9")
    assert info.value.fix == "reelsmith init"
