"""Tests for the spec.yaml model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel, load_model

SPEC_YAML = """\
version: 1
mode: produce
goal: Show how to save a favourite recipe
audience: customers
target_seconds: 90
formats: ["16:9"]
quality: 1080p
theme: dark
footage: web
voice:
  engine: kokoro
  kokoro_voice: af_heart
  speed: 1.0
  sample: null
  consent: null
options:
  allow_holds: true
  speed_up_waits: false
  captions: burned
  highlight_clicks: true
scenes:
  - id: intro
    layout: slide
    slide: intro
  - id: search
    layout: browser
    clip: search
blur:
  - clip: search
    box: [0.05, 0.10, 0.30, 0.06]
    start: 0.0
    end: null
"""


def base_spec(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "goal": "Show search",
        "scenes": [{"id": "search", "layout": "browser", "clip": "search"}],
    }
    data.update(changes)
    return data


def test_the_documented_example_loads(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(SPEC_YAML, encoding="utf-8")

    spec = load_model(path, SpecModel)

    assert spec.mode == "produce"
    assert spec.voice.engine == "kokoro"
    assert spec.voice.kokoro_voice == "af_heart"
    assert spec.options.captions == "burned"
    assert [s.id for s in spec.scenes] == ["intro", "search"]
    assert spec.scenes[0].slide == "intro"
    assert spec.blur[0].box == (0.05, 0.10, 0.30, 0.06)
    assert spec.blur[0].end is None


def test_defaults_match_the_plan() -> None:
    spec = SpecModel.model_validate(base_spec())

    assert spec.version == 1
    assert spec.formats == ["16:9"]
    assert spec.quality == "1080p"
    assert spec.voice.engine == "kokoro"
    assert spec.voice.kokoro_voice == "af_heart"
    assert spec.options.allow_holds is True
    assert spec.options.speed_up_waits is False
    assert spec.options.transition == "fade"


def test_chatterbox_without_consent_fails_with_a_clear_message(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        SPEC_YAML.replace("engine: kokoro", "engine: chatterbox").replace(
            "sample: null", "sample: me.wav"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReelsmithError) as info:
        load_model(path, SpecModel)

    assert "Cloning needs a voice sample and consent." in str(info.value)
    assert "voice" in str(info.value)


def test_chatterbox_without_sample_fails() -> None:
    data = base_spec(voice={"engine": "chatterbox", "consent": "own"})
    with pytest.raises(ValidationError, match="Cloning needs a voice sample and consent."):
        SpecModel.model_validate(data)


def test_chatterbox_with_sample_and_consent_loads() -> None:
    data = base_spec(voice={"engine": "chatterbox", "sample": "me.wav", "consent": "permission"})
    spec = SpecModel.model_validate(data)
    assert spec.voice.consent == "permission"


def test_scene_ids_must_be_unique() -> None:
    scenes = [
        {"id": "search", "layout": "browser", "clip": "a"},
        {"id": "search", "layout": "full", "clip": "b"},
    ]
    with pytest.raises(ValidationError, match="Scene id 'search' is used more than once"):
        SpecModel.model_validate(base_spec(scenes=scenes))


def test_slide_scene_needs_a_slide() -> None:
    scenes = [{"id": "intro", "layout": "slide"}]
    with pytest.raises(ValidationError, match="needs a slide"):
        SpecModel.model_validate(base_spec(scenes=scenes))


@pytest.mark.parametrize("layout", ["phone", "browser", "full"])
def test_clip_layouts_need_a_clip(layout: str) -> None:
    scenes = [{"id": "s", "layout": layout}]
    with pytest.raises(ValidationError, match="needs a clip"):
        SpecModel.model_validate(base_spec(scenes=scenes))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="colour"):
        SpecModel.model_validate(base_spec(colour="red"))


def test_blur_box_must_be_fractions() -> None:
    blur = [{"clip": "search", "box": [0.1, 0.1, 1.5, 0.1]}]
    with pytest.raises(ValidationError):
        SpecModel.model_validate(base_spec(blur=blur))


def test_bad_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SpecModel.model_validate(base_spec(formats=["4:3"]))


def test_voice_vocabulary_defaults_to_empty_and_can_be_filled() -> None:
    assert SpecModel().voice.vocabulary == []
    spec = SpecModel.model_validate({"voice": {"vocabulary": ["reelsmith", "kokoro"]}})
    assert spec.voice.vocabulary == ["reelsmith", "kokoro"]


def test_voice_pronounce_defaults_to_empty_and_can_be_filled() -> None:
    assert SpecModel().voice.pronounce == {}
    spec = SpecModel.model_validate({"voice": {"pronounce": {"reelsmith": "ɹˈiːl smɪθ"}}})
    assert spec.voice.pronounce == {"reelsmith": "ɹˈiːl smɪθ"}


def test_voice_pronounce_key_must_be_a_single_word() -> None:
    with pytest.raises(ValidationError, match="single word"):
        SpecModel.model_validate({"voice": {"pronounce": {"reel smith": "ɹˈiːl smɪθ"}}})


def test_voice_pronounce_key_cannot_be_blank() -> None:
    with pytest.raises(ValidationError, match="single word"):
        SpecModel.model_validate({"voice": {"pronounce": {"   ": "ɹˈiːl smɪθ"}}})


def motion_scene(**changes: Any) -> dict[str, Any]:
    scene: dict[str, Any] = {"id": "fav", "layout": "browser", "clip": "fav"}
    scene.update(changes)
    return scene


def test_scene_points_zoom_and_cursor_load_from_yaml() -> None:
    text = """
id: fav
layout: phone
clip: fav
eyebrow: Step 3
title: Save it for *later*
points:
  - text: One click adds it to *Favourites*
    line: fav-1
  - {text: Saved dishes get a tab, line: fav-2}
zoom:
  - box: [0.1, 0.2, 0.4, 0.3]
    at: e2
  - {box: [0.5, 0.5, 0.5, 0.5], at: 3.25, hold: 0.5}
cursor: false
"""
    spec = SpecModel.model_validate(base_spec(scenes=[yaml.safe_load(text)]))
    scene = spec.scenes[0]
    assert scene.eyebrow == "Step 3"
    assert scene.title == "Save it for *later*"
    assert [(p.text, p.line) for p in scene.points][1] == ("Saved dishes get a tab", "fav-2")
    assert scene.zoom[0].at == "e2" and scene.zoom[0].hold == 1.5
    assert scene.zoom[1].at == 3.25 and scene.zoom[1].hold == 0.5
    assert scene.cursor is False
    assert scene.has_panel


def test_motion_fields_default_to_off() -> None:
    scene = SpecModel.model_validate(base_spec()).scenes[0]
    assert scene.points == [] and scene.zoom == []
    assert scene.eyebrow is None and scene.title is None
    assert scene.cursor is None
    assert not scene.has_panel


@pytest.mark.parametrize(
    "zoom",
    [
        {"box": [0.8, 0.1, 0.4, 0.2], "at": "e1"},  # runs off the right edge
        {"box": [0.1, 0.1, 0.0, 0.2], "at": "e1"},  # no width
        {"box": [0.1, 0.1, 0.2, 0.2], "at": -1},  # before the clip
        {"box": [0.1, 0.1, 0.2, 0.2], "at": "e1", "hold": -0.5},
        {"box": [0.1, 0.1, 0.2, 0.2]},  # no moment
    ],
)
def test_bad_zooms_are_rejected(zoom: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SpecModel.model_validate(base_spec(scenes=[motion_scene(zoom=[zoom])]))


def test_points_need_text_and_a_line() -> None:
    for point in ({"text": "", "line": "l1"}, {"text": "hi"}, {"text": "hi", "line": "l1", "x": 1}):
        with pytest.raises(ValidationError):
            SpecModel.model_validate(base_spec(scenes=[motion_scene(points=[point])]))


def test_slides_cannot_take_footage_motion() -> None:
    scene = {"id": "intro", "layout": "slide", "slide": "intro", "title": "Hello"}
    with pytest.raises(ValidationError, match="only work beside footage"):
        SpecModel.model_validate(base_spec(scenes=[scene]))
