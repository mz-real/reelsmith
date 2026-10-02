"""Tests for the script.yaml model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from reelsmith.models import Line, Phrase, ScriptModel, ScriptScene


def script_data(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": 1, "scenes": scenes}


def test_the_documented_example_loads() -> None:
    script = ScriptModel.model_validate(
        script_data(
            [
                {
                    "id": "search",
                    "caption": "Find a recipe fast",
                    "lines": [
                        {
                            "id": "l1",
                            "phrases": [
                                {"text": "Type a dish into the search box.", "pin": "e1"},
                                {"text": "Results update as you type."},
                            ],
                        }
                    ],
                }
            ]
        )
    )
    scene = script.scenes[0]
    assert isinstance(scene, ScriptScene)
    assert isinstance(scene.lines[0], Line)
    assert scene.lines[0].phrases[1] == Phrase(text="Results update as you type.", pin=None)
    assert scene.lines[0].text == "Type a dish into the search box. Results update as you type."
    assert script.scene("search") is scene
    assert script.scene("nope") is None


def test_scene_ids_must_be_unique() -> None:
    scene = {"id": "a", "lines": []}
    with pytest.raises(ValidationError, match="Scene id 'a' is used more than once"):
        ScriptModel.model_validate(script_data([scene, scene]))


def test_line_ids_must_be_unique_in_a_scene() -> None:
    line = {"id": "l1", "phrases": [{"text": "Hi."}]}
    with pytest.raises(ValidationError, match="Line id 'l1' is used more than once"):
        ScriptModel.model_validate(script_data([{"id": "a", "lines": [line, line]}]))


def test_a_line_needs_at_least_one_phrase() -> None:
    with pytest.raises(ValidationError):
        ScriptModel.model_validate(
            script_data([{"id": "a", "lines": [{"id": "l1", "phrases": []}]}])
        )


def test_phrase_text_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        Phrase.model_validate({"text": "   "})
