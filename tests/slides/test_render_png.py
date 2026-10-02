"""Playwright slide render integration test."""

from __future__ import annotations

from pathlib import Path

from reelsmith.models import BrandModel, SpecModel
from reelsmith.models.slides import SlidesModel
from reelsmith.slides.render import render_slides_to_dir
from reelsmith.slides.themes import frame_size, resolve_theme


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def test_rendered_png_matches_format_size(tmp_path: Path) -> None:
    spec = SpecModel.model_validate(
        {"version": 1, "formats": ["16:9"], "quality": "1080p", "theme": "minimal"}
    )
    slides = SlidesModel.model_validate(
        {
            "version": 1,
            "slides": [{"id": "intro", "kind": "title", "title": "Hello"}],
        }
    )
    brand = BrandModel.model_validate({})
    theme = resolve_theme(spec, brand, tmp_path)
    width, height = frame_size(spec)
    out = tmp_path / "slides"
    written = render_slides_to_dir(slides, theme, out, width=width, height=height)
    assert written == ["intro.png"]
    assert _png_size(out / "intro.png") == (width, height)
