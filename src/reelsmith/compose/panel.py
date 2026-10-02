"""The points panel beside or below footage: eyebrow, title and points.

Text may mark words with *stars* to draw them in the accent colour. A
backslash keeps a star as it is: \\*.

Laying out is separate from drawing. panel_layout measures with the real
fonts and returns where every piece goes, so the timeline and QA can use
the same boxes the render draws into.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageColor, ImageDraw

from reelsmith.compose.captions import Font
from reelsmith.compose.layouts import Box, PanelKind
from reelsmith.compose.typeface import Face, Faces
from reelsmith.errors import ReelsmithError
from reelsmith.models import PanelPoint
from reelsmith.slides.markup import Run, parse_markup, plain_text
from reelsmith.timing import Placement

EYEBROW_SIZE = 21  # all sizes at 1080p
TITLE_SIZE = 62
POINT_SIZE = 31
EYEBROW_TRACKING = 0.12  # letter spacing, as a share of the font size
TITLE_LEADING = 1.12
POINT_LEADING = 1.34
EYEBROW_GAP = 18
TITLE_GAP = 22
RULE_W, RULE_H, RULE_GAP = 44, 4, 34
POINT_GAP = 24
BULLET = 10  # bullet diameter
BULLET_INDENT = 32
MIN_SCALE = 0.45
REVEAL_SECONDS = 0.55
REVEAL_RISE = 18
ENTRANCE_START = 0.1
POINT_TEXT_SHARE = 0.86  # point text is this share of the way from background to text colour

PieceKind = Literal["eyebrow", "title", "rule", "point"]


Word = tuple[Run, ...]


def words_of(runs: Sequence[Run]) -> list[Word]:
    """Words for wrapping, each a tuple of runs so a word can mix colours."""
    words: list[Word] = []
    current: list[Run] = []
    for run in runs:
        piece = ""
        for ch in run.text:
            if ch.isspace():
                if piece:
                    current.append(Run(piece, run.accent))
                    piece = ""
                if current:
                    words.append(tuple(current))
                    current = []
                continue
            piece += ch
        if piece:
            current.append(Run(piece, run.accent))
    if current:
        words.append(tuple(current))
    return words


def word_width(word: Word, font: Font) -> float:
    return sum(font.getlength(run.text) for run in word)


def wrap_words(words: Sequence[Word], width: float, font: Font) -> list[list[Word]]:
    """Greedy wrap. A word wider than the line gets a line of its own."""
    space = font.getlength(" ")
    lines: list[list[Word]] = []
    line: list[Word] = []
    used = 0.0
    for word in words:
        size = word_width(word, font)
        if line and used + space + size > width:
            lines.append(line)
            line, used = [], 0.0
        used = size if not line else used + space + size
        line.append(word)
    if line:
        lines.append(line)
    return lines


def balanced_wrap(words: Sequence[Word], width: float, font: Font) -> list[list[Word]]:
    """Wrap into as few lines as greedy wrapping needs, but with even lengths,
    so a last line is never one lonely word."""
    lines = wrap_words(words, width, font)
    if len(lines) < 2:
        return lines
    low, high = width / len(lines), width
    for _ in range(12):
        middle = (low + high) / 2
        if len(wrap_words(words, middle, font)) == len(lines):
            high = middle
        else:
            low = middle
    return wrap_words(words, high, font)


def reveal_times(
    points: Sequence[PanelPoint],
    line_ids: Sequence[str],
    placements: Sequence[Placement],
    scene_id: str,
) -> list[float]:
    """When each point appears: the start of the first phrase of its line."""
    starts: dict[str, float] = {}
    for line_id, placement in zip(line_ids, placements, strict=True):
        starts.setdefault(line_id, placement.out_start)
    times = []
    for point in points:
        if point.line not in starts:
            raise ReelsmithError(
                f"Scene '{scene_id}' has a point for line '{point.line}',"
                " but that line is not in the scene's script",
                fix="Use a line id from script.yaml for this scene",
            )
        times.append(starts[point.line])
    return times


@dataclass(frozen=True)
class PanelContent:
    eyebrow: str | None
    title: str | None
    points: list[tuple[str, float]]  # text and reveal time


@dataclass(frozen=True)
class Piece:
    """One drawn piece of the panel and where it goes on the canvas."""

    name: str
    kind: PieceKind
    text: str
    box: Box
    start: float  # when it starts to appear
    size: int  # font size in pixels
    lines: list[list[Word]]


@dataclass(frozen=True)
class PanelColors:
    text: str
    accent: str
    background: str


def _sizes(unit: float, scale: float) -> dict[str, int]:
    k = unit * scale
    return {
        "eyebrow": max(8, round(EYEBROW_SIZE * k)),
        "title": max(10, round(TITLE_SIZE * k)),
        "point": max(8, round(POINT_SIZE * k)),
    }


def _stack(
    content: PanelContent, width: int, faces: Faces, unit: float, scale: float
) -> list[tuple[PieceKind, str, int, int, list[list[Word]], int, float]]:
    """Kind, text, font size, height, lines, gap after and start of each piece."""
    sizes = _sizes(unit, scale)
    k = unit * scale
    out: list[tuple[PieceKind, str, int, int, list[list[Word]], int, float]] = []
    if content.eyebrow:
        size = sizes["eyebrow"]
        out.append(
            (
                "eyebrow",
                content.eyebrow,
                size,
                round(size * 1.3),
                [],
                round(EYEBROW_GAP * k),
                ENTRANCE_START,
            )
        )
    if content.title:
        size = sizes["title"]
        font = faces.bold.load(size)
        lines = balanced_wrap(words_of(parse_markup(content.title)), width, font)
        height = round(len(lines) * size * TITLE_LEADING)
        out.append(
            ("title", content.title, size, height, lines, round(TITLE_GAP * k), ENTRANCE_START)
        )
        out.append(
            ("rule", "", size, max(2, round(RULE_H * k)), [], round(RULE_GAP * k), ENTRANCE_START)
        )
    size = sizes["point"]
    font = faces.regular.load(size)
    indent = round(BULLET_INDENT * k)
    for text, start in content.points:
        lines = balanced_wrap(words_of(parse_markup(text)), width - indent, font)
        height = round(len(lines) * size * POINT_LEADING)
        out.append(("point", text, size, height, lines, round(POINT_GAP * k), start))
    return out  # fmt: skip


def panel_layout(
    content: PanelContent, panel: Box, kind: PanelKind, faces: Faces, unit: float
) -> list[Piece]:
    """Where each piece goes. Text shrinks until the whole stack fits the panel."""
    scale = 1.0
    while True:
        stack = _stack(content, panel.w, faces, unit, scale)
        total = sum(height + gap for _, _, _, height, _, gap, _ in stack)
        total -= stack[-1][5] if stack else 0
        if total <= panel.h or scale <= MIN_SCALE:
            break
        scale = max(MIN_SCALE, scale * 0.92)
    y = panel.y + (max(0, panel.h - total) // 2 if kind == "side" else 0)
    pieces: list[Piece] = []
    counts: dict[str, int] = {}
    for piece_kind, text, size, height, lines, gap, start in stack:
        number = counts.get(piece_kind, 0)
        counts[piece_kind] = number + 1
        name = piece_kind if piece_kind != "point" else f"point_{number}"
        width = panel.w if piece_kind != "rule" else max(4, round(RULE_W * unit * scale))
        pieces.append(
            Piece(name, piece_kind, text, Box(panel.x, y, width, height), start, size, lines)
        )
        y += height + gap
    return pieces


def _mix(a: str, b: str, share: float) -> tuple[int, int, int]:
    """share of the way from colour a to colour b."""
    ra, ga, ba = ImageColor.getrgb(a)[:3]
    rb, gb, bb = ImageColor.getrgb(b)[:3]
    return (
        round(ra + (rb - ra) * share),
        round(ga + (gb - ga) * share),
        round(ba + (bb - ba) * share),
    )


def draw_piece(piece: Piece, faces: Faces, colors: PanelColors, unit: float, dest: Path) -> Path:
    """Draw one piece into a transparent PNG of exactly its box size."""
    image = Image.new("RGBA", (piece.box.w, piece.box.h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = ImageColor.getrgb(colors.accent)[:3]
    if piece.kind == "eyebrow":
        _draw_tracked(draw, plain_text(piece.text).upper(), faces.medium, piece.size, accent)
    elif piece.kind == "rule":
        draw.rounded_rectangle(
            (0, 0, piece.box.w - 1, piece.box.h - 1), piece.box.h // 2, fill=(*accent, 255)
        )
    elif piece.kind == "title":
        text = ImageColor.getrgb(colors.text)[:3]
        _draw_lines(draw, piece, faces.bold, text, accent, TITLE_LEADING, 0)
    else:
        text = _mix(colors.background, colors.text, POINT_TEXT_SHARE)
        indent = round(BULLET_INDENT * piece.size / POINT_SIZE)
        _draw_lines(draw, piece, faces.regular, text, accent, POINT_LEADING, indent)
        _bullet(image, piece, accent)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def _draw_tracked(
    draw: ImageDraw.ImageDraw, text: str, face: Face, size: int, color: tuple[int, int, int]
) -> None:
    """Draw text with letter spacing, as small caps eyebrow labels use."""
    font = face.load(size)
    spacing = size * EYEBROW_TRACKING
    x = 0.0
    y = round(size * 0.15)
    for ch in text:
        draw.text(
            (x, y), ch, font=font, fill=color, stroke_width=face.stroke(size), stroke_fill=color
        )
        x += font.getlength(ch) + spacing


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    piece: Piece,
    face: Face,
    text: tuple[int, int, int],
    accent: tuple[int, int, int],
    leading: float,
    indent: int,
) -> None:
    font = face.load(piece.size)
    space = font.getlength(" ")
    stroke = face.stroke(piece.size)
    line_height = piece.size * leading
    for number, line in enumerate(piece.lines):
        x = float(indent)
        y = number * line_height + (line_height - piece.size) / 2
        for word in line:
            for run in word:
                color = accent if run.accent else text
                draw.text(
                    (x, y), run.text, font=font, fill=color, stroke_width=stroke, stroke_fill=color
                )
                x += font.getlength(run.text)
            x += space


def _bullet(image: Image.Image, piece: Piece, accent: tuple[int, int, int]) -> None:
    """An accent dot with a soft halo, centred on the first line."""
    s = 4
    k = piece.size / POINT_SIZE
    radius = BULLET * k / 2
    halo = radius * 2.1
    line_height = piece.size * POINT_LEADING
    cy = line_height / 2 + piece.size * 0.06
    cx = halo + 1
    side = round(2 * halo + 2)
    layer = Image.new("RGBA", (side * s, side * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    c = side * s / 2
    draw.ellipse((c - halo * s, c - halo * s, c + halo * s, c + halo * s), fill=(*accent, 48))
    draw.ellipse(
        (c - radius * s, c - radius * s, c + radius * s, c + radius * s), fill=(*accent, 255)
    )
    small = layer.resize((side, side), Image.Resampling.LANCZOS)
    image.alpha_composite(small, (max(0, round(cx - side / 2)), max(0, round(cy - side / 2))))
