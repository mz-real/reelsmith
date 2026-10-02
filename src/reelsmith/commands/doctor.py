"""reelsmith doctor: check your machine is ready."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.doctor import run_doctor


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor_cmd(
        fix: Annotated[
            bool,
            typer.Option("--fix", help="Offer to install missing tools."),
        ] = False,
        yes: Annotated[
            bool,
            typer.Option("--yes", help="Run all fixes without prompting."),
        ] = False,
        spec: Annotated[
            Path | None,
            typer.Option(
                "--spec",
                exists=True,
                dir_okay=False,
                readable=True,
                help="spec.yaml path (enables Chatterbox check when engine is chatterbox).",
            ),
        ] = None,
    ) -> None:
        """Check Python, ffmpeg, browser, mobile tools, models and GPU."""

        def ask_confirm(prompt: str) -> bool:
            answer = typer.prompt(prompt, default="n")
            return answer.strip().lower() in ("y", "yes")

        raise typer.Exit(
            run_doctor(
                spec_path=spec,
                apply_fix=fix,
                yes=yes,
                ask_confirm=ask_confirm,
            )
        )
