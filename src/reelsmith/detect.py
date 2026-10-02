"""Scene change detection and contact sheets for Narrate mode."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import probe, require_ffmpeg, run_ffmpeg
from reelsmith.models import ClipModel, load_model

ChangeKind = Literal["change", "periodic"]

_FRAME_LINE = re.compile(r"pts_time:([0-9.]+)")
_SCENE_SCORE = re.compile(r"lavfi\.scene_score=([0-9.]+)")
THUMB_WIDTH = 480
_THUMB_WIDTH = THUMB_WIDTH
_SHEET_COLS = 4
_SHEET_ROWS = 3
_FRAMES_PER_SHEET = _SHEET_COLS * _SHEET_ROWS
_LABEL_X = 8
_LABEL_Y = 8
_LABEL_FONT_SIZE = 22
_LABEL_BOX_PAD = 4


@dataclass(frozen=True)
class DetectedChange:
    t: float
    score: float
    kind: ChangeKind


@dataclass(frozen=True)
class DetectSummary:
    clip_id: str
    threshold: float
    changes: list[DetectedChange]
    sheet_count: int


def format_timestamp(t: float) -> str:
    """Format seconds as m:ss.s for burned in labels."""
    if t < 0:
        t = 0.0
    minutes = int(t // 60)
    seconds = t - minutes * 60
    return f"{minutes}:{seconds:04.1f}"


def format_thumb_label(index: int, t: float) -> str:
    """Label for a contact sheet thumbnail, for example '#7 0:04.2'."""
    return f"#{index} {format_timestamp(t)}"


def merge_min_gap(points: list[tuple[float, float]], min_gap: float) -> list[tuple[float, float]]:
    """Keep the first scene change in each cluster closer than min_gap seconds."""
    if min_gap <= 0:
        return sorted(points, key=lambda item: item[0])
    ordered = sorted(points, key=lambda item: item[0])
    kept: list[tuple[float, float]] = []
    last_t = -min_gap
    for t, score in ordered:
        if t <= 0:
            continue
        if t - last_t >= min_gap:
            kept.append((t, score))
            last_t = t
    return kept


def build_timeline(
    scene_points: list[tuple[float, float]],
    duration: float,
    min_gap: float,
    every: float,
) -> list[DetectedChange]:
    """Merge scene hits, always start at t=0, and fill long static gaps."""
    merged = merge_min_gap(scene_points, min_gap)
    changes: list[DetectedChange] = [DetectedChange(t=0.0, score=0.0, kind="change")]
    last_t = 0.0

    def add_periodic_until(before: float) -> None:
        nonlocal last_t
        if every <= 0:
            return
        while last_t + every < before - 1e-6:
            candidate = last_t + every
            if candidate >= duration:
                break
            changes.append(DetectedChange(t=candidate, score=0.0, kind="periodic"))
            last_t = candidate

    for t, score in merged:
        add_periodic_until(t)
        if t - last_t >= min_gap or last_t == 0.0:
            changes.append(DetectedChange(t=t, score=score, kind="change"))
            last_t = t

    add_periodic_until(duration + 1e-6)
    changes.sort(key=lambda item: item.t)
    return changes


def _parse_metadata_print(text: str) -> list[tuple[float, float]]:
    found: list[tuple[float, float]] = []
    pending_time: float | None = None
    for line in text.splitlines():
        time_match = _FRAME_LINE.search(line)
        if time_match is not None:
            pending_time = float(time_match.group(1))
            continue
        score_match = _SCENE_SCORE.search(line)
        if score_match is not None and pending_time is not None:
            found.append((pending_time, float(score_match.group(1))))
            pending_time = None
    return found


def detect_scene_points(video: Path, threshold: float) -> list[tuple[float, float]]:
    """Run ffmpeg scene detection on a downscaled copy and return times and scores."""
    require_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        meta_path = Path(tmp) / "scene.txt"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-an",
            "-vf",
            (
                f"scale=480:-2,select='gt(scene,{threshold})',"
                f"metadata=print:file={meta_path.as_posix()}"
            ),
            "-f",
            "null",
            "-",
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            tail = " ".join(completed.stderr.split())[-400:]
            raise ReelsmithError(f"Scene detection failed: {tail}")
        if not meta_path.is_file():
            return []
        return _parse_metadata_print(meta_path.read_text(encoding="utf-8"))


def _label_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=_LABEL_FONT_SIZE)


def label_box_bounds(draw: ImageDraw.ImageDraw, label: str) -> tuple[int, int, int, int]:
    """Return the pixel bounds of the label background box."""
    font = _label_font()
    bbox = draw.textbbox((_LABEL_X, _LABEL_Y), label, font=font)
    return (
        int(bbox[0]) - _LABEL_BOX_PAD,
        int(bbox[1]) - _LABEL_BOX_PAD,
        int(bbox[2]) + _LABEL_BOX_PAD,
        int(bbox[3]) + _LABEL_BOX_PAD,
    )


def render_label_on_image(image: Image.Image, label: str) -> Image.Image:
    """Draw a boxed timestamp label on a thumbnail."""
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = _label_font()
    box = label_box_bounds(draw, label)
    draw.rectangle(box, fill=(0, 0, 0))
    draw.text((_LABEL_X, _LABEL_Y), label, fill=(255, 255, 255), font=font)
    return canvas


def _extract_raw_thumb(video: Path, t: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-ss",
            f"{t:.6f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={_THUMB_WIDTH}:-2",
            str(dest),
        ]
    )


def _blank_cell(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), (0, 0, 0))


def _pad_cell(thumb: Image.Image, cell_w: int, cell_h: int) -> Image.Image:
    canvas = _blank_cell(cell_w, cell_h)
    offset_x = max(0, (cell_w - thumb.width) // 2)
    offset_y = max(0, (cell_h - thumb.height) // 2)
    canvas.paste(thumb, (offset_x, offset_y))
    return canvas


def _tile_sheet(thumbs: list[Image.Image], dest: Path) -> None:
    if not thumbs:
        return
    cell_w = _THUMB_WIDTH
    cell_h = max(thumb.height for thumb in thumbs)
    cells = [_pad_cell(thumb, cell_w, cell_h) for thumb in thumbs]
    while len(cells) < _FRAMES_PER_SHEET:
        cells.append(_blank_cell(cell_w, cell_h))
    sheet = Image.new("RGB", (cell_w * _SHEET_COLS, cell_h * _SHEET_ROWS), (0, 0, 0))
    for index, cell in enumerate(cells[:_FRAMES_PER_SHEET]):
        row, col = divmod(index, _SHEET_COLS)
        sheet.paste(cell, (col * cell_w, row * cell_h))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, format="JPEG", quality=90)


def write_contact_sheets(video: Path, changes: list[DetectedChange], sheets_dir: Path) -> int:
    """Render sheet_NNN.jpg grids and return how many sheets were written."""
    if sheets_dir.exists():
        backup_existing(sheets_dir)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    if not changes:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sheet_index = 0
        batch: list[Image.Image] = []
        for frame_index, change in enumerate(changes, start=1):
            raw = tmp_path / f"raw_{frame_index:04d}.jpg"
            label = format_thumb_label(frame_index, change.t)
            _extract_raw_thumb(video, change.t, raw)
            with Image.open(raw) as frame:
                thumb = render_label_on_image(frame, label)
            batch.append(thumb)
            if len(batch) == _FRAMES_PER_SHEET:
                sheet_index += 1
                dest = sheets_dir / f"sheet_{sheet_index:03d}.jpg"
                _tile_sheet(batch, dest)
                batch = []
        if batch:
            sheet_index += 1
            dest = sheets_dir / f"sheet_{sheet_index:03d}.jpg"
            _tile_sheet(batch, dest)
    return sheet_index


def write_detected_json(
    path: Path,
    clip_id: str,
    threshold: float,
    changes: list[DetectedChange],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing(path)
    payload = {
        "clip": clip_id,
        "threshold": threshold,
        "changes": [
            {"t": change.t, "score": change.score, "kind": change.kind} for change in changes
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_detect(
    clips_root: Path,
    clip_id: str,
    threshold: float = 0.08,
    min_gap: float = 0.4,
    every: float = 3.0,
) -> DetectSummary:
    """Detect changes for one clip and write detected.json plus contact sheets."""
    clip_dir = clips_root / clip_id
    clip_path = clip_dir / "clip.json"
    if not clip_path.is_file():
        raise ReelsmithError(
            f"capture/clips/{clip_id}/clip.json not found",
            fix="reelsmith capture import",
        )
    clip = load_model(clip_path, ClipModel)
    video = clip_dir / clip.video
    if not video.is_file():
        raise ReelsmithError(
            f"capture/clips/{clip_id}/{clip.video} not found",
            fix="reelsmith capture import",
        )
    info = probe(video)
    scene_points = detect_scene_points(video, threshold)
    changes = build_timeline(scene_points, info.duration, min_gap, every)
    write_detected_json(clip_dir / "detected.json", clip_id, threshold, changes)
    sheet_count = write_contact_sheets(video, changes, clip_dir / "sheets")
    return DetectSummary(
        clip_id=clip_id,
        threshold=threshold,
        changes=changes,
        sheet_count=sheet_count,
    )
