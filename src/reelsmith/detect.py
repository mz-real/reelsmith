"""Scene change detection and contact sheets for Narrate mode."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import probe, require_ffmpeg, run_ffmpeg
from reelsmith.models import ClipModel, load_model

ChangeKind = Literal["change", "periodic", "local"]
Box = tuple[float, float, float, float]

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
_BOX_OUTLINE = (255, 32, 32)
_BOX_OUTLINE_WIDTH = 3

# Local change detection: consecutive grayscale frames, decoded small and at
# a fixed rate, so a click that the whole frame scene score misses (because
# most of the picture stays the same) still shows up as one region that
# changed a lot while the rest held still.
LOCAL_FPS = 10.0
LOCAL_SCALE_WIDTH = 320
LOCAL_PIXEL_THRESHOLD = 24
LOCAL_FRACTION_MIN = 0.001
LOCAL_FRACTION_MAX = 0.25
LOCAL_DILATE_ITERATIONS = 1
_AROUND_COLUMNS = 6


@dataclass(frozen=True)
class DetectedChange:
    t: float
    score: float
    kind: ChangeKind
    box: Box | None = None


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


def merge_local_changes(changes: list[DetectedChange], min_gap: float) -> list[DetectedChange]:
    """Merge local changes closer than min_gap seconds, keeping the strongest."""
    if not changes:
        return []
    ordered = sorted(changes, key=lambda change: change.t)
    if min_gap <= 0:
        return ordered
    clusters: list[list[DetectedChange]] = [[ordered[0]]]
    for change in ordered[1:]:
        if change.t - clusters[-1][-1].t < min_gap:
            clusters[-1].append(change)
        else:
            clusters.append([change])
    return [max(cluster, key=lambda change: change.score) for cluster in clusters]


def build_timeline(
    scene_points: list[tuple[float, float]],
    duration: float,
    min_gap: float,
    every: float,
    local_changes: list[DetectedChange] | None = None,
) -> list[DetectedChange]:
    """Merge scene hits and local changes, always start at t=0, and fill long static gaps."""
    merged = merge_min_gap(scene_points, min_gap)
    scene_entries = [DetectedChange(t=t, score=score, kind="change") for t, score in merged]
    real_entries = sorted(scene_entries + list(local_changes or []), key=lambda item: item.t)

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

    for entry in real_entries:
        add_periodic_until(entry.t)
        if entry.kind == "change":
            if entry.t - last_t >= min_gap or last_t == 0.0:
                changes.append(entry)
                last_t = entry.t
        else:
            changes.append(entry)
            last_t = max(last_t, entry.t)

    add_periodic_until(duration + 1e-6)
    changes.sort(key=lambda item: item.t)
    return changes


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Grow a boolean mask outward by one pixel, iterations times."""
    grown = mask
    for _ in range(max(0, iterations)):
        padded = np.pad(grown, 1, mode="constant", constant_values=False)
        grown = (
            padded[:-2, 1:-1]
            | padded[2:, 1:-1]
            | padded[1:-1, :-2]
            | padded[1:-1, 2:]
            | padded[1:-1, 1:-1]
        )
    return grown


def _largest_blob_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Pixel bounding box (x, y, w, h) of the largest connected blob of True values."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    best_box: tuple[int, int, int, int] | None = None
    best_size = 0

    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or visited[start_y, start_x]:
                continue
            visited[start_y, start_x] = True
            stack = [(start_y, start_x)]
            min_x = max_x = start_x
            min_y = max_y = start_y
            size = 0
            while stack:
                y, x = stack.pop()
                size += 1
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and mask[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if size > best_size:
                best_size = size
                best_box = (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    return best_box


def _grayscale_frames(video: Path, fps: float, width: int) -> tuple[np.ndarray, int, int]:
    """Decode a video as small grayscale frames, sampled at a fixed rate."""
    require_ffmpeg()
    info = probe(video)
    if info.width <= 0 or info.height <= 0:
        raise ReelsmithError(f"Could not read video size from {video}")
    height = max(2, int(round(info.height * width / info.width / 2)) * 2)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video.resolve()),
        "-an",
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=area,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode != 0:
        tail = " ".join(completed.stderr.decode("utf-8", "replace").split())[-400:]
        raise ReelsmithError(f"Frame extraction failed: {tail}")
    frame_size = width * height
    frame_count = len(completed.stdout) // frame_size
    usable = completed.stdout[: frame_count * frame_size]
    frames = np.frombuffer(usable, dtype=np.uint8).reshape(frame_count, height, width)
    return frames, width, height


def detect_local_changes(
    video: Path,
    duration: float,
    fps: float = LOCAL_FPS,
    width: int = LOCAL_SCALE_WIDTH,
) -> list[DetectedChange]:
    """Find frames where a compact region changes a lot while the rest holds still.

    Consecutive frames of a small grayscale copy are diffed pixel by pixel.
    A candidate is a frame where the changed pixel fraction is small enough
    to be a local event (a click, a label flip) rather than a scene cut, but
    not so tiny it is just noise. Its box is the bounding box of the largest
    connected blob of changed pixels, after a small dilation, given back as
    fractions of the frame.
    """
    frames, frame_width, frame_height = _grayscale_frames(video, fps, width)
    changes: list[DetectedChange] = []
    for index in range(1, len(frames)):
        previous = frames[index - 1].astype(np.int16)
        current = frames[index].astype(np.int16)
        diff = np.abs(current - previous)
        mask = diff > LOCAL_PIXEL_THRESHOLD
        fraction = float(mask.mean())
        if fraction < LOCAL_FRACTION_MIN or fraction > LOCAL_FRACTION_MAX:
            continue
        grown = _dilate(mask, LOCAL_DILATE_ITERATIONS)
        box_px = _largest_blob_box(grown)
        if box_px is None:
            continue
        t = index / fps
        if t >= duration:
            continue
        x, y, w, h = box_px
        box: Box = (x / frame_width, y / frame_height, w / frame_width, h / frame_height)
        changes.append(DetectedChange(t=t, score=fraction, kind="local", box=box))
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
            str(video.resolve()),
            "-an",
            "-vf",
            (
                f"scale=480:-2,select='gt(scene,{threshold})',"
                # A bare file name, run from the temp folder: a Windows drive
                # colon would break the filter syntax.
                f"metadata=print:file={meta_path.name}"
            ),
            "-f",
            "null",
            "-",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, cwd=tmp)
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


def render_change_box_on_image(image: Image.Image, box: Box) -> Image.Image:
    """Outline a local change box (fractions of the frame) on a thumbnail."""
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x, y, w, h = box
    left, top = x * canvas.width, y * canvas.height
    right, bottom = left + w * canvas.width, top + h * canvas.height
    draw.rectangle([left, top, right, bottom], outline=_BOX_OUTLINE, width=_BOX_OUTLINE_WIDTH)
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


def _tile_grid(thumbs: list[Image.Image], dest: Path, columns: int) -> None:
    """Tile an arbitrary number of already labelled thumbnails into one sheet."""
    if not thumbs:
        return
    columns = max(1, min(columns, len(thumbs)))
    rows = ceil(len(thumbs) / columns)
    cell_w = _THUMB_WIDTH
    cell_h = max(thumb.height for thumb in thumbs)
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), (0, 0, 0))
    for index, thumb in enumerate(thumbs):
        row, col = divmod(index, columns)
        sheet.paste(_pad_cell(thumb, cell_w, cell_h), (col * cell_w, row * cell_h))
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
                thumb: Image.Image = frame
                if change.box is not None:
                    thumb = render_change_box_on_image(thumb, change.box)
                thumb = render_label_on_image(thumb, label)
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


def _change_json(change: DetectedChange) -> dict[str, object]:
    entry: dict[str, object] = {"t": change.t, "score": change.score, "kind": change.kind}
    if change.box is not None:
        entry["box"] = list(change.box)
    return entry


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
        "changes": [_change_json(change) for change in changes],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_clip(clips_root: Path, clip_id: str) -> tuple[ClipModel, Path]:
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
    return clip, video


def run_detect(
    clips_root: Path,
    clip_id: str,
    threshold: float = 0.08,
    min_gap: float = 0.4,
    every: float = 3.0,
) -> DetectSummary:
    """Detect changes for one clip and write detected.json plus contact sheets."""
    _clip, video = _load_clip(clips_root, clip_id)
    info = probe(video)
    scene_points = detect_scene_points(video, threshold)
    local_changes = merge_local_changes(detect_local_changes(video, info.duration), min_gap)
    changes = build_timeline(scene_points, info.duration, min_gap, every, local_changes)
    clip_dir = clips_root / clip_id
    write_detected_json(clip_dir / "detected.json", clip_id, threshold, changes)
    sheet_count = write_contact_sheets(video, changes, clip_dir / "sheets")
    return DetectSummary(
        clip_id=clip_id,
        threshold=threshold,
        changes=changes,
        sheet_count=sheet_count,
    )


@dataclass(frozen=True)
class AroundSummary:
    clip_id: str
    around: float
    span: float
    step: float
    frame_count: int
    sheet_path: Path


def _around_times(around: float, span: float, step: float, duration: float) -> list[float]:
    start = max(0.0, around - span)
    end = min(duration, around + span)
    if step <= 0 or end < start:
        return [start]
    count = int(round((end - start) / step))
    times = []
    for i in range(count + 1):
        candidate = round(start + i * step, 6)
        if candidate > end + 1e-9:
            break
        times.append(candidate)
    return times


def run_detect_around(
    clips_root: Path,
    clip_id: str,
    around: float,
    span: float = 1.5,
    step: float = 0.1,
) -> AroundSummary:
    """Write one sheet of frames across around +/- span, to pin a click precisely."""
    clip, video = _load_clip(clips_root, clip_id)
    times = _around_times(around, span, step, clip.duration)

    sheets_dir = clips_root / clip_id / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    dest = sheets_dir / f"around_{around:g}.jpg"
    backup_existing(dest)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        thumbs: list[Image.Image] = []
        for index, t in enumerate(times, start=1):
            raw = tmp_path / f"around_{index:04d}.jpg"
            _extract_raw_thumb(video, t, raw)
            with Image.open(raw) as frame:
                thumbs.append(render_label_on_image(frame, format_timestamp(t)))
        _tile_grid(thumbs, dest, _AROUND_COLUMNS)

    return AroundSummary(
        clip_id=clip_id,
        around=around,
        span=span,
        step=step,
        frame_count=len(times),
        sheet_path=dest,
    )
