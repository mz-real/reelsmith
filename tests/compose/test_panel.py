"""Tests for the points panel: markup, reveal timing and layout."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reelsmith.compose.captions import find_font
from reelsmith.compose.layouts import Box
from reelsmith.compose.panel import (
    PanelColors,
    PanelContent,
    Run,
    draw_piece,
    panel_layout,
    parse_markup,
    plain_text,
    reveal_times,
    words_of,
)
from reelsmith.compose.typeface import find_faces
from reelsmith.errors import ReelsmithError
from reelsmith.models import PanelPoint
from reelsmith.timing import Placement

FACES = find_faces([], find_font([]))


def test_stars_mark_accent_words_and_a_backslash_keeps_a_star() -> None:
    assert parse_markup("Find a dish *fast*.") == [
        Run("Find a dish ", False),
        Run("fast", True),
        Run(".", False),
    ]
    assert parse_markup(r"Rated 5\* by *cooks*") == [Run("Rated 5* by ", False), Run("cooks", True)]
    assert plain_text("an *odd star") == "an *odd star"
    assert plain_text("*all* of *it*") == "all of it"


def test_words_keep_mixed_colours_together() -> None:
    words = words_of(parse_markup("save *Favourites*, now"))
    assert words[1] == (Run("Favourites", True), Run(",", False))
    assert len(words) == 3


def test_points_appear_when_their_line_starts() -> None:
    lines = ["l1", "l2", "l2", "l3"]
    placements = [
        Placement(0, 0.0, 1.2),
        Placement(1, 1.5, 2.4),
        Placement(2, 2.6, 3.1),
        Placement(3, 5.25, 6.0),
    ]
    points = [PanelPoint(text="b", line="l2"), PanelPoint(text="c", line="l3")]
    assert reveal_times(points, lines, placements, "s") == [1.5, 5.25]
    with pytest.raises(ReelsmithError, match="line 'l9'"):
        reveal_times([PanelPoint(text="x", line="l9")], lines, placements, "s")


def content(points: int) -> PanelContent:
    texts = [f"Point number {n} says something *useful* about the app" for n in range(points)]
    return PanelContent(
        "Step 2", "Save it for *later*", [(t, n * 2.0) for n, t in enumerate(texts)]
    )


@pytest.mark.parametrize("kind", ["side", "band"])
@pytest.mark.parametrize("count", [1, 4, 9])
def test_the_stack_fits_inside_the_panel(kind: str, count: int) -> None:
    panel = Box(1270, 54, 596, 972) if kind == "side" else Box(54, 1290, 972, 420)
    pieces = panel_layout(content(count), panel, kind, FACES, 1.0)  # type: ignore[arg-type]
    assert [p.kind for p in pieces][:3] == ["eyebrow", "title", "rule"]
    assert sum(p.kind == "point" for p in pieces) == count
    for piece in pieces:
        assert panel.x <= piece.box.x and piece.box.x + piece.box.w <= panel.x + panel.w
        assert panel.y <= piece.box.y and piece.box.y + piece.box.h <= panel.y + panel.h
    tops = [p.box.y for p in pieces]
    assert tops == sorted(tops)
    assert [p.start for p in pieces if p.kind == "point"] == [n * 2.0 for n in range(count)]


def test_a_side_stack_is_centred_and_a_band_stack_starts_at_the_top() -> None:
    side = panel_layout(content(2), Box(0, 0, 600, 1000), "side", FACES, 1.0)
    band = panel_layout(content(2), Box(0, 0, 600, 1000), "band", FACES, 1.0)
    assert side[0].box.y > 200
    assert band[0].box.y == 0


def test_pieces_draw_at_their_box_size_with_the_accent(tmp_path: Path) -> None:
    pieces = panel_layout(content(1), Box(0, 0, 600, 1000), "side", FACES, 1.0)
    colors = PanelColors("#f5f7fa", "#2dd4bf", "#07090d")
    for piece in pieces:
        out = draw_piece(piece, FACES, colors, 1.0, tmp_path / f"{piece.name}.png")
        with Image.open(out) as image:
            assert image.size == (piece.box.w, piece.box.h)
            rgba = np.asarray(image.convert("RGBA")).astype(int)
        accent = (rgba[..., 3] > 200) & (rgba[..., 1] > 150) & (rgba[..., 0] < 120)
        assert accent.any(), piece.name  # every piece shows some accent colour
