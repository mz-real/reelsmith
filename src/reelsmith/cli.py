"""The reelsmith command line interface."""

from __future__ import annotations

import importlib
import sys

import typer

from reelsmith import __version__
from reelsmith.errors import ReelsmithError
from reelsmith.result import Result, Status, emit

# Later tasks add commands by creating src/reelsmith/commands/<name>.py with
# a `def register(app: typer.Typer) -> None` function, then listing the
# module name here.
COMMANDS: list[str] = ["schema", "script_check"]

app = typer.Typer(
    name="reelsmith",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)


def _version_callback(show: bool) -> None:
    if show:
        typer.echo(f"reelsmith {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the reelsmith version and exit.",
    ),
) -> None:
    """reelsmith: turn an app into a narrated demo video, all local."""


def _register_commands() -> None:
    for name in COMMANDS:
        module = importlib.import_module(f"reelsmith.commands.{name}")
        module.register(app)


_register_commands()


def run(target: typer.Typer, args: list[str]) -> int:
    """Run a typer app with the given arguments.

    Turns a ReelsmithError raised anywhere in a command into an ERROR
    result block instead of a traceback, and returns the process exit code.
    """
    try:
        result = target(args=args, standalone_mode=False)
    except ReelsmithError as exc:
        return emit(Result(status=Status.ERROR, message=str(exc), next_step=exc.fix))
    except typer.TyperException as exc:
        show = getattr(exc, "show", None)
        if callable(show):
            show()
        else:
            typer.echo(str(exc), err=True)
        return exc.exit_code
    if isinstance(result, int):
        return result
    return 0


def main() -> int:
    return run(app, sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
