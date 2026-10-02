"""reelsmith setup: install external pieces reelsmith needs."""

from __future__ import annotations

import subprocess
import sys

import typer

from reelsmith.errors import ReelsmithError
from reelsmith.result import Result, Status, emit

setup_app = typer.Typer(help="Install browsers and other setup steps.")


def install_chromium() -> int:
    """Download the Playwright Chromium build."""
    completed = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if completed.returncode != 0:
        raise ReelsmithError(
            "Playwright could not install Chromium.",
            fix=f"{sys.executable} -m playwright install chromium",
        )
    return emit(
        Result(
            status=Status.OK,
            message="Playwright Chromium is installed.",
            next_step="reelsmith doctor",
        )
    )


@setup_app.command("browser")
def browser_cmd() -> None:
    """Install the Chromium build used for web capture and slides."""
    raise typer.Exit(install_chromium())


def register(app: typer.Typer) -> None:
    app.add_typer(setup_app, name="setup")
