"""Tests for slide build step cue counts."""

from __future__ import annotations

from reelsmith.models.slides import BulletsSlide, ChartSlide, FlowSlide, TitleSlide
from reelsmith.slides.render import step_cue_count


def test_flow_step_cues_are_steps_minus_one() -> None:
    slide = FlowSlide(id="f", kind="flow", steps=["a", "b", "c"])
    assert step_cue_count(slide) == 2


def test_bullets_step_cues_are_items_minus_one() -> None:
    slide = BulletsSlide(id="b", kind="bullets", items=["one", "two"])
    assert step_cue_count(slide) == 1


def test_title_and_chart_have_no_step_cues() -> None:
    assert step_cue_count(TitleSlide(id="t", kind="title", title="Hi")) == 0
    assert (
        step_cue_count(
            ChartSlide(
                id="c",
                kind="chart",
                chart_type="bars",
                labels=["A"],
                values=[1.0],
            )
        )
        == 0
    )
