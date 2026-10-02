"""The `reelsmith voice` commands: generate, preview, pick-reference and compare."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import soundfile as sf
import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.models import ScriptModel, SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit
from reelsmith.voice.compare import CompareReport, clone_engine, compare_references, why
from reelsmith.voice.kokoro_engine import KokoroEngine
from reelsmith.voice.pipeline import LineReport, VoiceReport, generate
from reelsmith.voice.quality import pace_ok
from reelsmith.voice.reference import ReferencePick, load_recording, pick_reference
from reelsmith.voice.transcribe import transcribe

# Module level so tests can swap in a fake engine and transcriber.
compare_engine_factory = clone_engine
compare_transcribe = transcribe

app = typer.Typer(help="Generate and preview narration audio.")


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="voice")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _failure_reasons(line: LineReport) -> list[str]:
    reasons: list[str] = []
    if line.pace_checked and not pace_ok(line.wpm):
        reasons.append("pace")
    if not line.transcript_ok:
        reasons.append("dropped words")
    return reasons


def _result_for(report: VoiceReport) -> Result:
    total = len(report.lines)
    generated = [line for line in report.lines if not line.skipped and not line.left_out]
    skipped = [line for line in report.lines if line.skipped]
    pace_regen = sum(1 for line in generated if line.pace_retried)
    transcript_regen = sum(1 for line in generated if line.transcript_retried)

    failing: list[tuple[str, list[str]]] = []
    for line in report.lines:
        if line.skipped:
            continue
        reasons = _failure_reasons(line)
        if reasons:
            failing.append((f"{line.scene}/{line.line}", reasons))

    # Always shown, even at zero, so a --only run says plainly what happened
    # to the lines it touched instead of staying silent on a clean pass.
    details: list[str] = [
        f"{_plural(len(generated), 'line')} generated",
        f"{_plural(len(skipped), 'line')} skipped, already up to date",
        f"{_plural(pace_regen, 'line')} regenerated for pace",
        f"{_plural(transcript_regen, 'line')} regenerated for dropped words",
    ]

    if failing:
        for key, reasons in failing:
            details.append(f"{key} still fails: {' and '.join(reasons)}")
        # Repeat --only per line. A bare second id would be read as DIR.
        only_args = " ".join(f"--only {key}" for key, _ in failing)
        return Result(
            status=Status.WARN,
            message=f"Voice generated for {_plural(total, 'line')}, {len(failing)} need review",
            details=details,
            next_step=f"reelsmith voice generate {only_args}",
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
) -> int:
    """Synthesize narration for every line in script.yaml."""
    return emit(run_generate(demo_dir(directory, None), only))


def run_generate(directory: Path, only: list[str] | None = None) -> Result:
    """Generate narration for a demo folder and return the result block."""
    paths = DemoPaths.at(directory)
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)
    only_set = set(only) if only else None
    return _result_for(generate(paths, spec, script, only_set))


@app.command("preview")
def preview_command(
    directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    text: str = typer.Option(..., "--text", help="The line to read."),
    voices: str = typer.Option(
        "af_heart,bf_emma,am_michael",
        "--voices",
        help="Comma separated Kokoro voice names.",
    ),
) -> int:
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

    return emit(
        Result(
            status=Status.OK,
            message=f"Preview written for {_plural(len(written), 'voice')}",
            details=written,
            next_step="reelsmith voice generate",
        )
    )


def _pick_result(source: Path, out: Path, pick: ReferencePick) -> Result:
    best = pick.best
    details = [
        f"Picked {best.start:.1f} to {best.end:.1f} s of {source.name}, score {best.total:.2f}",
        f"Scores: speech {best.speech_score:.2f}, noise {best.noise_score:.2f}, "
        f"clipping {best.clip_score:.2f}, pace {best.pace_score:.2f}",
        "Why: " + "; ".join(pick.reasons),
        *pick.notes,
    ]
    status = Status.OK
    if best.clipped_samples:
        status = Status.WARN
        details.append("Every stretch clips. Record again a little further from the mic.")
    return Result(
        status=status,
        message=f"Reference written to {out}",
        details=details,
        next_step=f"Listen to {out.name}, then set voice.sample to it in spec.yaml",
    )


@app.command("pick-reference")
def pick_reference_command(
    recording: Annotated[Path, typer.Argument(help="A recording of your voice, any format.")],
    out: Annotated[Path, typer.Option("--out", help="Where to write the reference.")] = Path(
        "ref.wav"
    ),
    seconds: Annotated[
        float,
        typer.Option("--seconds", min=5.0, max=30.0, help="Length of the reference."),
    ] = 12.0,
) -> int:
    """Find the cleanest stretch of a recording and save it as a 24 kHz mono wav."""
    pick = pick_reference(load_recording(recording), seconds=seconds)
    if out.exists():
        backup_existing(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, pick.audio.samples, pick.audio.sample_rate, subtype="PCM_16")
    return emit(_pick_result(recording, out, pick))


def _resolve_ref(raw: str, root: Path) -> Path:
    ref = Path(raw)
    if not ref.is_absolute() and not ref.exists() and (root / ref).exists():
        return root / ref
    return ref


def _compare_result(report: CompareReport) -> Result:
    details = [
        f"{score.ref.name}: score {score.score:.2f}, {why(score)}" for score in report.scores
    ]
    best = report.recommended
    details.append(f"Recommended: {best.ref.name}")
    details.append(f"Notes in {report.markdown}")
    return Result(
        status=Status.OK,
        message=f"Compared {_plural(len(report.scores), 'reference')}",
        details=details,
        next_step=f"Set voice.sample to {best.ref.name} in spec.yaml, then run: "
        "reelsmith voice generate",
    )


@app.command("compare")
def compare_command(
    directory: Annotated[Path, typer.Argument(help="The demo folder.")] = Path("."),
    refs: str = typer.Option(..., "--refs", help="Comma separated reference files."),
    lines: Annotated[
        int, typer.Option("--lines", min=1, help="How many script lines to read.")
    ] = 3,
) -> int:
    """Read the first script lines with each reference and recommend one."""
    paths = DemoPaths.at(directory)
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)
    ref_paths = [_resolve_ref(raw.strip(), paths.root) for raw in refs.split(",") if raw.strip()]
    if not ref_paths:
        raise ReelsmithError("Give at least one reference.", fix="--refs a.wav,b.wav")
    report = compare_references(
        paths,
        spec,
        script,
        ref_paths,
        lines,
        engine_factory=compare_engine_factory,
        transcribe_fn=compare_transcribe,
    )
    return emit(_compare_result(report))
