"""Tests for scene detection and contact sheets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from reelsmith.detect import (
    THUMB_WIDTH,
    DetectedChange,
    build_timeline,
    detect_local_changes,
    format_thumb_label,
    format_timestamp,
    label_box_bounds,
    merge_local_changes,
    merge_min_gap,
    render_label_on_image,
    run_detect,
    run_detect_around,
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


def _local_box_change(tmp_path: Path) -> Path:
    """A static gray background where a small red box appears at t=2.0."""
    return _ffmpeg(
        tmp_path,
        "local_change.mp4",
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=320x240:d=4:r=25",
            "-vf",
            "drawbox=x=100:y=80:w=40:h=40:color=red@1.0:t=fill:enable='gte(t,2)'",
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


def test_local_change_found_with_box(tmp_path: Path) -> None:
    """A small rectangle changing colour at 2.0s is found within 0.1s, with its box."""
    video = _local_box_change(tmp_path)

    changes = detect_local_changes(video, duration=4.0)

    assert len(changes) == 1
    change = changes[0]
    assert change.kind == "local"
    assert abs(change.t - 2.0) <= 0.1
    assert change.box is not None
    x, y, w, h = change.box
    # The box is at (100, 80, 40, 40) in a 320x240 frame: (0.3125, 0.333, 0.125, 0.167).
    assert abs(x - 0.3125) < 0.05
    assert abs(y - 0.3333) < 0.05
    assert abs(w - 0.125) < 0.05
    assert abs(h - 0.1667) < 0.05


def test_full_frame_cut_is_not_reported_as_local(tmp_path: Path) -> None:
    """A full frame cut changes almost every pixel, so it is not a local change."""
    video = _three_color_cuts(tmp_path)

    changes = detect_local_changes(video, duration=6.0)

    assert changes == []


def test_merge_local_changes_keeps_the_strongest() -> None:
    changes = [
        DetectedChange(t=1.0, score=0.05, kind="local", box=(0.1, 0.1, 0.1, 0.1)),
        DetectedChange(t=1.2, score=0.2, kind="local", box=(0.1, 0.1, 0.1, 0.1)),
        DetectedChange(t=3.0, score=0.1, kind="local", box=(0.2, 0.2, 0.1, 0.1)),
    ]

    merged = merge_local_changes(changes, min_gap=0.4)

    assert len(merged) == 2
    assert merged[0].t == 1.2
    assert merged[0].score == 0.2
    assert merged[1].t == 3.0


def test_build_timeline_includes_local_changes() -> None:
    local = [DetectedChange(t=2.5, score=0.05, kind="local", box=(0.1, 0.1, 0.1, 0.1))]
    timeline = build_timeline([], duration=5.0, min_gap=0.4, every=99.0, local_changes=local)

    kinds = [item.kind for item in timeline]
    assert "local" in kinds
    local_entry = next(item for item in timeline if item.kind == "local")
    assert local_entry.t == 2.5
    assert local_entry.box == (0.1, 0.1, 0.1, 0.1)


def test_detected_json_includes_box_for_local_changes(tmp_path: Path) -> None:
    video = _local_box_change(tmp_path)
    clip_dir = tmp_path / "clips" / "demo"
    clip_dir.mkdir(parents=True)
    (clip_dir / "video.mp4").write_bytes(video.read_bytes())
    _write_clip(clip_dir, "demo", "video.mp4", 4.0)

    run_detect(tmp_path / "clips", "demo", every=99.0)
    data = json.loads((clip_dir / "detected.json").read_text(encoding="utf-8"))
    local_entries = [c for c in data["changes"] if c["kind"] == "local"]
    assert len(local_entries) == 1
    assert "box" in local_entries[0]
    assert len(local_entries[0]["box"]) == 4


def test_run_detect_around_writes_a_labelled_sheet(tmp_path: Path) -> None:
    video = _local_box_change(tmp_path)
    clip_dir = tmp_path / "clips" / "demo"
    clip_dir.mkdir(parents=True)
    (clip_dir / "video.mp4").write_bytes(video.read_bytes())
    _write_clip(clip_dir, "demo", "video.mp4", 4.0)

    summary = run_detect_around(tmp_path / "clips", "demo", around=2.0, span=0.3, step=0.1)

    assert summary.frame_count == 7
    assert summary.sheet_path.is_file()
    assert summary.sheet_path.name == "around_2.jpg"
