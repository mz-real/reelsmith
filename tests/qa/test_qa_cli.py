"""CLI integration for `reelsmith qa`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from media_fixtures import build_video

from reelsmith.cli import app, run

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
TIMELINE = {
    "format": "16x9",
    "duration": 2.0,
    "scenes": [
        {
            "id": "search",
            "out_start": 0.0,
            "out_end": 2.0,
            "segments": [],
            "placements": [
                {"line": "l1", "phrase": 0, "out_start": 0.0, "out_end": 1.0, "pin_event_out": 0.0}
            ],
            "captions": [],
            "blur": [],
        }
    ],
    "transitions": [],
}


def test_qa_help_registers_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(app, ["qa", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "qa" in out.lower()


def test_qa_missing_demo_is_an_error_block_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(app, ["qa", str(tmp_path)])
    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert out.startswith("[ERROR]")
    assert code == 1


def test_qa_when_the_speech_model_cannot_load_gives_a_clear_fix_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # For example offline on first use: the transcript check warns with the
    # fix and every other check still runs.
    from reelsmith.errors import ReelsmithError
    from reelsmith.voice import transcribe as voice_transcribe

    def offline(audio: object) -> list[object]:
        raise ReelsmithError("Could not load the base.en speech model.", fix="retry online")

    monkeypatch.setattr(voice_transcribe, "transcribe", offline)
    (tmp_path / "build").mkdir()
    (tmp_path / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (tmp_path / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    (tmp_path / "build" / "timeline.json").write_text(json.dumps(TIMELINE), encoding="utf-8")
    build_video(
        tmp_path / "build" / "master_16x9.mp4",
        [
            "sine=frequency=440:duration=1.0,loudnorm=I=-16:TP=-1.0:LRA=11",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=1.0",
        ],
        duration=2.0,
    )

    code = run(app, ["qa", str(tmp_path)])

    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert out.startswith("[WARN]")
    assert "Transcript vs script: WARN" in out
    assert code == 0

    report = (tmp_path / "qa" / "report.md").read_text(encoding="utf-8")
    assert "Could not load the base.en speech model" in report
    assert "retry online" in report
