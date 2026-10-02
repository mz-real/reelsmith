"""Tests for rendering the QA report."""

from __future__ import annotations

from datetime import datetime

from reelsmith.qa.checks import CheckRow, CheckStatus
from reelsmith.qa.report import ReportMeta, render_report


def test_render_report_lists_every_check_and_its_details() -> None:
    meta = ReportMeta(
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        format="16x9",
        master="build/master_16x9.mp4",
        master_duration=12.5,
        engine="kokoro",
        voice="af_heart",
        notes=[],
    )
    rows = [
        CheckRow("Sync", CheckStatus.PASS, ["Every pinned phrase starts inside its sync window."]),
        CheckRow(
            "Loudness", CheckStatus.FAIL, ["Integrated loudness is -22.0 LUFS. Fix: recompose."]
        ),
    ]

    text = render_report(meta, rows, ["qa/sheets/scenes.jpg"])

    assert "# QA report" in text
    assert "Format: 16x9" in text
    assert "build/master_16x9.mp4 (12.50s)" in text
    assert "kokoro / af_heart" in text
    assert "1. Sync - PASS" in text
    assert "2. Loudness - FAIL" in text
    assert "Integrated loudness is -22.0 LUFS" in text
    assert "qa/sheets/scenes.jpg" in text


def test_render_report_notes_a_missing_sheet() -> None:
    meta = ReportMeta(
        generated_at=datetime(2026, 1, 1),
        format="16x9",
        master="build/master_16x9.mp4",
        master_duration=1.0,
        engine=None,
        voice=None,
        notes=["voice/timings.json not found, so voice engine and voice are unknown"],
    )

    text = render_report(meta, [], [])

    assert "Note: voice/timings.json not found" in text
    assert "none written" in text
