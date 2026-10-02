"""Individual doctor checks."""

from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from reelsmith import __version__
from reelsmith.result import Status
from reelsmith.voice.models_dl import KOKORO_INT8, KOKORO_VOICES, models_dir
from reelsmith.voice.transcribe import WHISPER_MODEL, whisper_model_cache_dir


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    found: str
    fix: str | None


_KOKORO_MODEL = KOKORO_INT8.filename
_VOICES_BIN = KOKORO_VOICES.filename

_MIN_PYTHON = (3, 11)
_MAX_PYTHON = (3, 14)


def run_all_checks(spec_path: Path | None = None) -> list[Check]:
    """Run every doctor check and return the results."""
    want_chatterbox = _spec_wants_chatterbox(spec_path)
    checks = [
        check_python(),
        check_ffmpeg(),
        check_playwright_chromium(),
        check_java(),
        check_maestro(),
        check_simctl(),
        check_adb(),
        check_kokoro_model(),
        check_whisper_model(),
        check_gpu(),
        check_plugin_version(),
    ]
    if want_chatterbox:
        checks.append(check_chatterbox())
    return checks


def _spec_wants_chatterbox(spec_path: Path | None) -> bool:
    if spec_path is None or not spec_path.is_file():
        return False
    try:
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    voice = data.get("voice")
    if not isinstance(voice, dict):
        return False
    return voice.get("engine") == "chatterbox"


def check_python() -> Check:
    name = "python"
    vi = sys.version_info
    found = f"{vi.major}.{vi.minor}.{vi.micro}"
    if vi < _MIN_PYTHON or vi >= _MAX_PYTHON:
        return Check(
            name=name,
            status=Status.ERROR,
            found=f"Python {found} (need 3.11 to 3.13)",
            fix="Install Python 3.11 or newer from python.org or your package manager.",
        )
    return Check(name=name, status=Status.OK, found=f"Python {found}", fix=None)


def check_ffmpeg() -> Check:
    name = "ffmpeg"
    binary = shutil.which("ffmpeg")
    if binary is None:
        return Check(
            name=name,
            status=Status.ERROR,
            found="not on PATH",
            fix=_ffmpeg_install_fix(),
        )
    version = _tool_version(["ffmpeg", "-version"], r"ffmpeg version (\d+)")
    if version is None or version < 6:
        ver_text = str(version) if version is not None else "unknown"
        return Check(
            name=name,
            status=Status.ERROR,
            found=f"version {ver_text} (need 6 or newer)",
            fix=_ffmpeg_install_fix(),
        )
    return Check(name=name, status=Status.OK, found=f"version {version}", fix=None)


def _ffmpeg_install_fix() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ffmpeg"
    if system == "Windows":
        return "winget install ffmpeg"
    if shutil.which("dnf"):
        return "sudo dnf install ffmpeg"
    return "sudo apt install ffmpeg"


def check_playwright_chromium() -> Check:
    name = "chromium"
    if _chromium_executable_exists():
        return Check(name=name, status=Status.OK, found="Playwright Chromium installed", fix=None)
    return Check(
        name=name,
        status=Status.ERROR,
        found="Playwright Chromium not installed",
        fix="reelsmith setup browser",
    )


def _chromium_executable_exists() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            path = Path(pw.chromium.executable_path)
            return path.is_file()
    except (OSError, RuntimeError):
        return False


def check_java() -> Check:
    name = "java"
    binary = shutil.which("java")
    if binary is None:
        return Check(
            name=name,
            status=Status.WARN,
            found="not on PATH (needed for mobile capture)",
            fix=_java_install_fix(),
        )
    version = _java_major_version()
    if version is None or version < 17:
        ver_text = str(version) if version is not None else "unknown"
        return Check(
            name=name,
            status=Status.WARN,
            found=f"version {ver_text} (need 17 or newer for mobile)",
            fix=_java_install_fix(),
        )
    return Check(name=name, status=Status.OK, found=f"Java {version}", fix=None)


def _java_install_fix() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install openjdk@17"
    if system == "Windows":
        return "winget install EclipseAdoptium.Temurin.17.JDK"
    if shutil.which("dnf"):
        return "sudo dnf install java-17-openjdk"
    return "sudo apt install openjdk-17-jdk"


def _java_major_version() -> int | None:
    completed = subprocess.run(
        ["java", "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    text = stderr + stdout
    match = re.search(r'version "(\d+)', text) or re.search(r"openjdk version \"(\d+)", text)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1:
        minor = re.search(r'version "1\.(\d+)', text)
        if minor:
            return int(minor.group(1))
    return major


def check_maestro() -> Check:
    name = "maestro"
    if shutil.which("maestro") is not None:
        return Check(name=name, status=Status.OK, found="Maestro on PATH", fix=None)
    return Check(
        name=name,
        status=Status.WARN,
        found="not on PATH (needed for mobile capture)",
        fix='curl -fsSL "https://get.maestro.mobile.dev" | bash',
    )


def check_simctl() -> Check:
    name = "simctl"
    if platform.system() != "Darwin":
        return Check(name=name, status=Status.OK, found="not required on this OS", fix=None)
    if shutil.which("xcrun") is None:
        return Check(
            name=name,
            status=Status.WARN,
            found="xcrun not found (install Xcode for iOS simulators)",
            fix="Install Xcode from the App Store, then run xcode-select --install",
        )
    completed = subprocess.run(
        ["xcrun", "simctl", "help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return Check(
            name=name,
            status=Status.WARN,
            found="simctl not working",
            fix="Install Xcode from the App Store, then run xcode-select --install",
        )
    return Check(name=name, status=Status.OK, found="xcrun simctl available", fix=None)


def check_adb() -> Check:
    name = "adb"
    if shutil.which("adb") is not None:
        return Check(name=name, status=Status.OK, found="adb on PATH", fix=None)
    system = platform.system()
    if system == "Darwin":
        fix = "brew install --cask android-platform-tools"
    elif system == "Windows":
        fix = "winget install Google.PlatformTools"
    else:
        fix = "sudo apt install adb"
    return Check(
        name=name,
        status=Status.WARN,
        found="not on PATH (needed for Android capture)",
        fix=fix,
    )


def check_kokoro_model() -> Check:
    name = "kokoro model"
    path = models_dir() / _KOKORO_MODEL
    voices = models_dir() / _VOICES_BIN
    if path.is_file() and voices.is_file():
        return Check(name=name, status=Status.OK, found="cached locally", fix=None)
    missing: list[str] = []
    if not path.is_file():
        missing.append(_KOKORO_MODEL)
    if not voices.is_file():
        missing.append(_VOICES_BIN)
    return Check(
        name=name,
        status=Status.WARN,
        found=f"not cached ({', '.join(missing)})",
        fix="reelsmith voice generate (downloads on first use)",
    )


def check_whisper_model() -> Check:
    name = "whisper model"
    marker = whisper_model_cache_dir()
    if marker.is_dir():
        return Check(name=name, status=Status.OK, found=f"{WHISPER_MODEL} cached", fix=None)
    return Check(
        name=name,
        status=Status.WARN,
        found=f"{WHISPER_MODEL} not cached",
        fix="reelsmith voice generate (downloads on first use)",
    )


def check_chatterbox() -> Check:
    name = "chatterbox"
    if importlib.util.find_spec("chatterbox") is not None:
        return Check(name=name, status=Status.OK, found="importable", fix=None)
    return Check(
        name=name,
        status=Status.ERROR,
        found="not installed",
        fix='uv tool install "reelsmith[clone]"',
    )


def check_gpu() -> Check:
    name = "gpu"
    if shutil.which("nvidia-smi") is not None:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            line = completed.stdout.strip().splitlines()
            label = line[0] if line else "NVIDIA GPU"
            return Check(name=name, status=Status.OK, found=f"CUDA: {label}", fix=None)
    if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        return Check(name=name, status=Status.OK, found="Apple Silicon", fix=None)
    return Check(
        name=name,
        status=Status.WARN,
        found="no GPU detected, voice and video will use CPU",
        fix=None,
    )


def check_plugin_version() -> Check:
    name = "plugin version"
    expected = os.environ.get("REELSMITH_EXPECTED_VERSION")
    if not expected:
        return Check(name=name, status=Status.OK, found="not checked", fix=None)
    if expected == __version__:
        return Check(
            name=name,
            status=Status.OK,
            found=f"matches CLI {__version__}",
            fix=None,
        )
    return Check(
        name=name,
        status=Status.WARN,
        found=f"plugin expects {expected}, CLI is {__version__}",
        fix=f"Install reelsmith {expected} or update the plugin to {__version__}",
    )


def _tool_version(command: list[str], pattern: str) -> int | None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
    match = re.search(pattern, stdout + stderr)
    if not match:
        return None
    return int(match.group(1))
