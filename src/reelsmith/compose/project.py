"""Compose a whole demo: every scene, then the master, for each format."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from reelsmith import __version__
from reelsmith.compose.cache import is_cached, scene_key, scene_path
from reelsmith.compose.captions import find_font
from reelsmith.compose.graph import Encode, scene_args
from reelsmith.compose.inputs import ProjectInputs, SceneSource, load_project, resolve_slide_images
from reelsmith.compose.layouts import canvas_size, format_slug, theme_colors
from reelsmith.compose.master import master_args
from reelsmith.compose.scene import Look, plan_for_scene
from reelsmith.compose.timeline import timeline_document, write_timeline
from reelsmith.compose.transitions import XFADE
from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import run_ffmpeg
from reelsmith.models import SpecModel
from reelsmith.paths import DemoPaths

COMPOSE_VERSION = 1  # bump when the look changes, so cached scenes rebuild

Runner = Callable[[list[str]], None]


@dataclass(frozen=True)
class RenderSettings:
    scale: float  # canvas size relative to 1080p
    encode: Encode
    use_cache: bool
    preview: bool


PREVIEW = RenderSettings(0.5, Encode("ultrafast", 28), use_cache=False, preview=True)


def final_settings(spec: SpecModel) -> RenderSettings:
    scale = 2.0 if spec.quality == "4k" else 1.0
    return RenderSettings(scale, Encode("medium", 18), use_cache=True, preview=False)


@dataclass
class FormatReport:
    fmt: str
    master: Path
    duration: float
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)


@dataclass
class ComposeReport:
    formats: list[FormatReport]
    warnings: list[str]


def master_path(paths: DemoPaths, fmt: str, preview: bool = False) -> Path:
    suffix = "_preview" if preview else ""
    return paths.build / f"master_{format_slug(fmt)}{suffix}.mp4"


def compose_project(
    paths: DemoPaths, settings: RenderSettings, run: Runner = run_ffmpeg
) -> ComposeReport:
    """Render every scene (reusing cached ones) and join them per format."""
    project = load_project(paths)
    if not project.scenes:
        raise ReelsmithError("spec.yaml has no scenes", fix=f"Add scenes to {paths.spec}")
    slide_warnings: list[str] = []
    reports: list[FormatReport] = []
    for fmt in project.spec.formats:
        slides = {}
        for scene in project.scenes:
            images, warnings = _scene_slide_images(paths, scene, fmt)
            slides[scene.spec.id] = images
            slide_warnings.extend(warnings)
        reports.append(_compose_format(project, fmt, settings, slides, run))
    return ComposeReport(reports, conflict_lines(project) + slide_warnings)


def conflict_lines(project: ProjectInputs) -> list[str]:
    """Timing conflicts, as warnings. QA turns them into failures."""
    lines = []
    for scene in project.scenes:
        for conflict in scene.timeline.conflicts:
            phrase = scene.phrases[conflict.phrase_index]
            lines.append(
                f"Scene '{scene.spec.id}', line '{phrase.line_id}': \"{phrase.text}\" is"
                f" {conflict.seconds_over:g} s over ({conflict.reason})"
            )
    return lines


def _scene_slide_images(
    paths: DemoPaths, scene: SceneSource, fmt: str
) -> tuple[list[Path], list[str]]:
    """Make sure every file the scene needs is there. Returns its slide images."""
    for phrase in scene.phrases:
        if phrase.wav is not None and not phrase.wav.is_file():
            raise ReelsmithError(f"{phrase.wav} is missing", fix="reelsmith voice generate")
    if scene.clip is not None and scene.clip_dir is not None:
        video = scene.clip_dir / scene.clip.video
        if not video.is_file():
            raise ReelsmithError(
                f"Scene '{scene.spec.id}' needs {video}, which is missing",
                fix=f"Record clip '{scene.clip.id}' again with reelsmith capture",
            )
        return [], []
    slide_id = scene.spec.slide or scene.spec.id
    images, warnings = resolve_slide_images(paths.slides, slide_id, fmt)
    if not images:
        raise ReelsmithError(
            f"Scene '{scene.spec.id}' needs slides/{slide_id}.png, which is missing",
            fix="reelsmith slides",
        )
    return images, warnings


def _look(project: ProjectInputs, fmt: str, settings: RenderSettings) -> Look:
    spec, brand = project.spec, project.brand
    fonts = [project.paths.root / name for name in brand.font.files]
    return Look(
        fmt=fmt,
        canvas=canvas_size(fmt, settings.scale),
        colors=theme_colors(spec.theme, brand),
        dark=spec.theme == "dark",
        font=find_font(fonts),
        captions=spec.options.captions in ("burned", "both"),
        highlight_clicks=spec.options.highlight_clicks,
        blur=list(spec.blur),
    )


def _compose_format(
    project: ProjectInputs,
    fmt: str,
    settings: RenderSettings,
    slides: dict[str, list[Path]],
    run: Runner,
) -> FormatReport:
    paths = project.paths
    look = _look(project, fmt, settings)
    base = paths.build / "preview" if settings.preview else paths.build
    scenes_dir = base / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    report = FormatReport(fmt, master_path(paths, fmt, settings.preview), 0.0)
    files: list[Path] = []
    last = len(project.scenes) - 1
    for number, scene in enumerate(project.scenes):
        tail = XFADE if number < last else 0.0
        images = slides[scene.spec.id]
        key = scene_key(
            _payload(project, scene, look, settings, tail), _inputs(scene, images, look)
        )
        out = scene_path(scenes_dir, scene.spec.id, key)
        files.append(out)
        if settings.use_cache and is_cached(out):
            report.reused.append(scene.spec.id)
            continue
        work = base / "work" / format_slug(fmt) / scene.spec.id
        plan = plan_for_scene(scene, look, images, work, tail)
        _render_to(out, run, partial(scene_args, plan, settings.encode))
        report.rendered.append(scene.spec.id)
    durations = [scene.timeline.duration for scene in project.scenes]
    _render_to(report.master, run, partial(master_args, files, durations, settings.encode))
    report.duration = sum(durations)
    _write_timelines(project, look, settings, first=fmt == project.spec.formats[0])
    return report


def timeline_path(paths: DemoPaths, fmt: str, preview: bool = False) -> Path:
    suffix = "_preview" if preview else ""
    return paths.build / f"timeline_{format_slug(fmt)}{suffix}.json"


def _write_timelines(
    project: ProjectInputs, look: Look, settings: RenderSettings, *, first: bool
) -> None:
    """Write the timeline QA reads; build/timeline.json is the first final format."""
    document = timeline_document(project, look)
    paths = project.paths
    write_timeline(timeline_path(paths, look.fmt, settings.preview), document)
    if first and not settings.preview:
        write_timeline(paths.build / "timeline.json", document)


def _render_to(out: Path, run: Runner, args_for: Callable[[Path], list[str]]) -> None:
    """Render to a temp name, then move it in place, so a crash never
    leaves a half written file that looks finished."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.partial{out.suffix}")
    run(args_for(tmp))
    tmp.replace(out)


def _payload(
    project: ProjectInputs,
    scene: SceneSource,
    look: Look,
    settings: RenderSettings,
    tail: float,
) -> dict[str, object]:
    clip = scene.clip
    return {
        "compose": COMPOSE_VERSION,
        "reelsmith": __version__,
        "look": dataclasses.asdict(look)
        | {"blur": [b.model_dump() for b in look.blur if clip and b.clip == clip.id]},
        "settings": dataclasses.asdict(settings),
        "tail": tail,
        "scene": scene.spec.model_dump(),
        "script": scene.script.model_dump() if scene.script else None,
        "clip": clip.model_dump() if clip else None,
        "phrases": [dataclasses.asdict(p) for p in scene.phrases],
        "timeline": dataclasses.asdict(scene.timeline),
    }


def _inputs(scene: SceneSource, slides: list[Path], look: Look) -> list[Path]:
    files: list[Path] = []
    if scene.clip is not None and scene.clip_dir is not None:
        files.append(scene.clip_dir / scene.clip.video)
    files += slides
    files += sorted({p.wav for p in scene.phrases if p.wav is not None})
    if look.font is not None:
        files.append(look.font)
    return files
