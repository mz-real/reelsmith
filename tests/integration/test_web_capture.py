"""Record the Recipe Box search flow and validate script pins."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from reelsmith.capture.web import run_web_flow
from reelsmith.commands.script_check import run_check
from reelsmith.media.ffmpeg import probe
from reelsmith.result import Status

REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_FLOW = REPO_ROOT / "examples" / "recipe-box" / "flows" / "search.py"

pytestmark = pytest.mark.integration


def _keep_search_scene(demo: Path) -> None:
    spec = yaml.safe_load((demo / "spec.yaml").read_text(encoding="utf-8"))
    script = yaml.safe_load((demo / "script.yaml").read_text(encoding="utf-8"))
    spec["scenes"] = [scene for scene in spec["scenes"] if scene["id"] == "search"]
    script["scenes"] = [scene for scene in script["scenes"] if scene["id"] == "search"]
    (demo / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (demo / "script.yaml").write_text(yaml.safe_dump(script), encoding="utf-8")


def test_recipe_box_search_capture_and_script_check(tmp_path: Path, require_ffmpeg: None) -> None:
    if not SEARCH_FLOW.is_file():
        pytest.skip("recipe-box example is not in this checkout")

    demo = tmp_path / "recipe-box"
    shutil.copytree(REPO_ROOT / "examples" / "recipe-box", demo)
    clips = demo / "capture" / "clips"
    clips.mkdir(parents=True, exist_ok=True)

    clip = run_web_flow(SEARCH_FLOW, "search", clips, headed=False, size="1280x720")
    info = probe(clips / "search" / "video.mp4")

    assert clip.width == 1280
    assert clip.height == 720
    assert len(clip.events) == 3
    assert info.width == 1280
    assert info.height == 720

    _keep_search_scene(demo)
    result = run_check(demo)
    assert result.status in {Status.OK, Status.WARN}
    assert result.status != Status.ERROR
