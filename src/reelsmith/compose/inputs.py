"""Read everything compose needs: the models, voice timings and timelines.

voice/timings.json is read here from its documented format, so compose
does not depend on the voice code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from reelsmith.compose.layouts import FORMAT_SIZES, format_slug
from reelsmith.errors import ReelsmithError
from reelsmith.models import (
    BrandModel,
    ClipModel,
    SceneSpec,
    ScriptModel,
    ScriptScene,
    SpecModel,
    load_model,
)
from reelsmith.paths import DemoPaths
from reelsmith.timing import (
    PhraseInput,
    SceneInput,
    SceneTimeline,
    TimingRules,
    caption_duration,
    plan_scene,
)

VOICE_FIX = "reelsmith voice generate"


@dataclass(frozen=True)
class PhraseTiming:
    index: int
    start: float
    end: float


@dataclass(frozen=True)
class LineTiming:
    scene: str
    line: str
    file: str
    duration: float
    hash: str
    phrases: list[PhraseTiming]


@dataclass(frozen=True)
class VoiceTimings:
    engine: str
    voice: str
    lines: list[LineTiming]

    def line(self, scene: str, line: str) -> LineTiming | None:
        return next((t for t in self.lines if t.scene == scene and t.line == line), None)


def read_timings(path: Path, script: ScriptModel | None = None) -> VoiceTimings:
    """Read voice/timings.json, turning any problem into a clear error."""
    if not path.is_file():
        raise ReelsmithError(f"{path} not found, so there is no narration yet", fix=VOICE_FIX)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = [_line_timing(item) for item in data["lines"]]
        timings = VoiceTimings(str(data.get("engine", "")), str(data.get("voice", "")), lines)
        if script is not None:
            timings = _timings_for_script(timings, script)
        return timings
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ReelsmithError(f"{path.name} could not be read: {exc!r}", fix=VOICE_FIX) from None


def _timings_for_script(timings: VoiceTimings, script: ScriptModel) -> VoiceTimings:
    valid = {(scene.id, line.id) for scene in script.scenes for line in scene.lines}
    lines = [line for line in timings.lines if (line.scene, line.line) in valid]
    return VoiceTimings(timings.engine, timings.voice, lines)


def _line_timing(item: dict[str, object]) -> LineTiming:
    phrases = item["phrases"]
    if not isinstance(phrases, list):
        raise TypeError("phrases must be a list")
    timings = [PhraseTiming(int(p["index"]), float(p["start"]), float(p["end"])) for p in phrases]
    return LineTiming(
        scene=str(item["scene"]),
        line=str(item["line"]),
        file=str(item["file"]),
        duration=float(str(item["duration"])),
        hash=str(item.get("hash", "")),
        phrases=sorted(timings, key=lambda p: p.index),
    )


@dataclass(frozen=True)
class PhraseRef:
    """One spoken phrase: its text, its slice of a line wav and its pin."""

    index: int  # position in the scene, matching the timeline placements
    line_id: str
    text: str
    duration: float
    pin_time: float | None
    wav: Path | None
    audio_start: float
    audio_end: float


@dataclass(frozen=True)
class SceneSource:
    spec: SceneSpec
    script: ScriptScene | None
    clip: ClipModel | None
    clip_dir: Path | None
    phrases: list[PhraseRef]
    timeline: SceneTimeline

    @property
    def caption(self) -> str | None:
        return self.script.caption if self.script else None


@dataclass(frozen=True)
class ProjectInputs:
    paths: DemoPaths
    spec: SpecModel
    script: ScriptModel
    brand: BrandModel
    scenes: list[SceneSource]


def timing_rules(spec: SpecModel) -> TimingRules:
    return TimingRules(
        allow_holds=spec.options.allow_holds, speed_up_waits=spec.options.speed_up_waits
    )


def load_project(paths: DemoPaths) -> ProjectInputs:
    for path, fix in ((paths.spec, "reelsmith init"), (paths.script, "reelsmith script check")):
        if not path.is_file():
            raise ReelsmithError(f"{path} not found", fix=fix)
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)
    brand = load_model(paths.brand, BrandModel) if paths.brand.is_file() else BrandModel()
    timings = (
        None if spec.voice.engine == "none" else read_timings(paths.voice / "timings.json", script)
    )
    rules = timing_rules(spec)
    scenes = [_scene_source(paths, spec, s, script, timings, rules) for s in spec.scenes]
    return ProjectInputs(paths, spec, script, brand, scenes)


def _scene_source(
    paths: DemoPaths,
    spec: SpecModel,
    scene: SceneSpec,
    script: ScriptModel,
    timings: VoiceTimings | None,
    rules: TimingRules,
) -> SceneSource:
    clip, clip_dir = _load_clip(paths, spec, scene)
    script_scene = script.scene(scene.id)
    phrases = scene_phrases(scene.id, script_scene, timings, paths.voice, clip)
    scene_input = SceneInput(
        scene_id=scene.id,
        clip_duration=clip.duration if clip else None,
        phrases=[PhraseInput(p.index, p.duration, p.pin_time) for p in phrases],
    )
    timeline = plan_scene(scene_input, rules)
    return SceneSource(scene, script_scene, clip, clip_dir, phrases, timeline)


def _load_clip(
    paths: DemoPaths, spec: SpecModel, scene: SceneSpec
) -> tuple[ClipModel | None, Path | None]:
    if scene.clip is None:
        return None, None
    clip_dir = paths.clips / scene.clip
    clip_json = clip_dir / "clip.json"
    if not clip_json.is_file():
        raise ReelsmithError(
            f"Scene '{scene.id}' needs {clip_json}, which is missing",
            fix=f"reelsmith capture {spec.footage}",
        )
    return load_model(clip_json, ClipModel), clip_dir


def scene_phrases(
    scene_id: str,
    script_scene: ScriptScene | None,
    timings: VoiceTimings | None,
    voice_dir: Path,
    clip: ClipModel | None,
) -> list[PhraseRef]:
    """Every phrase of a scene in order, with its audio slice and pin time."""
    if script_scene is None:
        return []
    refs: list[PhraseRef] = []
    for line in script_scene.lines:
        slices = _line_slices(scene_id, line.id, len(line.phrases), timings)
        for number, phrase in enumerate(line.phrases):
            pin = _pin_time(scene_id, line.id, phrase.pin, clip)
            if slices is None:
                duration = caption_duration(phrase.text)
                refs.append(
                    PhraseRef(len(refs), line.id, phrase.text, duration, pin, None, 0.0, duration)
                )
                continue
            wav, timing = slices[0], slices[1][number]
            refs.append(
                PhraseRef(
                    len(refs),
                    line.id,
                    phrase.text,
                    max(0.0, timing.end - timing.start),
                    pin,
                    voice_dir / wav,
                    timing.start,
                    timing.end,
                )
            )
    return refs


def _line_slices(
    scene_id: str, line_id: str, count: int, timings: VoiceTimings | None
) -> tuple[str, list[PhraseTiming]] | None:
    if timings is None:
        return None
    line = timings.line(scene_id, line_id)
    if line is None:
        raise ReelsmithError(
            f"Scene '{scene_id}', line '{line_id}' has no voice yet", fix=VOICE_FIX
        )
    if len(line.phrases) != count:
        raise ReelsmithError(
            f"Scene '{scene_id}', line '{line_id}' has {count} phrases in script.yaml"
            f" but {len(line.phrases)} in timings.json",
            fix=VOICE_FIX,
        )
    return line.file, line.phrases


def _pin_time(scene_id: str, line_id: str, pin: str | None, clip: ClipModel | None) -> float | None:
    if pin is None or clip is None:
        return None
    event = clip.event(pin)
    if event is None:
        raise ReelsmithError(
            f"Scene '{scene_id}', line '{line_id}' is pinned to '{pin}',"
            f" but clip '{clip.id}' has no such event",
            fix="reelsmith script check",
        )
    return event.t


_STEP = re.compile(r"_step(\d+)\.png$")


def _png_pixel_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def _aspect_matches(a: tuple[int, int], b: tuple[int, int]) -> bool:
    if a[0] <= 0 or a[1] <= 0 or b[0] <= 0 or b[1] <= 0:
        return True
    return abs((a[0] / a[1]) - (b[0] / b[1])) < 0.02


def _slide_images_in_dir(slides_dir: Path, slide_id: str) -> list[Path]:
    """The build step images of a slide in order, or the single slide image."""
    steps = []
    for path in slides_dir.glob(f"{slide_id}_step*.png"):
        match = _STEP.search(path.name)
        if match and path.name == f"{slide_id}_step{match.group(1)}.png":
            steps.append((int(match.group(1)), path))
    if steps:
        return [path for _, path in sorted(steps)]
    single = slides_dir / f"{slide_id}.png"
    return [single] if single.is_file() else []


def slide_images(slides_dir: Path, slide_id: str) -> list[Path]:
    """Slide PNGs under slides_dir (legacy flat layout)."""
    return _slide_images_in_dir(slides_dir, slide_id)


def resolve_slide_images(slides_dir: Path, slide_id: str, fmt: str) -> tuple[list[Path], list[str]]:
    """Prefer slides/<format_slug>/, then fall back to the flat slides/ folder."""
    warnings: list[str] = []
    slug = format_slug(fmt)
    per_format = _slide_images_in_dir(slides_dir / slug, slide_id)
    if per_format:
        return per_format, warnings
    flat = _slide_images_in_dir(slides_dir, slide_id)
    if not flat:
        return [], warnings
    expected = FORMAT_SIZES[fmt]
    width, height = _png_pixel_size(flat[0])
    if not _aspect_matches((width, height), expected):
        warnings.append(
            f"Slide '{slide_id}' for {fmt} uses slides/{slide_id}.png at {width}x{height}."
            f" Run reelsmith slides to render slides/{slug}/"
        )
    return flat, warnings
