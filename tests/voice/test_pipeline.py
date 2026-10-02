"""Tests for reelsmith.voice.pipeline, using a fake engine and transcriber."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from reelsmith.models import Line, Phrase, ScriptModel, ScriptScene, SpecModel, VoiceSettings
from reelsmith.paths import DemoPaths
from reelsmith.voice.base import Audio
from reelsmith.voice.pipeline import generate
from reelsmith.voice.transcribe import Word


class FakeEngine:
    """Returns audio of a given duration for each successive synthesize call."""

    def __init__(self, durations: list[float], sample_rate: int = 1000) -> None:
        self.durations = durations
        self.sample_rate = sample_rate
        self.name = "fake"
        self.calls: list[tuple[str, int]] = []

    def synthesize(self, text: str, seed: int) -> Audio:
        index = len(self.calls)
        self.calls.append((text, seed))
        duration = self.durations[min(index, len(self.durations) - 1)]
        samples = np.full(max(1, int(duration * self.sample_rate)), 0.5, dtype=np.float32)
        return Audio(samples=samples, sample_rate=self.sample_rate)


class _BoomEngine:
    # Same name as FakeEngine, since a line should only be skipped when the
    # engine, text, voice and speed are all unchanged from the last run.
    name = "fake"

    def synthesize(self, text: str, seed: int) -> Audio:
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
    assert (paths.voice / "s__l1.wav").exists()
    assert (paths.voice / "timings.json").exists()


def test_generate_retries_for_pace_then_for_transcript(tmp_path: Path) -> None:
    paths = DemoPaths.at(tmp_path)
    text = "one two three four five six seven eight nine ten"
    spec = _spec()
    script = _script({"l1": text})

    # seed 0: 10s of audio for 10 words is 60 wpm, too slow.
    # seed 1 (first pace retry): 3s is 200 wpm, inside the window.
    # the transcript check on that audio is made to fail once, then pass.
    engine = FakeEngine(durations=[10.0, 3.0, 3.0])
    incomplete = [Word(text="one", start=0.0, end=0.1)]
    complete = _words_for(text)
    transcriber = FakeTranscriber(results=[incomplete, complete])

    report = generate(paths, spec, script, None, engine=engine, transcribe_fn=transcriber)

    line = report.lines[0]
    assert line.attempts == 3
    assert line.pace_retried is True
    assert line.transcript_retried is True
    assert line.transcript_ok is True
    assert line.missing_words == []


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
    assert "l2" in by_line
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
