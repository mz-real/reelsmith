"""Joining scenes with a short cross fade.

Every scene file except the last is rendered XFADE seconds longer, holding
its last frame. Each fade then runs over that padding, so scene k starts in
the master at the sum of the timeline durations before it, and no
narration is ever faded out.
"""

from __future__ import annotations

from collections.abc import Sequence

from reelsmith.compose.layouts import num

XFADE = 0.4


def scene_starts(durations: Sequence[float]) -> list[float]:
    """Master start time of each scene."""
    starts: list[float] = []
    total = 0.0
    for duration in durations:
        starts.append(total)
        total += duration
    return starts


def padded_lengths(durations: Sequence[float], fade: float) -> list[float]:
    """Length of each scene file, with the fade padding on all but the last."""
    last = len(durations) - 1
    return [d + (fade if i < last else 0.0) for i, d in enumerate(durations)]


def xfade_filters(durations: Sequence[float], fade: float, out: str) -> list[str]:
    """Chain [0:v], [1:v] and so on into [out] with fades at each start."""
    if len(durations) == 1:
        return [f"[0:v]null[{out}]"]
    starts = scene_starts(durations)
    chains: list[str] = []
    current = "0:v"
    for k in range(1, len(durations)):
        target = out if k == len(durations) - 1 else f"x{k}"
        chains.append(
            f"[{current}][{k}:v]xfade=transition=fade:duration={num(fade)}"
            f":offset={num(starts[k])}[{target}]"
        )
        current = target
    return chains
