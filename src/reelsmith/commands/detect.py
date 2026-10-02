"""reelsmith detect: find screen changes and build contact sheets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import validate_id_option
from reelsmith.detect import run_detect, run_detect_around
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit


def register(app: typer.Typer) -> None:
    @app.command("detect")
    def detect_cmd(
        clip_id: Annotated[str, typer.Option("--clip", help="Clip id under capture/clips.")],
        directory: Annotated[
            Path,
            typer.Argument(help="The demo folder."),
        ] = Path("."),
        threshold: Annotated[
            float,
            typer.Option("--threshold", help="Scene change sensitivity (0 to 1)."),
        ] = 0.08,
        min_gap: Annotated[
            float,
            typer.Option("--min-gap", help="Minimum seconds between scene changes."),
        ] = 0.4,
        every: Annotated[
            float,
            typer.Option("--every", help="Add a frame every N seconds in static stretches."),
        ] = 3.0,
        around: Annotated[
            float | None,
            typer.Option("--around", help="Center time in seconds for a frame by frame sheet."),
        ] = None,
        span: Annotated[
            float,
            typer.Option("--span", help="Seconds before and after --around to cover."),
        ] = 1.5,
        step: Annotated[
            float,
            typer.Option("--step", help="Seconds between frames in the --around sheet."),
        ] = 0.1,
    ) -> int:
        """Find screen changes in a clip and write contact sheets."""
        clip_id = validate_id_option(clip_id)
        paths = DemoPaths.at(directory)
        if around is not None:
            around_summary = run_detect_around(paths.clips, clip_id, around, span=span, step=step)
            return emit(
                Result(
                    status=Status.OK,
                    message=f"Wrote frames around {around:g}s for clip '{clip_id}'",
                    details=[
                        f"{around_summary.frame_count} frame"
                        f"{'' if around_summary.frame_count == 1 else 's'} "
                        f"every {step:g}s",
                        f"sheet: {around_summary.sheet_path}",
                    ],
                    next_step=(
                        "find the frame where the result first appears, then put the event "
                        "0.1 to 0.2s before it"
                    ),
                )
            )
        summary = run_detect(
            paths.clips,
            clip_id,
            threshold=threshold,
            min_gap=min_gap,
            every=every,
        )
        change_count = sum(1 for item in summary.changes if item.kind == "change")
        periodic_count = sum(1 for item in summary.changes if item.kind == "periodic")
        local_count = sum(1 for item in summary.changes if item.kind == "local")
        details = [
            f"{change_count} scene change{'' if change_count == 1 else 's'}",
            f"{local_count} local change{'' if local_count == 1 else 's'}",
            f"{periodic_count} periodic frame{'' if periodic_count == 1 else 's'}",
            f"{summary.sheet_count} contact sheet{'' if summary.sheet_count == 1 else 's'}",
        ]
        return emit(
            Result(
                status=Status.OK,
                message=f"Detected timeline for clip '{clip_id}'",
                details=details,
                next_step=(
                    "read the sheets and add events to clip.json, then reelsmith script check"
                ),
            )
        )
