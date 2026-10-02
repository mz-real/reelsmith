"""Install reelsmith instructions for an AI coding tool into a project.

The files come from ``reelsmith/agent_files``, which
``scripts/gen_instructions.py`` writes from ``instructions/``. This module
also owns the layout of that folder, so the generator and the installer
agree on every path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing

TOOLS: tuple[str, ...] = ("claude", "codex", "cursor", "gemini", "copilot")

# Layout inside the package folder agent_files/.
GUIDES_DIR = "guides"
SKILL_DIR = "skill"

# Where the guides land in the user's project for every tool except claude.
PROJECT_GUIDES_DIR = "reelsmith-guides"
PROJECT_SKILL_DIR = ".claude/skills/reelsmith"

# tool: (file in agent_files, path in the user's project)
ENTRY_FILES: dict[str, tuple[str, str]] = {
    "codex": ("AGENTS.md", "AGENTS.md"),
    "cursor": ("reelsmith.mdc", ".cursor/rules/reelsmith.mdc"),
    "gemini": ("GEMINI.md", "GEMINI.md"),
    "copilot": ("copilot-instructions.md", ".github/copilot-instructions.md"),
}

PLUGIN_STEPS = (
    "/plugin marketplace add mz-real/reelsmith",
    "/plugin install reelsmith@reelsmith",
)


@dataclass
class InstallReport:
    written: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    backups: list[Path] = field(default_factory=list)


def agent_files_dir() -> Path:
    """The folder of generated instruction files shipped in the package."""
    return Path(__file__).resolve().parent / "agent_files"


def _check_tool(tool: str) -> None:
    if tool not in TOOLS:
        raise ReelsmithError(
            f"Unknown tool '{tool}'. Pick one of: {', '.join(TOOLS)}.",
            fix="reelsmith agent install codex",
        )


def _markdown_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.suffix == ".md")


def planned_files(tool: str) -> list[tuple[Path, str]]:
    """Each (source file, project relative target) pair for a tool."""
    _check_tool(tool)
    base = agent_files_dir()
    if tool == "claude":
        skill = base / SKILL_DIR
        pairs = [(skill / "SKILL.md", f"{PROJECT_SKILL_DIR}/SKILL.md")]
        for ref in _markdown_files(skill / "references"):
            pairs.append((ref, f"{PROJECT_SKILL_DIR}/references/{ref.name}"))
        return pairs
    source, target = ENTRY_FILES[tool]
    pairs = [(base / source, target)]
    for guide in _markdown_files(base / GUIDES_DIR):
        pairs.append((guide, f"{PROJECT_GUIDES_DIR}/{guide.name}"))
    return pairs


def _install_one(source: Path, dest: Path, report: InstallReport) -> None:
    if not source.is_file():
        raise ReelsmithError(
            f"{source.name} is missing from the reelsmith install.",
            fix="uv tool install --reinstall reelsmith",
        )
    data = source.read_bytes()
    if dest.is_file() and dest.read_bytes() == data:
        report.unchanged.append(dest)
        return
    backup = backup_existing(dest)
    if backup is not None:
        report.backups.append(backup)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    report.written.append(dest)


def install(tool: str, project: Path) -> InstallReport:
    """Copy the instruction files for a tool into a project folder.

    A file that already holds the same content is left alone. Any other
    existing file is backed up first, never overwritten.
    """
    _check_tool(tool)
    if not project.is_dir():
        raise ReelsmithError(
            f"Project folder {project} does not exist.",
            fix="reelsmith agent install <tool> --project PATH_TO_YOUR_PROJECT",
        )
    report = InstallReport()
    for source, target in planned_files(tool):
        _install_one(source, project / target, report)
    return report
