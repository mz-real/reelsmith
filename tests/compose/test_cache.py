"""Tests for the scene cache key."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import reelsmith
import reelsmith.compose.project as project_module
from reelsmith.compose.cache import (
    code_fingerprint,
    is_cached,
    render_code_fingerprint,
    scene_key,
    scene_path,
)
from reelsmith.compose.project import compose_project, final_settings
from reelsmith.models import SpecModel
from reelsmith.paths import DemoPaths


def test_same_inputs_give_the_same_key(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"audio")
    assert scene_key({"a": 1}, [wav]) == scene_key({"a": 1}, [wav])


def test_changed_payload_changes_the_key(tmp_path: Path) -> None:
    assert scene_key({"a": 1}, []) != scene_key({"a": 2}, [])


def test_changed_file_content_changes_the_key(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"audio")
    before = scene_key({"a": 1}, [wav])
    wav.write_bytes(b"other audio")
    assert scene_key({"a": 1}, [wav]) != before


def test_missing_file_still_gives_a_key(tmp_path: Path) -> None:
    assert scene_key({}, [tmp_path / "gone.wav"]) != scene_key({}, [])


def test_cache_hit_and_miss(tmp_path: Path) -> None:
    key = scene_key({"scene": "intro"}, [])
    path = scene_path(tmp_path, "intro", key)
    assert path.name.startswith("intro-") and path.suffix == ".mp4"
    assert not is_cached(path)
    path.write_bytes(b"video")
    assert is_cached(path)
    other = scene_path(tmp_path, "intro", scene_key({"scene": "intro", "v": 2}, []))
    assert other != path
    assert not is_cached(other)


def test_empty_file_is_not_a_cache_hit(tmp_path: Path) -> None:
    path = scene_path(tmp_path, "intro", "abc")
    path.write_bytes(b"")
    assert not is_cached(path)


def test_render_code_fingerprint_is_a_stable_short_hex_string() -> None:
    first = render_code_fingerprint()
    assert first == render_code_fingerprint()
    assert len(first) == 16
    int(first, 16)


def test_changing_a_compose_file_changes_the_fingerprint(tmp_path: Path) -> None:
    package = Path(reelsmith.__file__).resolve().parent
    root = tmp_path / "reelsmith"
    for folder in ("compose", "slides"):
        shutil.copytree(
            package / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    before = code_fingerprint(root)
    assert before == render_code_fingerprint()
    target = root / "compose" / "blur.py"
    target.write_bytes(target.read_bytes() + b"\n# edit\n")
    assert code_fingerprint(root) != before
    shutil.copy(package / "compose" / "blur.py", target)
    (root / "slides" / "themes.py").write_bytes(b"changed")
    assert code_fingerprint(root) != before


def test_scene_payload_carries_the_fingerprint_and_a_new_one_rebuilds(
    ready: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads: list[dict[str, object]] = []
    real_key = project_module.scene_key

    def spy(payload: dict[str, object], files: list[Path]) -> str:
        payloads.append(payload)
        return real_key(payload, files)

    def fake(args: list[str]) -> None:
        Path(args[-1]).write_bytes(b"video")

    monkeypatch.setattr(project_module, "scene_key", spy)
    paths, settings = DemoPaths.at(ready), final_settings(SpecModel())
    compose_project(paths, settings, fake)
    assert payloads and all(p["code"] == render_code_fingerprint() for p in payloads)
    monkeypatch.setattr(project_module, "render_code_fingerprint", lambda: "0" * 16)
    report = compose_project(paths, settings, fake)
    assert report.formats[0].reused == []
    assert report.formats[0].rendered == ["intro", "search"]
