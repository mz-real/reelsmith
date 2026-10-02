"""Tests for reelsmith.voice.pipeline, using a fake engine and transcriber."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reelsmith.compose.inputs import load_project
from reelsmith.models import (
    Line,
    Phrase,
    SceneSpec,
    ScriptModel,
    ScriptScene,
    SpecModel,
    VoiceSettings,
    save_model,
)
from reelsmith.paths import DemoPaths
from reelsmith.voice.base import Audio
from reelsmith.voice.pipeline import TranscribeFn, generate
from reelsmith.voice.quality import pace_ok
from reelsmith.voice.transcribe import Word


class FakeEngine:
    """Returns audio of a given duration for each successive synthesize call."""

    def __init__(self, durations: list[float], sample_rate: int = 1000) -> None:
        self.durations = durations
        self.sample_rate = sample_rate
        self.name = "fake"
        self.calls: list[tuple[str, int, float | None]] = []

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        index = len(self.calls)
        self.calls.append((text, seed, speed))
        duration = self.durations[min(index, len(self.durations) - 1)]
        samples = np.full(max(1, int(duration * self.sample_rate)), 0.5, dtype=np.float32)
        return Audio(samples=samples, sample_rate=self.sample_rate)


class ScalingFakeEngine:
    """A fake engine whose measured words a minute scales with speed.

    Doubling speed halves the audio's duration and so doubles the words a
    minute that a first-to-last-word measurement would find, the same
    direction a real engine moves in.
    """

    def __init__(self, text: str, wpm_at_speed_one: float, sample_rate: int = 1000) -> None:
        self.text = text
        self.wpm_at_speed_one = wpm_at_speed_one
        self.sample_rate = sample_rate
        self.name = "fake"
        self.calls: list[tuple[str, int, float | None]] = []

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        used_speed = speed if speed is not None else 1.0
        self.calls.append((text, seed, speed))
        wpm = self.wpm_at_speed_one * used_speed
        seconds = (len(text.split()) / wpm) * 60.0
        samples = np.full(max(1, int(seconds * self.sample_rate)), 0.5, dtype=np.float32)
        return Audio(samples=samples, sample_rate=self.sample_rate)


def _matching_transcriber(text: str) -> TranscribeFn:
    """A fake transcriber whose word timestamps span the whole given audio.

    Used with ScalingFakeEngine so that a wpm measurement taken from word
    timestamps (first word's start to last word's end) matches the pace
    the engine was asked to read at, whatever that attempt's duration was.
    """
    tokens = text.split()

    def transcribe(audio: Audio) -> list[Word]:
        duration = audio.samples.size / audio.sample_rate
        step = duration / len(tokens)
        return [Word(text=t, start=i * step, end=(i + 1) * step) for i, t in enumerate(tokens)]

    return transcribe


class _BoomEngine:
    # Same name as FakeEngine, since a line should only be skipped when the
    # engine, text, voice and speed are all unchanged from the last run.
    name = "fake"

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        raise AssertionError("should not resynthesize a skipped line")


class FakeTranscriber:
    """Returns a preset list of words for each successive call."""

    def __init__(self, results: list[list[Word]]) -> None:
        self.results = results
        self.calls = 0

    def __call__(self, audio: Audio) -> list[Word]:
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        return self.results[index]


def _spec(speed: float = 1.0) -> SpecModel:
    return SpecModel(voice=VoiceSettings(engine="kokoro", kokoro_voice="af_heart", speed=speed))


def _script(lines: dict[str, str]) -> ScriptModel:
    return ScriptModel(
        scenes=[
            ScriptScene(
                id="s",
                caption="c",
                lines=[
                    Line(id=line_id, phrases=[Phrase(text=text)]) for line_id, text in lines.items()
                ],
            )
        ]
    )


def _words_for(text: str, start: float = 0.0, step: float = 0.1) -> list[Word]:
    words = []
    for i, token in enumerate(text.split()):
        t = start + i * step
        words.append(Word(text=token, start=t, end=t + step * 0.9))
    return words


def test_generate_writes_wav_and_timings(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    spec = _spec()
    script = _script({"l1": text})

    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for(text)])

    report = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    assert len(report.lines) == 1
    line = report.lines[0]
    assert line.scene == "s"
    assert line.line == "l1"
    assert line.file == "s__l1.wav"
    assert line.attempts == 1
    assert line.transcript_ok is True
    assert line.skipped is False
    assert line.pace_checked is False  # "hello world" is four words or fewer
    assert (paths.voice / "s__l1.wav").exists()
    timings_path = paths.voice / "timings.json"
    assert timings_path.exists()
    payload = json.loads(timings_path.read_text(encoding="utf-8"))
    assert payload["lines"][0]["pace_checked"] is False


def test_generate_corrects_pace_by_scaling_speed_within_two_attempts(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "one two three four five six seven eight nine ten"  # ten words, pace is checked
    spec = _spec()
    script = _script({"l1": text})

    # At speed 1.0 this fake engine reads at 220 wpm, too fast for the 130
    # to 210 window. Scaling speed directly towards the 175 wpm target,
    # instead of jittering it by a few percent, lands inside the window
    # on the very first retry.
    engine = ScalingFakeEngine(text, wpm_at_speed_one=220.0)
    transcriber = _matching_transcriber(text)

    report = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    line = report.lines[0]
    assert line.pace_checked is True
    assert line.pace_retried is True
    assert line.attempts <= 2
    assert pace_ok(line.wpm)
    assert line.transcript_ok is True


def test_generate_skips_the_pace_check_on_a_short_line(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "go"  # one word, far outside any pace window by duration alone
    spec = _spec()
    script = _script({"l1": text})

    engine = FakeEngine(durations=[5.0])  # 1 word in 5 seconds is 12 wpm
    transcriber = FakeTranscriber(results=[_words_for(text)])

    report = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    line = report.lines[0]
    assert line.pace_checked is False
    assert line.pace_retried is False
    assert line.attempts == 1


def test_generate_gives_up_after_three_retries_but_reports_missing_words(
    tmp_path: Path,
) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    spec = _spec()
    script = _script({"l1": text})

    engine = FakeEngine(durations=[0.8])
    always_incomplete = [Word(text="hello", start=0.0, end=0.1)]
    transcriber = FakeTranscriber(results=[always_incomplete])

    report = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    line = report.lines[0]
    assert line.attempts == 4  # one try plus three retries
    assert line.transcript_ok is False
    assert line.missing_words == ["world"]


def test_generate_skips_a_line_whose_hash_and_wav_already_match(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    spec = _spec()
    script = _script({"l1": text})

    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for(text)])
    first = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)
    assert first.lines[0].skipped is False

    second = generate(paths, spec, script, None, engine=_BoomEngine(), transcribe_fn=transcriber)

    assert second.lines[0].skipped is True
    assert second.lines[0].hash == first.lines[0].hash


def test_generate_reruns_a_line_whose_text_changed(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    spec = _spec()

    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for("hello world")])
    first = generate(
        paths, spec, _script({"l1": "hello world"}), None, engine=engine, transcribe_fn=transcriber
    )
    assert first.lines[0].skipped is False

    engine2 = FakeEngine(durations=[0.8])
    transcriber2 = FakeTranscriber(results=[_words_for("goodbye now")])
    second = generate(
        paths,
        spec,
        _script({"l1": "goodbye now"}),
        None,
        engine=engine2,
        transcribe_fn=transcriber2,
    )

    assert second.lines[0].skipped is False
    assert second.lines[0].hash != first.lines[0].hash
    assert len(engine2.calls) == 1


def test_generate_with_only_filters_lines_and_leaves_others_untouched(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    spec = _spec()
    script = _script({"l1": "hello world", "l2": "goodbye now"})

    engine = FakeEngine(durations=[0.8, 0.8])
    transcriber = FakeTranscriber(results=[_words_for("hello world"), _words_for("goodbye now")])
    first = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)
    assert {line.line for line in first.lines} == {"l1", "l2"}

    only_engine = FakeEngine(durations=[0.8])
    only_transcriber = FakeTranscriber(results=[_words_for("hello world")])

    second = generate(
        paths,
        spec,
        script,
        {"s/l1"},
        engine=only_engine,
        transcribe_fn=only_transcriber,
    )

    by_line = {line.line: line for line in second.lines}
    assert by_line["l1"].skipped is True
    assert by_line["l1"].left_out is False
    assert "l2" in by_line
    assert by_line["l2"].left_out is True
    assert len(only_engine.calls) == 0


def test_generate_backs_up_an_existing_wav_before_overwriting(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    spec = _spec()

    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for("hello world")])
    generate(
        paths, spec, _script({"l1": "hello world"}), None, engine=engine, transcribe_fn=transcriber
    )

    engine2 = FakeEngine(durations=[0.8])
    transcriber2 = FakeTranscriber(results=[_words_for("goodbye now")])
    generate(
        paths,
        spec,
        _script({"l1": "goodbye now"}),
        None,
        engine=engine2,
        transcribe_fn=transcriber2,
    )

    backups = list(paths.voice.glob("s__l1.wav.bak-*"))
    assert len(backups) == 1


def test_generate_reruns_a_line_whose_engine_changed(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    spec = _spec()
    script = _script({"l1": text})

    engine = FakeEngine(durations=[0.8])
    engine.name = "kokoro"
    transcriber = FakeTranscriber(results=[_words_for(text)])
    first = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    engine2 = FakeEngine(durations=[0.8])
    engine2.name = "chatterbox"
    transcriber2 = FakeTranscriber(results=[_words_for(text)])
    second = generate(paths, spec, script, None, engine=engine2, transcribe_fn=transcriber2)

    assert second.lines[0].hash != first.lines[0].hash
    assert second.lines[0].skipped is False
    assert len(engine2.calls) == 1


def test_generate_reruns_a_line_whose_speed_changed(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    script = _script({"l1": text})

    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for(text)])
    first = generate(
        paths, _spec(speed=1.0), script, None, engine=engine, transcribe_fn=transcriber
    )

    engine2 = FakeEngine(durations=[0.8])
    transcriber2 = FakeTranscriber(results=[_words_for(text)])
    second = generate(
        paths, _spec(speed=1.2), script, None, engine=engine2, transcribe_fn=transcriber2
    )

    assert second.lines[0].hash != first.lines[0].hash
    assert second.lines[0].skipped is False
    assert len(engine2.calls) == 1


def test_generate_reruns_a_line_when_the_cloned_voice_changed(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "hello world"
    spec = _spec()
    script = _script({"l1": text})

    first = FakeEngine(durations=[0.8])
    first.voice_id = "me.wav:aaa"  # type: ignore[attr-defined]
    report = generate(
        paths, spec, script, None, engine=first, transcribe_fn=FakeTranscriber([_words_for(text)])
    )
    assert report.voice == "me.wav:aaa"

    second = FakeEngine(durations=[0.8])
    second.voice_id = "me.wav:bbb"  # type: ignore[attr-defined]
    report = generate(
        paths, spec, script, None, engine=second, transcribe_fn=FakeTranscriber([_words_for(text)])
    )

    assert report.lines[0].skipped is False
    assert len(second.calls) == 1


def _say_script(text: str, say: str | None) -> ScriptModel:
    return ScriptModel(
        scenes=[ScriptScene(id="s", lines=[Line(id="l1", phrases=[Phrase(text=text, say=say)])])]
    )


def test_generate_reads_say_and_checks_the_transcript_against_it(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    engine = FakeEngine(durations=[0.8])
    transcriber = FakeTranscriber(results=[_words_for("run reelsmith q a")])

    report = generate(
        paths,
        _spec(),
        _say_script("Run reelsmith qa.", "Run reelsmith Q A."),
        None,
        engine=engine,
        transcribe_fn=transcriber,
    )

    assert engine.calls[0][0] == "Run reelsmith Q A."
    assert report.lines[0].transcript_ok is True
    assert report.lines[0].attempts == 1


def test_the_line_hash_includes_say(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    transcriber = FakeTranscriber(results=[_words_for("run reelsmith q a")])
    first = generate(
        paths,
        _spec(),
        _say_script("Run reelsmith qa.", None),
        None,
        engine=FakeEngine(durations=[0.8]),
        transcribe_fn=transcriber,
    )

    second = generate(
        paths,
        _spec(),
        _say_script("Run reelsmith qa.", "Run reelsmith Q A."),
        None,
        engine=FakeEngine(durations=[0.8]),
        transcribe_fn=transcriber,
    )

    assert second.lines[0].skipped is False
    assert second.lines[0].hash != first.lines[0].hash


def test_a_line_without_say_keeps_its_old_hash() -> None:
    import hashlib

    from reelsmith.voice.pipeline import _line_hash

    line = Line(id="l1", phrases=[Phrase(text="hello world")])
    old = hashlib.sha256(b"hello world|fake|af_heart|1.0").hexdigest()

    assert _line_hash(line, "fake", "af_heart", 1.0) == old


def test_generate_passes_the_vocabulary_hints_to_the_default_transcriber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reelsmith.voice import pipeline

    seen: list[list[str]] = []

    def fake_transcribe(audio: Audio, vocabulary: list[str] | None = None) -> list[Word]:
        seen.append(list(vocabulary or []))
        return _words_for("made with realsmith")

    monkeypatch.setattr(pipeline, "default_transcribe", fake_transcribe)
    spec = SpecModel(voice=VoiceSettings(vocabulary=["reelsmith"]))

    report = generate(
        DemoPaths.at(tmp_path),
        spec,
        _script({"l1": "Made with reelsmith."}),
        None,
        engine=FakeEngine(durations=[0.8]),
    )

    assert seen[0] == ["reelsmith"]
    assert report.lines[0].transcript_ok is True


def test_generate_drops_timings_for_lines_removed_from_script(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    spec = _spec()
    engine = FakeEngine(durations=[0.8, 0.8, 0.8])
    transcriber = FakeTranscriber(
        results=[_words_for("one"), _words_for("two a"), _words_for("two b")]
    )
    script_l3 = ScriptModel(
        scenes=[
            ScriptScene(
                id="demo",
                caption="c",
                lines=[Line(id="l3", phrases=[Phrase(text="one")])],
            )
        ]
    )
    generate(paths, spec, script_l3, None, engine=engine, transcribe_fn=transcriber)
    assert (paths.voice / "demo__l3.wav").exists()

    script_split = ScriptModel(
        scenes=[
            ScriptScene(
                id="demo",
                caption="c",
                lines=[
                    Line(id="l3a", phrases=[Phrase(text="two a")]),
                    Line(id="l3b", phrases=[Phrase(text="two b")]),
                ],
            )
        ]
    )
    only_engine = FakeEngine(durations=[0.8, 0.8])
    only_transcriber = FakeTranscriber(results=[_words_for("two a"), _words_for("two b")])
    report = generate(
        paths,
        spec,
        script_split,
        {"demo/l3a", "demo/l3b"},
        engine=only_engine,
        transcribe_fn=only_transcriber,
    )

    assert report.dropped_stale == 1
    payload = json.loads((paths.voice / "timings.json").read_text(encoding="utf-8"))
    keys = {(row["scene"], row["line"]) for row in payload["lines"]}
    assert ("demo", "l3") not in keys
    assert ("demo", "l3a") in keys
    assert ("demo", "l3b") in keys
    assert not (paths.voice / "demo__l3.wav").exists()
    assert list(paths.voice.glob("demo__l3.wav.bak-*"))

    compose_spec = SpecModel(scenes=[SceneSpec(id="demo", layout="slide", slide="demo")])
    save_model(paths.spec, compose_spec)
    save_model(paths.script, script_split)
    load_project(paths)
