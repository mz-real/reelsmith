"""Tests for the pure layout geometry."""

from __future__ import annotations

import pytest

from reelsmith.compose.layouts import (
    Box,
    Size,
    canvas_size,
    fit,
    format_slug,
    plan_layout,
    theme_colors,
)
from reelsmith.models import BrandModel


def inside(inner: Box, outer: Box) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.w <= outer.x + outer.w
        and inner.y + inner.h <= outer.y + outer.h
    )


def overlaps(a: Box, b: Box) -> bool:
    return not (a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y)


def test_canvas_sizes_per_format_and_scale() -> None:
    assert canvas_size("16:9", 1.0) == Size(1920, 1080)
    assert canvas_size("9:16", 1.0) == Size(1080, 1920)
    assert canvas_size("1:1", 2.0) == Size(2160, 2160)
    assert canvas_size("16:9", 0.5) == Size(960, 540)


def test_format_slug_is_file_safe() -> None:
    assert format_slug("16:9") == "16x9"
    assert format_slug("1:1") == "1x1"


def test_fit_keeps_aspect_centres_and_uses_even_sizes() -> None:
    box = fit(Size(1171, 2532), Box(0, 0, 1000, 1000))
    assert box.h == 1000
    assert box.w % 2 == 0 and box.h % 2 == 0
    assert abs(box.w / box.h - 1171 / 2532) < 0.01
    assert box.x == (1000 - box.w) // 2


@pytest.mark.parametrize("fmt", ["16:9", "9:16", "1:1"])
@pytest.mark.parametrize("kind", ["phone", "browser"])
def test_device_layouts_fit_on_canvas_and_keep_captions_clear(fmt: str, kind: str) -> None:
    canvas = canvas_size(fmt, 1.0)
    src = Size(1080, 2340) if kind == "phone" else Size(1280, 800)
    layout = plan_layout(kind, fmt, canvas, src, captions=True)  # type: ignore[arg-type]
    whole = Box(0, 0, canvas.width, canvas.height)
    assert layout.frame is not None and layout.panel is not None
    assert inside(layout.content, layout.frame)
    assert inside(layout.frame, whole)
    assert inside(layout.panel, whole)
    assert not overlaps(layout.frame, layout.panel)
    assert layout.frame_kind == kind


def test_wide_formats_put_captions_beside_the_device() -> None:
    layout = plan_layout("phone", "16:9", Size(1920, 1080), Size(1080, 2340), captions=True)
    assert layout.panel_kind == "side"
    assert layout.panel is not None and layout.panel.x > layout.frame.x  # type: ignore[union-attr]


def test_tall_format_puts_captions_in_a_band() -> None:
    layout = plan_layout("browser", "9:16", Size(1080, 1920), Size(1280, 800), captions=True)
    assert layout.panel_kind == "band"


def test_phone_has_a_blurred_background_and_browser_does_not() -> None:
    phone = plan_layout("phone", "16:9", Size(1920, 1080), Size(1080, 2340), captions=True)
    browser = plan_layout("browser", "16:9", Size(1920, 1080), Size(1280, 800), captions=True)
    assert phone.blurred_background
    assert not browser.blurred_background


def test_full_and_slide_fill_the_frame_with_a_bottom_band() -> None:
    for kind in ("full", "slide"):
        layout = plan_layout(kind, "16:9", Size(1920, 1080), Size(1920, 1080), captions=True)  # type: ignore[arg-type]
        assert layout.content == Box(0, 0, 1920, 1080)
        assert layout.frame is None
        assert layout.panel_kind == "band"
        assert layout.panel is not None and layout.panel.y > 540


def test_no_captions_means_no_panel_and_a_bigger_device() -> None:
    with_panel = plan_layout("phone", "16:9", Size(1920, 1080), Size(1080, 2340), captions=True)
    without = plan_layout("browser", "16:9", Size(1920, 1080), Size(1280, 800), captions=False)
    browser = plan_layout("browser", "16:9", Size(1920, 1080), Size(1280, 800), captions=True)
    assert without.panel is None
    assert without.content.w > browser.content.w
    assert with_panel.panel is not None


def test_theme_colors_follow_theme_and_brand_overrides() -> None:
    dark = theme_colors("dark", BrandModel())
    light = theme_colors("light", BrandModel())
    assert dark.background != light.background
    brand = BrandModel.model_validate(
        {"colors": {"background": "#112233", "text": "#ffffff", "accent": "#ff0000"}}
    )
    branded = theme_colors("dark", brand)
    assert branded.background == "#112233"
    assert branded.text == "#ffffff"
    assert branded.accent == "#ff0000"
