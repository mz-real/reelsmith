"""Tests for `reelsmith run`, with every step faked."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.commands import run as run_cmd
from reelsmith.errors import ReelsmithError
from reelsmith.result import Result, Status


class Recorder:
    """Stands in for every step, recording calls and returning preset results."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.results: dict[str, Result | Exception] = {}

    def hit(self, name: str) -> Result:
        self.calls.append(name)
        result = self.results.get(name, ok())
        if isinstance(result, Exception):
            raise result
        return result


def ok(message: str = "fine") -> Result:
    return Result(Status.OK, message)


@pytest.fixture
def rec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Recorder:
    r = Recorder()
    (tmp_path / "slides.yaml").write_text("slides: []\n", encoding="utf-8")
    monkeypatch.setattr(run_cmd, "run_check", lambda root: r.hit("script check"))
    monkeypatch.setattr(run_cmd, "run_generate", lambda root: r.hit("voice generate"))
    monkeypatch.setattr(run_cmd, "run_slides", lambda root: r.hit("slides"))
    monkeypatch.setattr(run_cmd, "_load_compose", lambda: lambda root, preview: r.hit("compose"))
    monkeypatch.setattr(run_cmd, "_load_qa", lambda: lambda root, fmt, preview: r.hit("qa"))
    monkeypatch.setattr(run_cmd, "_load_export", lambda: lambda root, name: r.hit("export"))
    return r


def _run(rec: Recorder, root: Path, preview: bool = False) -> Result:
    return run_cmd.run_steps(run_cmd.build_steps(root, preview))


def test_runs_every_step_in_order(rec: Recorder, tmp_path: Path) -> None:
    result = _run(rec, tmp_path)
    assert rec.calls == ["script check", "voice generate", "slides", "compose", "qa", "export"]
    assert result.status == Status.OK


def test_preview_skips_export(rec: Recorder, tmp_path: Path) -> None:
    result = _run(rec, tmp_path, preview=True)
    assert "export" not in rec.calls
    assert any("export" in d and "skipped" in d for d in result.details)


def test_voice_step_skipped_when_engine_is_none(rec: Recorder, tmp_path: Path) -> None:
    from reelsmith.models import SpecModel, VoiceSettings, save_model

    save_model(tmp_path / "spec.yaml", SpecModel(voice=VoiceSettings(engine="none")))

    result = _run(rec, tmp_path)

    assert "voice generate" not in rec.calls
    assert rec.calls == ["script check", "slides", "compose", "qa", "export"]
    assert result.status == Status.OK
    assert any("skipped" in d and "engine is none" in d for d in result.details)


def test_slides_only_run_when_slides_yaml_exists(rec: Recorder, tmp_path: Path) -> None:
    (tmp_path / "slides.yaml").unlink()
    _run(rec, tmp_path)
    assert "slides" not in rec.calls


def test_stops_at_the_first_error_with_its_next_hint(rec: Recorder, tmp_path: Path) -> None:
    failing = Result(Status.ERROR, "script.yaml has 1 problem", ["bad pin"], next_step="Fix it")
    rec.results["script check"] = failing

    result = _run(rec, tmp_path)

    assert rec.calls == ["script check"]
    assert result.status == Status.ERROR
    assert "script check" in result.message
    assert result.next_step == "Fix it"
    assert "bad pin" in result.details


def test_a_raised_reelsmith_error_stops_the_run(rec: Recorder, tmp_path: Path) -> None:
    error = ReelsmithError("Own voice cloning needs the clone extra.", fix="uv tool install x")
    rec.results["voice generate"] = error

    result = _run(rec, tmp_path)

    assert rec.calls == ["script check", "voice generate"]
    assert result.status == Status.ERROR
    assert "voice generate" in result.message
    assert result.next_step == "uv tool install x"


def test_a_warn_continues_and_is_listed(rec: Recorder, tmp_path: Path) -> None:
    warn = Result(Status.WARN, "Voice generated for 3 lines, 1 need review")
    rec.results["voice generate"] = warn

    result = _run(rec, tmp_path)

    assert rec.calls[-1] == "export"
    assert result.status == Status.WARN
    assert any("voice generate" in d and "need review" in d for d in result.details)


def test_missing_steps_are_skipped_with_a_warn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(run_cmd, "_load_compose", lambda: None)
    monkeypatch.setattr(run_cmd, "_load_qa", lambda: None)
    monkeypatch.setattr(run_cmd, "_load_export", lambda: None)
    monkeypatch.setattr(run_cmd, "run_check", lambda root: ok("checked"))
    monkeypatch.setattr(run_cmd, "run_generate", lambda root: ok("voiced"))

    result = run_cmd.run_steps(run_cmd.build_steps(tmp_path, preview=False))

    assert result.status == Status.WARN
    for name in ("compose", "qa", "export"):
        assert any(
            d.startswith(f"[WARN] {name}") and "step not available in this build" in d
            for d in result.details
        )


def test_qa_runs_once_per_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from reelsmith.models import SpecModel, save_model

    save_model(tmp_path / "spec.yaml", SpecModel(formats=["16:9", "9:16"]))
    seen: list[str] = []

    def fake_qa(root: Path, fmt: str, preview: bool) -> Result:
        seen.append(fmt)
        return ok()

    monkeypatch.setattr(run_cmd, "_load_qa", lambda: fake_qa)
    steps = {s.name: s for s in run_cmd.build_steps(tmp_path, preview=True)}
    assert steps["qa"].fn is not None
    steps["qa"].fn()
    assert seen == ["16x9", "9x16"]


def test_qa_gets_the_preview_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[bool] = []

    def fake_qa(root: Path, fmt: str, preview: bool) -> Result:
        seen.append(preview)
        return ok()

    monkeypatch.setattr(run_cmd, "_load_qa", lambda: fake_qa)
    steps = {s.name: s for s in run_cmd.build_steps(tmp_path, preview=True)}
    assert steps["qa"].fn is not None
    steps["qa"].fn()
    assert seen == [True]


def test_compose_gets_the_preview_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[bool] = []

    def fake_compose(root: Path, preview: bool) -> Result:
        seen.append(preview)
        return ok()

    monkeypatch.setattr(run_cmd, "_load_compose", lambda: fake_compose)
    steps = {s.name: s for s in run_cmd.build_steps(tmp_path, preview=True)}
    assert steps["compose"].fn is not None
    steps["compose"].fn()
    assert seen == [True]


def test_cli_prints_one_result_block_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    failing = Result(Status.ERROR, "spec.yaml not found", next_step="reelsmith init")
    monkeypatch.setattr(run_cmd, "run_check", lambda root: failing)

    code = run(app, ["run", str(tmp_path), "--preview"])

    out = capsys.readouterr().out
    assert code == 1
    assert "[ERROR] Run stopped at script check: spec.yaml not found" in out
    assert out.rstrip().endswith("Next: reelsmith init")


def test_preview_suggests_the_full_run(rec: Recorder, tmp_path: Path) -> None:
    result = run_cmd.run_steps(run_cmd.build_steps(tmp_path, True), preview=True)
    assert result.next_step is not None
    assert "reelsmith run" in result.next_step


def test_loaders_return_none_when_nothing_is_there(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_cmd, "_import_attr", lambda module, attr: None)
    monkeypatch.setattr(run_cmd, "_cli_fallback", lambda command: None)
    assert run_cmd._load_compose() is None
    assert run_cmd._load_qa() is None
    assert run_cmd._load_export() is None


def test_loaders_fall_back_to_the_typer_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fallback(command: str) -> object:
        def invoke(args: list[str]) -> Result:
            seen.append([command, *args])
            return ok()

        return invoke

    monkeypatch.setattr(run_cmd, "_import_attr", lambda module, attr: None)
    monkeypatch.setattr(run_cmd, "_cli_fallback", fallback)
    compose = run_cmd._load_compose()
    assert compose is not None
    compose(Path("demo"), True)
    assert seen == [["compose", "demo", "--preview"]]

    seen.clear()
    qa = run_cmd._load_qa()
    assert qa is not None
    qa(Path("demo"), "16x9", True)
    assert seen == [["qa", "demo", "--format", "16x9", "--preview"]]
