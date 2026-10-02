"""Tap ripples and the Android Back badge.

Event times are clip times. They are mapped through the scene timeline to
output times, so a ripple still lands on its tap after holds and speed ups.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

from reelsmith.compose.captions import load_font
from reelsmith.models import Event
from reelsmith.timing import Segment

EPS = 1e-6
RING_STEPS = 4  # a ripple is this many rings, each a little bigger and fainter
RING_STEP_SECONDS = 0.09
RING_RADII = (22, 34, 46, 58)  # at 1080p
BACK_SECONDS = 0.9
RIPPLE_TYPES = ("tap", "click")


@dataclass(frozen=True)
class RippleCue:
    t: float  # output time
    x: float  # fraction of the clip width
    y: float  # fraction of the clip height


def out_time(segments: Sequence[Segment], src: float) -> float | None:
    """Output time of a clip time. After a hold at src, the later time wins."""
    found: float | None = None
    for seg in segments:
        if seg.kind == "play" and seg.src_start - EPS <= src <= seg.src_end + EPS:
            found = seg.out_start + (src - seg.src_start) / seg.speed
    return found


def ripple_cues(events: Sequence[Event], segments: Sequence[Segment]) -> list[RippleCue]:
    cues: list[RippleCue] = []
    for event in events:
        if event.type not in RIPPLE_TYPES or event.x is None or event.y is None:
            continue
        t = out_time(segments, event.t)
        if t is not None:
            cues.append(RippleCue(t, event.x, event.y))
    return cues


def back_cues(events: Sequence[Event], segments: Sequence[Segment]) -> list[float]:
    times = (out_time(segments, e.t) for e in events if e.type == "back")
    return [t for t in times if t is not None]


def draw_ring(radius: int, color: str, opacity: float, dest: Path) -> Path:
    """A soft ring of the given radius, centred in a square PNG."""
    width = max(2, radius // 6)
    side = 2 * (radius + width)
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    red, green, blue = ImageColor.getrgb(color)[:3]
    alpha = round(255 * opacity)
    centre = side / 2
    bounds = (centre - radius, centre - radius, centre + radius, centre + radius)
    draw.ellipse(
        bounds, fill=(red, green, blue, alpha // 4), outline=(red, green, blue, alpha), width=width
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def draw_back_badge(unit: float, font: Path | None, dest: Path) -> Path:
    """A dark pill with a left pointing triangle and the word Back."""
    height = max(16, round(64 * unit))
    width = round(height * 2.9)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), height // 2, fill=(17, 24, 39, 220))
    pad = height * 0.32
    tri_w = height * 0.32
    mid = height / 2
    draw.polygon(
        [(pad, mid), (pad + tri_w, mid - tri_w * 0.9), (pad + tri_w, mid + tri_w * 0.9)],
        fill=(255, 255, 255, 255),
    )
    text_font = load_font(font, round(height * 0.45))
    draw.text((pad + tri_w + height * 0.25, mid), "Back", font=text_font, fill="white", anchor="lm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest
