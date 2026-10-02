"""Tests for reelsmith.media.ffmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import probe, require_ffmpeg, run_ffmpeg


def test_require_ffmpeg_passes_when_ffmpeg_is_on_path() -> None:
    require_ffmpeg()


def test_require_ffmpeg_raises_with_install_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ReelsmithError) as excinfo:
        require_ffmpeg()
    assert excinfo.value.fix is not None


def test_probe_handles_spaces_and_non_ascii_names(tiny_video: Path, tmp_path: Path) -> None:
    named = tmp_path / "my demo é.mp4"
    shutil.copyfile(tiny_video, named)

    info = probe(named)

    assert info.duration == pytest.approx(2.0, abs=0.1)
    assert info.width == 320
    assert info.height == 240
    assert info.has_audio is True


def test_probe_reports_rotation_default_zero(tiny_video: Path) -> None:
    info = probe(tiny_video)
    assert info.rotation == 0


def test_probe_reports_fps(tiny_video: Path) -> None:
    info = probe(tiny_video)
    assert info.fps == pytest.approx(30.0, abs=0.5)


def test_run_ffmpeg_failure_is_a_reelsmith_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    with pytest.raises(ReelsmithError) as info:
        run_ffmpeg(["-i", str(missing), str(tmp_path / "out.mp4")])
    assert "ffmpeg failed" in str(info.value)


def test_probe_unreadable_file_is_a_reelsmith_error(tmp_path: Path) -> None:
    bad = tmp_path / "not a video.mp4"
    bad.write_text("hello")
    with pytest.raises(ReelsmithError) as info:
        probe(bad)
    assert "not a video.mp4" in str(info.value)
