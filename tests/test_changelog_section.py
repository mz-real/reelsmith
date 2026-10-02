"""Tests for scripts/changelog_section.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "changelog_section.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("changelog_section", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


changelog_section = _load()

SAMPLE = """# Changelog

## [Unreleased]

### Added
- Something new

## [0.2.0] - 2026-01-02

### Fixed
- A bug

## [0.1.0] - 2025-12-01

### Added
- First release
"""


def test_section_includes_header_and_stops_at_next_version() -> None:
    block = changelog_section.section_for(SAMPLE, "0.2.0")
    assert block is not None
    assert block.startswith("## [0.2.0]")
    assert "A bug" in block
    assert "First release" not in block


def test_normalize_strips_v_prefix() -> None:
    assert changelog_section.normalize_version("v1.2.3") == "1.2.3"


def test_missing_version_returns_none() -> None:
    assert changelog_section.section_for(SAMPLE, "9.9.9") is None


def test_cli_prints_section(tmp_path: Path) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "0.1.0", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "## [0.1.0]" in result.stdout
    assert "First release" in result.stdout
