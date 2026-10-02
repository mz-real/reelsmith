"""Tests for reelsmith.paths."""

from __future__ import annotations

from pathlib import Path

from reelsmith.paths import DemoPaths


def test_demo_paths_at_builds_expected_layout(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)

    assert paths.root == tmp_path
    assert paths.spec == tmp_path / "spec.yaml"
    assert paths.brand == tmp_path / "brand.yaml"
    assert paths.script == tmp_path / "script.yaml"
    assert paths.flows == tmp_path / "capture" / "flows"
    assert paths.clips == tmp_path / "capture" / "clips"
    assert paths.voice == tmp_path / "voice"
    assert paths.slides == tmp_path / "slides"
    assert paths.build == tmp_path / "build"
    assert paths.qa == tmp_path / "qa"
    assert paths.out == tmp_path / "out"


def test_demo_paths_is_frozen(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    try:
        paths.root = tmp_path / "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("DemoPaths should be frozen")
