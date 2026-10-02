"""The clip.json model: one recorded clip and its events."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from reelsmith.models.common import Fraction, Identifier, StrictModel, check_unique

EventType = Literal["click", "tap", "key", "scroll", "screen", "back"]
POSITIONED_TYPES = ("click", "tap")


class Event(StrictModel):
    id: Identifier
    t: float = Field(ge=0.0)
    type: EventType
    x: Fraction | None = None
    y: Fraction | None = None
    label: str | None = None

    @model_validator(mode="after")
    def _position_rules(self) -> Self:
        if (self.x is None) != (self.y is None):
            raise ValueError(f"Event '{self.id}' needs both x and y, or neither")
        if self.type in POSITIONED_TYPES and self.x is None:
            raise ValueError(f"Event '{self.id}' is a {self.type}, so it needs x and y")
        return self


class ClipModel(StrictModel):
    id: Identifier
    video: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0.0)
    duration: float = Field(ge=0.0)
    events: list[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def _events_fit(self) -> Self:
        check_unique((event.id for event in self.events), "Event")
        for event in self.events:
            if event.t > self.duration + 1e-6:
                raise ValueError(
                    f"Event '{event.id}' at {event.t:g} s is after the end of the clip"
                    f" ({self.duration:g} s)"
                )
        return self

    def event(self, event_id: str) -> Event | None:
        return next((e for e in self.events if e.id == event_id), None)
