"""Tests for reelsmith.errors and the CLI error handling."""

from __future__ import annotations

import pytest
import typer

from reelsmith.cli import run
from reelsmith.errors import ReelsmithError


def test_reelsmith_error_holds_message_and_fix() -> None:
    error = ReelsmithError("ffmpeg not found", fix="brew install ffmpeg")
    assert str(error) == "ffmpeg not found"
    assert error.fix == "brew install ffmpeg"


def test_reelsmith_error_fix_is_optional() -> None:
    error = ReelsmithError("something broke")
    assert error.fix is None


def _build_boom_app() -> typer.Typer:
    # Two commands, so typer keeps "boom" as a named subcommand instead of
    # collapsing a lone command into the app itself.
    boom_app = typer.Typer()

    @boom_app.command()
    def boom() -> None:
        raise ReelsmithError("x", fix="brew install ffmpeg")

    @boom_app.command()
    def noop() -> None:
        pass

    return boom_app


def test_cli_turns_reelsmith_error_into_error_block(
    capsys: pytest.CaptureFixture[str],
) -> None:
    boom_app = _build_boom_app()

    code = run(boom_app, ["boom"])

    out = capsys.readouterr().out
    assert "Traceback" not in out
    lines = out.splitlines()
    assert lines[0] == "[ERROR] x"
    assert lines[-1] == "Next: brew install ffmpeg"
    assert code == 1


def test_cli_returns_zero_for_a_clean_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiet_app = typer.Typer()

    @quiet_app.command()
    def fine() -> None:
        typer.echo("all good")

    @quiet_app.command()
    def other() -> None:
        pass

    code = run(quiet_app, ["fine"])

    out = capsys.readouterr().out
    assert "all good" in out
    assert code == 0
