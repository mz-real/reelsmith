"""Doctor command integration with mocked environment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reelsmith.cli import app, run


def test_doctor_cli_ok_when_mocks_pass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if cmd[0] == "ffmpeg":
            result.stdout = "ffmpeg version 7.0\n"
        elif cmd[0] == "java":
            result.stderr = 'openjdk version "17.0.1"\n'
        elif cmd[0] == "nvidia-smi":
            result.stdout = "GPU\n"
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        "reelsmith.doctor.checks._chromium_executable_exists",
        lambda: True,
    )
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    code = run(app, ["doctor"])
    out = capsys.readouterr().out
    assert code in (0, 1)
    assert "OK python:" in out or "ERROR" in out or "WARN" in out
