"""A check that cannot run must not lose the other eight."""

from __future__ import annotations

from pathlib import Path

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.checks import CheckStatus, QAContext, run_checks
from reelsmith.qa.timeline import Timeline


def test_a_broken_check_becomes_a_warn_row_and_the_rest_still_run(tmp_path: Path) -> None:
    # No master file at all, so the Loudness check's own ffmpeg call fails.
    # Every other check has nothing to look at (no scenes) and should still
    # come back PASS instead of the whole report falling over.
    timeline = Timeline(format="16x9", duration=1.0, scenes=[], transitions=[])
    ctx = QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=tmp_path / "missing.mp4",
        master_duration=1.0,
        sheets_dir=tmp_path / "sheets",
        work_dir=tmp_path,
        transcriber=lambda path: [],
    )

    rows = run_checks(ctx)

    by_name = {row.name: row for row in rows}
    assert len(rows) == 9
    assert by_name["Loudness"].status == CheckStatus.WARN
    assert "Could not run this check" in by_name["Loudness"].details[0]
    assert by_name["Sync"].status == CheckStatus.PASS
    assert by_name["Contact sheets"].status == CheckStatus.PASS
