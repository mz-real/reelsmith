"""The slides.yaml model: slide definitions for produce mode.

Every text field accepts ``*accent*`` markup: the words between stars are
drawn in the accent colour. Write ``\\*`` for a plain star.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from reelsmith.models.common import Identifier, StrictModel, check_unique

SlideKind = Literal["title", "flow", "chart", "bullets"]
StepStyle = Literal["dim", "reveal"]


class SlideBase(StrictModel):
    """Fields every slide kind shares."""

    id: Identifier
    eyebrow: str | None = None  # small label above the title
    subtitle: str | None = None
    chapter: int | None = Field(default=None, ge=0, le=99)  # big faded number, top right
    step_style: StepStyle = "dim"  # future steps: dimmed, or hidden until they build in


class TitleSlide(SlideBase):
    kind: Literal["title"]
    title: str


class FlowStep(StrictModel):
    title: str
    detail: str | None = None


class FlowSlide(SlideBase):
    kind: Literal["flow"]
    title: str | None = None
    steps: list[str | FlowStep] = Field(min_length=1)
    exits: list[str] = Field(default_factory=list)

    def step_items(self) -> list[FlowStep]:
        """Every step as a card, turning plain strings into titles."""
        return [s if isinstance(s, FlowStep) else FlowStep(title=s) for s in self.steps]

    def step_titles(self) -> list[str]:
        return [item.title for item in self.step_items()]


class ChartSlide(SlideBase):
    kind: Literal["chart"]
    title: str | None = None
    chart_type: Literal["bars", "lines"]
    labels: list[str] = Field(min_length=1)
    values: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _labels_match_values(self) -> Self:
        if len(self.labels) != len(self.values):
            raise ValueError("Chart labels and values must be the same length")
        return self


class BulletsSlide(SlideBase):
    kind: Literal["bullets"]
    title: str | None = None
    items: list[str] = Field(min_length=1)


SlideItem = Annotated[
    TitleSlide | FlowSlide | ChartSlide | BulletsSlide,
    Field(discriminator="kind"),
]


class SlidesModel(StrictModel):
    version: Literal[1] = 1
    slides: list[SlideItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_slide_ids(self) -> Self:
        check_unique((slide.id for slide in self.slides), "Slide")
        return self

    def slide(self, slide_id: str) -> SlideItem | None:
        return next((item for item in self.slides if item.id == slide_id), None)
