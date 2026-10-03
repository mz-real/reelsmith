"""Tests for the Chatterbox engine, with torch and chatterbox faked."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel
from reelsmith.voice import chatterbox_engine
from reelsmith.voice.base import get_engine
from reelsmith.voice.chatterbox_engine import ChatterboxEngine


class FakeModel:
    def __init__(self, device: str) -> None:
        self.device = device
        self.sr = 24000
        self.watermarker: object | None = object()
        self.calls: list[dict[str, Any]] = []

    def generate(self, text: str, audio_prompt_path: str) -> np.ndarray:
        self.calls.append({"text": text, "audio_prompt_path": audio_prompt_path})
        return np.full((1, 2400), 0.1, dtype=np.float64)


class FakeTorch(types.ModuleType):
    def __init__(self, cuda: bool = False, mps: bool = False) -> None:
        super().__init__("torch")
        self.seeds: list[int] = []
        self.cuda = types.SimpleNamespace(is_available=lambda: cuda)
        self.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps))

    def manual_seed(self, seed: int) -> None:
        self.seeds.append(seed)


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch, *, cuda: bool = False, mps: bool = False
) -> tuple[FakeTorch, list[FakeModel]]:
    torch = FakeTorch(cuda=cuda, mps=mps)
    made: list[FakeModel] = []

    class ChatterboxTTS:
        @classmethod
        def from_pretrained(cls, device: str) -> FakeModel:
            model = FakeModel(device)
            made.append(model)
            return model

    tts = types.ModuleType("chatterbox.tts")
    tts.ChatterboxTTS = ChatterboxTTS  # type: ignore[attr-defined]
    package = types.ModuleType("chatterbox")
    package.tts = tts  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "chatterbox", package)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", tts)
    return torch, made


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chatterbox_engine, "_models", {})
    monkeypatch.setattr(chatterbox_engine.sys, "version_info", (3, 12, 0))


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    path = tmp_path / "me.wav"
    path.write_bytes(b"RIFF")
    return path


def test_synthesize_returns_float32_mono_at_model_rate(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    _install_fakes(monkeypatch, cuda=True)
    engine = ChatterboxEngine(sample=sample, consent="own")

    audio = engine.synthesize("Hello there.", seed=0)

    assert audio.sample_rate == 24000
    assert audio.samples.dtype == np.float32
    assert audio.samples.ndim == 1
    assert audio.samples.size == 2400
    assert engine.name == "chatterbox"


def test_reference_sample_is_passed_to_the_model(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    _, made = _install_fakes(monkeypatch, cuda=True)
    ChatterboxEngine(sample=sample, consent="permission").synthesize("Hi.", seed=0)
    assert made[0].calls == [{"text": "Hi.", "audio_prompt_path": str(sample)}]


def test_each_attempt_seeds_torch(monkeypatch: pytest.MonkeyPatch, sample: Path) -> None:
    torch, made = _install_fakes(monkeypatch, cuda=True)
    engine = ChatterboxEngine(sample=sample, consent="own")
    engine.synthesize("One.", seed=0)
    engine.synthesize("One.", seed=3)
    assert torch.seeds == [0, 3]
    assert len(made) == 1, "the model loads once and is reused"


@pytest.mark.parametrize(
    ("cuda", "mps", "device"),
    [(True, True, "cuda"), (False, True, "mps"), (False, False, "cpu")],
)
def test_device_prefers_cuda_then_mps_then_cpu(
    monkeypatch: pytest.MonkeyPatch, sample: Path, cuda: bool, mps: bool, device: str
) -> None:
    _, made = _install_fakes(monkeypatch, cuda=cuda, mps=mps)
    ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)
    assert made[0].device == device


def test_cpu_prints_a_speed_warning(
    monkeypatch: pytest.MonkeyPatch, sample: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _install_fakes(monkeypatch)
    ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)
    err = capsys.readouterr().err
    assert "WARN" in err
    assert "slow" in err


def test_gpu_prints_no_warning(
    monkeypatch: pytest.MonkeyPatch, sample: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _install_fakes(monkeypatch, mps=True)
    ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("consent", [None, "", "yes", "OWN"])
def test_refuses_without_valid_consent(sample: Path, consent: str | None) -> None:
    with pytest.raises(ReelsmithError, match="consent"):
        ChatterboxEngine(sample=sample, consent=consent)


def test_refuses_when_the_sample_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError, match="sample"):
        ChatterboxEngine(sample=tmp_path / "nope.wav", consent="own")


def test_consent_is_checked_again_at_synthesis(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    _, made = _install_fakes(monkeypatch, cuda=True)
    engine = ChatterboxEngine(sample=sample, consent="own")
    engine.consent = None
    with pytest.raises(ReelsmithError, match="consent"):
        engine.synthesize("Hi.", seed=0)
    assert made == []


def test_refuses_a_model_without_its_watermarker(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    _, made = _install_fakes(monkeypatch, cuda=True)
    original = FakeModel.__init__

    def no_watermark(self: FakeModel, device: str) -> None:
        original(self, device)
        self.watermarker = None

    monkeypatch.setattr(FakeModel, "__init__", no_watermark)
    with pytest.raises(ReelsmithError, match="watermark"):
        ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)


def test_pronounce_prints_a_warning_and_is_ignored(
    monkeypatch: pytest.MonkeyPatch, sample: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, made = _install_fakes(monkeypatch, cuda=True)
    engine = ChatterboxEngine(sample=sample, consent="own", pronounce={"reelsmith": "ɹˈiːl smɪθ"})
    err = capsys.readouterr().err
    assert "WARN" in err
    assert "say" in err

    engine.synthesize("Made with reelsmith.", seed=0)

    assert made[0].calls == [{"text": "Made with reelsmith.", "audio_prompt_path": str(sample)}]


def test_no_pronounce_prints_no_warning(
    monkeypatch: pytest.MonkeyPatch, sample: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _install_fakes(monkeypatch, cuda=True)
    ChatterboxEngine(sample=sample, consent="own")
    assert capsys.readouterr().err == ""


def test_has_no_way_to_turn_the_watermark_off(sample: Path) -> None:
    import dataclasses

    names = {f.name for f in dataclasses.fields(ChatterboxEngine)}
    assert not any("watermark" in name for name in names)


def test_missing_chatterbox_gives_the_install_fix(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    monkeypatch.setitem(sys.modules, "chatterbox", None)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", None)
    with pytest.raises(ReelsmithError) as info:
        ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)
    assert info.value.message == "Own voice cloning needs the clone extra."
    assert info.value.fix == 'uv tool install "reelsmith[clone]"'


def test_python_313_explains_the_version_limit(
    monkeypatch: pytest.MonkeyPatch, sample: Path
) -> None:
    _install_fakes(monkeypatch, cuda=True)
    monkeypatch.setattr(chatterbox_engine.sys, "version_info", (3, 13, 0))
    with pytest.raises(ReelsmithError, match=r"Python 3\.11 or 3\.12") as info:
        ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0)
    assert info.value.fix is not None
    assert "3.12" in info.value.fix


def test_voice_id_changes_with_the_sample_content(tmp_path: Path) -> None:
    sample = tmp_path / "me.wav"
    sample.write_bytes(b"one")
    first = ChatterboxEngine(sample=sample, consent="own").voice_id
    sample.write_bytes(b"two")
    second = ChatterboxEngine(sample=sample, consent="own").voice_id
    assert first != second
    assert first.startswith("me.wav:")


def _clone_spec(sample: str, consent: str | None = "own") -> SpecModel:
    return SpecModel.model_validate(
        {"voice": {"engine": "chatterbox", "sample": sample, "consent": consent}}
    )


def test_get_engine_returns_chatterbox_with_sample_relative_to_root(tmp_path: Path) -> None:
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "me.wav").write_bytes(b"RIFF")
    engine = get_engine(_clone_spec("voice/me.wav"), root=tmp_path)
    assert isinstance(engine, ChatterboxEngine)
    assert engine.sample == tmp_path / "voice" / "me.wav"


def test_get_engine_passes_pronounce_to_chatterbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "me.wav").write_bytes(b"RIFF")
    spec = _clone_spec("voice/me.wav")
    spec.voice = spec.voice.model_copy(update={"pronounce": {"reelsmith": "ɹˈiːl smɪθ"}})

    engine = get_engine(spec, root=tmp_path)

    assert isinstance(engine, ChatterboxEngine)
    assert engine.pronounce == {"reelsmith": "ɹˈiːl smɪθ"}
    assert "WARN" in capsys.readouterr().err


def test_get_engine_refuses_a_spec_built_without_validation(tmp_path: Path) -> None:
    (tmp_path / "me.wav").write_bytes(b"RIFF")
    spec = SpecModel()
    spec.voice = spec.voice.model_copy(update={"engine": "chatterbox", "sample": "me.wav"})
    with pytest.raises(ReelsmithError, match="consent"):
        get_engine(spec, root=tmp_path)


def _write_demo(root: Path, voice: str) -> None:
    (root / "spec.yaml").write_text(f"version: 1\nvoice:\n{voice}", encoding="utf-8")
    (root / "script.yaml").write_text(
        "version: 1\nscenes:\n  - id: s\n    caption: c\n    lines:\n"
        "      - id: l1\n        phrases:\n          - text: Hello there.\n",
        encoding="utf-8",
    )


def test_cli_voice_generate_refuses_clone_without_consent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    (tmp_path / "me.wav").write_bytes(b"RIFF")
    _write_demo(tmp_path, "  engine: chatterbox\n  sample: me.wav\n")

    code = run(app, ["voice", "generate", str(tmp_path)])

    assert code == 1
    assert "consent" in capsys.readouterr().out
    assert not (tmp_path / "voice" / "s__l1.wav").exists()


def test_cli_voice_generate_refuses_clone_when_sample_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith.cli import app, run

    _write_demo(tmp_path, "  engine: chatterbox\n  sample: gone.wav\n  consent: own\n")

    code = run(app, ["voice", "generate", str(tmp_path)])

    assert code == 1
    assert "gone.wav was not found" in capsys.readouterr().out


def test_no_cli_option_touches_consent_or_the_watermark() -> None:
    import typer.main

    from reelsmith.cli import app

    def walk(command: Any) -> list[str]:
        names = [opt for p in command.params for opt in getattr(p, "opts", [])]
        for sub in getattr(command, "commands", {}).values():
            names += walk(sub)
        return names

    options = walk(typer.main.get_command(app))
    assert "--refs" in options, "the walk reaches nested voice commands"
    assert not [o for o in options if "watermark" in o or "consent" in o]


def _one_second_tone(self: FakeModel, text: str, audio_prompt_path: str) -> np.ndarray:
    t = np.arange(24000) / 24000
    return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.mark.parametrize(("speed", "seconds"), [(0.9, 1 / 0.9), (0.5, 1 / 0.75), (1.4, 1 / 1.25)])
def test_speed_slows_or_speeds_the_cloned_audio(
    monkeypatch: pytest.MonkeyPatch, sample: Path, speed: float, seconds: float
) -> None:
    """Chatterbox has no speed setting, so the audio is time-stretched after.

    The stretch keeps the pitch and the Perth watermark (checked on real
    output at 0.85 to 0.95), and is clamped to 0.75 to 1.25.
    """
    _install_fakes(monkeypatch, cuda=True)
    monkeypatch.setattr(FakeModel, "generate", _one_second_tone)
    engine = ChatterboxEngine(sample=sample, consent="own")

    audio = engine.synthesize("Hello there.", seed=0, speed=speed)

    assert audio.sample_rate == 24000
    assert audio.samples.dtype == np.float32
    assert audio.samples.size / 24000 == pytest.approx(seconds, rel=0.03)


@pytest.mark.parametrize("speed", [None, 1.0])
def test_normal_speed_leaves_the_audio_untouched(
    monkeypatch: pytest.MonkeyPatch, sample: Path, speed: float | None
) -> None:
    _install_fakes(monkeypatch, cuda=True)
    monkeypatch.setattr(FakeModel, "generate", _one_second_tone)
    audio = ChatterboxEngine(sample=sample, consent="own").synthesize("Hi.", seed=0, speed=speed)
    assert audio.samples.size == 24000
