"""build/timeline_<format>.json: where everything lands in the master.

QA reads this file. All times are master output times, after the fades.
Boxes are [x, y, w, h] in master pixels.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from reelsmith.compose.blur import blur_boxes
from reelsmith.compose.footage import footage_box, panel_pieces
from reelsmith.compose.inputs import ProjectInputs, SceneSource
from reelsmith.compose.layouts import Box, Layout, even, format_slug
from reelsmith.compose.ripples import out_time
from reelsmith.compose.scene import Look, caption_slots, scene_layout
from reelsmith.compose.transitions import scene_starts
from reelsmith.slides.markup import plain_text
from reelsmith.timing import Segment

EPS = 1e-6


def src_range_to_out(
    segments: Sequence[Segment], start: float, end: float
) -> tuple[float, float] | None:
    """The output time span that shows clip times start to end, holds included."""
    spans: list[float] = []
    for seg in segments:
        if seg.src_end < start - EPS or seg.src_start > end + EPS:
            continue
        if seg.kind == "hold":
            spans += [seg.out_start, seg.out_end]
            continue
        lo, hi = max(start, seg.src_start), min(end, seg.src_end)
        spans += [
            seg.out_start + (lo - seg.src_start) / seg.speed,
            seg.out_start + (hi - seg.src_start) / seg.speed,
        ]
    if not spans:
        return None
    return min(spans), max(spans)


def _box(box: Box) -> list[int]:
    return [box.x, box.y, box.w, box.h]


def _round(value: float) -> float:
    return round(value, 4)


def _segments(scene: SceneSource, start: float) -> list[dict[str, Any]]:
    return [
        {
            "kind": seg.kind,
            "src_start": _round(seg.src_start),
            "src_end": _round(seg.src_end),
            "speed": _round(seg.speed),
            "out_start": _round(start + seg.out_start),
            "out_end": _round(start + seg.out_end),
        }
        for seg in scene.timeline.segments
    ]


def _placements(scene: SceneSource, start: float) -> list[dict[str, Any]]:
    entries = []
    seen: dict[str, int] = {}
    for phrase, placement in zip(scene.phrases, scene.timeline.placements, strict=True):
        number = seen.get(phrase.line_id, 0)
        seen[phrase.line_id] = number + 1
        pin = None
        if phrase.pin_time is not None:
            event = out_time(scene.timeline.segments, phrase.pin_time)
            pin = None if event is None else _round(start + event)
        entries.append(
            {
                "line": phrase.line_id,
                "phrase": number,
                "out_start": _round(start + placement.out_start),
                "out_end": _round(start + placement.out_end),
                "pin_event_out": pin,
            }
        )
    return entries


def _captions(scene: SceneSource, layout: Layout, look: Look, start: float) -> list[dict[str, Any]]:
    duration = scene.timeline.duration
    entries = [
        {
            "text": slot.text,
            "out_start": _round(start + (slot.start if slot.start is not None else 0.0)),
            "out_end": _round(start + (slot.end if slot.end is not None else duration)),
            "box": _box(slot.box),
            "panel": _box(slot.panel),
        }
        for slot in caption_slots(scene, layout, look)
    ]
    panel = layout.panel
    for piece in panel_pieces(scene, layout, look):
        if piece.kind not in ("title", "point") or panel is None:
            continue
        entries.append(
            {
                "text": plain_text(piece.text),
                "out_start": _round(start + piece.start),
                "out_end": _round(start + duration),
                "box": _box(piece.box),
                "panel": _box(panel),
            }
        )
    return entries


def _blur(scene: SceneSource, layout: Layout, look: Look, start: float) -> list[dict[str, Any]]:
    clip = scene.clip
    if clip is None:
        return []
    content = footage_box(layout)
    src_w, src_h = even(clip.width), even(clip.height)
    entries = []
    for box in blur_boxes(look.blur, clip.id, src_w, src_h):
        span = src_range_to_out(scene.timeline.segments, box.start, box.end or clip.duration)
        if span is None:
            continue
        sx, sy = content.w / src_w, content.h / src_h
        canvas_box = Box(
            content.x + round(box.x * sx),
            content.y + round(box.y * sy),
            round(box.w * sx),
            round(box.h * sy),
        )
        entries.append(
            {
                "box": _box(canvas_box),
                "out_start": _round(start + span[0]),
                "out_end": _round(start + span[1]),
            }
        )
    return entries


def timeline_document(project: ProjectInputs, look: Look) -> dict[str, Any]:
    durations = [scene.timeline.duration for scene in project.scenes]
    starts = scene_starts(durations)
    scenes = []
    for scene, start in zip(project.scenes, starts, strict=True):
        layout = scene_layout(scene, look)
        scenes.append(
            {
                "id": scene.spec.id,
                "out_start": _round(start),
                "out_end": _round(start + scene.timeline.duration),
                "segments": _segments(scene, start),
                "placements": _placements(scene, start),
                "captions": _captions(scene, layout, look, start),
                "blur": _blur(scene, layout, look, start),
            }
        )
    return {
        "format": format_slug(look.fmt),
        "duration": _round(sum(durations)),
        "scenes": scenes,
        "transitions": [_round(t) for t in starts[1:]],
    }


def write_timeline(path: Path, document: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
