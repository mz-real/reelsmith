"""The `reelsmith voice` commands: generate and preview narration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import soundfile as sf
import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.fsutil import backup_existing
from reelsmith.models import ScriptModel, SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit
from reelsmith.voice.kokoro_engine import KokoroEngine
from reelsmith.voice.pipeline import LineReport, VoiceReport, generate
from reelsmith.voice.quality import pace_ok

app = typer.Typer(help="Generate and preview narration audio.")


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="voice")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _failure_reasons(line: LineReport) -> list[str]:
    reasons: list[str] = []
    if not pace_ok(line.wpm):
        reasons.append("pace")
    if not line.transcript_ok:
        reasons.append("dropped words")
    return reasons


def _result_for(report: VoiceReport) -> Result:
    total = len(report.lines)
    skipped = [line for line in report.lines if line.skipped]
    pace_regen = sum(1 for line in report.lines if line.pace_retried)
    transcript_regen = sum(1 for line in report.lines if line.transcript_retried)

    failing: list[tuple[str, list[str]]] = []
    for line in report.lines:
        if line.skipped:
            continue
        reasons = _failure_reasons(line)
        if reasons:
            failing.append((f"{line.scene}/{line.line}", reasons))

    details: list[str] = []
    if pace_regen:
        details.append(f"{_plural(pace_regen, 'line')} regenerated for pace")
    if transcript_regen:
        details.append(f"{_plural(transcript_regen, 'line')} regenerated for dropped words")
    if skipped:
        details.append(f"{_plural(len(skipped), 'line')} skipped, already up to date")

    if failing:
        for key, reasons in failing:
            details.append(f"{key} still fails: {' and '.join(reasons)}")
        keys = " ".join(key for key, _ in failing)
        return Result(
            status=Status.WARN,
            message=f"Voice generated for {_plural(total, 'line')}, {len(failing)} need review",
            details=details,
            next_step=f"reelsmith voice generate --only {keys}",
        )

    return Result(
        status=Status.OK,
        message=f"Voice generated for {_plural(total, 'line')}",
        details=details,
        next_step="reelsmith compose --preview",
    )


@app.command("generate")
def generate_command(
    directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    only: list[str] | None = typer.Option(
        None,
        "--only",
        help="Limit to one or more scene/line ids, for example search/l1. Repeatable.",
    ),
) -> None:
    """Synthesize narration for every line in script.yaml."""
    paths = DemoPaths.at(demo_dir(directory, None))
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)
    only_set = set(only) if only else None

    report = generate(paths, spec, script, only_set)
    emit(_result_for(report))


@app.command("preview")
def preview_command(
    directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    text: str = typer.Option(..., "--text", help="The line to read."),
    voices: str = typer.Option(
        "af_heart,bf_emma,am_michael",
        "--voices",
        help="Comma separated Kokoro voice names.",
    ),
) -> None:
    """Read one line in a few voices, written to voice/preview/<voice>.wav."""
    paths = DemoPaths.at(demo_dir(directory, None))
    preview_dir = paths.voice / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    names = [name.strip() for name in voices.split(",") if name.strip()]
    written: list[str] = []
    for name in names:
        engine = KokoroEngine(voice=name)
        audio = engine.synthesize(text, seed=0)
        out_path = preview_dir / f"{name}.wav"
        if out_path.exists():
            backup_existing(out_path)
        sf.write(out_path, audio.samples, audio.sample_rate)
        written.append(out_path.name)

    emit(
        Result(
            status=Status.OK,
            message=f"Preview written for {_plural(len(written), 'voice')}",
            details=written,
            next_step="reelsmith voice generate",
        )
    )
