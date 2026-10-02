"""`reelsmith agent install`: add reelsmith instructions for an AI tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.agent_install import PLUGIN_STEPS, PROJECT_SKILL_DIR, TOOLS, install
from reelsmith.result import Result, Status, emit


def _relative(path: Path, project: Path) -> str:
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        return str(path)


def plugin_hint() -> Result:
    return Result(
        status=Status.OK,
        message="For Claude Code, install the reelsmith plugin instead",
        details=[f"run {step} inside Claude Code" for step in PLUGIN_STEPS],
        next_step=(
            "or copy the skill into this project with: reelsmith agent install claude --write-skill"
        ),
    )


def run_install(tool: str, project: Path, *, write_skill: bool) -> Result:
    if tool == "claude" and not write_skill:
        return plugin_hint()
    report = install(tool, project)
    details = [f"wrote {_relative(path, project)}" for path in report.written]
    details += [f"kept the old file as {_relative(path, project)}" for path in report.backups]
    if report.unchanged:
        count = len(report.unchanged)
        details.append(f"{count} file{'' if count == 1 else 's'} already up to date")
    where = f" in {PROJECT_SKILL_DIR}" if tool == "claude" else ""
    return Result(
        status=Status.OK,
        message=f"reelsmith instructions for {tool} installed{where} in {project}",
        details=details,
        next_step='ask your AI tool to "make a demo video of my app"',
    )


def register(app: typer.Typer) -> None:
    agent_app = typer.Typer(help="Set up reelsmith instructions for an AI coding tool.")

    @agent_app.command("install")
    def install_cmd(
        tool: Annotated[str, typer.Argument(help=f"One of: {', '.join(TOOLS)}.")],
        project: Annotated[
            Path, typer.Option("--project", help="The project folder to write into.")
        ] = Path("."),
        write_skill: Annotated[
            bool,
            typer.Option(
                "--write-skill",
                help="For claude: copy the skill into .claude/skills/reelsmith.",
            ),
        ] = False,
    ) -> int:
        """Write the instruction files for one AI tool into a project."""
        return emit(run_install(tool, project, write_skill=write_skill))

    app.add_typer(agent_app, name="agent")
