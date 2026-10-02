"""Tests for reelsmith.voice.compare and `reelsmith voice compare`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelsmith.errors import ReelsmithError
from reelsmith.models import Line, Phrase, ScriptModel, ScriptScene, SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.voice.base import Audio, VoiceEngine
from reelsmith.voice.compare import compare_references, cosine, mean_mfcc
from reelsmith.voice.transcribe import Word

SR = 24000


def tone(freqs: list[float], seconds: float = 2.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    wave = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    lobes = np.sin(np.pi * 3 * t) ** 2
    return (0.3 * wave / len(freqs) * lobes).astype(np.float32)


LOW = [150.0, 300.0, 450.0]
HIGH = [2500.0, 3700.0, 5100.0]


def test_mean_mfcc_has_twelve_coefficients() -> None:
    assert mean_mfcc(Audio(tone(LOW), SR)).shape == (12,)


def test_similar_sounds_score_higher_than_different_ones() -> None:
    ref = mean_mfcc(Audio(tone(LOW, seconds=3.0), SR))
    same = mean_mfcc(Audio(tone(LOW, seconds=1.5), SR))
    other = mean_mfcc(Audio(tone(HIGH), SR))
    assert cosine(ref, same) > 0.95
    assert cosine(ref, same) > cosine(ref, other) + 0.2


def test_mfcc_does_not_depend_on_sample_rate() -> None:
    a = mean_mfcc(Audio(tone(LOW, sr=24000), 24000))
    b = mean_mfcc(Audio(tone(LOW, sr=16000), 16000))
    assert cosine(a, b) > 0.95


class ToneEngine:
    """Speaks every line as a fixed tone, as long as `seconds_per_word` says."""

    name = "fake"

    def __init__(self, freqs: list[float], seconds_per_word: float) -> None:
        self.freqs = freqs
        self.seconds_per_word = seconds_per_word
        self.texts: list[str] = []

    def synthesize(self, text: str, seed: int) -> Audio:
        self.texts.append(text)
        seconds = self.seconds_per_word * len(text.split())
        return Audio(tone(self.freqs, seconds=seconds), SR)


def _script() -> ScriptModel:
    lines = ["Open the app and sign in.", "Search for a dish by name.", "Save it.", "Done now."]
    return ScriptModel(
        scenes=[
            ScriptScene(
                id="a",
                caption="c",
                lines=[Line(id="l1", phrases=[Phrase(text=lines[0])])],
            ),
            ScriptScene(
                id="b",
                caption="c",
                lines=[
                    Line(id=f"l{i}", phrases=[Phrase(text=text)])
                    for i, text in enumerate(lines[1:], start=1)
                ],
            ),
        ]
    )


def _spec(consent: str | None = "own") -> SpecModel:
    if consent is None:
        return SpecModel()
    return SpecModel.model_validate(
        {"voice": {"engine": "chatterbox", "sample": "low.wav", "consent": consent}}
    )


def _echo(audio: Audio) -> list[Word]:
    return []


def _perfect_transcriber(script: ScriptModel) -> object:
    texts = [line.text for scene in script.scenes for line in scene.lines]
    calls = {"n": 0}

    def transcribe(audio: Audio) -> list[Word]:
        text = texts[calls["n"] % 3]
        calls["n"] += 1
        return [Word(text=w, start=0.0, end=0.1) for w in text.split()]

    return transcribe


@pytest.fixture
def demo(tmp_path: Path) -> DemoPaths:
    sf.write(tmp_path / "low.wav", tone(LOW, seconds=10.0), SR)
    sf.write(tmp_path / "high.wav", tone(HIGH, seconds=10.0), SR)
    return DemoPaths.at(tmp_path)


def _factory(spec: SpecModel, ref: Path) -> VoiceEngine:
    # The low reference reads at a good pace, the high one far too fast.
    if ref.stem == "low":
        return ToneEngine(LOW, seconds_per_word=0.35)
    return ToneEngine(HIGH, seconds_per_word=0.15)


def test_compare_generates_first_lines_with_each_reference(demo: DemoPaths) -> None:
    script = _script()
    refs = [demo.root / "low.wav", demo.root / "high.wav"]

    report = compare_references(
        demo,
        _spec(),
        script,
        refs,
        lines=3,
        engine_factory=_factory,
        transcribe_fn=_perfect_transcriber(script),  # type: ignore[arg-type]
    )

    for stem in ("low", "high"):
        folder = demo.voice / "compare" / stem
        assert sorted(p.name for p in folder.glob("*.wav")) == [
            "a__l1.wav",
            "b__l1.wav",
            "b__l2.wav",
        ]
    assert report.recommended.ref.name == "low.wav"
    low, high = report.scores
    assert low.similarity > high.similarity
    assert low.pace_ok_lines == 3
    assert high.pace_ok_lines == 0
    assert low.transcript_ok_lines == 3
    assert 130 <= low.wpm <= 210
    md = (demo.voice / "compare" / "compare.md").read_text(encoding="utf-8")
    assert "low.wav" in md and "high.wav" in md
    assert "Recommended" in md


def test_compare_refuses_without_consent_before_building_an_engine(demo: DemoPaths) -> None:
    built: list[Path] = []

    def factory(spec: SpecModel, ref: Path) -> VoiceEngine:
        built.append(ref)
        return ToneEngine(LOW, 0.35)

    with pytest.raises(ReelsmithError, match="consent"):
        compare_references(
            demo,
            _spec(consent=None),
            _script(),
            [demo.root / "low.wav"],
            engine_factory=factory,
            transcribe_fn=_echo,
        )
    assert built == []


def test_compare_refuses_a_missing_reference(demo: DemoPaths) -> None:
    with pytest.raises(ReelsmithError, match="not found"):
        compare_references(
            demo,
            _spec(),
            _script(),
            [demo.root / "nope.wav"],
            engine_factory=_factory,
            transcribe_fn=_echo,
        )


def test_compare_refuses_two_refs_with_the_same_name(demo: DemoPaths) -> None:
    (demo.root / "x").mkdir()
    sf.write(demo.root / "x" / "low.wav", tone(LOW), SR)
    with pytest.raises(ReelsmithError, match="same name"):
        compare_references(
            demo,
            _spec(),
            _script(),
            [demo.root / "low.wav", demo.root / "x" / "low.wav"],
            engine_factory=_factory,
            transcribe_fn=_echo,
        )


def test_compare_cli_uses_the_injected_factory(
    demo: DemoPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from reelsmith.cli import app
    from reelsmith.commands import voice as voice_cmd
    from reelsmith.models import save_model

    script = _script()
    save_model(demo.spec, _spec())
    save_model(demo.script, script)
    monkeypatch.setattr(voice_cmd, "compare_engine_factory", _factory)
    monkeypatch.setattr(voice_cmd, "compare_transcribe", _perfect_transcriber(script))

    result = CliRunner().invoke(
        app,
        ["voice", "compare", "--refs", "low.wav,high.wav", "--lines", "2", str(demo.root)],
    )

    assert result.exit_code == 0, result.output
    assert "[OK]" in result.output
    assert "low.wav" in result.output
    assert len(list((demo.voice / "compare" / "low").glob("*.wav"))) == 2


def test_compare_cli_without_consent_is_an_error(demo: DemoPaths) -> None:
    from reelsmith.cli import app, run
    from reelsmith.models import save_model

    save_model(demo.spec, _spec(consent=None))
    save_model(demo.script, _script())
    code = run(app, ["voice", "compare", "--refs", "low.wav", str(demo.root)])
    assert code == 1
    assert not (demo.voice / "compare").exists()


def test_compare_reads_say_where_a_phrase_has_one(demo: DemoPaths) -> None:
    script = ScriptModel(
        scenes=[
            ScriptScene(
                id="a",
                lines=[Line(id="l1", phrases=[Phrase(text="Run qa.", say="Run Q A.")])],
            )
        ]
    )
    engines: list[ToneEngine] = []

    def factory(spec: SpecModel, ref: Path) -> VoiceEngine:
        engine = ToneEngine(LOW, seconds_per_word=0.35)
        engines.append(engine)
        return engine

    def heard(audio: Audio) -> list[Word]:
        return [Word(text=w, start=0.0, end=0.1) for w in "run q a".split()]

    report = compare_references(
        demo,
        _spec(),
        script,
        [demo.root / "low.wav"],
        lines=1,
        engine_factory=factory,
        transcribe_fn=heard,
    )

    assert engines[0].texts == ["Run Q A."]
    assert report.recommended.transcript_ok_lines == 1
