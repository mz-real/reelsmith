"""A real, tiny `reelsmith run` of a silent (voice.engine: none) demo.

Checks the full pipeline end to end with no voice: the voice step is
skipped, slides run on caption time alone, qa skips the checks that need
real narration instead of failing, and export writes the video and srt
without a narration wav or a separate silent copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reelsmith.commands.run import build_steps, run_steps
from reelsmith.paths import DemoPaths
from reelsmith.qa.checks import CheckStatus
from reelsmith.result import Status
from tests.integration._demo import write_slide

pytestmark = pytest.mark.integration

SPEC = {
    "version": 1,
    "formats": ["16:9"],
    "theme": "dark",
    "voice": {"engine": "none"},
    "scenes": [{"id": "intro", "layout": "slide", "slide": "intro"}],
}

SCRIPT = {
    "version": 1,
    "scenes": [
        {
            "id": "intro",
            "caption": "Silent demo",
            "lines": [
                {
                    "id": "l1",
                    "phrases": [
                        {"text": "This demo has no narration."},
                        {"text": "Captions alone carry the timing."},
                    ],
                }
            ],
        }
    ],
}


def _build_silent_demo(root: Path) -> Path:
    (root / "slides").mkdir(parents=True)
    write_slide(root / "slides" / "intro.png", "Silent")
    (root / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    return root


def test_silent_demo_runs_through_reelsmith_run(tmp_path: Path, require_ffmpeg: None) -> None:
    root = _build_silent_demo(tmp_path / "silent-demo")

    result = run_steps(build_steps(root, preview=False))

    assert result.status in {Status.OK, Status.WARN}
    assert any("voice" in d and "engine is none" in d for d in result.details)
    assert not (root / "voice" / "timings.json").exists()

    paths = DemoPaths.at(root)
    out_names = {p.name for p in paths.out.glob("*")}
    assert "silent-demo_16x9.mp4" in out_names
    assert "silent-demo.srt" in out_names
    assert not any("_silent" in name for name in out_names)
    assert not any(name.endswith("_narration.wav") for name in out_names)

    report = (paths.qa / "report.md").read_text(encoding="utf-8")
    assert "voice.engine is none" in report
    for check_name in ("Transcript vs script", "End of line noise", "Loudness"):
        start = report.index(f". {check_name} - ")
        row = report[start : report.index("\n", start)]
        assert CheckStatus.FAIL.value not in row
        assert check_name in row
