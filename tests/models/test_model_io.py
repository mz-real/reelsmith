"""Tests for load_model and save_model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.models import (
    BrandModel,
    ClipModel,
    ScriptModel,
    SpecModel,
    load_model,
    save_model,
)


def sample_spec() -> SpecModel:
    return SpecModel.model_validate(
        {
            "goal": "Show search",
            "scenes": [
                {"id": "intro", "layout": "slide", "slide": "intro"},
                {"id": "search", "layout": "browser", "clip": "search"},
            ],
            "blur": [{"clip": "search", "box": [0.1, 0.1, 0.2, 0.2]}],
        }
    )


def sample_script() -> ScriptModel:
    return ScriptModel.model_validate(
        {
            "scenes": [
                {
                    "id": "search",
                    "caption": "Find it",
                    "lines": [{"id": "l1", "phrases": [{"text": "Tap search.", "pin": "e1"}]}],
                }
            ]
        }
    )


def sample_clip() -> ClipModel:
    return ClipModel.model_validate(
        {
            "id": "search",
            "video": "video.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "duration": 5.0,
            "events": [{"id": "e1", "t": 1.0, "type": "click", "x": 0.5, "y": 0.5}],
        }
    )


@pytest.mark.parametrize("name", ["spec.yaml", "spec.yml", "spec.json"])
def test_spec_round_trips(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    spec = sample_spec()

    save_model(path, spec)

    assert load_model(path, SpecModel) == spec


def test_script_clip_and_brand_round_trip(tmp_path: Path) -> None:
    script = sample_script()
    clip = sample_clip()
    brand = BrandModel.model_validate({"logo": "logo.png", "colors": {"primary": "#123456"}})

    save_model(tmp_path / "script.yaml", script)
    save_model(tmp_path / "clips" / "search" / "clip.json", clip)
    save_model(tmp_path / "brand.yaml", brand)

    assert load_model(tmp_path / "script.yaml", ScriptModel) == script
    assert load_model(tmp_path / "clips" / "search" / "clip.json", ClipModel) == clip
    assert load_model(tmp_path / "brand.yaml", BrandModel) == brand


def test_json_output_is_plain_json(tmp_path: Path) -> None:
    path = tmp_path / "clip.json"
    save_model(path, sample_clip())

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["events"][0]["id"] == "e1"


def test_save_backs_up_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("old: true\n", encoding="utf-8")

    save_model(path, sample_spec())

    backups = list(tmp_path.glob("spec.yaml.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old: true\n"
    assert load_model(path, SpecModel) == sample_spec()


def test_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ReelsmithError, match="not found"):
        load_model(tmp_path / "spec.yaml", SpecModel)


def test_errors_name_the_field(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        "scenes:\n  - id: a\n    layout: browser\n    clip: a\n    speed: 2\n", encoding="utf-8"
    )

    with pytest.raises(ReelsmithError) as info:
        load_model(path, SpecModel)

    message = str(info.value)
    assert "spec.yaml" in message
    assert "scenes.0.speed" in message


def test_broken_yaml_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "script.yaml"
    path.write_text("scenes: [\n", encoding="utf-8")

    with pytest.raises(ReelsmithError, match="script.yaml"):
        load_model(path, ScriptModel)


def test_unknown_suffix_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "spec.toml"
    path.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(ReelsmithError, match="YAML or JSON"):
        load_model(path, SpecModel)
