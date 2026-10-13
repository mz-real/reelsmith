"""Joining scenes with a short cross fade.

Every scene file except the last is rendered XFADE seconds longer, holding
its last frame. Each fade then runs over that padding, so scene k starts in
the master at the sum of the timeline durations before it, and no
narration is ever faded out.
"""

from __future__ import annotations

from collections.abc import Sequence

from reelsmith.compose.layouts import num
from reelsmith.models.spec import TransitionKind

XFADE = 0.4
DISSOLVE = 0.2

FFMPEG_TRANSITION: dict[TransitionKind, str] = {
    "fade": "fade",
    "slide": "slideleft",
    "push": "smoothleft",
    "zoom": "zoomin",
}


def ffmpeg_transition(kind: TransitionKind) -> str:
    """The xfade transition name ffmpeg expects."""
    return FFMPEG_TRANSITION[kind]


def boundary_transitions(
    scene_kinds: Sequence[TransitionKind | None],
    default: TransitionKind,
) -> list[str]:
    """One ffmpeg transition per join; scene k sets the fade before it appears."""
    if len(scene_kinds) < 2:
        return []
    return [ffmpeg_transition(scene_kinds[i] or default) for i in range(1, len(scene_kinds))]


def _same_clip_pair(left: object, right: object) -> bool:
    left_clip = getattr(left, "clip", None)
    right_clip = getattr(right, "clip", None)
    if left_clip and right_clip and left_clip == right_clip:
        return True
    left_layout = getattr(left, "layout", None)
    right_layout = getattr(right, "layout", None)
    return (
        left_layout == right_layout
        and left_layout not in (None, "slide")
        and left_clip is not None
        and right_clip is not None
    )


def boundary_fade_durations(scenes: Sequence[object]) -> list[float]:
    """Fade length per join: short dissolve for similar clips, longer when a slide is involved."""
    if len(scenes) < 2:
        return []
    fades: list[float] = []
    for index in range(1, len(scenes)):
        left, right = scenes[index - 1], scenes[index]
        left_slide = getattr(left, "layout", None) == "slide"
        right_slide = getattr(right, "layout", None) == "slide"
        slide = left_slide or right_slide
        if slide:
            fades.append(XFADE)
        elif _same_clip_pair(left, right):
            fades.append(DISSOLVE)
        else:
            fades.append(XFADE)
    return fades


def boundary_join_plan(
    scene_kinds: Sequence[TransitionKind | None],
    scenes: Sequence[object],
    default: TransitionKind,
) -> tuple[list[str], list[float]]:
    """Transition names and fade durations per join (scene transition still wins on name)."""
    names = boundary_transitions(scene_kinds, default)
    fades = boundary_fade_durations(scenes)
    return names, fades


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


def xfade_filters(
    durations: Sequence[float],
    fade: float,
    out: str,
    transitions: Sequence[str] | None = None,
    fade_durations: Sequence[float] | None = None,
) -> list[str]:
    """Chain [0:v], [1:v] and so on into [out] with fades at each start."""
    if len(durations) == 1:
        return [f"[0:v]null[{out}]"]
    starts = scene_starts(durations)
    chains: list[str] = []
    current = "0:v"
    for k in range(1, len(durations)):
        target = out if k == len(durations) - 1 else f"x{k}"
        name = transitions[k - 1] if transitions else "fade"
        length = fade
        if fade_durations is not None and k - 1 < len(fade_durations):
            length = fade_durations[k - 1]
        chains.append(
            f"[{current}][{k}:v]xfade=transition={name}:duration={num(length)}"
            f":offset={num(starts[k])}[{target}]"
        )
        current = target
    return chains


def padded_lengths_per_fade(
    durations: Sequence[float], fade_lengths: Sequence[float]
) -> list[float]:
    """Length of each scene file, with per-join fade padding on all but the last."""
    last = len(durations) - 1
    return [
        durations[i] + (fade_lengths[i] if i < last and i < len(fade_lengths) else 0.0)
        for i in range(len(durations))
    ]
