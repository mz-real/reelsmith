"""Tests for reelsmith.result."""

from __future__ import annotations

from pathlib import Path

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


def test_emit_json_prints_one_compact_object(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from reelsmith.result import set_json_mode

    set_json_mode(True)
    try:
        code = emit(
            Result(
                status=Status.WARN,
                message="Loudness is slightly off",
                details=["-18 LUFS"],
                next_step="reelsmith qa",
            )
        )
    finally:
        set_json_mode(False)
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    data = json.loads(out)
    assert data == {
        "status": "WARN",
        "message": "Loudness is slightly off",
        "details": ["-18 LUFS"],
        "next": "reelsmith qa",
    }
    assert code == 0


def test_emit_json_error_keeps_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from reelsmith.result import set_json_mode

    set_json_mode(True)
    try:
        code = emit(Result(status=Status.ERROR, message="ffmpeg not found"))
    finally:
        set_json_mode(False)
    data = json.loads(capsys.readouterr().out)
    assert data["next"] is None
    assert data["details"] == []
    assert code == 1


def test_global_json_flag_switches_any_command(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    import json

    from reelsmith.cli import app, run
    from reelsmith.result import json_mode

    code = run(app, ["--json", "init", str(tmp_path / "demo")])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "OK"
    assert data["message"].startswith("Demo folder ready")
    # The mode never leaks into the next run.
    assert json_mode() is False
    run(app, ["init", str(tmp_path / "other")])
    assert capsys.readouterr().out.startswith("[OK]")


def test_global_json_flag_covers_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    import json

    from reelsmith.cli import app, run

    root = tmp_path / "demo"
    root.mkdir()
    (root / "notes.txt").write_text("hi", encoding="utf-8")
    code = run(app, ["--json", "init", str(root)])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["status"] == "ERROR"
    assert "--force" in data["next"]
