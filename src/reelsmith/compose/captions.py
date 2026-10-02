"""Burned captions: font lookup, wrapping to the panel and PNG rendering.

Captions are drawn with Pillow into transparent PNGs that compose then
overlays at the right times. Measuring with the real font means a caption
is wrapped to the panel width and never runs off its edge.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageColor, ImageDraw, ImageFont

from reelsmith.compose.layouts import Size
from reelsmith.timing import Placement

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
Align = Literal["left", "center"]
VAlign = Literal["top", "middle"]

LINE_SPACING = 1.3
ELLIPSIS = "..."


def _system_fonts() -> list[Path]:
    system = platform.system()
    if system == "Darwin":
        names = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/SFNS.ttf",
        ]
    elif system == "Windows":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        return [fonts / "segoeui.ttf", fonts / "arial.ttf", fonts / "calibri.ttf"]
    else:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        ]
    return [Path(name) for name in names]


def find_font(brand_files: Sequence[Path]) -> Path | None:
    """The first brand font file that exists, else a common system font.

    Returns None when nothing is found, and Pillow's built in font is used.
    """
    for path in [*brand_files, *_system_fonts()]:
        if path.is_file():
            return path
    return None


def load_font(path: Path | None, size: int) -> Font:
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def wrap_text(text: str, max_width: float, measure: Callable[[str], float]) -> list[str]:
    """Greedy word wrap. A word wider than the line is split by characters."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if measure(candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        for piece in _split_long_word(word, max_width, measure):
            if current:
                lines.append(current)
            current = piece
    if current:
        lines.append(current)
    return lines


def _split_long_word(word: str, max_width: float, measure: Callable[[str], float]) -> list[str]:
    pieces: list[str] = []
    piece = ""
    for char in word:
        if piece and measure(piece + char) > max_width:
            pieces.append(piece)
            piece = ""
        piece += char
    if piece:
        pieces.append(piece)
    return pieces


@dataclass(frozen=True)
class Fitted:
    size: int
    lines: list[str]
    widths: list[float]
    line_height: int


def fit_text(
    text: str,
    width: int,
    height: int,
    font_path: Path | None,
    *,
    start_size: int,
    min_size: int,
) -> Fitted:
    """Pick the biggest font size whose wrapped lines fit the box."""
    size = start_size
    while True:
        font = load_font(font_path, size)
        line_height = round(size * LINE_SPACING)
        lines = wrap_text(text, width, font.getlength)
        if len(lines) * line_height <= height or size <= min_size:
            break
        size = max(min_size, size - max(1, size // 12))
    max_lines = max(1, height // line_height)
    if len(lines) > max_lines:
        lines = _truncate(lines[:max_lines], width, font)
    widths = [font.getlength(line) for line in lines]
    return Fitted(size, lines, widths, line_height)


def _truncate(lines: list[str], width: int, font: Font) -> list[str]:
    last = lines[-1]
    while last and font.getlength(last + ELLIPSIS) > width:
        last = last[:-1].rstrip()
    return [*lines[:-1], last + ELLIPSIS]


@dataclass(frozen=True)
class CaptionStyle:
    font: Path | None
    color: str
    background: str | None = None  # "#rrggbbaa" box behind the text


def render_caption(
    text: str,
    size: Size,
    style: CaptionStyle,
    dest: Path,
    *,
    align: Align = "left",
    valign: VAlign = "middle",
    start_size: int = 44,
) -> Path:
    """Draw text wrapped into a transparent PNG of exactly size."""
    image = Image.new("RGBA", (size.width, size.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = round(min(size.width, size.height) * 0.12) if style.background else 0
    if style.background:
        radius = max(2, round(min(size.width, size.height) * 0.12))
        fill = ImageColor.getrgb(style.background)
        draw.rounded_rectangle((0, 0, size.width - 1, size.height - 1), radius, fill=fill)
    inner_w, inner_h = size.width - 2 * pad, size.height - 2 * pad
    fitted = fit_text(
        text, inner_w, inner_h, style.font, start_size=start_size, min_size=max(8, start_size // 3)
    )
    font = load_font(style.font, fitted.size)
    block = len(fitted.lines) * fitted.line_height
    top = pad if valign == "top" else pad + (inner_h - block) // 2
    color = ImageColor.getrgb(style.color)
    for number, (line, width) in enumerate(zip(fitted.lines, fitted.widths, strict=True)):
        x = pad if align == "left" else pad + (inner_w - width) / 2
        y = top + number * fitted.line_height + (fitted.line_height - fitted.size) / 2
        draw.text((x, y), line, font=font, fill=color)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


@dataclass(frozen=True)
class CaptionCue:
    text: str
    start: float
    end: float


def caption_cues(
    texts: Sequence[str], placements: Sequence[Placement], bridge: float = 0.0
) -> list[CaptionCue]:
    """One cue per phrase, on screen while that phrase is spoken.

    A gap shorter than bridge before the next phrase is filled, so the
    caption does not blink off between phrases.
    """
    cues = [
        CaptionCue(text, placement.out_start, placement.out_end)
        for text, placement in zip(texts, placements, strict=True)
    ]
    for number in range(len(cues) - 1):
        cue, following = cues[number], cues[number + 1]
        if 0 <= following.start - cue.end <= bridge:
            cues[number] = CaptionCue(cue.text, cue.start, following.start)
    return cues
