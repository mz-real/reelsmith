"""Blur boxes: crop a region, blur it and lay it back on the clip.

Blur runs on the raw clip, before holds and speed changes, so enable times
are clip times and every output frame that shows a listed moment is blurred.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from reelsmith.compose.layouts import num
from reelsmith.models import BlurRegion

MAX_RADIUS = 20
FRAME_PAD = 1.0 / 30.0
# Start a window two frames early: output frames can trail clip time by one frame,
# and blurring one extra frame is harmless where showing one sharp frame is not.
START_PAD = 2.0 / 30.0


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


def _enable_window(start: float, end: float) -> str:
    start_adj = max(0.0, start - START_PAD)
    end_adj = end + FRAME_PAD
    return f"between(t,{num(start_adj)},{num(end_adj)})"


def blur_filters_clip(boxes: Sequence[BlurBox], src: str, out: str) -> list[str]:
    """Blur on a continuous clip timeline (clip times in enable)."""
    if not boxes:
        return [f"[{src}]null[{out}]"]
    chains: list[str] = []
    current = src
    for number, box in enumerate(boxes):
        last = number == len(boxes) - 1
        target = out if last else f"blur{number}"
        radius = max(1, min(MAX_RADIUS, min(box.w, box.h) // 4 - 1))
        enable = (
            f"gte(t,{num(max(0.0, box.start - START_PAD))})"
            if box.end is None
            else _enable_window(box.start, box.end)
        )
        chains.append(
            f"[{current}]split[blurbase{number}][blurcut{number}];"
            f"[blurcut{number}]crop={box.w}:{box.h}:{box.x}:{box.y},"
            f"boxblur={radius}:2[blurred{number}];"
            f"[blurbase{number}][blurred{number}]overlay={box.x}:{box.y}:"
            f"enable='{enable}'[{target}]"
        )
        current = target
    return chains
