"""The slides.yaml model: slide definitions for produce mode."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from reelsmith.models.common import Identifier, StrictModel, check_unique

SlideKind = Literal["title", "flow", "chart", "bullets"]


class TitleSlide(StrictModel):
    id: Identifier
    kind: Literal["title"]
    title: str
    subtitle: str | None = None


class FlowSlide(StrictModel):
    id: Identifier
    kind: Literal["flow"]
    title: str | None = None
    steps: list[str] = Field(min_length=1)
    exits: list[str] = Field(default_factory=list)


class ChartSlide(StrictModel):
    id: Identifier
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


class BulletsSlide(StrictModel):
    id: Identifier
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
