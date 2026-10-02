"""`reelsmith script check`: make sure script.yaml fits the spec and clips."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.errors import ReelsmithError
from reelsmith.models import ClipModel, ScriptModel, SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit

ClipLoader = Callable[[str], ClipModel | None]


@dataclass
class ScriptReport:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scenes: int = 0
    lines: int = 0
    pins: int = 0


def check_script(spec: SpecModel, script: ScriptModel, load_clip: ClipLoader) -> ScriptReport:
    """Check scene ids against the spec and every pin against its clip's events."""
    report = ScriptReport(scenes=len(script.scenes))
    for scene in script.scenes:
        report.lines += len(scene.lines)
        spec_scene = spec.scene(scene.id)
        if spec_scene is None:
            report.problems.append(f"Scene '{scene.id}' is not in spec.yaml")
            continue
        clip: ClipModel | None = None
        if spec_scene.clip is not None:
            clip = load_clip(spec_scene.clip)
        for line in scene.lines:
            for number, phrase in enumerate(line.phrases, start=1):
                if phrase.pin is None:
                    continue
                report.pins += 1
                where = (
                    f"Scene '{scene.id}', line '{line.id}', phrase {number}"
                    f" is pinned to '{phrase.pin}'"
                )
                if spec_scene.clip is None:
                    report.problems.append(f"{where}, but the scene is a slide")
                elif clip is None:
                    report.problems.append(
                        f"{where}, but capture/clips/{spec_scene.clip}/clip.json is missing"
                    )
                elif clip.event(phrase.pin) is None:
                    report.problems.append(
                        f"{where}, but clip '{spec_scene.clip}' has no such event"
                    )
    for spec_scene in spec.scenes:
        if script.scene(spec_scene.id) is None:
            report.warnings.append(f"Scene '{spec_scene.id}' has no narration")
    return report


def _clip_loader(paths: DemoPaths) -> ClipLoader:
    def load(clip_id: str) -> ClipModel | None:
        path = paths.clips / clip_id / "clip.json"
        if not path.is_file():
            return None
        return load_model(path, ClipModel)

    return load


def run_check(root: Path) -> Result:
    paths = DemoPaths.at(root)
    for path in (paths.spec, paths.script):
        if not path.is_file():
            raise ReelsmithError(f"{path} not found", fix="reelsmith init")
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)
    report = check_script(spec, script, _clip_loader(paths))
    counts = (
        f"{report.scenes} scenes, {report.lines} lines, "
        f"{report.pins} pin{'' if report.pins == 1 else 's'}"
    )
    if report.problems:
        count = len(report.problems)
        return Result(
            status=Status.ERROR,
            message=f"script.yaml has {count} problem{'' if count == 1 else 's'}",
            details=report.problems + report.warnings,
            next_step=f"Fix {paths.script}, then run: reelsmith script check",
        )
    status = Status.WARN if report.warnings else Status.OK
    return Result(
        status=status,
        message=f"Script checked: {counts}",
        details=report.warnings,
        next_step="reelsmith voice generate",
    )


def register(app: typer.Typer) -> None:
    script_app = typer.Typer(help="Work with script.yaml.")

    @script_app.command("check")
    def check(
        directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    ) -> int:
        """Check that scenes match spec.yaml and pins name real clip events."""
        return emit(run_check(demo_dir(directory, None)))

    app.add_typer(script_app, name="script")
