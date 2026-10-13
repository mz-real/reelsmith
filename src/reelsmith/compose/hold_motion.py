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


def hold_scale_expr(duration: float, amount: float = HOLD_SCALE, var: str = "t") -> str:
    """ffmpeg scale factor at local time var in [0, duration], easing out at the end."""
    if duration <= EPS:
        return "1"
    p = f"clip({var}/{num(duration)},0,1)"
    eased = f"({num(amount)}*(1-pow(1-{p},3)))"
    return f"(1+{eased})"


def centered_zoom_filter(
    scale: str,
    center_x: str = "W/2",
    center_y: str = "H/2",
    fps: int = 30,
) -> str:
    """Zoom the frame by an ffmpeg scale expression without whole pixel steps.

    The perspective filter moves the four corners of the visible window by
    fractions of a pixel and samples the picture with cubic interpolation,
    so a slow push moves a little on every frame. The window is kept inside
    the frame. In scale, the local time in seconds is written as T.
    """
    t = f"(in/{fps})"
    s = f"({scale.replace('T', t)})"
    half_w, half_h = f"(W/(2*{s}))", f"(H/(2*{s}))"
    left = f"max(0,min(W-W/{s},({center_x})-{half_w}))"
    top = f"max(0,min(H-H/{s},({center_y})-{half_h}))"
    right = f"({left}+W/{s})"
    bottom = f"({top}+H/{s})"
    return (
        f"perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}':"
        f"x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}':"
        f"interpolation=cubic:eval=frame"
    )


def hold_push_chain(
    width: int,
    height: int,
    duration: float,
    center_x: float,
    center_y: float,
    amount: float = HOLD_SCALE,
    fps: int = 30,
) -> str:
    """Push in slowly on a footage point, moving a fraction of a pixel per frame."""
    scale = hold_scale_expr(duration, amount, "T")
    return centered_zoom_filter(scale, num(center_x * width), num(center_y * height), fps)


def eased_hold_amount(t: float, duration: float, amount: float = HOLD_SCALE) -> float:
    """Scale at time t for tests (matches hold_scale_expr)."""
    if duration <= EPS:
        return 1.0
    p = min(1.0, max(0.0, t / duration))
    return 1.0 + amount * (1.0 - (1.0 - p) ** 3)
