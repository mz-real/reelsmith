"""Expand stepped speed segments into eased multi-step ramps for render and QA."""

from __future__ import annotations

import math
from collections.abc import Sequence

from reelsmith.timing import EPS, Segment

RAMP_OUT = 0.4
RAMP_STEPS = 8
MAX_SPEED_STEP = 1.25
MIN_RAMP_STEPS = 6
MAX_RAMP_STEPS = 16


def _speed_ladder(lo: float, hi: float, steps: int) -> list[float]:
    """Speeds from lo to hi; each neighbour differs by at most MAX_SPEED_STEP."""
    if steps < 1:
        steps = 1
    lo = max(lo, EPS)
    hi = max(hi, EPS)
    if abs(lo - hi) < EPS:
        return [lo] * steps
    rising = lo < hi
    if rising:
        span = hi / lo
        count = max(steps, int(math.ceil(math.log(span) / math.log(MAX_SPEED_STEP))) + 1)
        count = min(MAX_RAMP_STEPS, max(MIN_RAMP_STEPS, count))
        speeds = [lo]
        for _ in range(count - 1):
            speeds.append(min(hi, speeds[-1] * MAX_SPEED_STEP))
        speeds[-1] = hi
        return speeds
    span = lo / hi
    count = max(steps, int(math.ceil(math.log(span) / math.log(MAX_SPEED_STEP))) + 1)
    count = min(MAX_RAMP_STEPS, max(MIN_RAMP_STEPS, count))
    speeds = [lo]
    for _ in range(count - 1):
        speeds.append(max(hi, speeds[-1] / MAX_SPEED_STEP))
    speeds[-1] = hi
    return speeds


def _ramp_source(out_time: float, speeds: Sequence[float]) -> float:
    if out_time <= EPS or not speeds:
        return 0.0
    step = out_time / len(speeds)
    return sum(speed * step for speed in speeds)


def _join_speed(left: Segment, right: Segment) -> float:
    """Playback speed at a cut between two play segments (before any ramp inside)."""
    if left.kind != "play" or right.kind != "play":
        return 1.0
    return min(left.speed, right.speed)


def _speed_in(segments: Sequence[Segment], index: int) -> float:
    if index <= 0:
        return 1.0
    left = segments[index - 1]
    if left.kind != "play":
        return 1.0
    return _join_speed(left, segments[index])


def _speed_out(segments: Sequence[Segment], index: int) -> float:
    if index + 1 >= len(segments):
        return 1.0
    right = segments[index + 1]
    if right.kind != "play":
        return 1.0
    return _join_speed(segments[index], right)


def _append_ramp(
    pieces: list[Segment],
    out_at: float,
    src_at: float,
    ramp_out: float,
    speeds: Sequence[float],
) -> tuple[float, float]:
    if ramp_out <= EPS:
        return out_at, src_at
    step = ramp_out / len(speeds)
    for speed in speeds:
        src_end = src_at + speed * step
        pieces.append(Segment("play", src_at, src_end, speed, out_at, out_at + step))
        src_at = src_end
        out_at += step
    return out_at, src_at


def _src_for_ramps(
    out_len: float,
    speed: float,
    ramp_in: float,
    ramp_out: float,
    speeds_in: Sequence[float],
    speeds_out: Sequence[float],
) -> float | None:
    mid_out = out_len - ramp_in - ramp_out
    if mid_out < -EPS:
        return None
    return _ramp_source(ramp_in, speeds_in) + speed * mid_out + _ramp_source(ramp_out, speeds_out)


def _fixed_ramp_in(out_len: float) -> float:
    return min(RAMP_OUT, max(0.0, out_len - 0.02))


def _fixed_ramp_pair(out_len: float) -> float:
    return min(RAMP_OUT, max(0.0, (out_len - 0.02) / 2))


def _solve_ramp_in_only(
    out_len: float,
    speed_in: float,
    nominal: float,
    src_len: float,
) -> tuple[float, float, float, float]:
    """Return ramp_in, plateau_speed, mid_out, mid_src."""
    ramp_in = _fixed_ramp_in(out_len)
    plateau = nominal
    mid_out = mid_src = 0.0
    for _ in range(32):
        speeds_in = _speed_ladder(speed_in, plateau, RAMP_STEPS)
        mid_out = out_len - ramp_in
        if mid_out <= EPS:
            ramp_in = max(0.0, out_len * 0.25)
            mid_out = out_len - ramp_in
        if mid_out <= EPS:
            return 0.0, plateau, 0.0, 0.0
        ramp_src = _ramp_source(ramp_in, speeds_in)
        mid_src = src_len - ramp_src
        plateau_new = mid_src / mid_out
        if abs(plateau_new - plateau) < 1e-5:
            return ramp_in, plateau_new, mid_out, mid_src
        plateau = plateau_new
    return ramp_in, plateau, mid_out, mid_src


def _solve_ramp_out_only(
    out_len: float,
    nominal: float,
    speed_out: float,
    src_len: float,
) -> tuple[float, float, float, float]:
    ramp_out = _fixed_ramp_in(out_len)
    plateau = nominal
    mid_out = mid_src = 0.0
    for _ in range(32):
        speeds_out = _speed_ladder(plateau, speed_out, RAMP_STEPS)
        mid_out = out_len - ramp_out
        if mid_out <= EPS:
            ramp_out = max(0.0, out_len * 0.25)
            mid_out = out_len - ramp_out
        if mid_out <= EPS:
            return 0.0, plateau, 0.0, 0.0
        ramp_src = _ramp_source(ramp_out, speeds_out)
        mid_src = src_len - ramp_src
        plateau_new = mid_src / mid_out
        if abs(plateau_new - plateau) < 1e-5:
            return ramp_out, plateau_new, mid_out, mid_src
        plateau = plateau_new
    return ramp_out, plateau, mid_out, mid_src


def _solve_pair_ramps(
    out_len: float,
    speed_in: float,
    speed_out: float,
    src_len: float,
    nominal: float,
) -> tuple[float, float, float, float, float]:
    """Return ramp_in, ramp_out, plateau_speed, mid_out, mid_src."""
    ramp_in = ramp_out = _fixed_ramp_pair(out_len)
    plateau = nominal
    mid_out = mid_src = 0.0
    for _ in range(32):
        speeds_in = _speed_ladder(speed_in, plateau, RAMP_STEPS)
        speeds_out = _speed_ladder(plateau, speed_out, RAMP_STEPS)
        mid_out = out_len - ramp_in - ramp_out
        if mid_out <= EPS:
            ramp_in = ramp_out = max(0.0, (out_len - 0.02) / 2)
            mid_out = out_len - ramp_in - ramp_out
        if mid_out <= EPS:
            return 0.0, 0.0, plateau, 0.0, 0.0
        ramp_src = _ramp_source(ramp_in, speeds_in) + _ramp_source(ramp_out, speeds_out)
        mid_src = src_len - ramp_src
        plateau_new = mid_src / mid_out
        if abs(plateau_new - plateau) < 1e-5:
            return ramp_in, ramp_out, plateau_new, mid_out, mid_src
        plateau = plateau_new
    return ramp_in, ramp_out, plateau, mid_out, mid_src


def _subdivide_play(segment: Segment, speed_in: float, speed_out: float) -> list[Segment]:
    speed = segment.speed
    out_len = segment.out_end - segment.out_start
    src_len = segment.src_end - segment.src_start
    if out_len <= EPS or src_len <= EPS:
        return [segment]
    need_in = abs(speed - speed_in) > EPS
    need_out = abs(speed - speed_out) > EPS
    if not need_in and not need_out:
        return [segment]

    plateau = speed
    ramp_in = ramp_out = 0.0
    mid_out = mid_src = 0.0
    speeds_in: Sequence[float] = ()
    speeds_out: Sequence[float] = ()

    if need_in and need_out:
        ramp_in, ramp_out, plateau, mid_out, mid_src = _solve_pair_ramps(
            out_len, speed_in, speed_out, src_len, speed
        )
        speeds_in = _speed_ladder(speed_in, plateau, RAMP_STEPS)
        speeds_out = _speed_ladder(plateau, speed_out, RAMP_STEPS)
    elif need_in:
        ramp_in, plateau, mid_out, mid_src = _solve_ramp_in_only(out_len, speed_in, speed, src_len)
        speeds_in = _speed_ladder(speed_in, plateau, RAMP_STEPS)
    else:
        ramp_out, plateau, mid_out, mid_src = _solve_ramp_out_only(
            out_len, speed, speed_out, src_len
        )
        speeds_out = _speed_ladder(plateau, speed_out, RAMP_STEPS)

    if mid_out <= EPS or mid_src <= EPS:
        return [segment]

    pieces: list[Segment] = []
    out_at = segment.out_start
    src_at = segment.src_start
    if ramp_in > EPS:
        out_at, src_at = _append_ramp(pieces, out_at, src_at, ramp_in, speeds_in)
    pieces.append(Segment("play", src_at, src_at + mid_src, plateau, out_at, out_at + mid_out))
    out_at += mid_out
    src_at += mid_src
    if ramp_out > EPS:
        out_at, src_at = _append_ramp(pieces, out_at, src_at, ramp_out, speeds_out)
    return _merge_play_runs(pieces)


def _merge_play_runs(segments: Sequence[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for seg in segments:
        if (
            merged
            and merged[-1].kind == "play"
            and seg.kind == "play"
            and abs(merged[-1].speed - seg.speed) < EPS
            and abs(merged[-1].src_end - seg.src_start) < EPS
            and abs(merged[-1].out_end - seg.out_start) < EPS
        ):
            merged[-1] = Segment(
                "play",
                merged[-1].src_start,
                seg.src_end,
                seg.speed,
                merged[-1].out_start,
                seg.out_end,
            )
            continue
        merged.append(seg)
    return merged


def expand_speed_ramps(segments: Sequence[Segment], ramp_out: float = RAMP_OUT) -> list[Segment]:
    """Split play segments at speed changes into eased ramps that keep src and out spans."""
    if ramp_out <= EPS:
        return list(segments)
    out: list[Segment] = []
    items = list(segments)
    for index, seg in enumerate(items):
        if seg.kind != "play":
            out.append(seg)
            continue
        speed_in = _speed_in(items, index)
        speed_out = _speed_out(items, index)
        if abs(seg.speed - speed_in) < EPS and abs(seg.speed - speed_out) < EPS:
            out.append(seg)
            continue
        out.extend(_subdivide_play(seg, speed_in, speed_out))
    return out


def max_step_speed_ratio(segments: Sequence[Segment]) -> float:
    """Largest speed ratio between consecutive play steps."""
    plays = [seg for seg in segments if seg.kind == "play"]
    worst = 1.0
    for left, right in zip(plays, plays[1:], strict=False):
        if left.speed <= EPS or right.speed <= EPS:
            continue
        worst = max(worst, left.speed / right.speed, right.speed / left.speed)
    return worst


def max_speed_jump(segments: Sequence[Segment], window: float) -> float:
    """Largest speed ratio between consecutive play steps within window seconds."""
    plays = [seg for seg in segments if seg.kind == "play"]
    worst = 1.0
    for left, right in zip(plays, plays[1:], strict=False):
        if right.out_start - left.out_start > window + EPS:
            continue
        if left.speed <= EPS or right.speed <= EPS:
            continue
        worst = max(worst, left.speed / right.speed, right.speed / left.speed)
    return worst


def check_segment_totals(original: Segment, expanded: Sequence[Segment]) -> bool:
    """True when expanded play pieces cover the same source and output spans."""
    plays = [seg for seg in expanded if seg.kind == "play"]
    if not plays:
        return False
    src = sum(seg.src_end - seg.src_start for seg in plays)
    out = sum(seg.out_end - seg.out_start for seg in plays)
    if abs(src - (original.src_end - original.src_start)) > 1e-5:
        return False
    if abs(out - (original.out_end - original.out_start)) > 1e-5:
        return False
    if abs(plays[0].out_start - original.out_start) > 1e-5:
        return False
    if abs(plays[-1].out_end - original.out_end) > 1e-4:
        return False
    orig_eff = (original.src_end - original.src_start) / (original.out_end - original.out_start)
    for seg in plays:
        span = seg.out_end - seg.out_start
        if span <= EPS:
            continue
        eff = (seg.src_end - seg.src_start) / span
        target = seg.speed
        if len(plays) == 1:
            target = orig_eff
        if abs(eff - target) > 1e-3:
            return False
    return True
