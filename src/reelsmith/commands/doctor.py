"""reelsmith doctor: check your machine is ready."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import DemoDirArgument
from reelsmith.doctor import DoctorProfile, run_doctor
from reelsmith.errors import ReelsmithError


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor_cmd(
        directory: DemoDirArgument = None,
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
                help="spec.yaml path (used to pick checks when --profile is omitted).",
            ),
        ] = None,
        profile: Annotated[
            DoctorProfile | None,
            typer.Option(
                "--profile",
                help="Which tools to check: web, mobile, narrate, voice, clone, or all.",
            ),
        ] = None,
    ) -> None:
        """Check the tools your workflow needs."""
        if directory is not None:
            if not directory.is_dir():
                raise ReelsmithError(f"No demo folder at {directory}", fix="reelsmith init <dir>")
            if spec is None and (directory / "spec.yaml").is_file():
                spec = directory / "spec.yaml"

        def ask_confirm(prompt: str) -> bool:
            answer = typer.prompt(prompt, default="n")
            return answer.strip().lower() in ("y", "yes")

        raise typer.Exit(
            run_doctor(
                spec_path=spec,
                profile=profile,
                apply_fix=fix,
                yes=yes,
                ask_confirm=ask_confirm,
            )
        )
