"""`reelsmith qa`: run the nine quality checks over a composed master."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.qa.runner import run_qa
from reelsmith.result import emit


def register(app: typer.Typer) -> None:
    @app.command("qa")
    def qa_cmd(
        directory: Annotated[Path, typer.Argument(help="The demo folder.")] = Path("."),
        format: Annotated[
            str, typer.Option("--format", help="The build format, such as 16x9.")
        ] = "16x9",
    ) -> int:
        """Check a composed master against its script, timing and loudness."""
        return emit(run_qa(directory, format))
