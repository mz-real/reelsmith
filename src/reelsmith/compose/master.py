"""Join the scene files into one master video with even loudness."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from reelsmith.compose.graph import SAMPLE_RATE, Encode, encode_args
from reelsmith.compose.layouts import num
from reelsmith.compose.transitions import XFADE, scene_starts, xfade_filters

DEFAULT_TRUE_PEAK = -1.5
FLOOR_DB = -90.0  # the steady bed under the whole master, so it is never digital silence


def loudnorm_filter(integrated: float = -16.0, true_peak: float = DEFAULT_TRUE_PEAK) -> str:
    return f"loudnorm=I={integrated:g}:TP={true_peak:g}:LRA=11"


LOUDNORM = loudnorm_filter()


def floor_source(total: float, sample_rate: int) -> str:
    """A constant, very quiet noise bed as long as the master (white, uniform)."""
    amplitude = 10 ** (FLOOR_DB / 20.0) * 3**0.5
    return (
        f"anoisesrc=c=white:r={sample_rate}:a={amplitude:.3e}:d={num(total)},"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo[floor]"
    )


def master_args(
    scene_files: Sequence[Path],
    durations: Sequence[float],
    encode: Encode,
    out: Path,
    fade: float = XFADE,
    transitions: Sequence[str] | None = None,
    loudness: float = -16.0,
    true_peak: float = DEFAULT_TRUE_PEAK,
    fade_durations: Sequence[float] | None = None,
) -> list[str]:
    """Cross fade the scenes and lay each scene's audio at its start time.

    durations are the timeline durations. Each scene file but the last is
    fade seconds longer, so the fades never cut into narration.
    """
    inputs: list[str] = []
    for path in scene_files:
        inputs += ["-i", str(path)]
    total = sum(durations)
    chains = xfade_filters(durations, fade, "vout", transitions, fade_durations)
    starts = scene_starts(durations)
    for k, start in enumerate(starts):
        chains.append(f"[{k}:a]adelay={round(start * 1000)}:all=1[sa{k}]")
    labels = "".join(f"[sa{k}]" for k in range(len(starts)))
    mix = f"amix=inputs={len(starts)}:normalize=0:duration=longest," if len(starts) > 1 else ""
    norm = loudnorm_filter(loudness, true_peak)
    chains.append(
        f"{labels}{mix}{norm},aresample={SAMPLE_RATE},atrim=duration={num(total)}[voiced]"
    )
    chains.append(floor_source(total, SAMPLE_RATE))
    chains.append("[voiced][floor]amix=inputs=2:normalize=0:duration=first[aout]")
    return [
        *inputs,
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        *encode_args(encode),
        "-t",
        num(total),
        str(out),
    ]
