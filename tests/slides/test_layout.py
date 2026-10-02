"""Layout stability and viewport tests for slide rendering."""

from __future__ import annotations

from reelsmith.models.slides import FlowSlide
from reelsmith.slides.render import element_boxes, format_chart_value, render_slide_html
from reelsmith.slides.themes import SlideTheme


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


def test_format_chart_value_drops_trailing_zero_decimal() -> None:
    assert format_chart_value(10.0) == "10"
    assert format_chart_value(3.5) == "3.5"


def test_first_flow_step_box_aligns_with_final_layout() -> None:
    slide = FlowSlide(
        id="logic",
        kind="flow",
        title="Process",
        steps=["Alpha", "Beta", "Gamma"],
        exits=[],
    )
    theme = _theme()
    width, height = 640, 360
    html_step = render_slide_html(slide, theme, build_index=0, width=width, height=height)
    html_full = render_slide_html(slide, theme, build_index=None, width=width, height=height)
    step_boxes = element_boxes(html_step, width, height, ".flow-step")
    full_boxes = element_boxes(html_full, width, height, ".flow-step")
    assert len(step_boxes) >= 1
    assert len(full_boxes) >= 1
    assert step_boxes[0]["x"] == full_boxes[0]["x"]
    assert step_boxes[0]["width"] == full_boxes[0]["width"]


def test_portrait_flow_stays_inside_viewport() -> None:
    slide = FlowSlide(
        id="mobile",
        kind="flow",
        title="Long flow",
        steps=["One", "Two", "Three", "Four"],
        exits=["Exit"],
    )
    theme = _theme()
    width, height = 1080, 1920
    html = render_slide_html(slide, theme, build_index=None, width=width, height=height)
    selectors = ".flow-step, .flow-arrow, .exit-chip, h1, .flow-row"
    boxes = element_boxes(html, width, height, selectors)
    assert boxes, "expected flow elements to measure"
    for box in boxes:
        assert box["x"] >= 0
        assert box["y"] >= 0
        assert box["x"] + box["width"] <= width
        assert box["y"] + box["height"] <= height
