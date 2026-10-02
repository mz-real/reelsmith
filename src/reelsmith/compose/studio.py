"""The Studio background for footage scenes, matching the Studio slides.

The same recipe as the slides: a 155 degree gradient from the theme
background to a dark tint of the accent, a soft accent glow at the top
left, a second glow (accent mixed with indigo) at the bottom right, a
vignette and a little grain. The bottom right glow is a separate image
that drifts slowly while the scene plays. The grain also keeps the dark
gradient from banding after encoding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageColor

from reelsmith.compose.layouts import Size, ThemeColors

DEEP_SHARE = 0.16  # how far the far end of the gradient leans to the accent
SECOND_HUE = "#6366f1"  # mixed into the accent for the second glow
SECOND_SHARE = 0.55
VIGNETTE = 0.42
GRAIN = 2.0  # levels of grain noise
DRIFT = 70  # pixels at 1080p the second glow moves either way
DRIFT_PERIOD = 16.0  # seconds for one slow loop
SEED = 7

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Backdrop:
    """The still background and the glow that drifts over it."""

    image: Path
    glow: Path
    glow_x: int  # top left of the glow at the middle of its path
    glow_y: int
    drift: int  # pixels the glow moves either way
    period: float


def _rgb(color: str) -> Array:
    return np.array(ImageColor.getrgb(color)[:3], dtype=np.float64)


def _glow_alpha(distance: Array, centre: float, middle: float) -> Array:
    """A closest side radial gradient: centre alpha, middle alpha at 55%, none at the edge."""
    inner = centre + (middle - centre) * distance / 0.55
    outer = middle * (1 - (distance - 0.55) / 0.45)
    alpha: Array = np.where(distance < 0.55, inner, np.clip(outer, 0.0, None))
    return alpha


def _distance(width: int, height: int, cx: float, cy: float, radius: float) -> Array:
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float64)
    result: Array = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max(1.0, radius)
    return result


def background_array(canvas: Size, colors: ThemeColors) -> Array:
    """The still background as an RGB float array, before grain."""
    w, h = canvas.width, canvas.height
    unit = min(w, h) / 1080
    base, accent = _rgb(colors.background), _rgb(colors.accent)
    deep = base + (accent - base) * DEEP_SHARE
    # A 155 degree CSS gradient: from the top left area towards the bottom right.
    angle = math.radians(155)
    dx, dy = math.sin(angle), -math.cos(angle)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    half = (abs(w * dx) + abs(h * dy)) / 2
    along = ((xs - w / 2) * dx + (ys - h / 2) * dy) / (2 * half) + 0.5
    share = np.clip((along - 0.38) / 0.62, 0.0, 1.0)[..., None]
    image: Array = base * (1 - share) + deep * share
    glow = _glow_alpha(_distance(w, h, 290 * unit, -50 * unit, 750 * unit), 0.26, 0.09)
    image = image + (accent - image) * glow[..., None]
    rx, ry = 1.3 * w, 1.1 * h
    ys_n = (ys - 0.2 * h) / ry
    xs_n = (xs - 0.3 * w) / rx
    reach = np.sqrt(xs_n**2 + ys_n**2)
    shade = np.clip((reach - 0.55) / 0.45, 0.0, 1.0) * VIGNETTE
    shaded: Array = image * (1 - shade[..., None])
    return shaded


def _second_glow(colors: ThemeColors, side: int) -> NDArray[np.uint8]:
    accent = _rgb(colors.accent)
    second = accent + (_rgb(SECOND_HUE) - accent) * SECOND_SHARE
    distance = _distance(side, side, side / 2, side / 2, side / 2)
    alpha = _glow_alpha(distance, 0.2, 0.06) * 255
    rgba = np.zeros((side, side, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(second, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return rgba


def draw_backdrop(canvas: Size, colors: ThemeColors, folder: Path) -> Backdrop:
    """Draw the background and drifting glow PNGs for one canvas size."""
    rng = np.random.default_rng(SEED)
    folder.mkdir(parents=True, exist_ok=True)
    w, h = canvas.width, canvas.height
    unit = min(w, h) / 1080
    grain = rng.normal(0.0, GRAIN, size=(h, w, 1))
    still = background_array(canvas, colors) + grain
    image_path = folder / f"studio_bg_{w}x{h}.png"
    Image.fromarray(np.clip(np.rint(still), 0, 255).astype(np.uint8), "RGB").save(image_path)
    side = round(1300 * unit)
    glow_path = folder / f"studio_glow_{w}x{h}.png"
    Image.fromarray(_second_glow(colors, side), "RGBA").save(glow_path)
    return Backdrop(
        image_path,
        glow_path,
        glow_x=round(w + 420 * unit - side),
        glow_y=round(h + 760 * unit - side),
        drift=round(DRIFT * unit),
        period=DRIFT_PERIOD,
    )
