"""Tests for caption wrapping, fitting, cues and rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reelsmith.compose.captions import (
    CaptionStyle,
    caption_cues,
    find_font,
    fit_text,
    render_caption,
    wrap_text,
)
from reelsmith.compose.layouts import Size
from reelsmith.timing import Placement


def chars(text: str) -> float:
    return 10.0 * len(text)


def test_wrap_keeps_every_line_within_the_width() -> None:
    lines = wrap_text("Type a dish into the search box and press enter", 120, chars)
    assert all(chars(line) <= 120 for line in lines)
    assert " ".join(lines) == "Type a dish into the search box and press enter"


def test_wrap_breaks_a_word_longer_than_the_width() -> None:
    lines = wrap_text("supercalifragilistic", 50, chars)
    assert all(chars(line) <= 50 for line in lines)
    assert "".join(lines) == "supercalifragilistic"


def test_wrap_of_empty_text_is_empty() -> None:
    assert wrap_text("   ", 100, chars) == []


def test_fit_shrinks_the_font_until_text_fits_the_box() -> None:
    text = "Results update as you type, so you can stop as soon as you see it"
    fitted = fit_text(text, 400, 120, None, start_size=60, min_size=12)
    assert fitted.size < 60
    assert len(fitted.lines) * fitted.line_height <= 120
    assert all(width <= 400 for width in fitted.widths)


def test_fit_truncates_with_an_ellipsis_when_even_the_smallest_font_is_too_big() -> None:
    text = " ".join(["word"] * 200)
    fitted = fit_text(text, 120, 40, None, start_size=30, min_size=20)
    assert len(fitted.lines) * fitted.line_height <= 40
    assert fitted.lines[-1].endswith("...")
    assert all(width <= 120 for width in fitted.widths)


def test_caption_cues_follow_placements() -> None:
    placements = [Placement(0, 0.0, 1.5), Placement(1, 1.65, 3.0)]
    cues = caption_cues(["First phrase.", "Second phrase."], placements)
    assert [(c.text, c.start, c.end) for c in cues] == [
        ("First phrase.", 0.0, 1.5),
        ("Second phrase.", 1.65, 3.0),
    ]


def test_short_gaps_between_cues_are_bridged() -> None:
    placements = [Placement(0, 0.0, 1.5), Placement(1, 1.65, 3.0), Placement(2, 5.0, 6.0)]
    cues = caption_cues(["a", "b", "c"], placements, bridge=0.6)
    assert [(c.start, c.end) for c in cues] == [(0.0, 1.65), (1.65, 3.0), (5.0, 6.0)]


def test_find_font_prefers_brand_files(tmp_path: Path) -> None:
    brand_font = tmp_path / "Brand.ttf"
    brand_font.write_bytes(b"not really a font")
    assert find_font([brand_font]) == brand_font


def test_find_font_skips_missing_brand_files(tmp_path: Path) -> None:
    found = find_font([tmp_path / "missing.ttf"])
    assert found is None or found.is_file()


@pytest.mark.parametrize("align", ["left", "center"])
def test_render_caption_writes_a_png_of_the_box_size(tmp_path: Path, align: str) -> None:
    style = CaptionStyle(font=find_font([]), color="#ffffff", background="#00000099")
    out = render_caption(
        "A caption that is long enough to wrap onto more than one line",
        Size(300, 120),
        style,
        tmp_path / "cap.png",
        align=align,  # type: ignore[arg-type]
        start_size=40,
    )
    with Image.open(out) as image:
        assert image.size == (300, 120)
        assert image.mode == "RGBA"
        assert image.getbbox() is not None
