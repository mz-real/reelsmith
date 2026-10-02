"""`reelsmith run`: every step from script check to export, in order.

Steps: script check, voice generate, slides (only with slides.yaml),
compose, qa and export (not with --preview). The run stops at the first
ERROR. A WARN does not stop it, but is listed at the end. A step whose
code is not in this build is skipped with a WARN.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from reelsmith.commands.script_check import run_check
from reelsmith.commands.slides import run_slides
from reelsmith.commands.voice import run_generate
from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit

NOT_AVAILABLE = "step not available in this build"

StepFn = Callable[[], Result]
ComposeFn = Callable[[Path, bool], Result]
QaFn = Callable[[Path, str, bool], Result]
ExportFn = Callable[[Path, str | None], Result]


@dataclass(frozen=True)
class Step:
    name: str
    fn: StepFn | None
    skip: str = ""
    skip_status: Status = Status.OK


def _import_attr(module: str, attr: str) -> Any:
    try:
        return getattr(importlib.import_module(module), attr, None)
    except ImportError:
        return None


def _cli_fallback(command: str) -> Callable[[list[str]], Result] | None:
    """Run a registered command through the typer app, if there is one."""
    from reelsmith import cli

    names = {c.name for c in cli.app.registered_commands}
    names |= {g.name for g in cli.app.registered_groups}
    if command not in names:
        return None

    def invoke(args: list[str]) -> Result:
        code = cli.run(cli.app, [command, *args])
        if code == 0:
            return Result(Status.OK, f"{command} finished")
        return Result(Status.ERROR, f"{command} failed, see above")

    return invoke


def _load_compose() -> ComposeFn | None:
    direct = _import_attr("reelsmith.commands.compose", "run_compose")
    if direct is not None:
        return lambda root, preview: direct(root, preview=preview)
    fallback = _cli_fallback("compose")
    if fallback is None:
        return None
    return lambda root, preview: fallback([str(root), *(["--preview"] if preview else [])])


def _load_qa() -> QaFn | None:
    direct = _import_attr("reelsmith.qa.runner", "run_qa")
    if direct is not None:
        return lambda root, fmt, preview: direct(root, fmt, preview=preview)
    fallback = _cli_fallback("qa")
    if fallback is None:
        return None
    return lambda root, fmt, preview: fallback(
        [str(root), "--format", fmt, *(["--preview"] if preview else [])]
    )


def _load_export() -> ExportFn | None:
    direct = _import_attr("reelsmith.commands.export", "run_export")
    if direct is not None:
        return direct  # type: ignore[no-any-return]
    fallback = _cli_fallback("export")
    if fallback is None:
        return None
    return lambda root, name: fallback([str(root)])


def _formats(root: Path) -> list[str]:
    spec_path = DemoPaths.at(root).spec
    spec = load_model(spec_path, SpecModel) if spec_path.is_file() else SpecModel()
    return [fmt.replace(":", "x") for fmt in spec.formats]


def _qa_all_formats(qa: QaFn, root: Path, preview: bool) -> Result:
    results = [(fmt, qa(root, fmt, preview)) for fmt in _formats(root)]
    for fmt, result in results:
        if result.status == Status.ERROR:
            return Result(
                Status.ERROR, f"{fmt}: {result.message}", result.details, result.next_step
            )
    status = Status.WARN if any(r.status == Status.WARN for _, r in results) else Status.OK
    details = [f"{fmt}: {d}" for fmt, r in results for d in r.details]
    message = "; ".join(f"{fmt}: {r.message}" for fmt, r in results)
    return Result(status, message, details, results[-1][1].next_step if results else None)


def build_steps(root: Path, preview: bool) -> list[Step]:
    steps = [
        Step("script check", lambda: run_check(root)),
        Step("voice generate", lambda: run_generate(root)),
    ]
    if (root / "slides.yaml").is_file():
        steps.append(Step("slides", lambda: run_slides(root)))
    else:
        steps.append(Step("slides", None, "skipped, there is no slides.yaml"))

    compose = _load_compose()
    if compose is None:
        steps.append(Step("compose", None, NOT_AVAILABLE, Status.WARN))
    else:
        steps.append(Step("compose", lambda: compose(root, preview)))

    qa = _load_qa()
    if qa is None:
        steps.append(Step("qa", None, NOT_AVAILABLE, Status.WARN))
    else:
        steps.append(Step("qa", lambda: _qa_all_formats(qa, root, preview)))

    if preview:
        steps.append(Step("export", None, "skipped with --preview"))
    else:
        export = _load_export()
        if export is None:
            steps.append(Step("export", None, NOT_AVAILABLE, Status.WARN))
        else:
            steps.append(Step("export", lambda: export(root, None)))
    return steps


def _call(fn: StepFn) -> Result:
    try:
        return fn()
    except ReelsmithError as exc:
        return Result(Status.ERROR, exc.message, next_step=exc.fix)


def run_steps(steps: list[Step], preview: bool = False) -> Result:
    """Run steps in order, stop at the first ERROR, collect every WARN."""
    lines: list[str] = []
    warnings = 0
    last: Result | None = None
    for number, step in enumerate(steps, start=1):
        if step.fn is None:
            lines.append(f"[{step.skip_status.value}] {step.name}: {step.skip}")
            warnings += step.skip_status == Status.WARN
            continue
        typer.echo(f"Step {number} of {len(steps)}: {step.name}")
        result = _call(step.fn)
        if result.status == Status.ERROR:
            return Result(
                Status.ERROR,
                f"Run stopped at {step.name}: {result.message}",
                [*lines, *result.details],
                next_step=result.next_step,
            )
        lines.append(f"[{result.status.value}] {step.name}: {result.message}")
        if result.status == Status.WARN:
            warnings += 1
            lines.extend(f"{step.name}: {detail}" for detail in result.details)
        last = result
    next_step = last.next_step if last else None
    if preview:
        next_step = "Watch the preview, then run: reelsmith run"
    if warnings:
        plural = "" if warnings == 1 else "s"
        return Result(
            Status.WARN, f"Run finished with {warnings} warning{plural}", lines, next_step
        )
    return Result(Status.OK, "Run finished", lines, next_step)


def register(app: typer.Typer) -> None:
    @app.command("run")
    def run(
        directory: Annotated[Path, typer.Argument(help="The demo folder.")] = Path("."),
        preview: Annotated[
            bool, typer.Option("--preview", help="Fast draft. Composes a preview, no export.")
        ] = False,
    ) -> int:
        """Run every step from script check to export, stopping at the first error."""
        return emit(run_steps(build_steps(directory, preview), preview))
