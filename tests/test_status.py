"""Tests for reelsmith.status and the `reelsmith status` command."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from reelsmith.cli import app, run
from reelsmith.commands.init import init_demo
from reelsmith.models import ScriptModel
from reelsmith.status import demo_status
from reelsmith.voice.pipeline import _line_hash

SPEC = {
    "version": 1,
    "mode": "produce",
    "formats": ["16:9"],
    "footage": "web",
    "scenes": [
        {"id": "intro", "layout": "slide", "slide": "intro"},
        {"id": "search", "layout": "browser", "clip": "search"},
    ],
}
SCRIPT = {
    "version": 1,
    "scenes": [
        {"id": "intro", "lines": [{"id": "l1", "phrases": [{"text": "Hello there."}]}]},
        {
            "id": "search",
            "lines": [{"id": "l2", "phrases": [{"text": "Type a dish.", "pin": "e1"}]}],
        },
    ],
}
CLIP = {
    "id": "search",
    "video": "video.mp4",
    "width": 1280,
    "height": 720,
    "fps": 30,
    "duration": 5,
    "events": [{"id": "e1", "t": 1.0, "type": "screen"}],
}
QA_REPORT = """# QA report

Generated: 2026-10-02 16:11:20
Format: 16x9
Master: build/master_16x9.mp4 (10.00s)

## 1. Transcript vs script - PASS
- ok

## 2. Sync - {sync}

## 3. Loudness - WARN
- a little quiet

## Contact sheets
- none written
"""

SLIDES = "version: 1\nslides:\n  - {{id: intro, kind: title, title: {title}}}\n"

_clock = [1_000_000.0]


def _touch(path: Path, data: bytes | str = b"x") -> Path:
    """Write a file with an mtime later than every file written before it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    _clock[0] += 10
    os.utime(path, (_clock[0], _clock[0]))
    return path


def _write_voice(root: Path) -> None:
    script = ScriptModel.model_validate(SCRIPT)
    lines = []
    for scene in script.scenes:
        for line in scene.lines:
            name = f"{scene.id}__{line.id}.wav"
            _touch(root / "voice" / name)
            lines.append(
                {
                    "scene": scene.id,
                    "line": line.id,
                    "file": name,
                    "hash": _line_hash(line, "kokoro", "af_heart", 1.0, {}),
                }
            )
    payload = {"engine": "kokoro", "voice": "af_heart", "lines": lines}
    _touch(root / "voice" / "timings.json", json.dumps(payload))


def _demo(tmp_path: Path, upto: str = "export", sync: str = "PASS") -> Path:
    """A demo folder that is done up to and including the named step."""
    order = ["spec", "clips", "script", "voice", "slides", "master", "qa", "export"]
    stop = order.index(upto)
    root = tmp_path / "demo"
    root.mkdir()
    _touch(root / "spec.yaml", yaml.safe_dump(SPEC))
    if stop >= 1:
        _touch(root / "capture" / "clips" / "search" / "video.mp4")
        _touch(root / "capture" / "clips" / "search" / "clip.json", json.dumps(CLIP))
    if stop >= 2:
        _touch(root / "script.yaml", yaml.safe_dump(SCRIPT))
    if stop >= 3:
        _write_voice(root)
    if stop >= 4:
        _touch(root / "slides.yaml", SLIDES.format(title="Hi"))
        _touch(root / "slides" / "16x9" / "intro_step0.png")
        _touch(root / "slides" / "16x9" / "intro.png")
    if stop >= 5:
        _touch(root / "build" / "master_16x9.mp4")
    if stop >= 6:
        _touch(root / "qa" / "report.md", QA_REPORT.format(sync=sync))
    if stop >= 7:
        for name in ("demo_16x9.mp4", "demo_16x9_silent.mp4", "demo_narration.wav", "demo.srt"):
            _touch(root / "out" / name)
    return root


def _states(root: Path) -> dict[str, str]:
    return {step.name: step.state for step in demo_status(root).steps}


def test_empty_folder_says_to_init_with_a_preset(tmp_path: Path) -> None:
    report = demo_status(tmp_path)
    assert report.steps[0].name == "spec"
    assert report.steps[0].state == "missing"
    assert report.next.startswith("reelsmith init")
    assert "--preset" in report.next


def test_step_names_are_in_workflow_order(tmp_path: Path) -> None:
    names = [step.name for step in demo_status(tmp_path).steps]
    assert names == ["spec", "clips", "script", "voice", "slides", "master", "qa", "export"]


def test_a_finished_demo_is_all_done(tmp_path: Path) -> None:
    root = _demo(tmp_path)
    report = demo_status(root)
    assert {step.state for step in report.steps} == {"done"}, report.steps
    assert "out" in report.next


def test_fresh_quick_preset_needs_footage_first(tmp_path: Path) -> None:
    root = tmp_path / "quick"
    init_demo(root, force=False, preset="quick")
    report = demo_status(root)
    states = {step.name: step.state for step in report.steps}
    assert states["spec"] == "done"
    assert states["clips"] == "missing"
    assert report.next.startswith("reelsmith capture web capture/flows/feature.py --id feature")


def test_starter_text_in_the_script_is_not_done(tmp_path: Path) -> None:
    root = tmp_path / "quick"
    init_demo(root, force=False, preset="quick")
    script = next(step for step in demo_status(root).steps if step.name == "script")
    assert script.state == "missing"
    assert "starter text" in script.detail


def test_narrate_clip_without_events_says_to_detect(tmp_path: Path) -> None:
    root = tmp_path / "narrate"
    init_demo(root, force=False, preset="narrate")
    clip = dict(CLIP, id="main", events=[])
    _touch(root / "capture" / "clips" / "main" / "video.mp4")
    _touch(root / "capture" / "clips" / "main" / "clip.json", json.dumps(clip))
    report = demo_status(root)
    assert report.next.startswith("reelsmith detect --clip main")


def test_bad_spec_is_failed(tmp_path: Path) -> None:
    (tmp_path / "spec.yaml").write_text("version: 1\nnot_a_field: 1\n", encoding="utf-8")
    report = demo_status(tmp_path)
    assert report.steps[0].state == "failed"
    assert "not_a_field" in report.steps[0].detail


def test_unresolved_pin_fails_the_script(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="script")
    clip = dict(CLIP, events=[])
    _touch(root / "capture" / "clips" / "search" / "clip.json", json.dumps(clip))
    report = demo_status(root)
    script = next(step for step in report.steps if step.name == "script")
    assert script.state == "failed"
    assert "e1" in script.detail
    assert report.next.endswith("reelsmith script check " + str(root))


def test_voice_missing_then_done_then_stale(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="script")
    assert _states(root)["voice"] == "missing"
    _write_voice(root)
    voice = next(step for step in demo_status(root).steps if step.name == "voice")
    assert voice.state == "done"
    assert voice.detail.startswith("2/2 lines up to date")
    changed = json.loads(json.dumps(SCRIPT))
    changed["scenes"][0]["lines"][0]["phrases"][0]["text"] = "Hello again."
    _touch(root / "script.yaml", yaml.safe_dump(changed))
    report = demo_status(root)
    voice = next(step for step in report.steps if step.name == "voice")
    assert voice.state == "stale"
    assert "intro/l1" in voice.detail
    assert report.next == f"reelsmith voice generate {root}"


def test_voice_off_counts_as_done(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="script")
    spec = dict(SPEC, voice={"engine": "none"})
    _touch(root / "spec.yaml", yaml.safe_dump(spec))
    assert _states(root)["voice"] == "done"


def test_slides_per_format(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="slides")
    spec = dict(SPEC, formats=["16:9", "9:16"])
    _touch(root / "spec.yaml", yaml.safe_dump(spec))
    report = demo_status(root)
    slides = next(step for step in report.steps if step.name == "slides")
    assert slides.state == "missing"
    assert "16x9: 1/1" in slides.detail
    assert "9x16: 0/1" in slides.detail
    assert report.next == f"reelsmith slides {root}"


def test_slides_older_than_slides_yaml_are_stale(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="slides")
    _touch(root / "slides.yaml", SLIDES.format(title="Yo"))
    assert _states(root)["slides"] == "stale"


def test_master_missing_suggests_a_preview_first(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="slides")
    assert demo_status(root).next == f"reelsmith compose --preview {root}"
    _touch(root / "build" / "master_16x9_preview.mp4")
    report = demo_status(root)
    master = next(step for step in report.steps if step.name == "master")
    assert master.state == "missing"
    assert "preview" in master.detail
    assert report.next == f"reelsmith compose {root}"


def test_master_older_than_an_input_is_stale(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="master")
    assert _states(root)["master"] == "done"
    _touch(root / "voice" / "intro__l1.wav", b"new take")
    report = demo_status(root)
    master = next(step for step in report.steps if step.name == "master")
    assert master.state == "stale"
    assert "intro__l1.wav" in master.detail


def test_qa_counts_and_failures(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="qa")
    qa = next(step for step in demo_status(root).steps if step.name == "qa")
    assert qa.state == "done"
    assert qa.detail == "3 checks: 2 PASS, 1 WARN, 0 FAIL"
    _touch(root / "qa" / "report.md", QA_REPORT.format(sync="FAIL"))
    report = demo_status(root)
    qa = next(step for step in report.steps if step.name == "qa")
    assert qa.state == "failed"
    assert "Sync" in qa.detail
    assert report.next.endswith(f"reelsmith qa {root}")


def test_qa_older_than_master_is_stale(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="qa")
    _touch(root / "build" / "master_16x9.mp4")
    assert _states(root)["qa"] == "stale"


def test_export_missing_and_custom_name(tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="qa")
    report = demo_status(root)
    assert report.next == f"reelsmith export {root}"
    for name in ("promo_16x9.mp4", "promo_16x9_silent.mp4", "promo_narration.wav", "promo.srt"):
        _touch(root / "out" / name)
    assert _states(root)["export"] == "done"


def test_status_cli_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="voice")
    code = run(app, ["status", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("[OK] 4 of 8 steps done")
    assert "  - voice: done, 2/2 lines up to date" in lines
    assert lines[-1] == f"Next: Write slides.yaml, then run: reelsmith slides {root}"


def test_status_cli_json_is_one_compact_object(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _demo(tmp_path, upto="voice")
    code = run(app, ["status", str(root), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("\n") == 1
    data = json.loads(out)
    assert out == json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    assert set(data) == {"steps", "next"}
    assert data["next"] == f"Write slides.yaml, then run: reelsmith slides {root}"
    assert data["steps"][0]["state"] == "done"
    assert {tuple(step) for step in data["steps"]} == {("name", "state", "detail")}


def test_global_json_flag_gives_the_same_status_object(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _demo(tmp_path, upto="voice")
    run(app, ["status", str(root), "--json"])
    local = capsys.readouterr().out
    run(app, ["--json", "status", str(root)])
    assert capsys.readouterr().out == local


def test_status_in_the_current_folder_leaves_the_folder_out(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _demo(tmp_path, upto="voice")
    monkeypatch.chdir(root)
    run(app, ["status"])
    last = capsys.readouterr().out.splitlines()[-1]
    assert last == "Next: Write slides.yaml, then run: reelsmith slides"


def test_status_with_stale_steps_warns(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    root = _demo(tmp_path, upto="master")
    _touch(root / "voice" / "intro__l1.wav", b"new take")
    run(app, ["status", str(root)])
    assert capsys.readouterr().out.startswith("[WARN]")
