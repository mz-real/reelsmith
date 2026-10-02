"""Doctor result detail formatting."""

from __future__ import annotations

import pytest

from reelsmith.doctor import format_check_details, run_doctor
from reelsmith.doctor.checks import Check
from reelsmith.result import Status


def test_format_check_details_prefixes_status_and_fix() -> None:
    checks = [
        Check(name="python", status=Status.OK, found="Python 3.13.12", fix=None),
        Check(
            name="maestro",
            status=Status.WARN,
            found="not on PATH (needed for mobile capture)",
            fix='curl -fsSL "https://get.maestro.mobile.dev" | bash',
        ),
        Check(
            name="ffmpeg",
            status=Status.ERROR,
            found="not on PATH",
            fix="brew install ffmpeg",
        ),
    ]
    lines = format_check_details(checks)
    assert lines[0] == "OK python: Python 3.13.12"
    assert lines[1] == "WARN maestro: not on PATH (needed for mobile capture)"
    assert lines[2] == '    fix: curl -fsSL "https://get.maestro.mobile.dev" | bash'
    assert lines[3] == "ERROR ffmpeg: not on PATH"
    assert lines[4] == "    fix: brew install ffmpeg"


def test_run_doctor_details_in_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = [
        Check(
            name="ffmpeg",
            status=Status.ERROR,
            found="not on PATH",
            fix="brew install ffmpeg",
        )
    ]
    monkeypatch.setattr("reelsmith.doctor.run_all_checks", lambda spec_path=None: checks)

    code = run_doctor(
        spec_path=None,
        apply_fix=False,
        yes=False,
        ask_confirm=lambda _p: False,
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "  - ERROR ffmpeg: not on PATH" in out
    assert "  -     fix: brew install ffmpeg" in out
    assert "Next: brew install ffmpeg" in out
