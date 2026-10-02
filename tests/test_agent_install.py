"""Tests for reelsmith agent install."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from reelsmith.agent_install import TOOLS, install, planned_files
from reelsmith.cli import run
from reelsmith.commands import agent
from reelsmith.errors import ReelsmithError

GUIDES = (
    "capture-mobile",
    "capture-web",
    "interview",
    "narrate",
    "qa",
    "script-writing",
    "troubleshooting",
    "voice",
)
ENTRY_TARGETS = {
    "codex": "AGENTS.md",
    "cursor": ".cursor/rules/reelsmith.mdc",
    "gemini": "GEMINI.md",
    "copilot": ".github/copilot-instructions.md",
}


def _app() -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _root() -> None:
        """Test root."""

    agent.register(app)
    return app


def test_tools_list() -> None:
    assert TOOLS == ("claude", "codex", "cursor", "gemini", "copilot")


@pytest.mark.parametrize("tool", sorted(ENTRY_TARGETS))
def test_install_writes_entry_and_guides(tool: str, tmp_path: Path) -> None:
    report = install(tool, tmp_path)
    expected = {ENTRY_TARGETS[tool]} | {f"reelsmith-guides/{name}.md" for name in GUIDES}
    assert {p.relative_to(tmp_path).as_posix() for p in report.written} == expected
    for rel in expected:
        assert (tmp_path / rel).is_file()
    entry = (tmp_path / ENTRY_TARGETS[tool]).read_text(encoding="utf-8")
    assert "reelsmith-guides/interview.md" in entry
    assert report.backups == []


def test_install_claude_writes_skill(tmp_path: Path) -> None:
    report = install("claude", tmp_path)
    expected = {".claude/skills/reelsmith/SKILL.md"} | {
        f".claude/skills/reelsmith/references/{name}.md" for name in GUIDES
    }
    assert {p.relative_to(tmp_path).as_posix() for p in report.written} == expected


def test_install_matches_package_files(tmp_path: Path) -> None:
    for tool in TOOLS:
        for source, target in planned_files(tool):
            assert source.is_file(), source
            assert not Path(target).is_absolute()
            assert ".." not in Path(target).parts


def test_install_backs_up_existing_files(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("my own notes\n", encoding="utf-8")
    report = install("codex", tmp_path)
    assert len(report.backups) == 1
    backup = report.backups[0]
    assert backup.name.startswith("AGENTS.md.bak-")
    assert backup.read_text(encoding="utf-8") == "my own notes\n"
    assert "reelsmith" in agents.read_text(encoding="utf-8")


def test_install_twice_leaves_identical_files(tmp_path: Path) -> None:
    install("gemini", tmp_path)
    report = install("gemini", tmp_path)
    assert report.written == []
    assert report.backups == []
    assert len(report.unchanged) == 1 + len(GUIDES)


def test_install_unknown_tool(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError) as exc:
        install("notepad", tmp_path)
    assert "claude, codex, cursor, gemini, copilot" in str(exc.value)


def test_install_missing_project(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError):
        install("codex", tmp_path / "nope")


def test_cli_codex(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(_app(), ["agent", "install", "codex", "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[OK]" in out
    assert "Next:" in out
    assert (tmp_path / "AGENTS.md").is_file()


def test_cli_claude_points_to_plugin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(_app(), ["agent", "install", "claude", "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "/plugin marketplace add mz-real/reelsmith" in out
    assert "/plugin install reelsmith@reelsmith" in out
    assert not (tmp_path / ".claude").exists()


def test_cli_claude_write_skill(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(_app(), ["agent", "install", "claude", "--project", str(tmp_path), "--write-skill"])
    assert code == 0
    assert (tmp_path / ".claude/skills/reelsmith/SKILL.md").is_file()


def test_cli_unknown_tool(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run(_app(), ["agent", "install", "notepad", "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "[ERROR]" in out
