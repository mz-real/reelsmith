"""Work out which steps of a demo folder are done and what to run next.

Each step is done, stale (made from older inputs), missing or failed. The
first step that is not done gives the next command. Nothing here writes to
the demo folder, renders or loads a model, so it is cheap to run often.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reelsmith.commands.script_check import check_script
from reelsmith.compose.inputs import slide_images
from reelsmith.compose.layouts import format_slug
from reelsmith.compose.project import master_path
from reelsmith.errors import ReelsmithError
from reelsmith.export import demo_name, expected_outputs
from reelsmith.models import ClipModel, ScriptModel, SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.voice.pipeline import _line_hash

State = Literal["done", "stale", "missing", "failed"]

STARTER_TEXT = "Replace this"
_QA_ROW = re.compile(r"^## \d+\. (.+) - (PASS|WARN|FAIL)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Step:
    name: str
    state: State
    detail: str
    next: str | None = None  # what to run when this is the first step not done

    def to_json(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state, "detail": self.detail}


@dataclass(frozen=True)
class StatusReport:
    steps: list[Step]
    next: str

    def to_json(self) -> dict[str, object]:
        return {"steps": [step.to_json() for step in self.steps], "next": self.next}

    @property
    def done(self) -> int:
        return sum(1 for step in self.steps if step.state == "done")


@dataclass
class _Demo:
    paths: DemoPaths
    arg: str  # " DIR" to add to commands, or "" for the current folder
    spec: SpecModel | None = None
    script: ScriptModel | None = None

    def cmd(self, base: str) -> str:
        return base + self.arg

    def clip(self, clip_id: str) -> ClipModel | None:
        path = self.paths.clips / clip_id / "clip.json"
        if not path.is_file():
            return None
        try:
            return load_model(path, ClipModel)
        except ReelsmithError:
            return None


def _newest(paths: Iterable[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime, default=None)


def _mtime(path: Path) -> float:
    return path.stat().st_mtime


def _rel(demo: _Demo, path: Path) -> str:
    try:
        return path.relative_to(demo.paths.root).as_posix()
    except ValueError:
        return str(path)


def _short_list(items: list[str], limit: int = 3) -> str:
    shown = ", ".join(items[:limit])
    extra = len(items) - limit
    return f"{shown} and {extra} more" if extra > 0 else shown


def _needs(name: str, what: str) -> Step:
    return Step(name, "missing", f"needs {what}")


# spec


def _spec_step(demo: _Demo) -> Step:
    path = demo.paths.spec
    if not path.is_file():
        return Step(
            "spec",
            "missing",
            "no spec.yaml",
            f"reelsmith init {demo.arg.strip() or '.'} --preset quick",
        )
    again = demo.cmd("reelsmith status")
    try:
        demo.spec = load_model(path, SpecModel)
    except ReelsmithError as exc:
        return Step("spec", "failed", str(exc), f"Fix spec.yaml, then run: {again}")
    spec = demo.spec
    if not spec.scenes:
        return Step("spec", "failed", "no scenes", f"Add scenes to spec.yaml, then run: {again}")
    formats = ", ".join(spec.formats)
    return Step("spec", "done", f"{spec.mode} mode, {_count(len(spec.scenes), 'scene')}, {formats}")


# clips


def _capture_command(demo: _Demo, spec: SpecModel, clip_id: str) -> str:
    if spec.footage == "web":
        return demo.cmd(f"reelsmith capture web capture/flows/{clip_id}.py --id {clip_id}")
    if spec.footage == "mobile":
        return demo.cmd(
            f"reelsmith capture mobile capture/flows/{clip_id}.yaml --id {clip_id} --platform ios"
        )
    return demo.cmd(f"reelsmith capture import <video file> --id {clip_id}")


def _clips_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("clips", "a valid spec.yaml")
    clip_ids = list(dict.fromkeys(scene.clip for scene in spec.scenes if scene.clip))
    if not clip_ids:
        return Step("clips", "done", "no footage scenes")
    missing: list[str] = []
    no_events: list[str] = []
    for clip_id in clip_ids:
        clip = demo.clip(clip_id)
        if clip is None or not (demo.paths.clips / clip_id / clip.video).is_file():
            missing.append(clip_id)
        elif spec.mode == "narrate" and not clip.events:
            no_events.append(clip_id)
    total = len(clip_ids)
    if missing:
        return Step(
            "clips",
            "missing",
            f"{total - len(missing)}/{total} clips present, missing: {_short_list(missing)}",
            _capture_command(demo, spec, missing[0]),
        )
    if no_events:
        clip_id = no_events[0]
        detected = demo.paths.clips / clip_id / "detected.json"
        next_step = demo.cmd(f"reelsmith detect --clip {clip_id}")
        if detected.is_file():
            next_step = (
                f"Add events to capture/clips/{clip_id}/clip.json from the contact sheets,"
                f" then run: {demo.cmd('reelsmith status')}"
            )
        return Step("clips", "missing", f"no events yet in: {_short_list(no_events)}", next_step)
    return Step("clips", "done", f"{total}/{total} clips present")


# script


def _starter_lines(script: ScriptModel) -> list[str]:
    return [
        f"{scene.id}/{line.id}"
        for scene in script.scenes
        for line in scene.lines
        if any(phrase.text.startswith(STARTER_TEXT) for phrase in line.phrases)
    ]


def _script_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("script", "a valid spec.yaml")
    path = demo.paths.script
    check = demo.cmd("reelsmith script check")
    if not path.is_file():
        return Step("script", "missing", "no script.yaml", f"Write script.yaml, then run: {check}")
    try:
        demo.script = load_model(path, ScriptModel)
    except ReelsmithError as exc:
        return Step("script", "failed", str(exc), f"Fix script.yaml, then run: {check}")
    report = check_script(spec, demo.script, demo.clip)
    if report.problems:
        detail = _short_list(report.problems, limit=2)
        return Step("script", "failed", detail, f"Fix script.yaml, then run: {check}")
    starter = _starter_lines(demo.script)
    if starter:
        return Step(
            "script",
            "missing",
            f"still has starter text in {_short_list(starter)}",
            f"Write the narration in script.yaml, then run: {check}",
        )
    counts = ", ".join(
        (_count(report.scenes, "scene"), _count(report.lines, "line"), _count(report.pins, "pin"))
    )
    return Step("script", "done", f"{counts} resolved")


# voice


def _read_timings(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _voice_id(spec: SpecModel, timings: dict[str, object]) -> str:
    """The voice id the pipeline would hash. A cloned voice is identified by
    its sample, which only the engine can work out, so trust the last run."""
    if spec.voice.engine == "kokoro":
        return spec.voice.kokoro_voice
    if timings.get("engine") == spec.voice.engine:
        return str(timings.get("voice") or "")
    return ""


def _voice_lines(demo: _Demo, spec: SpecModel, script: ScriptModel) -> tuple[list[str], list[str]]:
    """Script line keys that are up to date, and those that are not."""
    timings = _read_timings(demo.paths.voice / "timings.json")
    raw_lines = timings.get("lines")
    prior = {
        f"{item.get('scene')}/{item.get('line')}": item
        for item in (raw_lines if isinstance(raw_lines, list) else [])
        if isinstance(item, dict)
    }
    voice_id = _voice_id(spec, timings)
    pronounce = spec.voice.pronounce if spec.voice.engine == "kokoro" else None
    fresh: list[str] = []
    stale: list[str] = []
    for scene in script.scenes:
        for line in scene.lines:
            key = f"{scene.id}/{line.id}"
            expected = _line_hash(line, spec.voice.engine, voice_id, spec.voice.speed, pronounce)
            entry = prior.get(key, {})
            wav = demo.paths.voice / f"{scene.id}__{line.id}.wav"
            if entry.get("hash") == expected and wav.is_file():
                fresh.append(key)
            else:
                stale.append(key)
    return fresh, stale


def _voice_step(demo: _Demo) -> Step:
    spec, script = demo.spec, demo.script
    if spec is None or script is None:
        return _needs("voice", "a valid spec.yaml and script.yaml")
    if spec.voice.engine == "none":
        return Step("voice", "done", "voice is off, captions only")
    fresh, stale = _voice_lines(demo, spec, script)
    total = len(fresh) + len(stale)
    command = demo.cmd("reelsmith voice generate")
    if total == 0:
        return Step("voice", "missing", "script.yaml has no lines", command)
    summary = f"{len(fresh)}/{total} lines up to date"
    if not stale:
        return Step("voice", "done", summary)
    if not fresh:
        return Step("voice", "missing", summary, command)
    return Step("voice", "stale", f"{summary}, changed: {_short_list(stale)}", command)


# slides


def _slide_ids(spec: SpecModel) -> list[str]:
    return list(
        dict.fromkeys(scene.slide or scene.id for scene in spec.scenes if scene.layout == "slide")
    )


def _slides_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("slides", "a valid spec.yaml")
    slide_ids = _slide_ids(spec)
    if not slide_ids:
        return Step("slides", "done", "no slide scenes")
    command = demo.cmd("reelsmith slides")
    slides_yaml = demo.paths.root / "slides.yaml"
    if not slides_yaml.is_file():
        write = f"Write slides.yaml, then run: {command}"
        return Step("slides", "missing", "no slides.yaml", write)
    newest_source = _newest([slides_yaml, demo.paths.brand])
    parts: list[str] = []
    complete = True
    stale_against: Path | None = None
    for fmt in spec.formats:
        found = _slides_for(demo, spec, fmt, slide_ids)
        parts.append(f"{format_slug(fmt)}: {len(found)}/{len(slide_ids)} rendered")
        complete = complete and len(found) == len(slide_ids)
        images = [image for group in found.values() for image in group]
        if images and newest_source is not None:
            oldest = min(_mtime(image) for image in images)
            if _mtime(newest_source) > oldest:
                stale_against = newest_source
    detail = "; ".join(parts)
    if not complete:
        return Step("slides", "missing", detail, command)
    if stale_against is not None:
        return Step("slides", "stale", f"{detail}, older than {stale_against.name}", command)
    return Step("slides", "done", detail)


def _slides_for(
    demo: _Demo, spec: SpecModel, fmt: str, slide_ids: list[str]
) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for slide_id in slide_ids:
        images = slide_images(demo.paths.slides / format_slug(fmt), slide_id)
        if not images and fmt == spec.formats[0]:
            images = slide_images(demo.paths.slides, slide_id)
        if images:
            found[slide_id] = images
    return found


# master


def _master_inputs(demo: _Demo, spec: SpecModel, fmt: str) -> list[Path]:
    paths = demo.paths
    files = [paths.spec, paths.script, paths.brand, paths.voice / "timings.json"]
    script = demo.script
    if script is not None and spec.voice.engine != "none":
        files += [
            paths.voice / f"{scene.id}__{line.id}.wav"
            for scene in script.scenes
            for line in scene.lines
        ]
    for scene in spec.scenes:
        if scene.clip:
            clip_dir = paths.clips / scene.clip
            files.append(clip_dir / "clip.json")
            clip = demo.clip(scene.clip)
            if clip is not None:
                files.append(clip_dir / clip.video)
    for images in _slides_for(demo, spec, fmt, _slide_ids(spec)).values():
        files += images
    return files


def _master_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("master", "a valid spec.yaml")
    parts: list[str] = []
    state: State = "done"
    command = demo.cmd("reelsmith compose")
    preview_command = demo.cmd("reelsmith compose --preview")
    next_step: str | None = None
    for fmt in spec.formats:
        master = master_path(demo.paths, fmt)
        newest = _newest(_master_inputs(demo, spec, fmt))
        if master.is_file():
            if newest is not None and _mtime(newest) > _mtime(master):
                parts.append(f"{_rel(demo, master)} is older than {_rel(demo, newest)}")
                if state == "done":
                    state, next_step = "stale", command
            else:
                parts.append(_rel(demo, master))
            continue
        preview = master_path(demo.paths, fmt, preview=True)
        fresh_preview = preview.is_file() and (newest is None or _mtime(preview) >= _mtime(newest))
        if fresh_preview:
            parts.append(f"{format_slug(fmt)}: only a preview, {_rel(demo, preview)}")
        else:
            parts.append(f"{format_slug(fmt)}: not composed")
        if state != "missing":
            state = "missing"
            next_step = command if fresh_preview else preview_command
    return Step("master", state, "; ".join(parts), next_step)


# qa


def _qa_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("qa", "a valid spec.yaml")
    report = demo.paths.qa / "report.md"
    command = demo.cmd("reelsmith qa")
    if not report.is_file():
        return Step("qa", "missing", "no qa/report.md", command)
    text = report.read_text(encoding="utf-8")
    rows = _QA_ROW.findall(text)
    counts = {status: sum(1 for _, s in rows if s == status) for status in ("PASS", "WARN", "FAIL")}
    detail = (
        f"{len(rows)} checks: {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL"
    )
    master = master_path(demo.paths, spec.formats[0])
    if text.startswith("# QA report (preview check)") and master.is_file():
        return Step("qa", "stale", f"{detail}, checked the preview only", command)
    if master.is_file() and _mtime(master) > _mtime(report):
        return Step("qa", "stale", f"{detail}, older than {_rel(demo, master)}", command)
    if counts["FAIL"]:
        failing = [name for name, status in rows if status == "FAIL"]
        return Step(
            "qa",
            "failed",
            f"{detail}: {_short_list(failing)}",
            f"Fix each FAIL in qa/report.md, then run: {command}",
        )
    return Step("qa", "done", detail)


# export


def _export_name(demo: _Demo, slug: str) -> str:
    """The base name export used: the folder name, or the newest --name."""
    default = demo_name(demo.paths.root)
    if (demo.paths.out / f"{default}_{slug}.mp4").is_file():
        return default
    candidates = [
        path
        for path in demo.paths.out.glob(f"*_{slug}.mp4")
        if not path.name.endswith("_silent.mp4")
    ]
    newest = _newest(candidates)
    return newest.name.removesuffix(f"_{slug}.mp4") if newest is not None else default


def _export_step(demo: _Demo) -> Step:
    spec = demo.spec
    if spec is None:
        return _needs("export", "a valid spec.yaml")
    out = demo.paths.out
    name = _export_name(demo, format_slug(spec.formats[0]))
    narrated = spec.voice.engine != "none"
    expected = expected_outputs(out, name, spec.formats, narrated)
    command = demo.cmd("reelsmith export")
    present = [path for path in expected if path.is_file()]
    summary = f"{len(present)}/{len(expected)} files in out/"
    if len(present) < len(expected):
        return Step("export", "missing", summary, command)
    masters = [master_path(demo.paths, fmt) for fmt in spec.formats]
    newest_master = _newest(masters)
    oldest = min(_mtime(path) for path in present)
    if newest_master is not None and _mtime(newest_master) > oldest:
        detail = f"{summary}, older than {_rel(demo, newest_master)}"
        return Step("export", "stale", detail, command)
    return Step("export", "done", summary)


STEPS: tuple[Callable[[_Demo], Step], ...] = (
    _spec_step,
    _clips_step,
    _script_step,
    _voice_step,
    _slides_step,
    _master_step,
    _qa_step,
    _export_step,
)


WINDOWS_SPECIAL = set(" \t&()[]{}^=;!'+,`~%|<>\"")


def shell_arg(value: str, *, windows: bool | None = None) -> str:
    """Quote a path so it can be pasted into the user's shell.

    POSIX shells get shlex quoting. cmd and PowerShell do not understand
    single quotes, so on Windows a path is wrapped in double quotes, and
    only when it needs them.
    """
    if windows if windows is not None else os.name == "nt":
        return f'"{value}"' if WINDOWS_SPECIAL.intersection(value) else value
    return shlex.quote(value)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _dir_arg(root: Path, cwd: Path) -> str:
    return "" if root == cwd else " " + shell_arg(str(root))


def demo_status(root: Path, cwd: Path | None = None) -> StatusReport:
    """Inspect a demo folder. Commands name the folder unless it is cwd."""
    root = root.resolve()
    here = (cwd or Path.cwd()).resolve()
    demo = _Demo(DemoPaths.at(root), _dir_arg(root, here))
    steps = [step(demo) for step in STEPS]
    pending = next((step for step in steps if step.state != "done" and step.next), None)
    if pending is not None and pending.next is not None:
        next_step = pending.next
    else:
        next_step = f"Nothing left to run. The finished files are in {demo.paths.out}"
    return StatusReport(steps, next_step)
