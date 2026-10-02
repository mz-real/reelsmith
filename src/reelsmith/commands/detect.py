"""reelsmith detect: find screen changes and build contact sheets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.detect import run_detect
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
    ) -> int:
        """Find screen changes in a clip and write contact sheets."""
        paths = DemoPaths.at(directory)
        summary = run_detect(
            paths.clips,
            clip_id,
            threshold=threshold,
            min_gap=min_gap,
            every=every,
        )
        change_count = sum(1 for item in summary.changes if item.kind == "change")
        periodic_count = sum(1 for item in summary.changes if item.kind == "periodic")
        details = [
            f"{change_count} scene change{'' if change_count == 1 else 's'}",
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
