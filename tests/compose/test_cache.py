"""Tests for the scene cache key."""

from __future__ import annotations

from pathlib import Path

from reelsmith.compose.cache import is_cached, scene_key, scene_path


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
