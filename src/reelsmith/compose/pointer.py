"""The drawn cursor and the click and tap pulse, made with Pillow.

Shapes are drawn at a larger size and scaled down, so their edges are
smooth. Everything is drawn from scratch here; no image is downloaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageColor, ImageDraw, ImageFilter

from reelsmith.compose.motion import ease

SUPERSAMPLE = 4
PULSE_FRAMES = 16  # at 30 fps, about half a second
CURSOR_HEIGHT = 30  # at 1080p
PULSE_RADIUS = 46  # at 1080p, the widest ring

PulseKind = Literal["click", "tap"]

# A classic arrow pointer on a 0..1 grid, tip at the top left.
_ARROW = [
    (0.0, 0.0),
    (0.0, 0.80),
    (0.20, 0.62),
    (0.335, 0.92),
    (0.46, 0.865),
    (0.33, 0.585),
    (0.58, 0.585),
]


@dataclass(frozen=True)
class Sprite:
    image: Path
    width: int
    height: int
    hot_x: int  # the pixel that points, from the left
    hot_y: int


def draw_cursor(height: int, dest: Path) -> Sprite:
    """A white arrow with a dark outline and a soft shadow."""
    s = SUPERSAMPLE
    h = max(8, height) * s
    pad = round(h * 0.25)
    size = (round(h * 0.62) + 2 * pad, h + 2 * pad)
    points = [(pad + x * h, pad + y * h) for x, y in _ARROW]
    body = Image.new("L", size, 0)
    ImageDraw.Draw(body).polygon(points, fill=255)
    edge = 2 * max(1, round(h * 0.045)) + 1
    outline = body.filter(ImageFilter.MaxFilter(edge))
    shadow = outline.point(lambda v: v * 0.55)
    shift = round(h * 0.035)
    shadow = shadow.transform(
        size, Image.Transform.AFFINE, (1, 0, -shift * 0.6, 0, 1, -shift * 1.4)
    ).filter(ImageFilter.GaussianBlur(h * 0.05))
    image = _tint(shadow, (0, 0, 0))
    image = Image.alpha_composite(image, _tint(outline, (17, 20, 26)))
    image = Image.alpha_composite(image, _tint(body, (255, 255, 255)))
    final = image.resize((size[0] // s, size[1] // s), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    final.save(dest)
    return Sprite(dest, final.width, final.height, round(pad / s), round(pad / s))


def _tint(alpha: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    layer = Image.new("RGBA", alpha.size, (*rgb, 0))
    layer.putalpha(alpha)
    return layer


def pulse_frames(radius: int, color: str, kind: PulseKind, folder: Path) -> Sprite:
    """Frames of one pulse, saved as folder/pulse_00.png and on.

    A click pulse is a ring that grows and fades, with a quick bright core.
    A tap pulse adds a soft filled touch dot that shrinks away.
    The returned Sprite names the first frame; the hot spot is the centre.
    """
    s = SUPERSAMPLE
    r = max(6, radius)
    side = 2 * (r + max(2, r // 5))
    red, green, blue = ImageColor.getrgb(color)[:3]
    folder.mkdir(parents=True, exist_ok=True)
    for frame in range(PULSE_FRAMES):
        p = frame / (PULSE_FRAMES - 1)
        grow = 1 - (1 - p) ** 3
        image = Image.new("RGBA", (side * s, side * s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        c = side * s / 2
        ring = (0.35 + 0.65 * grow) * r * s
        width = max(s, round((0.16 - 0.1 * grow) * r * s))
        fade = (1 - p) ** 1.4
        draw.ellipse(
            (c - ring, c - ring, c + ring, c + ring),
            fill=(red, green, blue, round(60 * fade)),
            outline=(red, green, blue, round(235 * fade)),
            width=width,
        )
        core = (0.32 if kind == "tap" else 0.18) * r * s * (1 - 0.6 * ease(p))
        core_alpha = round((200 if kind == "tap" else 230) * (1 - ease(min(1.0, p * 1.6))))
        draw.ellipse(
            (c - core, c - core, c + core, c + core),
            fill=(255, 255, 255, core_alpha) if kind == "click" else (red, green, blue, core_alpha),
        )
        small = image.resize((side, side), Image.Resampling.LANCZOS)
        small.save(folder / f"pulse_{frame:02d}.png")
    return Sprite(folder / "pulse_00.png", side, side, side // 2, side // 2)


def pulse_pattern(sprite: Sprite) -> Path:
    """The numbered file pattern ffmpeg reads the pulse frames with."""
    folder = str(sprite.image.parent).replace("%", "%%")
    return Path(folder) / "pulse_%02d.png"
