"""Shared helpers for command modules."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.errors import ReelsmithError

DEMO_DIR_HELP = "The demo folder (default: current folder)."

DemoDirArgument = Annotated[
    Path | None,
    typer.Argument(help=DEMO_DIR_HELP),
]

DemoDirOption = Annotated[
    Path | None,
    typer.Option("--demo", help=DEMO_DIR_HELP, hidden=True),
]


def demo_dir(positional: Path | None, option: Path | None) -> Path:
    """Pick the demo folder from an optional DIR argument and/or hidden --demo."""
    if positional is not None and option is not None:
        pos = positional.resolve()
        opt = option.resolve()
        if pos != opt:
            raise ReelsmithError("Give the demo folder once, either as DIR or --demo.")
        return pos
    if positional is not None:
        return positional.resolve()
    if option is not None:
        return option.resolve()
    return Path(".").resolve()
