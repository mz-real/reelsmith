"""Tests for the brand.yaml model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reelsmith.models import BrandModel


def test_an_empty_brand_is_valid() -> None:
    brand = BrandModel.model_validate({})
    assert brand.logo is None
    assert brand.colors.primary is None
    assert brand.font.files == []


def test_a_full_brand_loads() -> None:
    brand = BrandModel.model_validate(
        {
            "version": 1,
            "name": "Recipe Box",
            "logo": "assets/logo.png",
            "colors": {"primary": "#FF6600", "background": "#101010", "text": "#ffffff"},
            "font": {"family": "Inter", "files": ["fonts/Inter.ttf"]},
        }
    )
    assert brand.colors.primary == "#FF6600"
    assert brand.font.family == "Inter"


def test_colours_must_be_hex() -> None:
    with pytest.raises(ValidationError):
        BrandModel.model_validate({"colors": {"primary": "orange"}})
