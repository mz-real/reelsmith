"""Doctor --fix planning and prompts."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reelsmith.doctor.checks import Check
from reelsmith.doctor.fixes import apply_fixes
from reelsmith.result import Status


def test_apply_fixes_skips_when_user_declines(monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [
        Check(
            name="ffmpeg",
            status=Status.ERROR,
            found="missing",
            fix="brew install ffmpeg",
        )
    ]
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)

    def ask(_prompt: str) -> bool:
        return False

    result = apply_fixes(checks, spec_path=None, yes=False, ask_confirm=ask)
    run_mock.assert_not_called()
    assert result


def test_apply_fixes_runs_brew_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [
        Check(
            name="ffmpeg",
            status=Status.ERROR,
            found="missing",
            fix="brew install ffmpeg",
        )
    ]
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)
    monkeypatch.setattr(
        "reelsmith.doctor.checks.run_all_checks",
        lambda spec_path=None: checks,
    )

    apply_fixes(checks, spec_path=None, yes=True, ask_confirm=lambda _p: True)
    run_mock.assert_called_once()
    assert run_mock.call_args[0][0] == ["brew", "install", "ffmpeg"]


def test_apply_fixes_runs_openjdk_on_darwin_java(monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [
        Check(
            name="java",
            status=Status.WARN,
            found="missing",
            fix="brew install openjdk@17",
        )
    ]
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)
    monkeypatch.setattr(
        "reelsmith.doctor.checks.run_all_checks",
        lambda spec_path=None: checks,
    )

    apply_fixes(checks, spec_path=None, yes=True, ask_confirm=lambda _p: True)
    run_mock.assert_called_once()
    assert run_mock.call_args[0][0] == ["brew", "install", "openjdk@17"]


def test_apply_fixes_chromium_uses_playwright_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = [
        Check(
            name="chromium",
            status=Status.ERROR,
            found="missing",
            fix="reelsmith setup browser",
        )
    ]
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)
    monkeypatch.setattr(
        "reelsmith.doctor.checks.run_all_checks",
        lambda spec_path=None: [],
    )

    apply_fixes(checks, spec_path=None, yes=True, ask_confirm=lambda _p: True)
    cmd = run_mock.call_args[0][0]
    assert cmd[-2:] == ["install", "chromium"]
    assert "playwright" in cmd
