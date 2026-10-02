"""Export the composed masters: voiced and silent videos, narration, captions.

Every output that already exists is backed up first, never overwritten.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from reelsmith.compose.captions import wrap_text
from reelsmith.compose.inputs import ProjectInputs, load_project
from reelsmith.compose.layouts import format_slug
from reelsmith.compose.project import master_path
from reelsmith.compose.transitions import scene_starts
from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import run_ffmpeg
from reelsmith.paths import DemoPaths

SRT_LINE = 42
SRT_LINES = 2

Runner = Callable[[list[str]], None]


@dataclass(frozen=True)
class SrtCue:
    start: float
    end: float
    text: str


@dataclass
class ExportReport:
    written: list[Path] = field(default_factory=list)
    backups: list[Path] = field(default_factory=list)


def srt_cues(project: ProjectInputs) -> list[SrtCue]:
    """One cue per phrase, at its placement plus its scene's start."""
    starts = scene_starts([scene.timeline.duration for scene in project.scenes])
    cues: list[SrtCue] = []
    for scene, start in zip(project.scenes, starts, strict=True):
        for phrase, placement in zip(scene.phrases, scene.timeline.placements, strict=True):
            cues.append(SrtCue(start + placement.out_start, start + placement.out_end, phrase.text))
    return cues


def srt_time(seconds: float) -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _srt_lines(text: str) -> list[str]:
    lines = wrap_text(text, SRT_LINE, len)
    if len(lines) <= SRT_LINES:
        return lines
    # Too long for two lines of the usual width: balance it over two lines.
    width = max(SRT_LINE, -(-len(text) // SRT_LINES))
    return wrap_text(text, width, len)


def format_srt(cues: Sequence[SrtCue]) -> str:
    blocks = []
    for number, cue in enumerate(cues, start=1):
        body = "\n".join(_srt_lines(cue.text))
        blocks.append(f"{number}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{body}")
    return "\n\n".join(blocks) + "\n"


def demo_name(root: Path) -> str:
    """A file safe name from the demo folder name."""
    slug = re.sub(r"[^\w]+", "-", root.resolve().name.lower()).strip("-_")
    return slug or "demo"


def voiced_args(master: Path, out: Path) -> list[str]:
    return ["-i", str(master), "-map", "0", "-c", "copy", "-movflags", "+faststart", str(out)]


def silent_args(master: Path, out: Path) -> list[str]:
    return [
        "-i",
        str(master),
        "-map",
        "0:v",
        "-c:v",
        "copy",
        "-an",
        "-movflags",
        "+faststart",
        str(out),
    ]


def narration_args(master: Path, out: Path) -> list[str]:
    return ["-i", str(master), "-map", "0:a", "-vn", "-c:a", "pcm_s16le", "-ar", "48000", str(out)]


def export_project(paths: DemoPaths, name: str, run: Runner = run_ffmpeg) -> ExportReport:
    """Write the voiced and silent video per format, the narration and the srt."""
    project = load_project(paths)
    masters = [(fmt, master_path(paths, fmt)) for fmt in project.spec.formats]
    missing = [str(path) for _, path in masters if not path.is_file()]
    if missing:
        raise ReelsmithError(
            f"No composed video yet: {', '.join(missing)}", fix="reelsmith compose"
        )
    paths.out.mkdir(parents=True, exist_ok=True)
    report = ExportReport()

    def write(out: Path, args_for: Callable[[Path], list[str]] | None = None) -> Path:
        backup = backup_existing(out)
        if backup is not None:
            report.backups.append(backup)
        if args_for is not None:
            run(args_for(out))
        report.written.append(out)
        return out

    for fmt, master in masters:
        slug = format_slug(fmt)
        write(paths.out / f"{name}_{slug}.mp4", partial(voiced_args, master))
        write(paths.out / f"{name}_{slug}_silent.mp4", partial(silent_args, master))
    write(paths.out / f"{name}_narration.wav", partial(narration_args, masters[0][1]))
    srt = write(paths.out / f"{name}.srt")
    srt.write_text(format_srt(srt_cues(project)), encoding="utf-8")
    return report
