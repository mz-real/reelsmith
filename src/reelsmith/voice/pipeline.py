"""Turns script lines into narration audio, with quality checks and retries.

Per line: synthesize, trim the tail, transcribe, check the pace, check the
transcript, then align the phrases. A line whose text, voice and speed
have not changed, and whose wav file already exists, is skipped.

Pace is measured from the transcribed words rather than the file's
length (see speaking_seconds in quality.py), so the line is transcribed
before its pace is judged. A pace retry scales speed by how far off
target the measured words-a-minute was, rather than jittering it by a
fixed amount: a line that reads at 220 wpm needs a real correction, not
a plus-or-minus three percent nudge. Lines with four words or fewer have
too little speech for wpm to mean anything, so their pace is not
checked at all.

A phrase may have say as well as text. The captions show text; the
voice reads say, and the transcript is checked against say. The speech
model gets the vocabulary hints from spec.yaml and the script (see
voice/transcribe.py), the same hints QA uses.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path

import soundfile as sf

from reelsmith.fsutil import backup_existing
from reelsmith.models import Line, ScriptModel, SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.voice.align import phrase_bounds
from reelsmith.voice.base import Audio, VoiceEngine, get_engine
from reelsmith.voice.quality import (
    pace_ok,
    speaking_seconds,
    transcript_matches,
    trim_tail,
    words_per_minute,
)
from reelsmith.voice.transcribe import Word, vocabulary_hints
from reelsmith.voice.transcribe import transcribe as default_transcribe

_MAX_RETRIES = 3
_TARGET_WPM = 175.0
_MIN_SPEED_FACTOR = 0.75
_MAX_SPEED_FACTOR = 1.25
_SHORT_LINE_MAX_WORDS = 4
_WORD_RETRY_JITTER = 0.02

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
    pace_checked: bool = True
    left_out: bool = False
    warnings: list[str] = field(default_factory=list)

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
            "pace_checked": self.pace_checked,
        }


@dataclass(frozen=True)
class VoiceReport:
    engine: str
    voice: str
    lines: list[LineReport]
    dropped_stale: int = 0
    rerecorded_on_request: int = 0


def _applicable_pronunciations(text: str, pronounce: Mapping[str, str]) -> list[tuple[str, str]]:
    """The pronounce entries (lower cased word, phonemes) whose word is in text."""
    applicable = [
        (word.lower(), phonemes)
        for word, phonemes in pronounce.items()
        if re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)
    ]
    return sorted(applicable)


def _line_hash(
    line: Line,
    engine_name: str,
    voice: str,
    speed: float,
    pronounce: Mapping[str, str] | None = None,
) -> str:
    # The engine name is part of the hash so switching engines, for example
    # from Kokoro to Chatterbox, regenerates every line instead of being
    # mistaken for a line that has not changed. What the voice reads is
    # added only when a phrase has say, so lines without it keep the hash
    # they had before say existed and are not voiced again. Only the
    # pronounce entries that actually apply to this line are hashed, so
    # changing an unrelated word in voice.pronounce does not regenerate it.
    raw = f"{line.text}|{engine_name}|{voice}|{speed}"
    if line.has_say:
        raw += f"|say={line.spoken_text}"
    applicable = _applicable_pronunciations(line.spoken_text, pronounce or {})
    if applicable:
        raw += "|pronounce=" + ",".join(f"{word}={phonemes}" for word, phonemes in applicable)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _duration(audio: Audio) -> float:
    if audio.sample_rate <= 0:
        return 0.0
    return audio.samples.size / audio.sample_rate


def _synthesize_and_trim(
    engine: VoiceEngine, text: str, seed: int, speed: float | None = None
) -> Audio:
    audio = engine.synthesize(text, seed, speed)
    return trim_tail(audio)


def _pace_corrected_speed(current_speed: float, wpm: float) -> float:
    """Scale speed by how far off target the measured pace was.

    A flat jitter cannot reliably fix a line that is well outside the
    comfortable window: af_heart at speed 1.0 can read 200 to 235 words a
    minute on short lines, and a plus-or-minus three percent nudge barely
    moves that. Scaling directly towards the target wpm converges in far
    fewer attempts. The correction is clamped to three quarters to five
    quarters of the current speed per attempt, so one bad pace reading
    cannot send the next attempt to an unusable speed.
    """
    if wpm <= 0:
        return current_speed
    factor = min(_MAX_SPEED_FACTOR, max(_MIN_SPEED_FACTOR, _TARGET_WPM / wpm))
    return current_speed * factor


def _with_tiny_jitter(speed: float, attempt: int) -> float:
    """A small speed nudge so a dropped word retry is not identical audio.

    Pace has already been corrected (or skipped as unreliable) by the
    time this runs, so the nudge is kept small: enough to get a different
    take from an engine with no real seed, not enough to push a line back
    out of the comfortable pace window.
    """
    sign = 1 if attempt % 2 == 1 else -1
    step = (attempt + 1) // 2
    return speed * (1 + sign * _WORD_RETRY_JITTER * step)


def _generate_line_audio(
    engine: VoiceEngine,
    transcribe_fn: TranscribeFn,
    text: str,
    base_speed: float,
    vocabulary: Sequence[str] = (),
) -> tuple[Audio, float, bool, bool, list[str], list[Word], int, bool, bool]:
    """Synthesize one line, retrying for pace and then for dropped words.

    Returns the final audio, its words per minute, whether pace was
    checked at all, whether the transcript matched, the missing words if
    not, the transcribed words used for alignment, the total number of
    synthesis attempts, and whether a retry was needed for pace or for
    the transcript.
    """
    pace_checked = len(text.split()) > _SHORT_LINE_MAX_WORDS

    attempts = 1
    speed = base_speed
    audio = _synthesize_and_trim(engine, text, seed=0, speed=speed)
    words = transcribe_fn(audio)
    wpm = words_per_minute(text, speaking_seconds(words, _duration(audio)))

    pace_retried = False
    if pace_checked:
        for _ in range(_MAX_RETRIES):
            if pace_ok(wpm):
                break
            pace_retried = True
            attempts += 1
            speed = _pace_corrected_speed(speed, wpm)
            audio = _synthesize_and_trim(engine, text, seed=0, speed=speed)
            words = transcribe_fn(audio)
            wpm = words_per_minute(text, speaking_seconds(words, _duration(audio)))

    transcript_ok, missing = transcript_matches(text, words, vocabulary)

    transcript_retried = False
    for retry in range(1, _MAX_RETRIES + 1):
        if transcript_ok:
            break
        transcript_retried = True
        attempts += 1
        retry_speed = _with_tiny_jitter(speed, retry)
        audio = _synthesize_and_trim(engine, text, seed=retry, speed=retry_speed)
        words = transcribe_fn(audio)
        if pace_checked:
            wpm = words_per_minute(text, speaking_seconds(words, _duration(audio)))
        transcript_ok, missing = transcript_matches(text, words, vocabulary)

    return (
        audio,
        wpm,
        pace_checked,
        transcript_ok,
        missing,
        words,
        attempts,
        pace_retried,
        transcript_retried,
    )


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
            pace_checked=bool(line_raw.get("pace_checked", True)),
        )
        existing[f"{report.scene}/{report.line}"] = report
    return existing


def _script_line_keys(script: ScriptModel) -> set[str]:
    return {f"{scene.id}/{line.id}" for scene in script.scenes for line in scene.lines}


def _drop_stale_lines(voice_dir: Path, existing: dict[str, LineReport], script: ScriptModel) -> int:
    """Remove timings entries (and back up wavs) for lines no longer in script.yaml."""
    valid = _script_line_keys(script)
    dropped = 0
    for key, prior in list(existing.items()):
        if key in valid:
            continue
        dropped += 1
        wav_path = voice_dir / prior.file
        if wav_path.is_file():
            backup_existing(wav_path)
        del existing[key]
    return dropped


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
    transcribe_fn: TranscribeFn | None = None,
) -> VoiceReport:
    """Generate narration audio for every line, or just those in only.

    only holds "scene/line" keys. When given, lines outside it are left as
    they are: kept from any previous run, otherwise skipped entirely.
    Without a transcribe_fn, faster-whisper is used with the vocabulary
    hints.
    """
    hints = vocabulary_hints(spec, script)
    active_transcribe: TranscribeFn = transcribe_fn or partial(default_transcribe, vocabulary=hints)
    active_engine = engine if engine is not None else get_engine(spec, root=paths.root)
    # A cloned voice is identified by its sample, so a new sample regenerates.
    voice_id = str(getattr(active_engine, "voice_id", "") or spec.voice.kokoro_voice)
    paths.voice.mkdir(parents=True, exist_ok=True)
    timings_path = paths.voice / "timings.json"
    existing = _load_existing(timings_path)
    dropped_stale = _drop_stale_lines(paths.voice, existing, script)

    line_reports: list[LineReport] = []
    rerecorded_on_request = 0
    for scene in script.scenes:
        for line in scene.lines:
            key = f"{scene.id}/{line.id}"
            if only is not None and key not in only:
                prior = existing.get(key)
                if prior is not None:
                    line_reports.append(replace(prior, left_out=True))
                continue

            text = line.spoken_text
            # Only Kokoro ever reads voice.pronounce, so only its lines are
            # regenerated when the map changes.
            engine_pronounce = spec.voice.pronounce if active_engine.name == "kokoro" else None
            line_hash = _line_hash(
                line, active_engine.name, voice_id, spec.voice.speed, engine_pronounce
            )
            wav_path = paths.voice / f"{scene.id}__{line.id}.wav"
            forced = only is not None and key in only

            prior = existing.get(key)
            if not forced and prior is not None and prior.hash == line_hash and wav_path.exists():
                line_reports.append(replace(prior, skipped=True))
                continue
            if forced:
                rerecorded_on_request += 1

            (
                audio,
                wpm,
                pace_checked,
                transcript_ok,
                missing,
                words,
                attempts,
                pace_retried,
                transcript_retried,
            ) = _generate_line_audio(
                active_engine, active_transcribe, text, spec.voice.speed, hints
            )

            bounds = phrase_bounds([phrase.spoken for phrase in line.phrases], words, audio)
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
                    pace_checked=pace_checked,
                    warnings=[audio.warning] if audio.warning else [],
                )
            )

    report = VoiceReport(
        engine=active_engine.name,
        voice=voice_id,
        lines=line_reports,
        dropped_stale=dropped_stale,
        rerecorded_on_request=rerecorded_on_request,
    )
    _write_timings(timings_path, report)
    return report


__all__ = [
    "LineReport",
    "PhraseTiming",
    "VoiceReport",
    "generate",
]
