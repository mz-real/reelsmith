"""`reelsmith status`: what is done in a demo folder and what to run next."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.result import Result, Status, emit, json_mode, print_json
from reelsmith.status import StatusReport, demo_status


def status_result(report: StatusReport) -> Result:
    total = len(report.steps)
    details = [f"{step.name}: {step.state}, {step.detail}" for step in report.steps]
    trouble = any(step.state in ("stale", "failed") for step in report.steps)
    return Result(
        status=Status.WARN if trouble else Status.OK,
        message=f"{report.done} of {total} steps done",
        details=details,
        next_step=report.next,
    )


def register(app: typer.Typer) -> None:
    @app.command("status")
    def status_cmd(
        directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
        as_json: Annotated[
            bool,
            typer.Option(
                "--json",
                help='Print one compact JSON object: {"steps": [...], "next": "..."}.',
            ),
        ] = False,
    ) -> int:
        """Show which steps are done and the exact command to run next."""
        report = demo_status(demo_dir(directory, None))
        if as_json or json_mode():
            print_json(report.to_json())
            return 0
        return emit(status_result(report))
