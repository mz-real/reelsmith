"""Run all nine QA checks over a demo folder and write qa/report.md."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import probe
from reelsmith.models import ScriptModel, SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.qa.checks import CheckStatus, QAContext, run_checks
from reelsmith.qa.report import ReportMeta, render_report
from reelsmith.qa.timeline import load_timeline
from reelsmith.qa.timings import load_timings
from reelsmith.qa.transcribe import Transcriber, get_transcriber
from reelsmith.result import Result, Status


def run_qa(
    root: Path, format: str, transcriber: Transcriber | None = None, *, preview: bool = False
) -> Result:
    """Run the nine QA checks and write qa/report.md.

    With preview, checks the fast draft that `reelsmith compose --preview`
    writes (build/master_<format>_preview.mp4 and its matching timeline)
    instead of the final build, and says so in the report header.

    Returns a Result whose status is ERROR if any check FAILs, WARN if any
    check WARNs (and none FAIL), OK otherwise.
    """
    paths = DemoPaths.at(root.resolve())
    for path, fix in ((paths.spec, "reelsmith init"), (paths.script, "reelsmith init")):
        if not path.is_file():
            raise ReelsmithError(f"{path} not found", fix=fix)

    suffix = "_preview" if preview else ""
    compose_fix = f"reelsmith compose --format {format}" + (" --preview" if preview else "")
    master_path = paths.build / f"master_{format}{suffix}.mp4"
    if not master_path.is_file():
        raise ReelsmithError(f"{master_path} not found", fix=compose_fix)

    timeline_filename = f"timeline_{format}{suffix}.json" if preview else "timeline.json"
    timeline = load_timeline(paths.build / timeline_filename)
    spec = load_model(paths.spec, SpecModel)
    script = load_model(paths.script, ScriptModel)

    notes = list(timeline.warnings)
    engine: str | None = None
    voice: str | None = None
    timings_path = paths.voice / "timings.json"
    if timings_path.is_file():
        timings = load_timings(timings_path)
        engine, voice = timings.engine, timings.voice
        notes.extend(timings.warnings)
    else:
        notes.append(f"{timings_path} not found, so voice engine and voice are unknown")

    info = probe(master_path)
    master_duration = timeline.duration if timeline.duration is not None else info.duration

    paths.qa.mkdir(parents=True, exist_ok=True)
    sheets_dir = paths.qa / "sheets"
    backup_existing(sheets_dir)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    active_transcriber = transcriber if transcriber is not None else get_transcriber()

    with tempfile.TemporaryDirectory(dir=paths.qa) as raw_work_dir:
        ctx = QAContext(
            spec=spec,
            script=script,
            timeline=timeline,
            master=master_path,
            master_duration=master_duration,
            sheets_dir=sheets_dir,
            work_dir=Path(raw_work_dir),
            transcriber=active_transcriber,
        )
        rows = run_checks(ctx)

    sheet_paths = sorted(_relative(p, paths.root) for p in sheets_dir.glob("*.jpg"))

    meta = ReportMeta(
        generated_at=datetime.now(),
        format=format,
        master=_relative(master_path, paths.root),
        master_duration=master_duration,
        engine=engine,
        voice=voice,
        notes=notes,
        preview=preview,
    )
    report_md = render_report(meta, rows, sheet_paths)
    report_path = paths.qa / "report.md"
    backup_existing(report_path)
    report_path.write_text(report_md, encoding="utf-8")

    fail_count = sum(1 for row in rows if row.status == CheckStatus.FAIL)
    warn_count = sum(1 for row in rows if row.status == CheckStatus.WARN)
    pass_count = len(rows) - fail_count - warn_count
    counts = f"{pass_count} passed, {warn_count} warned, {fail_count} failed"
    details = [f"{row.name}: {row.status.value}" for row in rows]
    report_rel = _relative(report_path, paths.root)

    qa_fix = f"reelsmith qa --format {format}" + (" --preview" if preview else "")
    if fail_count:
        status = Status.ERROR
        next_step = f"Fix the FAILs in {report_rel}, then run: {qa_fix}"
    elif warn_count:
        status = Status.WARN
        next_step = f"Review the WARNs in {report_rel}"
    else:
        status = Status.OK
        next_step = "Watch the preview, then run: reelsmith run" if preview else "reelsmith export"

    kind = "preview" if preview else "format"
    return Result(
        status=status,
        message=f"QA checked {kind} {format}: {counts}",
        details=details,
        next_step=next_step,
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
