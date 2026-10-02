"""Tests for capture import normalisation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from reelsmith.capture.importer import import_recording
from reelsmith.media.ffmpeg import MediaInfo, probe
from reelsmith.models import ClipModel, load_model


def _ffmpeg(tmp_path: Path, name: str, args: list[str]) -> Path:
    out = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, str(out)],
        check=True,
    )
    return out


def test_import_odd_size_becomes_even(tmp_path: Path) -> None:
    source = _ffmpeg(
        tmp_path,
        "odd.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=1171x2532:rate=24",
            "-c:v",
            "mpeg4",
        ],
    )
    clips = tmp_path / "clips"
    clip = import_recording(source, "phone", clips)

    info = probe(clips / "phone" / "video.mp4")
    assert info.width % 2 == 0
    assert info.height % 2 == 0
    assert info.width == 1170
    assert info.height == 2532
    assert info.fps == pytest.approx(30.0, abs=0.5)
    assert clip.width == info.width
    assert clip.height == info.height
    assert clip.events == []


def test_import_applies_rotation_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _ffmpeg(
        tmp_path,
        "rotated.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=30",
            "-pix_fmt",
            "yuv420p",
        ],
    )
    real_probe = probe

    def fake_probe(path: Path) -> MediaInfo:
        info = real_probe(path)
        if path.resolve() == source.resolve():
            return MediaInfo(
                duration=info.duration,
                width=info.width,
                height=info.height,
                fps=info.fps,
                has_audio=info.has_audio,
                rotation=90,
            )
        return info

    monkeypatch.setattr("reelsmith.capture.importer.probe", fake_probe)

    clips = tmp_path / "clips"
    import_recording(source, "rot", clips)

    info = probe(clips / "rot" / "video.mp4")
    assert info.rotation == 0
    assert info.width == 240
    assert info.height == 320


def test_import_adds_audio_when_source_is_silent(tmp_path: Path) -> None:
    source = _ffmpeg(
        tmp_path,
        "silent.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=30",
            "-pix_fmt",
            "yuv420p",
            "-an",
        ],
    )
    assert probe(source).has_audio is False

    clips = tmp_path / "clips"
    import_recording(source, "silent", clips)

    info = probe(clips / "silent" / "video.mp4")
    assert info.has_audio is True


def test_import_variable_frame_rate_to_cfr(tmp_path: Path) -> None:
    source = _ffmpeg(
        tmp_path,
        "vfr.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=24",
            "-pix_fmt",
            "yuv420p",
        ],
    )
    before = probe(source)
    assert before.fps == pytest.approx(24.0, abs=0.5)

    clips = tmp_path / "clips"
    import_recording(source, "vfr", clips)

    after = probe(clips / "vfr" / "video.mp4")
    assert after.fps == pytest.approx(30.0, abs=0.5)

    saved = load_model(clips / "vfr" / "clip.json", ClipModel)
    assert saved.fps == pytest.approx(30.0, abs=0.01)
    assert saved.events == []
