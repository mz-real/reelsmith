"""Tests for reelsmith setup browser."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reelsmith.cli import app, run
from reelsmith.commands.setup import install_chromium
from reelsmith.errors import ReelsmithError


def test_install_chromium_success(monkeypatch: pytest.MonkeyPatch) -> None:
    result = MagicMock()
    result.returncode = 0
    monkeypatch.setattr("subprocess.run", lambda *a, **k: result)
    assert install_chromium() == 0


def test_install_chromium_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    result = MagicMock()
    result.returncode = 1
    monkeypatch.setattr("subprocess.run", lambda *a, **k: result)
    with pytest.raises(ReelsmithError):
        install_chromium()


def test_setup_browser_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = MagicMock()
    result.returncode = 0
    monkeypatch.setattr("subprocess.run", lambda *a, **k: result)
    code = run(app, ["setup", "browser"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[OK]" in out
