"""Doctor profile selection and scoped checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.doctor.checks import run_all_checks
from reelsmith.doctor.profiles import (
    DoctorProfile,
    format_skipped_line,
    profile_from_spec,
    resolve_profile,
)
from reelsmith.result import Status


def _write_spec(tmp_path: Path, body: str) -> Path:
    spec = tmp_path / "spec.yaml"
    spec.write_text(body, encoding="utf-8")
    return spec


def test_profile_from_spec_web(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path, "version: 1\nfootage: web\n")
    assert profile_from_spec(spec) == DoctorProfile.WEB


def test_profile_from_spec_mobile(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path, "version: 1\nfootage: mobile\n")
    assert profile_from_spec(spec) == DoctorProfile.MOBILE


def test_profile_from_spec_import(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path, "version: 1\nfootage: import\n")
    assert profile_from_spec(spec) == DoctorProfile.NARRATE


def test_profile_from_spec_voice_none_skips_models(tmp_path: Path) -> None:
    spec = _write_spec(
        tmp_path,
        "version: 1\nfootage: web\nvoice:\n  engine: none\n",
    )
    profile, resolved = resolve_profile(None, spec)
    assert profile == DoctorProfile.WEB
    assert resolved == spec
    names = {c.name for c in run_all_checks(resolved, profile=profile)}
    assert "kokoro model" not in names
    assert "whisper model" not in names


def test_profile_from_spec_chatterbox(tmp_path: Path) -> None:
    spec = _write_spec(
        tmp_path,
        "version: 1\nvoice:\n  engine: chatterbox\n  sample: ref.wav\n  consent: own\n",
    )
    assert profile_from_spec(spec) == DoctorProfile.CLONE


def test_web_profile_ok_without_java_or_maestro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}" if name == "ffmpeg" else None)

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        from unittest.mock import MagicMock

        result = MagicMock()
        result.returncode = 0
        result.stdout = "ffmpeg version 7.0\n" if cmd[0] == "ffmpeg" else ""
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        "reelsmith.doctor.checks._chromium_executable_exists",
        lambda: True,
    )
    checks = run_all_checks(profile=DoctorProfile.WEB)
    by_name = {c.name: c for c in checks}
    assert "java" not in by_name
    assert "maestro" not in by_name
    assert by_name["python"].status == Status.OK
    assert by_name["ffmpeg"].status == Status.OK


def test_mobile_profile_warns_without_maestro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/bin/{name}" if name in ("ffmpeg", "java") else None,
    )

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        from unittest.mock import MagicMock

        result = MagicMock()
        result.returncode = 0
        result.stdout = "ffmpeg version 7.0\n" if cmd[0] == "ffmpeg" else ""
        result.stderr = 'openjdk version "17.0.1"\n' if cmd[0] == "java" else ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        "reelsmith.doctor.checks._chromium_executable_exists",
        lambda: True,
    )
    monkeypatch.setattr("platform.system", lambda: "Linux")
    checks = run_all_checks(profile=DoctorProfile.MOBILE)
    maestro = next(c for c in checks if c.name == "maestro")
    assert maestro.status == Status.WARN


def test_uncached_models_ok_with_note(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import reelsmith.doctor.checks as checks_mod
    import reelsmith.voice.models_dl as models_dl_mod
    import reelsmith.voice.transcribe as transcribe_mod

    empty = tmp_path / "models"
    monkeypatch.setattr(models_dl_mod, "models_dir", lambda: empty)
    monkeypatch.setattr(transcribe_mod, "models_dir", lambda: empty)
    monkeypatch.setattr(checks_mod, "models_dir", lambda: empty)
    monkeypatch.setattr(
        transcribe_mod,
        "whisper_model_cache_dir",
        lambda: empty / "whisper",
    )

    checks = run_all_checks(profile=DoctorProfile.VOICE)
    kokoro = next(c for c in checks if c.name == "kokoro model")
    whisper = next(c for c in checks if c.name == "whisper model")
    assert kokoro.status == Status.OK
    assert whisper.status == Status.OK
    assert "290 MB" in kokoro.found
    assert "290 MB" in whisper.found


def test_skipped_line_for_web_profile() -> None:
    line = format_skipped_line(DoctorProfile.WEB, None)
    assert line is not None
    assert line.startswith("skipped for web:")
    assert "java" in line
    assert "maestro" in line


def test_doctor_takes_the_demo_folder_and_reads_its_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    seen: list[object] = []

    def fake_checks(spec_path: Path | None, *, profile: DoctorProfile) -> list[object]:
        seen.append((spec_path, profile))
        return []

    monkeypatch.setattr("reelsmith.doctor.run_all_checks", fake_checks)
    spec = _write_spec(tmp_path, "version: 1\nfootage: mobile\n")

    code = run(app, ["doctor", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert seen == [(spec, DoctorProfile.MOBILE)]
    assert f"spec: {spec}" in out
    assert "Next: reelsmith status" in out


def test_doctor_without_a_spec_suggests_init(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    monkeypatch.setattr("reelsmith.doctor.run_all_checks", lambda spec, *, profile: [])
    monkeypatch.chdir(tmp_path)

    code = run(app, ["doctor"])

    out = capsys.readouterr().out
    assert code == 0
    assert "profile: web" in out
    assert "Next: reelsmith init my-demo" in out


def test_doctor_names_a_missing_demo_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    code = run(app, ["doctor", str(tmp_path / "nope")])

    assert code == 1
    assert "No demo folder at" in capsys.readouterr().out
