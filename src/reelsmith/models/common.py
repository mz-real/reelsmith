"""Shared building blocks for the reelsmith file models."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
"""A share of the frame width or height, from 0 to 1."""

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""An id such as a scene, line, clip or event id."""


class StrictModel(BaseModel):
    """Base for every file model: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


def check_unique(ids: Iterable[str], kind: str) -> None:
    """Raise ValueError naming the first id that appears twice."""
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise ValueError(f"{kind} id '{item}' is used more than once")
        seen.add(item)
