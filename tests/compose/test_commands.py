"""Tests for the compose and export commands."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from reelsmith.cli import run
from reelsmith.commands import compose, export
from reelsmith.commands.compose import compose_result
from reelsmith.compose.project import ComposeReport, FormatReport
from reelsmith.result import Status


def make_app() -> typer.Typer:
    """An app with only these commands, as auto discovery would register them."""
    app = typer.Typer()
    compose.register(app)
    export.register(app)
    return app


def report(warnings: list[str]) -> ComposeReport:
    fmt = FormatReport("16:9", Path("build/master_16x9.mp4"), 12.5, ["a"], ["b"])
    return ComposeReport([fmt], warnings)


def test_compose_result_ok_points_to_qa() -> None:
    result = compose_result(report([]), preview=False)
    assert result.status == Status.OK
    assert result.message == "Video composed: 2 scenes in 1 format"
    assert "1 scenes rendered, 1 reused" in result.details[0]
    assert result.next_step == "reelsmith qa"


def test_compose_result_preview_points_to_a_full_compose() -> None:
    result = compose_result(report([]), preview=True)
    assert result.message.startswith("Preview composed")
    assert result.next_step == "reelsmith compose"


def test_timing_conflicts_make_compose_warn() -> None:
    result = compose_result(report(["Scene 'a', line 'l1': \"Hi\" is 1.2 s over"]), preview=False)
    assert result.status == Status.WARN
    assert result.details[-1].startswith("Scene 'a'")


def test_compose_in_an_empty_folder_is_an_error_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(make_app(), ["compose", str(tmp_path), "--preview"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("[ERROR]")
    assert "Next: reelsmith init" in out


def test_export_before_compose_is_an_error_block(
    demo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(make_app(), ["export", str(demo)])
    out = capsys.readouterr().out
    assert code == 1
    assert "Next: reelsmith compose" in out
