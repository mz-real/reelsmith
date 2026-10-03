"""Tests for shared model building blocks: Identifier and check_unique."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reelsmith.models.clip import ClipModel
from reelsmith.models.common import IDENTIFIER_MESSAGE, check_identifier, check_unique


@pytest.mark.parametrize("value", ["a", "A1", "a-b_c", "9ab", "a" * 64])
def test_check_identifier_accepts_safe_ids(value: str) -> None:
    assert check_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    ["../x", "a/b", "a\\b", ".", "..", "", " ", "a b", "a.b", "-a", "_a", "a" * 65],
)
def test_check_identifier_rejects_unsafe_ids(value: str) -> None:
    with pytest.raises(ValueError) as info:
        check_identifier(value)
    assert str(info.value) == IDENTIFIER_MESSAGE


def test_check_identifier_strips_surrounding_whitespace() -> None:
    assert check_identifier("  a1  ") == "a1"


def test_a_model_field_rejects_an_unsafe_id_with_a_clear_message() -> None:
    with pytest.raises(ValidationError) as info:
        ClipModel.model_validate(
            {
                "id": "../x",
                "video": "video.mp4",
                "width": 10,
                "height": 10,
                "fps": 30,
                "duration": 1.0,
            }
        )
    assert IDENTIFIER_MESSAGE in str(info.value)


def test_check_unique_names_the_first_duplicate() -> None:
    with pytest.raises(ValueError, match="thing id 'b' is used more than once"):
        check_unique(["a", "b", "b", "c"], "thing")
