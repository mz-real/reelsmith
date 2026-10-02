"""Browser and phone frames, drawn with Pillow at the exact size needed.

Nothing is downloaded. Each frame is a PNG with a clear hole where the
screen goes, laid over the scaled clip.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from reelsmith.compose.layouts import FRAME_INSETS, FrameKind, Size

TRAFFIC_LIGHTS = ("#ff5f57", "#febc2e", "#28c840")


def draw_frame(kind: FrameKind, outer: Size, unit: float, *, dark: bool, dest: Path) -> Path:
    """Draw a frame of size outer whose hole matches FRAME_INSETS."""
    left, top, right, bottom = (round(v * unit) for v in FRAME_INSETS[kind])
    hole = (left, top, outer.width - right - 1, outer.height - bottom - 1)
    if kind == "browser":
        image = _browser(outer, unit, hole, dark)
    else:
        image = _phone(outer, unit, hole)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def _shape(
    outer: Size, radius: int, hole: tuple[int, int, int, int], hole_radius: int
) -> Image.Image:
    mask = Image.new("L", (outer.width, outer.height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, outer.width - 1, outer.height - 1), radius, fill=255)
    draw.rounded_rectangle(hole, hole_radius, fill=0)
    return mask


def _browser(outer: Size, unit: float, hole: tuple[int, int, int, int], dark: bool) -> Image.Image:
    chrome = "#1e293b" if dark else "#e2e8f0"
    field = "#0f172a" if dark else "#ffffff"
    image = Image.new("RGBA", (outer.width, outer.height), chrome)
    image.putalpha(_shape(outer, max(2, round(12 * unit)), hole, 0))
    draw = ImageDraw.Draw(image)
    bar = hole[1]
    mid = bar / 2
    dot = max(2, round(6 * unit))
    for number, color in enumerate(TRAFFIC_LIGHTS):
        cx = round((22 + 20 * number) * unit)
        draw.ellipse((cx - dot, mid - dot, cx + dot, mid + dot), fill=color)
    pill_h = max(4, round(28 * unit))
    x0 = round(110 * unit)
    x1 = max(x0 + 4, outer.width - round(60 * unit))
    draw.rounded_rectangle((x0, mid - pill_h / 2, x1, mid + pill_h / 2), pill_h // 2, fill=field)
    return image


def _phone(outer: Size, unit: float, hole: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (outer.width, outer.height), "#0b0f19")
    image.putalpha(_shape(outer, max(4, round(64 * unit)), hole, max(2, round(42 * unit))))
    draw = ImageDraw.Draw(image)
    camera = max(2, round(7 * unit))
    cx = outer.width / 2
    cy = hole[1] + round(20 * unit)
    draw.ellipse((cx - camera, cy - camera, cx + camera, cy + camera), fill="#000000")
    return image
