"""Tests for brand and theme merging."""

from __future__ import annotations

from pathlib import Path

from reelsmith.models import BrandModel, SpecModel
from reelsmith.slides.themes import resolve_theme


def test_brand_colours_override_the_spec_theme(tmp_path: Path) -> None:
    spec = SpecModel.model_validate({"version": 1, "theme": "dark", "formats": ["16:9"]})
    brand = BrandModel.model_validate(
        {
            "colors": {
                "background": "#010101",
                "text": "#fefefe",
                "primary": "#ff0000",
            }
        }
    )
    theme = resolve_theme(spec, brand, tmp_path)
    assert theme.background == "#010101"
    assert theme.text == "#fefefe"
    assert theme.primary == "#ff0000"
