"""Turns script lines into narration audio, with quality checks and retries.

Per line: synthesize, trim the tail, check the pace, check the transcript,
then align the phrases. A line whose text, voice and speed have not
changed, and whose wav file already exists, is skipped.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import soundfile as sf

from reelsmith.fsutil import backup_existing
from reelsmith.models import ScriptModel, SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.voice.align import phrase_bounds
from reelsmith.voice.base import Audio, VoiceEngine, get_engine
from reelsmith.voice.quality import pace_ok, transcript_matches, trim_tail, words_per_minute
from reelsmith.voice.transcribe import Word
from reelsmith.voice.transcribe import transcribe as default_transcribe

_MAX_RETRIES = 3

TranscribeFn = Callable[[Audio], list[Word]]


@dataclass(frozen=True)
class PhraseTiming:
    index: int
    start: float
    end: float


@dataclass(frozen=True)
class LineReport:
    scene: str
    line: str
    file: str
    duration: float
    hash: str
    phrases: list[PhraseTiming]
    wpm: float
    transcript_ok: bool
    attempts: int
    skipped: bool = False
    missing_words: list[str] = field(default_factory=list)
    pace_retried: bool = False
    transcript_retried: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "scene": self.scene,
            "line": self.line,
            "file": self.file,
            "duration": self.duration,
            "hash": self.hash,
            "phrases": [{"index": p.index, "start": p.start, "end": p.end} for p in self.phrases],
            "wpm": self.wpm,
            "transcript_ok": self.transcript_ok,
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class VoiceReport:
    engine: str
    voice: str
    lines: list[LineReport]


def _line_hash(text: str, engine_name: str, voice: str, speed: float) -> str:
    # The engine name is part of the hash so switching engines, for example
    # from Kokoro to Chatterbox, regenerates every line instead of being
    # mistaken for a line that has not changed.
    raw = f"{text}|{engine_name}|{voice}|{speed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _duration(audio: Audio) -> float:
    if audio.sample_rate <= 0:
        return 0.0
    return audio.samples.size / audio.sample_rate


def _synthesize_and_trim(engine: VoiceEngine, text: str, seed: int) -> Audio:
    audio = engine.synthesize(text, seed)
    return trim_tail(audio)


def _generate_line_audio(
    engine: VoiceEngine, transcribe_fn: TranscribeFn, text: str
) -> tuple[Audio, float, bool, list[str], list[Word], int, bool, bool]:
    """Synthesize one line, retrying for pace and then for dropped words.

    Returns the final audio, its words per minute, whether the transcript
    matched, the missing words if not, the transcribed words used for
    alignment, the total number of synthesis attempts, and whether a retry
    was needed for pace or for the transcript.
    """
    attempts = 1
    audio = _synthesize_and_trim(engine, text, seed=0)
    wpm = words_per_minute(text, _duration(audio))

    pace_retried = False
    for retry in range(1, _MAX_RETRIES + 1):
        if pace_ok(wpm):
            break
        pace_retried = True
        attempts += 1
        audio = _synthesize_and_trim(engine, text, seed=retry)
        wpm = words_per_minute(text, _duration(audio))

    words = transcribe_fn(audio)
    transcript_ok, missing = transcript_matches(text, words)

    transcript_retried = False
    for retry in range(1, _MAX_RETRIES + 1):
        if transcript_ok:
            break
        transcript_retried = True
        attempts += 1
        audio = _synthesize_and_trim(engine, text, seed=_MAX_RETRIES + retry)
        wpm = words_per_minute(text, _duration(audio))
        words = transcribe_fn(audio)
        transcript_ok, missing = transcript_matches(text, words)

    return audio, wpm, transcript_ok, missing, words, attempts, pace_retried, transcript_retried


def _load_existing(timings_path: Path) -> dict[str, LineReport]:
    if not timings_path.exists():
        return {}
    try:
        data = json.loads(timings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    existing: dict[str, LineReport] = {}
    for line_raw in data.get("lines", []):
        phrases = [
            PhraseTiming(index=p["index"], start=p["start"], end=p["end"])
            for p in line_raw.get("phrases", [])
        ]
        report = LineReport(
            scene=line_raw["scene"],
            line=line_raw["line"],
            file=line_raw["file"],
            duration=line_raw["duration"],
            hash=line_raw["hash"],
            phrases=phrases,
            wpm=line_raw["wpm"],
            transcript_ok=line_raw["transcript_ok"],
            attempts=line_raw["attempts"],
        )
        existing[f"{report.scene}/{report.line}"] = report
    return existing


def _write_timings(timings_path: Path, report: VoiceReport) -> None:
    if timings_path.exists():
        backup_existing(timings_path)
    payload = {
        "engine": report.engine,
        "voice": report.voice,
        "lines": [line.to_json() for line in report.lines],
    }
    timings_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def generate(
    paths: DemoPaths,
    spec: SpecModel,
    script: ScriptModel,
    only: set[str] | None = None,
    *,
    engine: VoiceEngine | None = None,
    transcribe_fn: TranscribeFn = default_transcribe,
) -> VoiceReport:
    """Generate narration audio for every line, or just those in only.

    only holds "scene/line" keys. When given, lines outside it are left as
    they are: kept from any previous run, otherwise skipped entirely.
    """
    active_engine = engine if engine is not None else get_engine(spec)
    paths.voice.mkdir(parents=True, exist_ok=True)
    timings_path = paths.voice / "timings.json"
    existing = _load_existing(timings_path)

    line_reports: list[LineReport] = []
    for scene in script.scenes:
        for line in scene.lines:
            key = f"{scene.id}/{line.id}"
            if only is not None and key not in only:
                prior = existing.get(key)
                if prior is not None:
                    line_reports.append(prior)
                continue

            text = line.text
            line_hash = _line_hash(
                text, active_engine.name, spec.voice.kokoro_voice, spec.voice.speed
            )
            wav_path = paths.voice / f"{scene.id}__{line.id}.wav"

            prior = existing.get(key)
            if prior is not None and prior.hash == line_hash and wav_path.exists():
                line_reports.append(replace(prior, skipped=True))
                continue

            (
                audio,
                wpm,
                transcript_ok,
                missing,
                words,
                attempts,
                pace_retried,
                transcript_retried,
            ) = _generate_line_audio(active_engine, transcribe_fn, text)

            bounds = phrase_bounds([phrase.text for phrase in line.phrases], words, audio)
            phrase_timings = [
                PhraseTiming(index=i, start=start, end=end) for i, (start, end) in enumerate(bounds)
            ]

            if wav_path.exists():
                backup_existing(wav_path)
            sf.write(wav_path, audio.samples, audio.sample_rate)

            line_reports.append(
                LineReport(
                    scene=scene.id,
                    line=line.id,
                    file=wav_path.name,
                    duration=_duration(audio),
                    hash=line_hash,
                    phrases=phrase_timings,
                    wpm=wpm,
                    transcript_ok=transcript_ok,
                    attempts=attempts,
                    skipped=False,
                    missing_words=missing,
                    pace_retried=pace_retried,
                    transcript_retried=transcript_retried,
                )
            )

    report = VoiceReport(
        engine=active_engine.name, voice=spec.voice.kokoro_voice, lines=line_reports
    )
    _write_timings(timings_path, report)
    return report


__all__ = [
    "LineReport",
    "PhraseTiming",
    "VoiceReport",
    "generate",
]
