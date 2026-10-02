"""`reelsmith export`: write the finished files to out/."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.export import demo_name, export_project
from reelsmith.media.ffmpeg import require_ffmpeg
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit


def run_export(root: Path, name: str | None) -> Result:
    require_ffmpeg()
    paths = DemoPaths.at(root)
    report = export_project(paths, name or demo_name(root))
    details = [str(path) for path in report.written]
    details += [f"Kept the old file as {path.name}" for path in report.backups]
    return Result(
        Status.OK,
        f"Exported {len(report.written)} files to {paths.out}",
        details,
        next_step=None,
    )


def register(app: typer.Typer) -> None:
    @app.command("export")
    def export(
        directory: Annotated[Path, typer.Argument(help="The demo folder.")] = Path("."),
        name: Annotated[
            str | None,
            typer.Option("--name", help="Base name for the files. Default: folder name."),
        ] = None,
    ) -> int:
        """Write voiced and silent videos, the narration and an .srt to out/."""
        return emit(run_export(directory, name))
