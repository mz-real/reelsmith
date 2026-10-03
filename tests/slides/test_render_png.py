"""Playwright slide render integration test."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.compose.layouts import format_slug
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
    assert written == ["intro_step0.mp4", "intro_step0.png", "intro.png"]
    assert _png_size(out / "intro.png") == (width, height)
    assert _png_size(out / "intro_step0.png") == (width, height)


def test_multi_format_spec_writes_sized_pngs_per_folder(tmp_path: Path) -> None:
    spec = SpecModel.model_validate(
        {
            "version": 1,
            "formats": ["16:9", "9:16", "1:1"],
            "quality": "1080p",
            "theme": "minimal",
        }
    )
    slides = SlidesModel.model_validate(
        {
            "version": 1,
            "slides": [{"id": "intro", "kind": "title", "title": "Hello"}],
        }
    )
    brand = BrandModel.model_validate({})
    theme = resolve_theme(spec, brand, tmp_path)
    expected = {
        "16x9": frame_size(spec, "16:9"),
        "9x16": frame_size(spec, "9:16"),
        "1x1": frame_size(spec, "1:1"),
    }
    for fmt in spec.formats:
        width, height = frame_size(spec, fmt)
        slug = format_slug(fmt)
        out = tmp_path / "slides" / slug
        render_slides_to_dir(slides, theme, out, width=width, height=height, clips=False)
        assert _png_size(out / "intro.png") == expected[slug]
        assert not (out / "intro_step0.mp4").exists()


def test_render_reports_progress_per_slide(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reelsmith import progress

    spec = SpecModel.model_validate({"version": 1, "formats": ["16:9"], "theme": "minimal"})
    slides = SlidesModel.model_validate(
        {
            "version": 1,
            "slides": [
                {"id": "a", "kind": "title", "title": "One"},
                {"id": "b", "kind": "title", "title": "Two"},
            ],
        }
    )
    theme = resolve_theme(spec, BrandModel.model_validate({}), tmp_path)
    width, height = frame_size(spec)
    progress.configure(force=True)
    try:
        render_slides_to_dir(
            slides, theme, tmp_path / "16x9", width=width, height=height, clips=False
        )
    finally:
        progress.reset()
    lines = capsys.readouterr().err.splitlines()
    assert lines == ["Slides 16x9 1/2: a", "Slides 16x9 2/2: b"]
