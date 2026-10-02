"""Render the QA checks into qa/report.md."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from reelsmith.qa.checks import CheckRow


@dataclass(frozen=True)
class ReportMeta:
    generated_at: datetime
    format: str
    master: str
    master_duration: float
    engine: str | None
    voice: str | None
    notes: list[str]
    preview: bool = False


def render_report(meta: ReportMeta, rows: list[CheckRow], sheet_paths: list[str]) -> str:
    title = "QA report (preview check)" if meta.preview else "QA report"
    lines = [f"# {title}", ""]
    lines.append(f"Generated: {meta.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Format: {meta.format}")
    lines.append(f"Master: {meta.master} ({meta.master_duration:.2f}s)")
    if meta.engine or meta.voice:
        lines.append(f"Voice: {meta.engine or 'unknown'} / {meta.voice or 'unknown'}")
    lines.append("")
    if meta.notes:
        for note in meta.notes:
            lines.append(f"Note: {note}")
        lines.append("")

    for number, row in enumerate(rows, start=1):
        lines.append(f"## {number}. {row.name} - {row.status.value}")
        for detail in row.details:
            lines.append(f"- {detail}")
        lines.append("")

    lines.append("## Contact sheets")
    if sheet_paths:
        for path in sheet_paths:
            lines.append(f"- {path}")
    else:
        lines.append("- none written")
    lines.append("")

    return "\n".join(lines)
