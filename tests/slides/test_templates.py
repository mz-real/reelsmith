"""Tests for slide template rendering."""

from __future__ import annotations

from reelsmith.models.slides import FlowSlide, TitleSlide
from reelsmith.slides.render import apply_template, render_slide_html
from reelsmith.slides.themes import SlideTheme, theme_styles


def _theme() -> SlideTheme:
    return SlideTheme(
        background="#111111",
        text="#eeeeee",
        primary="#3366cc",
        secondary="#888888",
        accent="#44aaff",
        muted="#222222",
        font_family="system-ui, sans-serif",
        font_face_css="",
        logo_uri=None,
    )


def test_apply_template_fills_named_placeholders() -> None:
    out = apply_template("<p>{{ greeting }} {{ name }}</p>", {"greeting": "Hi", "name": "Sam"})
    assert out == "<p>Hi Sam</p>"


def test_title_slide_html_includes_escaped_title() -> None:
    slide = TitleSlide(id="intro", kind="title", title="Save & share", subtitle="Demo")
    html = render_slide_html(slide, _theme(), build_index=None, width=1920, height=1080)
    assert "Save &amp; share" in html
    assert "Demo" in html
    assert theme_styles(_theme(), 1080).strip() in html or "#111111" in html


def test_flow_arrows_only_between_sequence_steps() -> None:
    slide = FlowSlide(
        id="logic",
        kind="flow",
        steps=["One", "Two", "Three"],
        exits=["Cancel"],
    )
    html = render_slide_html(slide, _theme(), build_index=None, width=1920, height=1080)
    assert html.count('class="flow-arrow"') == 2
    assert "Cancel" in html
    assert html.index("flow-arrow") < html.index("Cancel")
