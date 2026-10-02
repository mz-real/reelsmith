"""Doctor profiles: which checks apply for web, mobile, voice, and related workflows."""

from __future__ import annotations

import enum
from pathlib import Path

import yaml

_CHECK_PYTHON = "python"
_CHECK_FFMPEG = "ffmpeg"
_CHECK_CHROMIUM = "chromium"
_CHECK_JAVA = "java"
_CHECK_MAESTRO = "maestro"
_CHECK_SIMCTL = "simctl"
_CHECK_ADB = "adb"
_CHECK_KOKORO = "kokoro model"
_CHECK_WHISPER = "whisper model"
_CHECK_GPU = "gpu"
_CHECK_CHATTERBOX = "chatterbox"
_CHECK_PLUGIN = "plugin version"

_MOBILE_TOOL_CHECKS = (_CHECK_JAVA, _CHECK_MAESTRO, _CHECK_SIMCTL, _CHECK_ADB)
_VOICE_MODEL_CHECKS = (_CHECK_KOKORO, _CHECK_WHISPER)

_CHECK_ORDER: tuple[str, ...] = (
    _CHECK_PYTHON,
    _CHECK_FFMPEG,
    _CHECK_CHROMIUM,
    _CHECK_JAVA,
    _CHECK_MAESTRO,
    _CHECK_SIMCTL,
    _CHECK_ADB,
    _CHECK_KOKORO,
    _CHECK_WHISPER,
    _CHECK_CHATTERBOX,
    _CHECK_GPU,
    _CHECK_PLUGIN,
)


class DoctorProfile(enum.StrEnum):
    WEB = "web"
    MOBILE = "mobile"
    NARRATE = "narrate"
    VOICE = "voice"
    CLONE = "clone"
    ALL = "all"


def find_spec_path(spec_path: Path | None) -> Path | None:
    """Return an explicit spec path or spec.yaml in the current working directory."""
    if spec_path is not None and spec_path.is_file():
        return spec_path
    cwd_spec = Path.cwd() / "spec.yaml"
    if cwd_spec.is_file():
        return cwd_spec
    return spec_path if spec_path is not None else None


def profile_from_spec(spec_path: Path) -> DoctorProfile:
    """Pick the doctor profile that best matches a spec.yaml file."""
    data = _load_spec_dict(spec_path)
    voice = _voice_dict(data)
    engine = voice.get("engine", "kokoro")
    if engine == "chatterbox":
        return DoctorProfile.CLONE
    if data.get("mode") == "narrate":
        return DoctorProfile.NARRATE
    footage = data.get("footage", "web")
    if footage == "mobile":
        return DoctorProfile.MOBILE
    if footage == "import":
        return DoctorProfile.NARRATE
    return DoctorProfile.WEB


def resolve_profile(
    profile: DoctorProfile | None,
    spec_path: Path | None,
) -> tuple[DoctorProfile, Path | None]:
    """Resolve the active profile and spec path for a doctor run."""
    resolved_spec = find_spec_path(spec_path)
    if profile is not None:
        return profile, resolved_spec
    if resolved_spec is not None and resolved_spec.is_file():
        return profile_from_spec(resolved_spec), resolved_spec
    return DoctorProfile.WEB, resolved_spec


def active_check_names(profile: DoctorProfile, spec_path: Path | None) -> frozenset[str]:
    """Return check names to run for this profile and optional spec."""
    names = set(_base_checks_for_profile(profile))
    if profile != DoctorProfile.ALL and _spec_voice_engine_none(spec_path):
        names -= set(_VOICE_MODEL_CHECKS)
    if profile in (DoctorProfile.CLONE, DoctorProfile.ALL):
        names.add(_CHECK_CHATTERBOX)
    elif _spec_wants_chatterbox(spec_path):
        names.add(_CHECK_CHATTERBOX)
    return frozenset(names)


def skipped_check_names(profile: DoctorProfile, spec_path: Path | None) -> tuple[str, ...]:
    """Checks not run for this profile, in stable order."""
    active = active_check_names(profile, spec_path)
    skipped = [name for name in _CHECK_ORDER if name not in active]
    return tuple(skipped)


def format_skipped_line(profile: DoctorProfile, spec_path: Path | None) -> str | None:
    skipped = skipped_check_names(profile, spec_path)
    if not skipped:
        return None
    return f"skipped for {profile.value}: {', '.join(skipped)}"


def check_run_order() -> tuple[str, ...]:
    return _CHECK_ORDER


def _base_checks_for_profile(profile: DoctorProfile) -> frozenset[str]:
    common = {_CHECK_PYTHON, _CHECK_PLUGIN}
    if profile == DoctorProfile.VOICE:
        return frozenset(common | set(_VOICE_MODEL_CHECKS))
    if profile == DoctorProfile.NARRATE:
        return frozenset(common | {_CHECK_FFMPEG} | set(_VOICE_MODEL_CHECKS))
    if profile == DoctorProfile.WEB:
        return frozenset(common | {_CHECK_FFMPEG, _CHECK_CHROMIUM} | set(_VOICE_MODEL_CHECKS))
    if profile == DoctorProfile.MOBILE:
        web = _base_checks_for_profile(DoctorProfile.WEB)
        return frozenset(web | set(_MOBILE_TOOL_CHECKS))
    if profile == DoctorProfile.CLONE:
        voice = _base_checks_for_profile(DoctorProfile.VOICE)
        return frozenset(voice | {_CHECK_CHATTERBOX, _CHECK_GPU})
    if profile == DoctorProfile.ALL:
        return frozenset(_CHECK_ORDER)
    raise ValueError(f"unknown profile: {profile}")


def _load_spec_dict(spec_path: Path) -> dict[str, object]:
    try:
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _voice_dict(data: dict[str, object]) -> dict[str, object]:
    voice = data.get("voice")
    if isinstance(voice, dict):
        return voice
    return {}


def _spec_voice_engine_none(spec_path: Path | None) -> bool:
    if spec_path is None or not spec_path.is_file():
        return False
    voice = _voice_dict(_load_spec_dict(spec_path))
    return voice.get("engine") == "none"


def _spec_wants_chatterbox(spec_path: Path | None) -> bool:
    if spec_path is None or not spec_path.is_file():
        return False
    voice = _voice_dict(_load_spec_dict(spec_path))
    return voice.get("engine") == "chatterbox"
