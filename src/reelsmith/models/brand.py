"""The brand.yaml model: logo, colours and font. Every field is optional."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from reelsmith.models.common import StrictModel

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class BrandColors(StrictModel):
    primary: HexColor | None = None
    secondary: HexColor | None = None
    accent: HexColor | None = None
    background: HexColor | None = None
    text: HexColor | None = None


class BrandFont(StrictModel):
    family: str | None = None
    files: list[str] = Field(default_factory=list)  # local font files only


class BrandModel(StrictModel):
    version: Literal[1] = 1
    name: str | None = None
    logo: str | None = None  # path to a local image
    colors: BrandColors = Field(default_factory=BrandColors)
    font: BrandFont = Field(default_factory=BrandFont)
