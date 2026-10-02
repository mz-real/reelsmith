"""Where things go on screen: canvas sizes, device boxes, caption panels.

Everything here is pure geometry. Sizes are whole, even pixels so the
encoder never has to round them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reelsmith.models import BrandModel

LayoutKind = Literal["slide", "phone", "browser", "full"]
FrameKind = Literal["browser", "phone"]
PanelKind = Literal["side", "band"]

FORMAT_SIZES: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}

# Frame borders around the screen, in pixels at 1080p.
FRAME_INSETS: dict[str, tuple[int, int, int, int]] = {
    "browser": (8, 52, 8, 8),  # left, top, right, bottom
    "phone": (22, 22, 22, 22),
}

SIDE_PANEL_SHARE = 0.30
BAND_SHARE = {"16:9": 0.17, "9:16": 0.15, "1:1": 0.17}


@dataclass(frozen=True)
class Size:
    width: int
    height: int


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Layout:
    canvas: Size
    content: Box
    frame: Box | None
    frame_kind: FrameKind | None
    panel: Box | None
    panel_kind: PanelKind | None
    blurred_background: bool
    unit: float  # pixels per 1080p pixel


@dataclass(frozen=True)
class ThemeColors:
    background: str
    text: str
    accent: str


THEMES: dict[str, ThemeColors] = {
    "studio": ThemeColors("#05070a", "#f5f7fa", "#2dd4bf"),
    "dark": ThemeColors("#0f172a", "#f8fafc", "#38bdf8"),
    "light": ThemeColors("#f1f5f9", "#0f172a", "#2563eb"),
    "minimal": ThemeColors("#ffffff", "#111827", "#111827"),
}


def even(value: float) -> int:
    """Round to the nearest even whole number, never below 2."""
    return max(2, 2 * round(value / 2))


def format_slug(fmt: str) -> str:
    """A file safe name for a format: 16:9 becomes 16x9."""
    return fmt.replace(":", "x")


def canvas_size(fmt: str, scale: float) -> Size:
    width, height = FORMAT_SIZES[fmt]
    return Size(even(width * scale), even(height * scale))


def unit_of(canvas: Size) -> float:
    return min(canvas.width, canvas.height) / 1080


def fit(src: Size, region: Box) -> Box:
    """The largest box with the aspect of src, centred in region."""
    scale = min(region.w / src.width, region.h / src.height)
    w = min(even(src.width * scale), region.w - region.w % 2)
    h = min(even(src.height * scale), region.h - region.h % 2)
    return Box(region.x + (region.w - w) // 2, region.y + (region.h - h) // 2, w, h)


def theme_colors(theme: str, brand: BrandModel) -> ThemeColors:
    """Theme colours with any brand.yaml colours on top."""
    base = THEMES.get(theme, THEMES["dark"])
    colors = brand.colors
    return ThemeColors(
        background=colors.background or base.background,
        text=colors.text or base.text,
        accent=colors.accent or colors.primary or base.accent,
    )


def plan_layout(kind: LayoutKind, fmt: str, canvas: Size, src: Size, *, captions: bool) -> Layout:
    """Lay out one scene: the content box, its frame and the caption panel."""
    unit = unit_of(canvas)
    whole = Box(0, 0, canvas.width, canvas.height)
    if kind in ("slide", "full"):
        content = whole if kind == "slide" else fit(src, whole)
        panel = _band(canvas, fmt) if captions else None
        return Layout(canvas, content, None, None, panel, "band" if panel else None, False, unit)
    region, panel, panel_kind = _regions(kind, fmt, canvas, captions)
    left, top, right, bottom = (round(v * unit) for v in FRAME_INSETS[kind])
    inner = Box(region.x + left, region.y + top, region.w - left - right, region.h - top - bottom)
    content = fit(src, inner)
    frame = Box(
        content.x - left, content.y - top, content.w + left + right, content.h + top + bottom
    )
    frame_kind: FrameKind = "phone" if kind == "phone" else "browser"
    return Layout(canvas, content, frame, frame_kind, panel, panel_kind, kind == "phone", unit)


def _margin(canvas: Size) -> int:
    return even(0.05 * min(canvas.width, canvas.height))


def _band(canvas: Size, fmt: str) -> Box:
    m = _margin(canvas)
    height = even(canvas.height * BAND_SHARE.get(fmt, 0.17))
    return Box(m, canvas.height - m - height, canvas.width - 2 * m, height)


def _regions(
    kind: LayoutKind, fmt: str, canvas: Size, captions: bool
) -> tuple[Box, Box | None, PanelKind | None]:
    """The device region and the caption panel beside or below it."""
    m = _margin(canvas)
    if not captions:
        return Box(m, m, canvas.width - 2 * m, canvas.height - 2 * m), None, None
    side = fmt == "16:9" or (fmt == "1:1" and kind == "phone")
    if side:
        width = even(canvas.width * SIDE_PANEL_SHARE)
        panel = Box(canvas.width - m - width, m, width, canvas.height - 2 * m)
        region = Box(m, m, canvas.width - 3 * m - width, canvas.height - 2 * m)
        return region, panel, "side"
    band = _band(canvas, fmt)
    region = Box(m, m, canvas.width - 2 * m, band.y - 2 * m)
    return region, band, "band"


def num(value: float) -> str:
    """A number for an ffmpeg filter: at most 3 decimals, no trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text
