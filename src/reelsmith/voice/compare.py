"""Read the same script lines with several references and recommend one.

Each reference gets the first few script lines. Every set is scored on
voice similarity (the cosine of mean MFCCs between the output and its
reference), pace (words a minute inside the comfortable window) and
whether the transcript matches the script. Each line is read as the
voice step would read it: say where a phrase has one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import numpy as np
import soundfile as sf

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.models import ScriptModel, SpecModel
from reelsmith.paths import DemoPaths
from reelsmith.voice.base import Audio, VoiceEngine
from reelsmith.voice.chatterbox_engine import ChatterboxEngine, check_consent
from reelsmith.voice.quality import pace_ok, transcript_matches, trim_tail, words_per_minute
from reelsmith.voice.reference import load_recording, resample
from reelsmith.voice.transcribe import Word, vocabulary_hints
from reelsmith.voice.transcribe import transcribe as default_transcribe

EngineFactory = Callable[[SpecModel, Path], VoiceEngine]
TranscribeFn = Callable[[Audio], list[Word]]

MFCC_RATE = 16000
_N_FFT = 512
_FRAME = 400  # 25 ms at 16 kHz
_HOP = 160  # 10 ms at 16 kHz
_N_MELS = 26
_N_COEFFS = 12


def clone_engine(spec: SpecModel, ref: Path) -> VoiceEngine:
    """The default factory: a Chatterbox engine that clones from ref."""
    return ChatterboxEngine(sample=ref, consent=spec.voice.consent)


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return np.asarray(2595.0 * np.log10(1.0 + hz / 700.0))


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return np.asarray(700.0 * (10 ** (mel / 2595.0) - 1.0))


def _mel_filterbank() -> np.ndarray:
    edges_mel = np.linspace(0.0, float(_hz_to_mel(np.array(MFCC_RATE / 2))), _N_MELS + 2)
    bins = np.floor((_N_FFT + 1) * _mel_to_hz(edges_mel) / MFCC_RATE).astype(int)
    bank = np.zeros((_N_MELS, _N_FFT // 2 + 1))
    for m in range(1, _N_MELS + 1):
        left, centre, right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(left, centre):
            bank[m - 1, k] = (k - left) / max(1, centre - left)
        for k in range(centre, right):
            bank[m - 1, k] = (right - k) / max(1, right - centre)
    return bank


def _dct_matrix() -> np.ndarray:
    n = np.arange(_N_MELS)
    k = np.arange(_N_COEFFS + 1)[:, None]
    matrix = np.cos(np.pi * k * (2 * n + 1) / (2 * _N_MELS)) * np.sqrt(2.0 / _N_MELS)
    matrix[0] /= np.sqrt(2.0)
    return np.asarray(matrix)


def mean_mfcc(audio: Audio) -> np.ndarray:
    """Mean of MFCC 1 to 12 over the voiced frames, in plain numpy.

    Coefficient 0 is loudness, so it is left out: two takes of the same
    voice should match even if one is louder.
    """
    samples = resample(audio.samples, audio.sample_rate, MFCC_RATE).astype(np.float64)
    if samples.size < _FRAME:
        samples = np.pad(samples, (0, _FRAME - samples.size))
    emphasised = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
    count = 1 + (emphasised.size - _FRAME) // _HOP
    index = np.arange(_FRAME)[None, :] + _HOP * np.arange(count)[:, None]
    frames = emphasised[index] * np.hamming(_FRAME)
    power = np.abs(np.fft.rfft(frames, n=_N_FFT)) ** 2 / _N_FFT
    energy = power.sum(axis=1)
    peak = float(np.max(energy))
    voiced = energy >= peak * 1e-3  # within 30 dB of the loudest frame
    mel = np.log(power[voiced] @ _mel_filterbank().T + 1e-10)
    coeffs = mel @ _dct_matrix().T
    return np.asarray(coeffs[:, 1:].mean(axis=0))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm == 0.0:
        return 0.0
    return float(np.dot(a, b) / norm)


@dataclass(frozen=True)
class RefScore:
    ref: Path
    similarity: float
    wpm: float
    pace_ok_lines: int
    transcript_ok_lines: int
    lines: int
    files: list[Path] = field(default_factory=list)

    @property
    def score(self) -> float:
        if self.lines == 0:
            return 0.0
        similarity = max(0.0, self.similarity)
        return (
            0.5 * similarity
            + 0.25 * self.pace_ok_lines / self.lines
            + 0.25 * self.transcript_ok_lines / self.lines
        )


@dataclass(frozen=True)
class CompareReport:
    scores: list[RefScore]
    recommended: RefScore
    markdown: Path


def read_audio(path: Path) -> Audio:
    """Read a wav or flac directly, anything else through ffmpeg."""
    try:
        data, rate = sf.read(path, dtype="float32", always_2d=True)
    except RuntimeError:
        return load_recording(path)
    return Audio(samples=np.asarray(data.mean(axis=1), dtype=np.float32), sample_rate=int(rate))


def _first_lines(script: ScriptModel, count: int) -> list[tuple[str, str, str]]:
    picked = [
        (scene.id, line.id, line.spoken_text) for scene in script.scenes for line in scene.lines
    ][:count]
    if not picked:
        raise ReelsmithError("script.yaml has no lines to read.", fix="Add lines to script.yaml")
    return picked


def _check_refs(spec: SpecModel, refs: list[Path]) -> None:
    if not refs:
        raise ReelsmithError("Give at least one reference.", fix="--refs a.wav,b.wav")
    stems: set[str] = set()
    for ref in refs:
        check_consent(spec.voice.consent, ref)
        if ref.stem in stems:
            raise ReelsmithError(
                f"Two references have the same name: {ref.stem}. Rename one of them."
            )
        stems.add(ref.stem)


def _write_wav(path: Path, audio: Audio) -> None:
    if path.exists():
        backup_existing(path)
    sf.write(path, audio.samples, audio.sample_rate)


def _score_ref(
    paths: DemoPaths,
    spec: SpecModel,
    ref: Path,
    lines: list[tuple[str, str, str]],
    engine_factory: EngineFactory,
    transcribe_fn: TranscribeFn,
    vocabulary: list[str],
) -> RefScore:
    engine = engine_factory(spec, ref)
    folder = paths.voice / "compare" / ref.stem
    folder.mkdir(parents=True, exist_ok=True)
    outputs: list[np.ndarray] = []
    rate = 0
    files: list[Path] = []
    pace_count = 0
    transcript_count = 0
    total_words = 0
    total_seconds = 0.0
    for scene_id, line_id, text in lines:
        audio = trim_tail(engine.synthesize(text, seed=0))
        seconds = audio.samples.size / audio.sample_rate
        if pace_ok(words_per_minute(text, seconds)):
            pace_count += 1
        if transcript_matches(text, transcribe_fn(audio), vocabulary)[0]:
            transcript_count += 1
        total_words += len(text.split())
        total_seconds += seconds
        out = folder / f"{scene_id}__{line_id}.wav"
        _write_wav(out, audio)
        files.append(out)
        rate = audio.sample_rate
        outputs.append(audio.samples)

    joined = Audio(samples=np.concatenate(outputs), sample_rate=rate)
    similarity = cosine(mean_mfcc(joined), mean_mfcc(read_audio(ref)))
    wpm = total_words / (total_seconds / 60.0) if total_seconds > 0 else 0.0
    return RefScore(
        ref=ref,
        similarity=similarity,
        wpm=wpm,
        pace_ok_lines=pace_count,
        transcript_ok_lines=transcript_count,
        lines=len(lines),
        files=files,
    )


def why(score: RefScore) -> str:
    return (
        f"similarity {score.similarity:.2f}, {score.wpm:.0f} wpm, "
        f"{score.pace_ok_lines}/{score.lines} lines in pace, "
        f"{score.transcript_ok_lines}/{score.lines} transcripts ok"
    )


def _markdown(scores: list[RefScore], best: RefScore) -> str:
    rows = [
        "# Voice compare",
        "",
        "| Reference | Similarity | Words a minute | Lines in pace | Transcripts ok | Score |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in scores:
        rows.append(
            f"| {s.ref.name} | {s.similarity:.2f} | {s.wpm:.0f} | {s.pace_ok_lines}/{s.lines}"
            f" | {s.transcript_ok_lines}/{s.lines} | {s.score:.2f} |"
        )
    rows += [
        "",
        f"Recommended: {best.ref.name}. It scored {best.score:.2f}: {why(best)}.",
        "",
        "Listen to the files in each folder before you choose. To use it, set",
        f"voice.sample to {best.ref.name} in spec.yaml.",
        "",
    ]
    return "\n".join(rows)


def compare_references(
    paths: DemoPaths,
    spec: SpecModel,
    script: ScriptModel,
    refs: list[Path],
    lines: int = 3,
    *,
    engine_factory: EngineFactory = clone_engine,
    transcribe_fn: TranscribeFn = default_transcribe,
) -> CompareReport:
    """Read the first `lines` script lines with each reference and score them.

    Consent and every reference file are checked before any engine is
    built, whatever factory is passed in.
    """
    _check_refs(spec, refs)
    picked = _first_lines(script, lines)
    hints = vocabulary_hints(spec, script)
    if transcribe_fn is default_transcribe:
        transcribe_fn = partial(default_transcribe, vocabulary=hints)
    scores = [
        _score_ref(paths, spec, ref, picked, engine_factory, transcribe_fn, hints) for ref in refs
    ]
    best = max(scores, key=lambda s: s.score)
    markdown = paths.voice / "compare" / "compare.md"
    if markdown.exists():
        backup_existing(markdown)
    markdown.write_text(_markdown(scores, best), encoding="utf-8")
    return CompareReport(scores=scores, recommended=best, markdown=markdown)
