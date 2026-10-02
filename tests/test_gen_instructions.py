"""Tests for scripts/gen_instructions.py and the files it generates."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gen_instructions.py"
GUIDES = (
    "interview",
    "narrate",
    "capture-web",
    "capture-mobile",
    "script-writing",
    "voice",
    "qa",
    "troubleshooting",
)
GUIDE_SECTIONS = (
    "## Goal",
    "## Rules",
    "## What to ask or check",
    "## Commands",
    "## Reading the output",
    "## Common failures and fixes",
    "## Done when",
)
NON_CLAUDE_ENTRIES = (
    "src/reelsmith/agent_files/AGENTS.md",
    "src/reelsmith/agent_files/reelsmith.mdc",
    "src/reelsmith/agent_files/GEMINI.md",
    "src/reelsmith/agent_files/copilot-instructions.md",
    "prompts/HANDOVER_PROMPT.md",
)


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_instructions", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    """A copy of only the generator inputs, so tests never touch the repo."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(REPO_ROOT / "instructions", root / "instructions")
    shutil.copy2(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


def _frontmatter(text: str) -> dict[str, object]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "file must start with YAML frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_build_is_deterministic(source_root: Path) -> None:
    first = gen.build(source_root)
    second = gen.build(source_root)
    assert first == second
    assert list(first) == sorted(first)


def test_build_covers_every_target(source_root: Path) -> None:
    outputs = gen.build(source_root)
    expected = {
        "skills/reelsmith/SKILL.md",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "src/reelsmith/agent_files/skill/SKILL.md",
        *NON_CLAUDE_ENTRIES,
    }
    for name in GUIDES:
        expected.add(f"skills/reelsmith/references/{name}.md")
        expected.add(f"src/reelsmith/agent_files/skill/references/{name}.md")
        expected.add(f"src/reelsmith/agent_files/guides/{name}.md")
    assert set(outputs) == expected


def test_write_then_check_is_clean(source_root: Path) -> None:
    gen.write(source_root)
    assert gen.check(source_root) == []
    # A second write changes nothing.
    assert gen.write(source_root) == []


def test_check_reports_drift(source_root: Path) -> None:
    gen.write(source_root)
    target = source_root / "src/reelsmith/agent_files/AGENTS.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    assert gen.check(source_root) == ["src/reelsmith/agent_files/AGENTS.md"]


def test_check_reports_missing_and_stale_files(source_root: Path) -> None:
    gen.write(source_root)
    (source_root / ".claude-plugin/plugin.json").unlink()
    stale = source_root / "skills/reelsmith/references/old-guide.md"
    stale.write_text("old\n", encoding="utf-8")
    drift = gen.check(source_root)
    assert ".claude-plugin/plugin.json" in drift
    assert "skills/reelsmith/references/old-guide.md" in drift
    gen.write(source_root)
    assert not stale.exists()
    assert gen.check(source_root) == []


def test_cli_check_exit_codes(source_root: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(source_root), *args],
            capture_output=True,
            text=True,
        )

    assert run("--check").returncode == 1
    assert run().returncode == 0
    assert run("--check").returncode == 0
    skill = source_root / "skills/reelsmith/SKILL.md"
    skill.write_text("changed\n", encoding="utf-8")
    result = run("--check")
    assert result.returncode == 1
    assert "skills/reelsmith/SKILL.md" in result.stdout


def test_repo_files_match_generator() -> None:
    assert gen.check(REPO_ROOT) == []


def test_plugin_json_fields() -> None:
    data = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "reelsmith"
    assert data["version"] == _version()
    assert data["description"]
    assert data["author"]["name"] == "mz-real"
    assert data["license"] == "MIT"
    assert data["repository"] == "https://github.com/mz-real/reelsmith"


def test_marketplace_json_fields() -> None:
    path = REPO_ROOT / ".claude-plugin/marketplace.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "reelsmith"
    assert data["owner"]["name"] == "mz-real"
    plugins = data["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["name"] == "reelsmith"
    assert plugins[0]["source"] == "./"
    assert plugins[0]["version"] == _version()


@pytest.mark.parametrize(
    "path", ["skills/reelsmith/SKILL.md", "src/reelsmith/agent_files/skill/SKILL.md"]
)
def test_skill_frontmatter(path: str) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    data = _frontmatter(text)
    assert data["name"] == "reelsmith"
    description = data["description"]
    assert isinstance(description, str)
    assert "make a demo video of my app" in description
    assert "narrate this recording" in description


def test_skill_points_to_every_reference() -> None:
    text = (REPO_ROOT / "skills/reelsmith/SKILL.md").read_text(encoding="utf-8")
    for name in GUIDES:
        assert f"references/{name}.md" in text
        assert (REPO_ROOT / f"skills/reelsmith/references/{name}.md").is_file()
    assert "reelsmith-guides/" not in text


def test_cursor_rule_frontmatter() -> None:
    text = (REPO_ROOT / "src/reelsmith/agent_files/reelsmith.mdc").read_text(encoding="utf-8")
    data = _frontmatter(text)
    assert data["description"]
    assert data["globs"] in (None, "")
    assert data["alwaysApply"] is False


@pytest.mark.parametrize("path", NON_CLAUDE_ENTRIES)
def test_non_claude_files_embed_entry_and_index(path: str) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    assert "Approval point 1" in text
    for name in GUIDES:
        assert f"reelsmith-guides/{name}.md" in text
    assert "references/" not in text


def test_every_generated_file_says_it_is_generated() -> None:
    outputs = gen.build(REPO_ROOT)
    for path, text in outputs.items():
        if path.endswith(".json"):
            continue
        assert "Generated by scripts/gen_instructions.py from instructions/" in text, path
        if text.startswith("---\n"):
            body = text.split("\n---\n", 1)[1]
            assert body.startswith("<!-- Generated by"), path
        else:
            assert text.startswith("<!-- Generated by"), path


def test_entry_states_version_and_install_and_doctor() -> None:
    version = _version()
    for path in ("skills/reelsmith/SKILL.md", *NON_CLAUDE_ENTRIES):
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert f"reelsmith {version}" in text, path
        assert "reelsmith --version" in text
        assert "uv tool install reelsmith" in text
        assert f"REELSMITH_EXPECTED_VERSION={version}" in text
        assert "reelsmith doctor" in text
        assert "{{" not in text


@pytest.mark.parametrize("name", GUIDES)
def test_every_guide_has_the_sections_in_order(name: str) -> None:
    text = (REPO_ROOT / f"skills/reelsmith/references/{name}.md").read_text(encoding="utf-8")
    positions = [text.find(section + "\n") for section in GUIDE_SECTIONS]
    assert all(pos >= 0 for pos in positions), (name, positions)
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", GUIDES)
def test_every_guide_carries_the_rules(name: str) -> None:
    text = (REPO_ROOT / f"skills/reelsmith/references/{name}.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "truth rule" in lowered
    assert "reelsmith qa" in text
    assert "one question at a time" in lowered
    assert "never invent features" in lowered
    assert "business logic first" in lowered


def test_interview_starts_with_mode_and_has_consent_gate() -> None:
    text = (REPO_ROOT / "instructions/references/interview.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "narrate" in lowered and "produce" in lowered
    assert "consent" in lowered
    assert "no consent, no cloning" in lowered


def test_no_dashes_or_attribution_in_sources_and_outputs() -> None:
    bad_chars = (chr(0x2014), chr(0x2013))
    attribution = re.compile(r"co-authored-by|generated with|generated by (ai|claude)", re.I)
    sources = sorted((REPO_ROOT / "instructions").rglob("*.md"))
    texts = {str(p): p.read_text(encoding="utf-8") for p in sources}
    texts.update(gen.build(REPO_ROOT))
    for path, text in texts.items():
        assert not any(char in text for char in bad_chars), path
        assert not attribution.search(text), path
