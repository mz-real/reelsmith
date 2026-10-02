"""Blur boxes: crop a region, blur it and lay it back on the clip.

Blur runs on the source clip before the timeline and layout, so its times
are clip times and every export already has the regions hidden.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from reelsmith.compose.layouts import num
from reelsmith.models import BlurRegion

MAX_RADIUS = 20


@dataclass(frozen=True)
class BlurBox:
    x: int
    y: int
    w: int
    h: int
    start: float
    end: float | None


def _even_down(value: float) -> int:
    return max(2, int(value) - int(value) % 2)


def blur_boxes(
    regions: Sequence[BlurRegion], clip_id: str, width: int, height: int
) -> list[BlurBox]:
    """Pixel boxes for the regions listed for this clip."""
    boxes: list[BlurBox] = []
    for region in regions:
        if region.clip != clip_id:
            continue
        fx, fy, fw, fh = region.box
        x = min(_even_down(fx * width) if fx > 0 else 0, width - 2)
        y = min(_even_down(fy * height) if fy > 0 else 0, height - 2)
        w = min(_even_down(round(fw * width)), _even_down(width - x))
        h = min(_even_down(round(fh * height)), _even_down(height - y))
        boxes.append(BlurBox(x, y, w, h, region.start, region.end))
    return boxes


def _enable(box: BlurBox) -> str:
    if box.end is None:
        return f"gte(t,{num(box.start)})"
    return f"between(t,{num(box.start)},{num(box.end)})"


def blur_filters(boxes: Sequence[BlurBox], src: str, out: str) -> list[str]:
    """Filter chains that blur each box in turn, from [src] to [out]."""
    if not boxes:
        return [f"[{src}]null[{out}]"]
    chains: list[str] = []
    current = src
    for number, box in enumerate(boxes):
        last = number == len(boxes) - 1
        target = out if last else f"blur{number}"
        # The chroma planes are half size and need a radius below half of that.
        radius = max(1, min(MAX_RADIUS, min(box.w, box.h) // 4 - 1))
        chains.append(
            f"[{current}]split[blurbase{number}][blurcut{number}];"
            f"[blurcut{number}]crop={box.w}:{box.h}:{box.x}:{box.y},"
            f"boxblur={radius}:2[blurred{number}];"
            f"[blurbase{number}][blurred{number}]overlay={box.x}:{box.y}:"
            f"enable='{_enable(box)}'[{target}]"
        )
        current = target
    return chains
