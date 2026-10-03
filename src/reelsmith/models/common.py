"""Shared building blocks for the reelsmith file models."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
"""A share of the frame width or height, from 0 to 1."""

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
IDENTIFIER_MESSAGE = "Ids may use letters, numbers, - and _ and start with a letter or number."


def check_identifier(value: str) -> str:
    """Raise ValueError unless value is a safe id. Returns it stripped.

    Ids are used directly in file and folder names (voice/<scene>__<line>.wav,
    slides/<id>_step<n>.png, capture/clips/<id>/ and so on), so this is also
    the rule that keeps an id from ever becoming an unsafe path.
    """
    value = value.strip()
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(IDENTIFIER_MESSAGE)
    return value


Identifier = Annotated[
    str,
    AfterValidator(check_identifier),
    Field(json_schema_extra={"pattern": IDENTIFIER_PATTERN.pattern}),
]
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
