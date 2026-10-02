"""Tests for reelsmith.progress."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from reelsmith import progress


@pytest.fixture(autouse=True)
def _reset() -> None:
    progress.reset()


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_progress_is_silent_when_stderr_is_not_a_tty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    progress.count("Voice line", 3, 34)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_forced_progress_writes_lines_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    progress.configure(force=True)
    progress.count("Voice line", 3, 34, "intro/l1")
    progress.count("Slide", 27, 27)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == ["Voice line 3/34: intro/l1", "Slide 27/27"]


def test_tty_progress_rewrites_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _Tty()
    monkeypatch.setattr(progress.sys, "stderr", stream)
    assert progress.enabled()
    progress.count("Scene", 1, 2)
    progress.count("Scene", 2, 2)
    text = stream.getvalue()
    assert text.startswith("\r")
    assert "Scene 1/2" in text
    assert text.endswith("Scene 2/2\n")


def test_bytes_progress_shows_megabytes(capsys: pytest.CaptureFixture[str]) -> None:
    progress.configure(force=True)
    total = 10 * 1024 * 1024
    for done in range(0, total + 1, 1024 * 1024):
        progress.transfer("Downloading model.onnx", done, total)
    lines = capsys.readouterr().err.splitlines()
    assert lines[-1] == "Downloading model.onnx 10.0/10.0 MB"
    # Without a TTY it prints at most one line per tenth, not per chunk.
    assert len(lines) <= 11


def test_reset_turns_force_off(capsys: pytest.CaptureFixture[str]) -> None:
    progress.configure(force=True)
    progress.reset()
    progress.count("Slide", 1, 2)
    assert capsys.readouterr().err == ""


def test_progress_flag_on_the_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import reelsmith.commands.init as init_module
    from reelsmith.cli import app, run

    seen: list[bool] = []

    def spy(*args: object, **kwargs: object) -> int:
        seen.append(progress.enabled())
        return 0

    monkeypatch.setattr(init_module, "init_demo", spy)
    assert run(app, ["init", str(tmp_path / "a")]) == 0
    assert run(app, ["--progress", "init", str(tmp_path / "b")]) == 0
    assert seen == [False, True]
    # The flag never leaks into the next run.
    assert progress.enabled() is False
