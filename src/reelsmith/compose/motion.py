"""Keyframed motion: zoom views and the cursor path.

Both are tracks of keyframes. Between two keyframes the value eases in
and out. Before the first and after the last keyframe it holds still.
The same track gives a value in Python (for tests and checks) and an
ffmpeg expression (for the render), so the two can never disagree.

All times are scene output times, after holds and speed ups.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from reelsmith.compose.layouts import num
from reelsmith.compose.ripples import out_time
from reelsmith.models import ClipModel, ZoomSpec
from reelsmith.timing import Segment

ZOOM_EASE = 0.6  # seconds to ease in, and again to ease out
ZOOM_LEAD = 0.25  # the view is fully in this long before the moment
MAX_ZOOM = 2.5
CURSOR_LEAD = 0.25  # the cursor arrives this long before its click
CURSOR_SETTLE = 0.12  # and rests this long after it before moving on
CURSOR_MIN_MOVE = 0.3
CURSOR_MAX_MOVE = 0.9
CURSOR_SPEED = 0.6  # extra seconds per unit of distance travelled
EPS = 1e-6

Values = tuple[float, ...]


@dataclass(frozen=True)
class Key:
    t: float
    v: Values


def ease(p: float) -> float:
    """Ease in and out (cubic), from 0 at p=0 to 1 at p=1."""
    p = min(1.0, max(0.0, p))
    return 4 * p**3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def value_at(keys: Sequence[Key], t: float) -> Values:
    """The value of a track at time t."""
    if not keys:
        raise ValueError("A track needs at least one keyframe")
    if t <= keys[0].t:
        return keys[0].v
    for before, after in zip(keys, keys[1:], strict=False):
        if t < after.t:
            span = after.t - before.t
            p = ease((t - before.t) / span) if span > EPS else 1.0
            return tuple(a + (b - a) * p for a, b in zip(before.v, after.v, strict=True))
    return keys[-1].v


def _ease_expr(p: str) -> str:
    return f"if(lt({p},0.5),4*pow({p},3),1-pow(2-2*{p},3)/2)"


def track_expr(keys: Sequence[Key], pick: Callable[[Values], float], var: str = "t") -> str:
    """An ffmpeg expression for pick(value) over time var."""
    if not keys:
        raise ValueError("A track needs at least one keyframe")
    expr = num(pick(keys[-1].v))
    for before, after in reversed(list(zip(keys, keys[1:], strict=False))):
        a, b = pick(before.v), pick(after.v)
        span = after.t - before.t
        if span <= EPS or abs(b - a) < EPS:
            piece = num(b if span <= EPS else a)
        else:
            p = f"(({var}-{num(before.t)})/{num(span)})"
            piece = f"({num(a)}+{num(b - a)}*{_ease_expr(p)})"
        expr = f"if(lt({var},{num(after.t)}),{piece},{expr})"
    return f"if(lt({var},{num(keys[0].t)}),{num(pick(keys[0].v))},{expr})"


# Zoom: a view is the visible part of the footage, as fractions
# (left, top, right, bottom). The full frame is (0, 0, 1, 1).

FULL_VIEW: Values = (0.0, 0.0, 1.0, 1.0)


def zoom_view(box: tuple[float, float, float, float]) -> Values:
    """The view for a zoom box: the box grown to the footage aspect, kept inside it."""
    x, y, w, h = box
    side = min(1.0, max(w, h, 1.0 / MAX_ZOOM))
    cx, cy = x + w / 2, y + h / 2
    left = min(max(cx - side / 2, 0.0), 1.0 - side)
    top = min(max(cy - side / 2, 0.0), 1.0 - side)
    return (left, top, left + side, top + side)


@dataclass(frozen=True)
class ZoomWindow:
    view: Values
    start: float  # the ease in starts
    full: float  # fully zoomed in
    release: float  # the ease out starts
    end: float  # back to the full frame


def zoom_moment(zoom: ZoomSpec, clip: ClipModel, segments: Sequence[Segment]) -> float:
    """The output time of a zoom's at: an event id or seconds in clip time."""
    if isinstance(zoom.at, str):
        event = clip.event(zoom.at)
        if event is None:
            raise ValueError(f"clip '{clip.id}' has no event '{zoom.at}'")
        src = event.t
    else:
        src = min(float(zoom.at), clip.duration)
    found = out_time(segments, src)
    if found is None:
        raise ValueError(f"{src:g} s is outside clip '{clip.id}'")
    return found


def zoom_windows(moments: Sequence[tuple[float, ZoomSpec]], duration: float) -> list[ZoomWindow]:
    """When each zoom eases in, holds and eases out, kept inside the scene."""
    windows = []
    for at, zoom in sorted(moments, key=lambda item: item[0]):
        full = min(max(at - ZOOM_LEAD, ZOOM_EASE), max(duration, ZOOM_EASE))
        start = max(0.0, full - ZOOM_EASE)
        release = max(full, at + zoom.hold)
        end = release + ZOOM_EASE
        windows.append(ZoomWindow(zoom_view(zoom.box), start, full, release, end))
    return windows


def zoom_keys(windows: Sequence[ZoomWindow]) -> list[Key]:
    """Keyframes for the view. A zoom that starts before the last one ends
    moves straight from one box to the next instead of zooming out between."""
    keys = [Key(0.0, FULL_VIEW)]
    for number, window in enumerate(windows):
        following = windows[number + 1] if number + 1 < len(windows) else None
        start = max(window.start, keys[-1].t)
        full = max(window.full, start + EPS)
        keys.append(Key(start, keys[-1].v))
        keys.append(Key(full, window.view))
        release = max(window.release, full)
        if following is not None and following.start < window.end:
            keys.append(Key(min(release, max(following.start, full)), window.view))
            continue
        keys.append(Key(release, window.view))
        keys.append(Key(release + ZOOM_EASE, FULL_VIEW))
    return _clean(keys)


def _clean(keys: list[Key]) -> list[Key]:
    """Drop keys that repeat the time and value of the key before them."""
    out: list[Key] = []
    for key in keys:
        if out and abs(out[-1].t - key.t) < EPS and out[-1].v == key.v:
            continue
        out.append(key)
    return out


def view_point(view: Values, x: float, y: float) -> tuple[float, float]:
    """Where a footage point (fractions) lands in the zoomed picture (fractions)."""
    left, top, right, bottom = view
    return (x - left) / (right - left), (y - top) / (bottom - top)


def view_scale(view: Values) -> float:
    return 1.0 / (view[2] - view[0])


# Cursor: a path of (x, y) fractions of the footage.


@dataclass(frozen=True)
class Click:
    t: float  # output time
    x: float
    y: float


def clicks_of(clip: ClipModel, segments: Sequence[Segment], kinds: Sequence[str]) -> list[Click]:
    """Positioned events of the given kinds, at their output times."""
    clicks = []
    for event in clip.events:
        if event.type not in kinds or event.x is None or event.y is None:
            continue
        t = out_time(segments, event.t)
        if t is not None:
            clicks.append(Click(t, event.x, event.y))
    return sorted(clicks, key=lambda c: c.t)


def move_seconds(a: tuple[float, float], b: tuple[float, float]) -> float:
    distance = math.dist(a, b)
    return min(CURSOR_MAX_MOVE, max(CURSOR_MIN_MOVE, CURSOR_MIN_MOVE + CURSOR_SPEED * distance))


def rest_position(first: Click) -> tuple[float, float]:
    """Where the cursor waits before the first click: below and right of it."""
    x = first.x + 0.12 if first.x < 0.8 else first.x - 0.12
    y = first.y + 0.16 if first.y < 0.75 else first.y - 0.16
    return x, y


def cursor_keys(clicks: Sequence[Click]) -> list[Key]:
    """The cursor path: it arrives CURSOR_LEAD before each click and waits there."""
    if not clicks:
        return []
    first = clicks[0]
    start = rest_position(first)
    arrive = max(0.0, first.t - CURSOR_LEAD)
    keys = [Key(0.0, start)]
    leave = max(0.0, arrive - move_seconds(start, (first.x, first.y)))
    keys += [Key(leave, start), Key(max(arrive, leave + EPS), (first.x, first.y))]
    for before, after in zip(clicks, clicks[1:], strict=False):
        here, there = (before.x, before.y), (after.x, after.y)
        arrive = max(after.t - CURSOR_LEAD, keys[-1].t)
        leave = max(before.t + CURSOR_SETTLE, arrive - move_seconds(here, there), keys[-1].t)
        leave = min(leave, arrive)
        if arrive - leave < EPS:
            arrive = leave + EPS  # back to back clicks: jump
        keys += [Key(leave, here), Key(arrive, there)]
    return _clean(keys)
