"""`reelsmith compose`: render every scene and join them into a master."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.compose.project import PREVIEW, ComposeReport, compose_project, final_settings
from reelsmith.media.ffmpeg import require_ffmpeg
from reelsmith.models import SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit

CONFLICT_FIX = "Shorten the lines named above in script.yaml, then run: reelsmith voice generate"


def run_compose(root: Path, *, preview: bool) -> Result:
    paths = DemoPaths.at(root)
    require_ffmpeg()
    if preview:
        settings = PREVIEW
    else:
        spec = load_model(paths.spec, SpecModel) if paths.spec.is_file() else SpecModel()
        settings = final_settings(spec)
    report = compose_project(paths, settings)
    return compose_result(report, preview=preview)


def compose_result(report: ComposeReport, *, preview: bool) -> Result:
    details = []
    for fmt in report.formats:
        details.append(
            f"{fmt.fmt}: {fmt.master} ({fmt.duration:.1f} s, {len(fmt.rendered)} scenes"
            f" rendered, {len(fmt.reused)} reused)"
        )
    details += report.warnings
    first = report.formats[0]
    scenes = len(first.rendered) + len(first.reused)
    kind = "Preview" if preview else "Video"
    count = len(report.formats)
    message = f"{kind} composed: {scenes} scenes in {count} format{'' if count == 1 else 's'}"
    if report.warnings:
        return Result(
            Status.WARN,
            message,
            details,
            next_step=CONFLICT_FIX,
        )
    next_step = "reelsmith compose" if preview else "reelsmith qa"
    return Result(Status.OK, message, details, next_step=next_step)


def register(app: typer.Typer) -> None:
    @app.command("compose")
    def compose(
        directory: Annotated[Path, typer.Argument(help="The demo folder.")] = Path("."),
        preview: Annotated[
            bool, typer.Option("--preview", help="Fast 540p draft. Ignores the scene cache.")
        ] = False,
    ) -> int:
        """Render each scene and join them into build/master_<format>.mp4."""
        return emit(run_compose(directory, preview=preview))
