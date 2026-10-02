"""Chart rendering details."""

from __future__ import annotations

from reelsmith.models.slides import ChartSlide
from reelsmith.slides.render import render_slide_html
from reelsmith.slides.themes import SlideTheme


def test_bar_chart_shows_formatted_value_above_bar() -> None:
    theme = SlideTheme(
        background="#fff",
        text="#000",
        primary="#00f",
        secondary="#666",
        accent="#0af",
        muted="#eee",
        font_family="sans-serif",
        font_face_css="",
        logo_uri=None,
    )
    slide = ChartSlide(
        id="stats",
        kind="chart",
        chart_type="bars",
        labels=["A"],
        values=[10.0],
    )
    html = render_slide_html(slide, theme, build_index=None, width=1920, height=1080)
    assert ">10</text>" in html or ">10<" in html
    assert "10.0" not in html
