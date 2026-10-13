"""Slow push on held frames so the picture does not freeze."""

from __future__ import annotations

from reelsmith.compose.layouts import num
from reelsmith.models import ClipModel

HOLD_SCALE = 0.025
EPS = 1e-9


def hold_center(clip: ClipModel | None, hold_src: float) -> tuple[float, float]:
    """Centre of the push, as fractions of the clip (last event or frame centre)."""
    if clip is None:
        return 0.5, 0.5
    best = None
    for event in clip.events:
        if event.t <= hold_src + EPS and event.x is not None and event.y is not None:
            if best is None or event.t >= best[0]:
                best = (event.t, event.x, event.y)
    if best is not None:
        return best[1], best[2]
    return 0.5, 0.5


def hold_scale_expr(duration: float, amount: float = HOLD_SCALE) -> str:
    """ffmpeg scale factor at local time t in [0, duration], easing out at the end."""
    if duration <= EPS:
        return "1"
    p = f"clip(t/{num(duration)},0,1)"
    eased = f"({num(amount)}*(1-pow(1-{p},3)))"
    return f"(1+{eased})"


def hold_push_chain(
    width: int,
    height: int,
    duration: float,
    center_x: float,
    center_y: float,
    amount: float = HOLD_SCALE,
) -> str:
    """Scale up slowly and crop back to size, centred on a footage point."""
    scale = hold_scale_expr(duration, amount)
    cx = num(center_x * width)
    cy = num(center_y * height)
    return (
        f"scale=w='2*trunc(iw*({scale})/2)':h='2*trunc(ih*({scale})/2)':eval=frame,"
        f"crop={width}:{height}:x='max(0,min(iw-{width},({cx})-iw/2))':"
        f"y='max(0,min(ih-{height},({cy})-ih/2))'"
    )


def eased_hold_amount(t: float, duration: float, amount: float = HOLD_SCALE) -> float:
    """Scale at time t for tests (matches hold_scale_expr)."""
    if duration <= EPS:
        return 1.0
    p = min(1.0, max(0.0, t / duration))
    return 1.0 + amount * (1.0 - (1.0 - p) ** 3)
