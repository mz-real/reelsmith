"""A tolerant reader for voice's ``voice/timings.json``.

Voice (T3) is being built in parallel, so this reads the plain JSON
format from the design directly instead of importing the voice module.
A missing field is recorded as a warning rather than raised as an error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from reelsmith.errors import ReelsmithError


@dataclass(frozen=True)
class PhraseTiming:
    index: int
    start: float
    end: float


@dataclass(frozen=True)
class LineTiming:
    scene: str
    line: str
    file: str | None
    duration: float | None
    hash: str | None
    phrases: list[PhraseTiming]
    wpm: float | None
    transcript_ok: bool | None
    attempts: int | None


@dataclass(frozen=True)
class Timings:
    engine: str | None
    voice: str | None
    lines: list[LineTiming]
    warnings: list[str] = field(default_factory=list)

    def line(self, scene_id: str, line_id: str) -> LineTiming | None:
        for entry in self.lines:
            if entry.scene == scene_id and entry.line == line_id:
                return entry
        return None


def load_timings(path: Path) -> Timings:
    """Read voice/timings.json. Raises if the file itself is unreadable."""
    if not path.is_file():
        raise ReelsmithError(f"{path} not found", fix="reelsmith voice generate")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReelsmithError(f"{path.name} could not be read: {exc}") from None
    if not isinstance(data, dict):
        raise ReelsmithError(f"{path.name} must contain a JSON object")

    warnings: list[str] = []
    engine = _get_str(data, "engine", warnings)
    voice = _get_str(data, "voice", warnings)
    raw_lines = data.get("lines")
    if raw_lines is None:
        warnings.append("timings.json has no 'lines' field")
        raw_lines = []
    elif not isinstance(raw_lines, list):
        raw_lines = []
    lines = [_read_line(item, warnings) for item in raw_lines if isinstance(item, dict)]
    return Timings(engine, voice, lines, warnings)


def _read_line(data: dict[str, object], warnings: list[str]) -> LineTiming:
    scene = str(data.get("scene", "?"))
    line = str(data.get("line", "?"))
    where = f"line '{scene}/{line}'"
    raw_phrases = data.get("phrases")
    if raw_phrases is None:
        warnings.append(f"{where} has no 'phrases' field")
        raw_phrases = []
    if not isinstance(raw_phrases, list):
        raw_phrases = []
    phrases = [_read_phrase(item) for item in raw_phrases if isinstance(item, dict)]
    duration = data.get("duration")
    attempts = data.get("attempts")
    wpm = data.get("wpm")
    transcript_ok = data.get("transcript_ok")
    return LineTiming(
        scene=scene,
        line=line,
        file=_optional_str(data.get("file")),
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        hash=_optional_str(data.get("hash")),
        phrases=phrases,
        wpm=float(wpm) if isinstance(wpm, (int, float)) else None,
        transcript_ok=bool(transcript_ok) if isinstance(transcript_ok, bool) else None,
        attempts=int(attempts) if isinstance(attempts, (int, float)) else None,
    )


def _read_phrase(data: dict[str, object]) -> PhraseTiming:
    index = data.get("index")
    start = data.get("start")
    end = data.get("end")
    return PhraseTiming(
        index=int(index) if isinstance(index, (int, float)) else 0,
        start=float(start) if isinstance(start, (int, float)) else 0.0,
        end=float(end) if isinstance(end, (int, float)) else 0.0,
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _get_str(data: dict[str, object], key: str, warnings: list[str]) -> str | None:
    value = data.get(key)
    if value is None:
        warnings.append(f"timings.json has no '{key}' field")
        return None
    return str(value)
