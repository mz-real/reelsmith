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
    # Every scene's audio is padded to the whole master so the mix never ends early.
    assert "[0:a]adelay=0:all=1,apad=whole_dur=9.5[sa0]" in graph
    assert "[1:a]adelay=3000:all=1,apad=whole_dur=9.5[sa1]" in graph
    assert "[2:a]adelay=7500:all=1,apad=whole_dur=9.5[sa2]" in graph
    assert "amix=inputs=3:normalize=0:duration=longest" in graph
    assert f"{LOUDNORM}," in graph
    assert LOUDNORM == "loudnorm=I=-16:TP=-1.5:LRA=11"
    assert "atrim=duration=9.5[voiced]" in graph
    assert graph.endswith("amix=inputs=2:normalize=0:duration=first[aout]")
    assert args[args.index("-t") + 1] == "9.5"
    assert args[-1] == str(Path("build/master_16x9.mp4"))


def test_one_scene_master_only_normalises_loudness() -> None:
    graph = graph_of(master_args([Path("a.mp4")], [5.0], Encode("ultrafast", 28), Path("m.mp4")))
    assert "xfade" not in graph
    assert "[0:v]null[vout]" in graph
    assert "[0:a]adelay=0:all=1,apad=whole_dur=5[sa0]" in graph
    assert "duration=longest" not in graph
    assert "[voiced][floor]amix=inputs=2" in graph


def test_a_silent_master_still_has_a_steady_very_quiet_floor(tmp_path: Path) -> None:
    import shutil
    import subprocess

    import numpy as np
    import pytest

    if shutil.which("ffmpeg") is None:
        pytest.skip("needs ffmpeg")
    scene = tmp_path / "a.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=4:r=30",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(scene)],
        check=True,
    )  # fmt: skip
    out = tmp_path / "m.mp4"
    args = master_args([scene], [4.0], Encode("ultrafast", 30), out)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    samples = np.frombuffer(raw, dtype=np.float32)
    windows = samples[: samples.size // 320 * 320].reshape(-1, 320)
    levels = 20 * np.log10(np.maximum(np.sqrt(np.mean(windows**2, axis=1)), 1e-12))

    assert float(levels.min()) > -110.0
    assert -100.0 < float(np.median(levels)) < -85.0
