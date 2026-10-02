"""Tests for `reelsmith script check`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.cli import app, run

SPEC = """\
goal: Show search
scenes:
  - id: intro
    layout: slide
    slide: intro
  - id: search
    layout: browser
    clip: search
"""

SCRIPT = """\
scenes:
  - id: intro
    lines:
      - id: l1
        phrases:
          - text: Meet Recipe Box.
  - id: search
    caption: Find a recipe fast
    lines:
      - id: l1
        phrases:
          - text: Type a dish into the search box.
            pin: {pin}
          - text: Results update as you type.
"""

CLIP = {
    "id": "search",
    "video": "video.mp4",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "duration": 12.4,
    "events": [{"id": "e1", "t": 2.1, "type": "click", "x": 0.42, "y": 0.18}],
}


def make_demo(root: Path, pin: str = "e1", script: str | None = None) -> Path:
    (root / "spec.yaml").write_text(SPEC, encoding="utf-8")
    text = script if script is not None else SCRIPT.format(pin=pin)
    (root / "script.yaml").write_text(text, encoding="utf-8")
    clip_dir = root / "capture" / "clips" / "search"
    clip_dir.mkdir(parents=True)
    (clip_dir / "clip.json").write_text(json.dumps(CLIP), encoding="utf-8")
    return root


def test_a_good_script_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_demo(tmp_path)

    code = run(app, ["script", "check", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0].startswith("[OK]")
    assert "2 scenes, 2 lines, 1 pin" in out


def test_a_pin_to_a_missing_event_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_demo(tmp_path, pin="e9")

    code = run(app, ["script", "check", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("[ERROR]")
    assert "Scene 'search', line 'l1', phrase 1 is pinned to 'e9'" in out
    assert "clip 'search' has no such event" in out


def test_a_pin_in_a_slide_scene_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = SCRIPT.format(pin="e1").replace(
        "- text: Meet Recipe Box.", "- text: Meet Recipe Box.\n            pin: e1"
    )
    make_demo(tmp_path, script=script)

    code = run(app, ["script", "check", str(tmp_path)])

    assert code == 1
    assert "is a slide" in capsys.readouterr().out


def test_a_scene_missing_from_the_spec_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = SCRIPT.format(pin="e1") + "  - id: extra\n    lines: []\n"
    make_demo(tmp_path, script=script)

    code = run(app, ["script", "check", str(tmp_path)])

    assert code == 1
    assert "Scene 'extra' is not in spec.yaml" in capsys.readouterr().out


def test_a_missing_clip_for_a_pin_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_demo(tmp_path)
    (tmp_path / "capture" / "clips" / "search" / "clip.json").unlink()

    code = run(app, ["script", "check", str(tmp_path)])

    assert code == 1
    assert "clip.json" in capsys.readouterr().out


def test_a_missing_script_gives_an_error_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "spec.yaml").write_text(SPEC, encoding="utf-8")

    code = run(app, ["script", "check", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 1
    assert "Traceback" not in out
    assert "script.yaml" in out


def test_spec_scenes_without_narration_are_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = "scenes:\n  - id: intro\n    lines:\n      - id: l1\n        phrases:\n"
    script += "          - text: Hello.\n"
    make_demo(tmp_path, script=script)

    code = run(app, ["script", "check", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("[WARN]")
    assert "Scene 'search' has no narration" in out
