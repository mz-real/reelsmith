"""Tests for scene detection and contact sheets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from reelsmith.detect import (
    THUMB_WIDTH,
    build_timeline,
    format_thumb_label,
    format_timestamp,
    label_box_bounds,
    merge_min_gap,
    render_label_on_image,
    run_detect,
)
from reelsmith.media.ffmpeg import probe
from reelsmith.models import ClipModel, save_model


def _ffmpeg(tmp_path: Path, name: str, args: list[str]) -> Path:
    out = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, str(out)],
        check=True,
    )
    return out


def _three_color_cuts(tmp_path: Path) -> Path:
    return _ffmpeg(
        tmp_path,
        "cuts.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x240:d=2",
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-pix_fmt",
            "yuv420p",
        ],
    )


def _write_clip(clip_dir: Path, clip_id: str, video_name: str, duration: float) -> None:
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip = ClipModel(
        id=clip_id,
        video=video_name,
        width=320,
        height=240,
        fps=25.0,
        duration=duration,
        events=[],
    )
    save_model(clip_dir / "clip.json", clip)


def test_format_timestamp() -> None:
    assert format_timestamp(0.0) == "0:00.0"
    assert format_timestamp(4.2) == "0:04.2"
    assert format_timestamp(65.5) == "1:05.5"


def test_format_thumb_label() -> None:
    assert format_thumb_label(7, 4.2) == "#7 0:04.2"


def test_merge_min_gap_keeps_first_in_cluster() -> None:
    points = [(1.0, 0.5), (1.2, 0.4), (2.0, 0.3), (2.1, 0.2)]
    merged = merge_min_gap(points, min_gap=0.4)
    assert merged == [(1.0, 0.5), (2.0, 0.3)]


def test_periodic_frames_on_static_clip(tmp_path: Path) -> None:
    video = _ffmpeg(
        tmp_path,
        "static.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=320x240:d=10",
            "-pix_fmt",
            "yuv420p",
        ],
    )
    clip_dir = tmp_path / "clips" / "idle"
    video_dest = clip_dir / "video.mp4"
    clip_dir.mkdir(parents=True)
    video_dest.write_bytes(video.read_bytes())
    _write_clip(clip_dir, "idle", "video.mp4", 10.0)

    summary = run_detect(tmp_path / "clips", "idle", threshold=0.08, min_gap=0.4, every=3.0)
    times = [change.t for change in summary.changes]
    assert times[0] == 0.0
    assert 2.9 < times[1] < 3.1
    assert 5.9 < times[2] < 6.1
    assert 8.9 < times[3] < 9.1
    assert all(change.kind == "periodic" for change in summary.changes[1:])


def test_detects_color_cuts_near_two_and_four(tmp_path: Path) -> None:
    video = _three_color_cuts(tmp_path)
    clip_dir = tmp_path / "clips" / "demo"
    clip_dir.mkdir(parents=True)
    (clip_dir / "video.mp4").write_bytes(video.read_bytes())
    _write_clip(clip_dir, "demo", "video.mp4", 6.0)

    summary = run_detect(tmp_path / "clips", "demo", threshold=0.08, min_gap=0.4, every=99.0)
    change_times = [change.t for change in summary.changes if change.kind == "change"]
    assert change_times[0] == 0.0
    assert any(abs(t - 2.0) < 0.1 for t in change_times)
    assert any(abs(t - 4.0) < 0.1 for t in change_times)


def test_sheet_count_and_thumbnail_width(tmp_path: Path) -> None:
    video = _ffmpeg(
        tmp_path,
        "long.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=15:size=640x360:rate=30",
            "-pix_fmt",
            "yuv420p",
        ],
    )
    clip_dir = tmp_path / "clips" / "long"
    clip_dir.mkdir(parents=True)
    (clip_dir / "video.mp4").write_bytes(video.read_bytes())
    info = probe(video)
    _write_clip(clip_dir, "long", "video.mp4", info.duration)

    summary = run_detect(tmp_path / "clips", "long", every=3.0)
    assert summary.sheet_count >= 1
    first_sheet = clip_dir / "sheets" / "sheet_001.jpg"
    assert first_sheet.is_file()
    sheet_info = probe(first_sheet)
    assert sheet_info.width == THUMB_WIDTH * 4


def test_detected_json_written(tmp_path: Path) -> None:
    video = _three_color_cuts(tmp_path)
    clip_dir = tmp_path / "clips" / "demo"
    clip_dir.mkdir(parents=True)
    (clip_dir / "video.mp4").write_bytes(video.read_bytes())
    _write_clip(clip_dir, "demo", "video.mp4", 6.0)

    run_detect(tmp_path / "clips", "demo", every=99.0)
    data = json.loads((clip_dir / "detected.json").read_text(encoding="utf-8"))
    assert data["clip"] == "demo"
    assert data["threshold"] == 0.08
    assert data["changes"][0]["t"] == 0.0


def test_build_timeline_includes_zero() -> None:
    timeline = build_timeline([], duration=5.0, min_gap=0.4, every=3.0)
    assert timeline[0].t == 0.0
    assert timeline[0].kind == "change"


def test_labeled_thumbnail_differs_in_label_box() -> None:
    plain = Image.new("RGB", (THUMB_WIDTH, 270), (200, 50, 50))
    label = "#1 0:00.0"
    labeled = render_label_on_image(plain, label)
    draw = ImageDraw.Draw(plain)
    box = label_box_bounds(draw, label)
    sample_x = (box[0] + box[2]) // 2
    sample_y = (box[1] + box[3]) // 2
    assert plain.getpixel((sample_x, sample_y)) != labeled.getpixel((sample_x, sample_y))
