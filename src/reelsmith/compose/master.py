"""Join the scene files into one master video with even loudness."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from reelsmith.compose.graph import SAMPLE_RATE, Encode, encode_args
from reelsmith.compose.layouts import num
from reelsmith.compose.transitions import XFADE, scene_starts, xfade_filters

LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def master_args(
    scene_files: Sequence[Path],
    durations: Sequence[float],
    encode: Encode,
    out: Path,
    fade: float = XFADE,
    transitions: Sequence[str] | None = None,
) -> list[str]:
    """Cross fade the scenes and lay each scene's audio at its start time.

    durations are the timeline durations. Each scene file but the last is
    fade seconds longer, so the fades never cut into narration.
    """
    inputs: list[str] = []
    for path in scene_files:
        inputs += ["-i", str(path)]
    total = sum(durations)
    chains = xfade_filters(durations, fade, "vout", transitions)
    starts = scene_starts(durations)
    for k, start in enumerate(starts):
        chains.append(f"[{k}:a]adelay={round(start * 1000)}:all=1[sa{k}]")
    labels = "".join(f"[sa{k}]" for k in range(len(starts)))
    mix = f"amix=inputs={len(starts)}:normalize=0:duration=longest," if len(starts) > 1 else ""
    chains.append(
        f"{labels}{mix}{LOUDNORM},aresample={SAMPLE_RATE},atrim=duration={num(total)}[aout]"
    )
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
