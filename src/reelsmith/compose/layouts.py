"""Where things go on screen: canvas sizes, device boxes, caption panels.

Everything here is pure geometry. Sizes are whole, even pixels so the
encoder never has to round them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    "browser": (2, 46, 2, 2),  # left, top, right, bottom
    "phone": (18, 18, 18, 18),
}

SIDE_PANEL_SHARE = 0.30
BAND_SHARE = {"16:9": 0.17, "9:16": 0.15, "1:1": 0.17}
POINTS_SIDE_SHARE = 0.31
POINTS_BAND_SHARE = {"16:9": 0.30, "9:16": 0.30, "1:1": 0.33}
STATUS_BAR_SHARE = 0.125  # phone status bar height, as a share of the screen width
SUBTITLE_SHARE = 0.075  # a strip for spoken subtitles under the device


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
    subtitle: Box | None = None  # spoken subtitles when the panel shows points
    inset: Box | None = None  # the footage inside the screen, under a status bar


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


def plan_layout(
    kind: LayoutKind,
    fmt: str,
    canvas: Size,
    src: Size,
    *,
    captions: bool,
    points: bool = False,
    subtitles: bool = False,
    status_bar: bool = False,
) -> Layout:
    """Lay out one scene: the content box, its frame and the caption panel.

    With points, the panel holds curated points beside or below the
    footage, and full footage sits in a box of its own instead of filling
    the canvas. With subtitles too, a strip under the footage holds the
    spoken words. With a status bar, a phone screen is made taller by the
    bar and the footage sits below it, letterboxed and never stretched.
    """
    unit = unit_of(canvas)
    whole = Box(0, 0, canvas.width, canvas.height)
    if kind == "slide" or (kind == "full" and not points):
        content = whole if kind == "slide" else fit(src, whole)
        panel = _band(canvas, fmt) if captions else None
        return Layout(canvas, content, None, None, panel, "band" if panel else None, False, unit)
    strip: Box | None = None
    panel_kind: PanelKind | None
    if points:
        region, panel, panel_kind, strip = _points_regions(kind, fmt, canvas, subtitles)
    else:
        region, panel, panel_kind = _regions(kind, fmt, canvas, captions)
    if kind == "full":
        content = fit(src, region)
        layout = Layout(canvas, content, None, None, panel, panel_kind, False, unit, strip)
        return _group_band(layout) if points else layout
    left, top, right, bottom = (round(v * unit) for v in FRAME_INSETS[kind])
    inner = Box(region.x + left, region.y + top, region.w - left - right, region.h - top - bottom)
    bar = status_bar and kind == "phone"
    screen_src = Size(src.width, src.height + round(src.width * STATUS_BAR_SHARE)) if bar else src
    content = fit(screen_src, inner)
    inset = _below_bar(src, content) if bar else None
    frame = Box(
        content.x - left, content.y - top, content.w + left + right, content.h + top + bottom
    )
    frame_kind: FrameKind = "phone" if kind == "phone" else "browser"
    blurred = kind == "phone" and not points
    layout = Layout(
        canvas, content, frame, frame_kind, panel, panel_kind, blurred, unit, strip, inset
    )
    if not points:
        return layout
    return _group_side(layout) if kind == "phone" else _group_band(layout)


def _below_bar(src: Size, screen: Box) -> Box:
    """Where footage goes inside a phone screen: under the status bar, aspect kept."""
    bar = round(screen.w * STATUS_BAR_SHARE)
    room = fit(src, Box(0, bar, screen.w, screen.h - bar))
    return Box(room.x, bar, room.w, room.h)


def _group_side(layout: Layout) -> Layout:
    """Bring a narrow phone and the side panel together, centred as one group."""
    if layout.panel_kind != "side" or layout.panel is None or layout.frame is None:
        return layout
    m = _margin(layout.canvas)
    gap = 2 * m
    total = layout.frame.w + gap + layout.panel.w
    left = max(m, (layout.canvas.width - total) // 2)
    dx = left - layout.frame.x
    frame, content = layout.frame, layout.content
    return replace(
        layout,
        frame=Box(frame.x + dx, frame.y, frame.w, frame.h),
        content=Box(content.x + dx, content.y, content.w, content.h),
        panel=Box(left + frame.w + gap, layout.panel.y, layout.panel.w, layout.panel.h),
    )


def _moved(box: Box | None, dy: int) -> Box | None:
    return None if box is None else Box(box.x, box.y + dy, box.w, box.h)


def _group_band(layout: Layout) -> Layout:
    """With a band below, centre the device, subtitles and band as one group."""
    if layout.panel_kind != "band" or layout.panel is None:
        return layout
    device = layout.frame or layout.content
    m = _margin(layout.canvas)
    strip_h = layout.subtitle.h + m // 2 if layout.subtitle else 0
    total = device.h + strip_h + m + layout.panel.h
    top = max(m, (layout.canvas.height - total) // 2)
    dy = top - device.y
    panel_y = top + device.h + strip_h + m
    subtitle = layout.subtitle
    if subtitle is not None:
        subtitle = Box(subtitle.x, top + device.h + m // 2, subtitle.w, subtitle.h)
    panel = Box(layout.panel.x, panel_y, layout.panel.w, layout.panel.h)
    return replace(
        layout,
        content=_moved(layout.content, dy) or layout.content,
        frame=_moved(layout.frame, dy),
        panel=panel,
        subtitle=subtitle,
    )


def fit_band(layout: Layout, used: int) -> Layout:
    """Shrink a points band to the height its text uses and centre the group again."""
    if layout.panel_kind != "band" or layout.panel is None or used >= layout.panel.h:
        return layout
    panel = layout.panel
    return _group_band(replace(layout, panel=Box(panel.x, panel.y, panel.w, max(2, used))))


def _margin(canvas: Size) -> int:
    return even(0.05 * min(canvas.width, canvas.height))


def _band(canvas: Size, fmt: str, share: float | None = None) -> Box:
    m = _margin(canvas)
    height = even(canvas.height * (share or BAND_SHARE.get(fmt, 0.17)))
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


def _points_regions(
    kind: LayoutKind, fmt: str, canvas: Size, subtitles: bool
) -> tuple[Box, Box, PanelKind, Box | None]:
    """The device region, the points panel and an optional subtitle strip."""
    m = _margin(canvas)
    strip_h = even(canvas.height * SUBTITLE_SHARE) if subtitles else 0
    side = fmt == "16:9" or (fmt == "1:1" and kind == "phone")
    if side:
        width = even(canvas.width * POINTS_SIDE_SHARE)
        gap = round(1.4 * m)
        panel = Box(canvas.width - m - width, m, width, canvas.height - 2 * m)
        region = Box(m, m, canvas.width - 2 * m - gap - width, canvas.height - 2 * m)
        kind_of: PanelKind = "side"
    else:
        panel = _band(canvas, fmt, POINTS_BAND_SHARE.get(fmt, 0.30))
        region = Box(m, m, canvas.width - 2 * m, panel.y - 2 * m)
        kind_of = "band"
    strip = None
    if subtitles:
        strip = Box(region.x, region.y + region.h - strip_h, region.w, strip_h)
        region = Box(region.x, region.y, region.w, region.h - strip_h - m // 2)
    return region, panel, kind_of, strip


def num(value: float) -> str:
    """A number for an ffmpeg filter: at most 3 decimals, no trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text
