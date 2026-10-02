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
