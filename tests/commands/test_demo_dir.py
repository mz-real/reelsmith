"""Tests for shared demo folder CLI helpers."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import click
import pytest
from typer.core import TyperArgument
from typer.main import get_command

from reelsmith.cli import app, run
from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.errors import ReelsmithError


def test_demo_dir_defaults_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert demo_dir(None, None) == Path(".").resolve()


def test_demo_dir_prefers_positional(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    assert demo_dir(demo, None) == demo.resolve()


def test_demo_dir_accepts_hidden_option(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    assert demo_dir(None, demo) == demo.resolve()


def test_demo_dir_rejects_conflicting_paths(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    with pytest.raises(ReelsmithError, match="Give the demo folder once"):
        demo_dir(first, second)


def _ffmpeg_source(tmp_path: Path) -> Path:
    out = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=0.2:size=320x240:rate=30",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


def test_capture_import_uses_positional_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    source = _ffmpeg_source(tmp_path)

    code = run(app, ["capture", "import", str(source), str(demo), "--id", "take1"])

    out = capsys.readouterr().out
    assert code == 0
    assert "[OK]" in out
    assert (demo / "capture" / "clips" / "take1" / "video.mp4").is_file()


def test_capture_import_uses_hidden_demo_option(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    source = _ffmpeg_source(tmp_path)

    code = run(app, ["capture", "import", str(source), "--demo", str(demo), "--id", "take2"])

    out = capsys.readouterr().out
    assert code == 0
    assert "[OK]" in out
    assert (demo / "capture" / "clips" / "take2" / "video.mp4").is_file()


def test_capture_import_rejects_two_demo_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    source = _ffmpeg_source(tmp_path)

    code = run(
        app,
        [
            "capture",
            "import",
            str(source),
            str(first),
            "--demo",
            str(second),
            "--id",
            "x",
        ],
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "[ERROR] Give the demo folder once, either as DIR or --demo." in out


def _iter_click_commands(
    group: click.Command,
    prefix: str = "",
) -> Iterator[tuple[str, click.Command]]:
    subcommands = getattr(group, "commands", None)
    if isinstance(subcommands, dict) and subcommands:
        for name, cmd in subcommands.items():
            path = f"{prefix}{name}".strip()
            yield from _iter_click_commands(cmd, f"{path} ")
        return
    name = prefix.strip()
    if name:
        yield name, group


def test_demo_folder_params_are_positional_directory() -> None:
    click_app = get_command(app)

    seen: list[str] = []
    for cmd_path, cmd in _iter_click_commands(click_app):
        demo_args = [
            param
            for param in cmd.params
            if getattr(param, "help", None) == DEMO_DIR_HELP and isinstance(param, TyperArgument)
        ]
        if not demo_args:
            continue
        seen.append(cmd_path)
        assert len(demo_args) == 1, cmd_path
        assert demo_args[0].name == "directory", cmd_path

    assert "capture import" in seen
    assert "slides" in seen
    assert "script check" in seen
