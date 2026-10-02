"""A tolerant reader for compose's ``build/timeline.json``.

Compose (T6) is being built in parallel, so this reads the plain JSON
format from the design directly instead of importing a compose module.
A field that is missing from the file is recorded as a warning and left
as ``None`` on the result, instead of raising an error. A check that
needs a missing field reports a WARN for itself, never a crash.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from reelsmith.errors import ReelsmithError

T = TypeVar("T")

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class SegmentOut:
    kind: str
    src_start: float
    src_end: float
    speed: float
    out_start: float
    out_end: float


@dataclass(frozen=True)
class PlacementOut:
    line: str
    phrase: int
    out_start: float
    out_end: float
    pin_event_out: float | None


@dataclass(frozen=True)
class CaptionOut:
    text: str
    out_start: float
    out_end: float
    box: Box
    panel: Box


@dataclass(frozen=True)
class BlurOut:
    box: Box
    out_start: float
    out_end: float


@dataclass(frozen=True)
class SceneOut:
    id: str
    out_start: float
    out_end: float
    segments: list[SegmentOut] | None
    placements: list[PlacementOut] | None
    captions: list[CaptionOut] | None
    blur: list[BlurOut] | None


@dataclass(frozen=True)
class Timeline:
    format: str | None
    duration: float | None
    scenes: list[SceneOut]
    transitions: list[float] | None
    warnings: list[str] = field(default_factory=list)

    def scene(self, scene_id: str) -> SceneOut | None:
        return next((s for s in self.scenes if s.id == scene_id), None)


def load_timeline(path: Path) -> Timeline:
    """Read build/timeline.json. Raises if the file itself is unreadable."""
    if not path.is_file():
        raise ReelsmithError(f"{path} not found", fix="reelsmith compose")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReelsmithError(f"{path.name} could not be read: {exc}") from None
    if not isinstance(data, dict):
        raise ReelsmithError(f"{path.name} must contain a JSON object")

    warnings: list[str] = []
    fmt = _get_str(data, "format", warnings, "timeline.json")
    duration = _get_float(data, "duration", warnings, "timeline.json")
    raw_scenes = data.get("scenes")
    if raw_scenes is None:
        warnings.append("timeline.json has no 'scenes' field")
        raw_scenes = []
    elif not isinstance(raw_scenes, list):
        raw_scenes = []
    scenes = [_read_scene(item, warnings) for item in raw_scenes if isinstance(item, dict)]
    transitions = _read_floats(data, "transitions", warnings, "timeline.json")
    return Timeline(fmt, duration, scenes, transitions, warnings)


def _read_scene(data: dict[str, object], warnings: list[str]) -> SceneOut:
    scene_id = str(data.get("id", "?"))
    where = f"scene '{scene_id}'"
    out_start = _get_float(data, "out_start", warnings, where) or 0.0
    out_end = _get_float(data, "out_end", warnings, where) or 0.0
    segments = _read_list(data, "segments", warnings, where, _read_segment)
    placements = _read_list(data, "placements", warnings, where, _read_placement)
    captions = _read_list(data, "captions", warnings, where, _read_caption)
    blur = _read_list(data, "blur", warnings, where, _read_blur)
    return SceneOut(scene_id, out_start, out_end, segments, placements, captions, blur)


def _read_segment(data: dict[str, object]) -> SegmentOut:
    return SegmentOut(
        kind=str(data.get("kind", "play")),
        src_start=_as_float(data.get("src_start")),
        src_end=_as_float(data.get("src_end")),
        speed=_as_float(data.get("speed"), 1.0),
        out_start=_as_float(data.get("out_start")),
        out_end=_as_float(data.get("out_end")),
    )


def _read_placement(data: dict[str, object]) -> PlacementOut:
    pin = data.get("pin_event_out")
    phrase_raw = data.get("phrase")
    phrase = int(phrase_raw) if isinstance(phrase_raw, (int, float)) else 0
    return PlacementOut(
        line=str(data.get("line", "?")),
        phrase=phrase,
        out_start=_as_float(data.get("out_start")),
        out_end=_as_float(data.get("out_end")),
        pin_event_out=float(pin) if isinstance(pin, (int, float)) else None,
    )


def _read_caption(data: dict[str, object]) -> CaptionOut:
    return CaptionOut(
        text=str(data.get("text", "")),
        out_start=_as_float(data.get("out_start")),
        out_end=_as_float(data.get("out_end")),
        box=_as_box(data.get("box")),
        panel=_as_box(data.get("panel")),
    )


def _read_blur(data: dict[str, object]) -> BlurOut:
    return BlurOut(
        box=_as_box(data.get("box")),
        out_start=_as_float(data.get("out_start")),
        out_end=_as_float(data.get("out_end")),
    )


def _read_list(
    data: dict[str, object],
    key: str,
    warnings: list[str],
    where: str,
    reader: Callable[[dict[str, object]], T],
) -> list[T] | None:
    raw = data.get(key)
    if raw is None:
        warnings.append(f"{where} has no '{key}' field")
        return None
    if not isinstance(raw, list):
        warnings.append(f"{where} field '{key}' is not a list")
        return None
    return [reader(item) for item in raw if isinstance(item, dict)]


def _read_floats(
    data: dict[str, object], key: str, warnings: list[str], where: str
) -> list[float] | None:
    raw = data.get(key)
    if raw is None:
        warnings.append(f"{where} has no '{key}' field")
        return None
    if not isinstance(raw, list):
        return None
    return [float(v) for v in raw if isinstance(v, (int, float))]


def _as_box(raw: object) -> Box:
    if isinstance(raw, list) and len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw):
        x, y, w, h = (float(v) for v in raw)
        return (x, y, w, h)
    return (0.0, 0.0, 0.0, 0.0)


def _as_float(raw: object, default: float = 0.0) -> float:
    return float(raw) if isinstance(raw, (int, float)) else default


def _get_str(data: dict[str, object], key: str, warnings: list[str], where: str) -> str | None:
    value = data.get(key)
    if value is None:
        warnings.append(f"{where} has no '{key}' field")
        return None
    return str(value)


def _get_float(data: dict[str, object], key: str, warnings: list[str], where: str) -> float | None:
    value = data.get(key)
    if value is None:
        warnings.append(f"{where} has no '{key}' field")
        return None
    if not isinstance(value, (int, float)):
        warnings.append(f"{where} field '{key}' is not a number")
        return None
    return float(value)
