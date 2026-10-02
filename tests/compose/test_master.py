"""Tests for the master join arguments."""

from __future__ import annotations

from pathlib import Path

from reelsmith.compose.graph import Encode
from reelsmith.compose.master import LOUDNORM, master_args


def graph_of(args: list[str]) -> str:
    return args[args.index("-filter_complex") + 1]


def test_scenes_join_with_xfade_and_narration_keeps_its_place() -> None:
    files = [
        Path("build/scenes/a-1.mp4"),
        Path("build/scenes/b-2.mp4"),
        Path("build/scenes/c-3.mp4"),
    ]
    args = master_args(files, [3.0, 4.5, 2.0], Encode("medium", 18), Path("build/master_16x9.mp4"))
    graph = graph_of(args)
    assert args[:6] == [
        "-i",
        str(Path("build/scenes/a-1.mp4")),
        "-i",
        str(Path("build/scenes/b-2.mp4")),
        "-i",
        str(Path("build/scenes/c-3.mp4")),
    ]
    assert "xfade=transition=fade:duration=0.4:offset=3[x1]" in graph
    assert "xfade=transition=fade:duration=0.4:offset=7.5[vout]" in graph
    assert "[0:a]adelay=0:all=1[sa0]" in graph
    assert "[1:a]adelay=3000:all=1[sa1]" in graph
    assert "[2:a]adelay=7500:all=1[sa2]" in graph
    assert "amix=inputs=3:normalize=0:duration=longest" in graph
    assert f"{LOUDNORM}," in graph
    assert LOUDNORM == "loudnorm=I=-16:TP=-1.5:LRA=11"
    assert graph.endswith("atrim=duration=9.5[aout]")
    assert args[args.index("-t") + 1] == "9.5"
    assert args[-1] == str(Path("build/master_16x9.mp4"))


def test_one_scene_master_only_normalises_loudness() -> None:
    graph = graph_of(master_args([Path("a.mp4")], [5.0], Encode("ultrafast", 28), Path("m.mp4")))
    assert "xfade" not in graph
    assert "[0:v]null[vout]" in graph
    assert "[0:a]adelay=0:all=1[sa0]" in graph
    assert "amix" not in graph
