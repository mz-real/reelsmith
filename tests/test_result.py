"""Tests for reelsmith.result."""

from __future__ import annotations

import pytest

from reelsmith.result import Result, Status, emit


def test_emit_ok_prints_message_only(capsys: pytest.CaptureFixture[str]) -> None:
    code = emit(Result(status=Status.OK, message="Voice generated for 12 lines"))
    out = capsys.readouterr().out
    assert out == "[OK] Voice generated for 12 lines\n"
    assert code == 0


def test_emit_prints_details_and_next_in_order(capsys: pytest.CaptureFixture[str]) -> None:
    result = Result(
        status=Status.OK,
        message="Voice generated for 12 lines",
        details=["2 lines regenerated for pace"],
        next_step="reelsmith compose --preview",
    )
    code = emit(result)
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines == [
        "[OK] Voice generated for 12 lines",
        "  - 2 lines regenerated for pace",
        "Next: reelsmith compose --preview",
    ]
    assert code == 0


def test_emit_warn_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = emit(Result(status=Status.WARN, message="Loudness is slightly off"))
    out = capsys.readouterr().out
    assert out.startswith("[WARN] Loudness is slightly off")
    assert code == 0


def test_emit_error_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    code = emit(Result(status=Status.ERROR, message="ffmpeg not found"))
    out = capsys.readouterr().out
    assert out.startswith("[ERROR] ffmpeg not found")
    assert code == 1


def test_emit_multiple_details_each_on_own_line(capsys: pytest.CaptureFixture[str]) -> None:
    result = Result(
        status=Status.OK,
        message="Export complete",
        details=["16:9 written", "9:16 written"],
    )
    emit(result)
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines == [
        "[OK] Export complete",
        "  - 16:9 written",
        "  - 9:16 written",
    ]
