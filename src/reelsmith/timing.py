"""The timing engine: where each phrase lands and how the clip plays.

Everything here is a pure function of its inputs. Times named ``src`` are
clip times; times named ``out`` are times in the finished scene.

The engine never moves a phrase earlier than the end of the phrase before
it plus a short gap, so narration can never overlap itself. When a phrase
cannot land on its event, the engine either holds the frame before the
event (when holds are allowed) or reports a Conflict. It never drifts
silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EPS = 1e-9

NO_HOLD_REASON = "line too long for the gap before its event"
TAIL_HOLD_REASON = "narration runs past the end of the clip and the last frame holds too long"


@dataclass(frozen=True)
class TimingRules:
    max_hold: float = 3.0
    allow_holds: bool = True
    speed_up_waits: bool = False
    pin_lead: float = 0.25  # a pinned phrase may start this early before its event
    pin_late: float = 0.40  # and must start no later than this after it
    breath: float = 0.35  # gap after the last phrase of a scene
    phrase_gap: float = 0.15
    max_speed: float = 4.0
    min_wait_to_speed: float = 2.5


@dataclass(frozen=True)
class PhraseInput:
    index: int
    duration: float
    pin_time: float | None  # in clip time


@dataclass(frozen=True)
class SceneInput:
    scene_id: str
    clip_duration: float | None  # None means a slide
    phrases: list[PhraseInput]


@dataclass(frozen=True)
class Segment:
    kind: Literal["play", "hold"]
    src_start: float
    src_end: float
    speed: float
    out_start: float
    out_end: float


@dataclass(frozen=True)
class Placement:
    index: int
    out_start: float
    out_end: float


@dataclass(frozen=True)
class Conflict:
    phrase_index: int
    seconds_over: float
    reason: str


@dataclass(frozen=True)
class SceneTimeline:
    scene_id: str
    segments: list[Segment]
    placements: list[Placement]
    duration: float
    conflicts: list[Conflict]


def caption_duration(text: str) -> float:
    """How long a caption stays on screen: max(1.5, words / 2.8 + 0.5)."""
    words = len(text.split())
    return max(1.5, words / 2.8 + 0.5)


class _Track:
    """Builds contiguous segments while walking forward through a clip."""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.src = 0.0  # clip time emitted so far
        self.out = 0.0  # output time at self.src

    def play(self, until: float, speed: float = 1.0) -> None:
        if until - self.src <= EPS:
            return
        length = (until - self.src) / speed
        self.segments.append(Segment("play", self.src, until, speed, self.out, self.out + length))
        self.src = until
        self.out += length

    def hold(self, seconds: float) -> None:
        if seconds <= EPS:
            return
        self.segments.append(Segment("hold", self.src, self.src, 1.0, self.out, self.out + seconds))
        self.out += seconds

    def out_at(self, src: float) -> float:
        """Output time of a clip time, assuming normal speed from here on."""
        if src >= self.src - EPS:
            return self.out + (src - self.src)
        for seg in self.segments:
            if seg.kind == "play" and seg.src_start - EPS <= src <= seg.src_end + EPS:
                return seg.out_start + (src - seg.src_start) / seg.speed
        return self.out

    def src_at(self, out: float) -> float:
        """Clip time at an output time at or after the emitted end."""
        return self.src + max(0.0, out - self.out)

    def speed_quiet(self, quiet_from_out: float, until_src: float, rules: TimingRules) -> None:
        """Play a long stretch with no narration faster, up to max_speed."""
        start = self.src_at(quiet_from_out)
        length = until_src - start
        if length <= rules.min_wait_to_speed + EPS:
            return
        speed = min(rules.max_speed, length / rules.min_wait_to_speed)
        self.play(start)
        self.play(until_src, speed)


def plan_scene(scene: SceneInput, rules: TimingRules) -> SceneTimeline:
    """Place each phrase and lay out the clip for one scene."""
    if scene.clip_duration is None:
        return _plan_slide(scene, rules)
    clip_end = max(0.0, scene.clip_duration)
    track = _Track()
    placements: list[Placement] = []
    conflicts: list[Conflict] = []
    prev_end: float | None = None
    for phrase in scene.phrases:
        earliest = 0.0 if prev_end is None else prev_end + rules.phrase_gap
        if phrase.pin_time is None:
            start = earliest
        else:
            quiet_from = track.out if prev_end is None else max(prev_end, track.out)
            start, conflict = _place_pinned(track, phrase, earliest, quiet_from, clip_end, rules)
            if conflict is not None:
                conflicts.append(conflict)
        placements.append(Placement(phrase.index, start, start + phrase.duration))
        prev_end = start + phrase.duration
    narration_end = 0.0 if prev_end is None else prev_end + rules.breath
    if rules.speed_up_waits:
        track.speed_quiet(max(narration_end, track.out), clip_end, rules)
    track.play(clip_end)
    duration = max(track.out, narration_end)
    tail = duration - track.out
    track.hold(tail)
    if tail > rules.max_hold + EPS and scene.phrases:
        conflicts.append(
            Conflict(scene.phrases[-1].index, _round(tail - rules.max_hold), TAIL_HOLD_REASON)
        )
    return SceneTimeline(scene.scene_id, track.segments, placements, duration, conflicts)


def _place_pinned(
    track: _Track,
    phrase: PhraseInput,
    earliest: float,
    quiet_from: float,
    clip_end: float,
    rules: TimingRules,
) -> tuple[float, Conflict | None]:
    """Start time for a pinned phrase, adding a hold before its event if needed."""
    assert phrase.pin_time is not None
    pin = min(max(phrase.pin_time, 0.0), clip_end)
    ahead = pin >= track.src - EPS
    if ahead and rules.speed_up_waits:
        track.speed_quiet(quiet_from, max(track.src, pin - rules.pin_lead), rules)
    event = track.out_at(pin)
    start = max(event - rules.pin_lead, earliest, 0.0)
    late = start - (event + rules.pin_late)
    if late <= EPS:
        return start, None
    if not (rules.allow_holds and ahead):
        return start, Conflict(phrase.index, _round(late), NO_HOLD_REASON)
    needed = start - (event - rules.pin_lead)
    hold = min(needed, rules.max_hold)
    track.play(pin)
    track.hold(hold)
    event += hold
    start = max(event - rules.pin_lead, earliest, 0.0)
    late = start - (event + rules.pin_late)
    if late <= EPS:
        return start, None
    reason = f"{NO_HOLD_REASON}, even with a {rules.max_hold:g} s hold"
    return start, Conflict(phrase.index, _round(late), reason)


def _plan_slide(scene: SceneInput, rules: TimingRules) -> SceneTimeline:
    placements: list[Placement] = []
    prev_end: float | None = None
    for phrase in scene.phrases:
        start = 0.0 if prev_end is None else prev_end + rules.phrase_gap
        placements.append(Placement(phrase.index, start, start + phrase.duration))
        prev_end = start + phrase.duration
    duration = (0.0 if prev_end is None else prev_end) + rules.breath
    segment = Segment("play", 0.0, duration, 1.0, 0.0, duration)
    return SceneTimeline(scene.scene_id, [segment], placements, duration, [])


def _round(seconds: float) -> float:
    return round(seconds, 3)
