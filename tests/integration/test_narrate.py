"""Narrate mode: import, detect, voice, compose, qa and export."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from reelsmith.capture.importer import import_recording
from reelsmith.commands.compose import run_compose
from reelsmith.commands.export import run_export
from reelsmith.commands.voice import run_generate
from reelsmith.detect import run_detect
from reelsmith.models import ClipModel, Event, save_model
from reelsmith.paths import DemoPaths
from reelsmith.qa.checks import CheckStatus
from reelsmith.qa.runner import run_qa
from reelsmith.result import Status

pytestmark = [
    pytest.mark.integration,
    pytest.mark.models,
    pytest.mark.skipif(
        os.environ.get("REELSMITH_TEST_MODELS") != "1",
        reason="set REELSMITH_TEST_MODELS=1 to run model integration tests",
    ),
]


def _ffmpeg(tmp_path: Path, name: str, args: list[str]) -> Path:
    out = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, str(out)],
        check=True,
    )
    return out


def _fifteen_second_sample(tmp_path: Path) -> Path:
    return _ffmpeg(
        tmp_path,
        "narrate.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=640x360:d=5",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=5:size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=640x360:d=5",
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-pix_fmt",
            "yuv420p",
        ],
    )


def _write_narrate_project(root: Path, clip: ClipModel) -> None:
    spec = {
        "version": 1,
        "mode": "narrate",
        "goal": "Integration narrate sample",
        "audience": "ci",
        "target_seconds": 15,
        "formats": ["16:9"],
        "footage": "import",
        "voice": {"engine": "kokoro", "kokoro_voice": "af_heart", "speed": 1.0},
        "options": {
            "allow_holds": True,
            "speed_up_waits": False,
            "captions": "none",
            "highlight_clicks": False,
        },
        "scenes": [{"id": "main", "layout": "full", "clip": "main"}],
        "blur": [],
    }
    script = {
        "version": 1,
        "scenes": [
            {
                "id": "main",
                "lines": [
                    {
                        "id": "l1",
                        "phrases": [
                            {"text": "Red screen.", "pin": "e1"},
                            {"text": "Test pattern.", "pin": "e2"},
                            {"text": "Blue screen.", "pin": "e3"},
                        ],
                    }
                ],
            }
        ],
    }
    (root / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(script), encoding="utf-8")
    clip_dir = root / "capture" / "clips" / "main"
    clip_dir.mkdir(parents=True, exist_ok=True)
    save_model(clip_dir / "clip.json", clip)


def test_narrate_pipeline_exports_and_passes_core_qa(tmp_path: Path, require_ffmpeg: None) -> None:
    root = tmp_path / "narrate-demo"
    root.mkdir()
    source = _fifteen_second_sample(tmp_path)
    import_recording(source, "main", root / "capture" / "clips")
    run_detect(root / "capture" / "clips", "main")

    clip_path = root / "capture" / "clips" / "main" / "clip.json"
    clip = ClipModel.model_validate(json.loads(clip_path.read_text(encoding="utf-8")))
    clip.events = [
        Event(id="e1", t=1.0, type="screen", label="red"),
        Event(id="e2", t=6.0, type="screen", label="pattern"),
        Event(id="e3", t=11.0, type="screen", label="blue"),
    ]
    save_model(clip_path, clip)
    _write_narrate_project(root, clip)

    voice = run_generate(root)
    assert voice.status in {Status.OK, Status.WARN}

    compose = run_compose(root, preview=False)
    assert compose.status in {Status.OK, Status.WARN}

    qa = run_qa(root, "16x9")
    for row_name in ("Sync", "Cut off lines", "Hold limits"):
        line = next(d for d in qa.details if d.startswith(f"{row_name}:"))
        assert CheckStatus.FAIL.value not in line

    export = run_export(root, None)
    assert export.status == Status.OK
    paths = DemoPaths.at(root)
    out_files = list(paths.out.glob("*"))
    assert out_files
    assert any(p.suffix == ".mp4" for p in out_files)
