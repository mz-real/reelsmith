"""Doctor checks with mocked tools and OS."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reelsmith.doctor.checks import (
    check_adb,
    check_ffmpeg,
    check_java,
    check_kokoro_model,
    check_maestro,
    check_playwright_chromium,
    check_plugin_version,
    check_python,
    check_simctl,
    check_whisper_model,
    run_all_checks,
)
from reelsmith.doctor.profiles import DoctorProfile
from reelsmith.result import Status
from reelsmith.voice.models_dl import KOKORO_INT8, KOKORO_VOICES
from reelsmith.voice.transcribe import whisper_model_cache_dir


def test_check_python_ok() -> None:
    check = check_python()
    assert check.status == Status.OK
    assert check.name == "python"


def test_check_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    check = check_ffmpeg()
    assert check.status == Status.ERROR
    assert check.fix is not None


@pytest.mark.parametrize(
    ("system", "which_map", "expected_fragment"),
    [
        ("Darwin", {}, "brew install ffmpeg"),
        ("Windows", {}, "winget install ffmpeg"),
        ("Linux", {"dnf": "/usr/bin/dnf"}, "dnf install ffmpeg"),
        ("Linux", {}, "apt install ffmpeg"),
    ],
)
def test_check_ffmpeg_fix_per_os(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    which_map: dict[str, str],
    expected_fragment: str,
) -> None:
    def which(name: str) -> str | None:
        if name == "ffmpeg":
            return None
        return which_map.get(name)

    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("platform.system", lambda: system)
    check = check_ffmpeg()
    assert expected_fragment in (check.fix or "")


def test_check_ffmpeg_version_too_old(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ffmpeg version 5.1.2\n"
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    check = check_ffmpeg()
    assert check.status == Status.ERROR
    assert "5" in check.found or "need 6" in check.found


def test_check_ffmpeg_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ffmpeg version 7.0\n"
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    check = check_ffmpeg()
    assert check.status == Status.OK


def test_check_chromium_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "reelsmith.doctor.checks._chromium_executable_exists",
        lambda: False,
    )
    check = check_playwright_chromium()
    assert check.status == Status.ERROR
    assert check.fix == "reelsmith setup browser"


def test_check_java_warn_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    check = check_java()
    assert check.status == Status.WARN
    assert check.fix == "brew install openjdk@17"


@pytest.mark.parametrize(
    ("system", "which_map", "expected_fragment"),
    [
        ("Darwin", {}, "brew install openjdk@17"),
        ("Windows", {}, "winget install EclipseAdoptium.Temurin.17.JDK"),
        ("Linux", {"dnf": "/usr/bin/dnf"}, "dnf install java-17-openjdk"),
        ("Linux", {}, "apt install openjdk-17-jdk"),
    ],
)
def test_check_java_fix_per_os(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    which_map: dict[str, str],
    expected_fragment: str,
) -> None:
    def which(name: str) -> str | None:
        if name == "java":
            return None
        return which_map.get(name)

    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("platform.system", lambda: system)
    check = check_java()
    assert expected_fragment in (check.fix or "")


def test_voice_model_checks_ok_when_cache_paths_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import reelsmith.doctor.checks as checks_mod
    import reelsmith.voice.models_dl as models_dl_mod
    import reelsmith.voice.transcribe as transcribe_mod

    root = tmp_path / "cache"
    model_root = root / "models"

    def fake_models_dir() -> Path:
        return model_root

    monkeypatch.setattr(models_dl_mod, "models_dir", fake_models_dir)
    monkeypatch.setattr(transcribe_mod, "models_dir", fake_models_dir)
    monkeypatch.setattr(checks_mod, "models_dir", fake_models_dir)

    model_root.mkdir(parents=True)
    (model_root / KOKORO_INT8.filename).write_bytes(b"x")
    (model_root / KOKORO_VOICES.filename).write_bytes(b"y")
    whisper_model_cache_dir().mkdir()

    kokoro = check_kokoro_model()
    whisper = check_whisper_model()
    assert kokoro.status == Status.OK
    assert whisper.status == Status.OK
    assert "cached" in kokoro.found
    assert "cached" in whisper.found


def test_check_maestro_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    check = check_maestro()
    assert check.status == Status.WARN
    assert "get.maestro.mobile.dev" in (check.fix or "")


def test_check_simctl_skipped_off_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    check = check_simctl()
    assert check.status == Status.OK
    assert "not required" in check.found


def test_check_simctl_warn_without_xcrun(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    check = check_simctl()
    assert check.status == Status.WARN


def test_check_adb_fix_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("platform.system", lambda: "Windows")
    check = check_adb()
    assert check.status == Status.WARN
    assert "winget" in (check.fix or "")


def test_plugin_version_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELSMITH_EXPECTED_VERSION", "9.9.9")
    check = check_plugin_version()
    assert check.status == Status.WARN
    assert "9.9.9" in check.found


def test_chatterbox_check_only_with_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if cmd[0] == "ffmpeg":
            result.stdout = "ffmpeg version 7.0\n"
        elif cmd[0] == "java":
            result.stderr = 'openjdk version "17.0.1"\n'
        elif cmd[0] == "xcrun":
            result.returncode = 1
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        "reelsmith.doctor.checks._chromium_executable_exists",
        lambda: True,
    )
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "version: 1\nvoice:\n  engine: kokoro\n",
        encoding="utf-8",
    )
    names = [c.name for c in run_all_checks(spec_path=spec, profile=DoctorProfile.WEB)]
    assert "chatterbox" not in names

    spec.write_text(
        "version: 1\nvoice:\n  engine: chatterbox\n  sample: ref.wav\n  consent: own\n",
        encoding="utf-8",
    )
    names = [c.name for c in run_all_checks(spec_path=spec)]
    assert "chatterbox" in names


def test_check_python_error_when_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    import reelsmith.doctor.checks as checks_mod

    monkeypatch.setattr(checks_mod, "_MIN_PYTHON", (99, 99))
    check = check_python()
    assert check.status == Status.ERROR
