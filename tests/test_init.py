"""Tests for reelsmith init."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reelsmith.cli import run
from reelsmith.commands.init import init_demo
from reelsmith.errors import ReelsmithError
from reelsmith.models import BrandModel, ScriptModel, SpecModel
from reelsmith.models.io import load_model
from reelsmith.paths import DemoPaths


def test_init_creates_tree_and_starter_files(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    code = init_demo(root, force=False)
    assert code == 0
    paths = DemoPaths.at(root)
    assert paths.spec.is_file()
    assert paths.brand.is_file()
    assert paths.script.is_file()
    assert paths.flows.is_dir()
    assert paths.clips.is_dir()
    assert paths.voice.is_dir()
    assert paths.out.is_dir()
    text = paths.spec.read_text(encoding="utf-8")
    assert "kokoro" in text


def test_init_refuses_nonempty_without_force(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "notes.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(ReelsmithError) as exc:
        init_demo(root, force=False)
    assert "not empty" in str(exc.value)


def test_init_force_allows_nonempty(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "notes.txt").write_text("hi", encoding="utf-8")
    assert init_demo(root, force=True) == 0
    assert DemoPaths.at(root).spec.is_file()


def test_init_force_backups_edited_starter_files(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    assert init_demo(root, force=False) == 0
    paths = DemoPaths.at(root)
    paths.spec.write_text("version: 1\ncustom: true\n", encoding="utf-8")

    assert init_demo(root, force=True) == 0

    backups = sorted(root.glob("spec.yaml.bak-*"))
    assert len(backups) == 1
    assert "custom: true" in backups[0].read_text(encoding="utf-8")
    assert "kokoro" in paths.spec.read_text(encoding="utf-8")


def test_init_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from reelsmith.cli import app

    root = tmp_path / "my demo"
    code = run(app, ["init", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[OK]" in out
    assert root.is_dir()


def test_init_force_skips_backup_of_unchanged_files(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    init_demo(root, force=False)
    init_demo(root, force=True)
    assert not list(root.glob("*.bak-*"))


@pytest.mark.parametrize(
    ("name", "model"),
    [("spec.yaml", SpecModel), ("script.yaml", ScriptModel), ("brand.yaml", BrandModel)],
)
def test_starter_files_match_the_models(tmp_path: Path, name: str, model: type[Any]) -> None:
    root = tmp_path / "demo"
    init_demo(root, force=False)
    load_model(root / name, model)


PRESETS = ("quick", "tour", "mobile", "release-notes", "narrate")


@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_writes_valid_files(tmp_path: Path, preset: str) -> None:
    from reelsmith.commands.script_check import check_script
    from reelsmith.models import SlidesModel

    root = tmp_path / "demo"
    assert init_demo(root, force=False, preset=preset) == 0
    spec = load_model(root / "spec.yaml", SpecModel)
    script = load_model(root / "script.yaml", ScriptModel)
    load_model(root / "brand.yaml", BrandModel)
    assert spec.theme == "studio"
    report = check_script(spec, script, lambda _clip: None)
    assert report.problems == []
    assert report.warnings == []
    slide_ids = {scene.slide for scene in spec.scenes if scene.layout == "slide"}
    if slide_ids:
        slides = load_model(root / "slides.yaml", SlidesModel)
        assert slide_ids <= {slide.id for slide in slides.slides}
    for scene in spec.scenes:
        for point in scene.points:
            script_scene = script.scene(scene.id)
            assert script_scene is not None
            assert point.line in {line.id for line in script_scene.lines}


@pytest.mark.parametrize("preset", PRESETS)
def test_preset_files_have_no_todo_markers(tmp_path: Path, preset: str) -> None:
    root = tmp_path / "demo"
    init_demo(root, force=False, preset=preset)
    for name in ("spec.yaml", "script.yaml", "slides.yaml"):
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "TODO" not in text.upper()
            assert "#" in text, f"{name} should carry comments for the AI"


@pytest.mark.parametrize(
    ("preset", "low", "high"),
    [("quick", 30, 60), ("tour", 180, 300), ("release-notes", 60, 120)],
)
def test_preset_lengths_match_the_design(
    tmp_path: Path, preset: str, low: float, high: float
) -> None:
    root = tmp_path / "demo"
    init_demo(root, force=False, preset=preset)
    spec = load_model(root / "spec.yaml", SpecModel)
    assert low <= spec.target_seconds <= high


def test_mobile_and_narrate_presets_pick_their_footage(tmp_path: Path) -> None:
    init_demo(tmp_path / "m", force=False, preset="mobile")
    init_demo(tmp_path / "n", force=False, preset="narrate")
    mobile = load_model(tmp_path / "m" / "spec.yaml", SpecModel)
    narrate = load_model(tmp_path / "n" / "spec.yaml", SpecModel)
    assert mobile.footage == "mobile"
    assert any(scene.layout == "phone" for scene in mobile.scenes)
    assert narrate.mode == "narrate"
    assert narrate.footage == "import"
    assert all(scene.layout == "full" for scene in narrate.scenes)
    assert not (tmp_path / "n" / "slides.yaml").exists()


def test_init_without_preset_keeps_the_starter(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    init_demo(root, force=False)
    assert not (root / "slides.yaml").exists()
    assert "Find a recipe fast" in (root / "script.yaml").read_text(encoding="utf-8")


def test_unknown_preset_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as exc:
        init_demo(tmp_path / "demo", force=False, preset="nope")
    assert "quick" in str(exc.value)


def test_init_cli_with_preset(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from reelsmith.cli import app

    root = tmp_path / "demo"
    code = run(app, ["init", str(root), "--preset", "tour"])
    out = capsys.readouterr().out
    assert code == 0
    assert "tour" in out
    assert "reelsmith status" in out
    assert (root / "slides.yaml").is_file()
