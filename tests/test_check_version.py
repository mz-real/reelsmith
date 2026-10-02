"""Tests for scripts/check_version.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_version.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_version", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_version = _load()


def _canonical_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_repo_versions_match() -> None:
    errors = check_version.check(REPO_ROOT)
    assert errors == []


def test_detects_plugin_drift(tmp_path: Path) -> None:
    for rel in (
        "pyproject.toml",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "src/reelsmith/agent_files/AGENTS.md",
    ):
        src = REPO_ROOT / rel
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    data["version"] = "9.9.9"
    plugin_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = check_version.check(tmp_path)
    assert any("plugin.json" in line for line in errors)


def test_cli_exits_0_on_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert _canonical_version() in result.stdout
