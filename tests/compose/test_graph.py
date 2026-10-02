"""Tests for the scene ffmpeg argument builder. No rendering here."""

from __future__ import annotations

from pathlib import Path

from reelsmith.compose.blur import BlurBox
from reelsmith.compose.graph import (
    AudioPiece,
    ClipSource,
    Encode,
    ScenePlan,
    SlideSource,
    SlideStep,
    Still,
    audio_filters,
    scene_args,
    segment_filters,
)
from reelsmith.compose.layouts import Box, Size
from reelsmith.timing import Segment

PLAY_HOLD_FAST = [
    Segment("play", 0.0, 2.0, 1.0, 0.0, 2.0),
    Segment("hold", 2.0, 2.0, 1.0, 2.0, 3.5),
    Segment("play", 2.0, 6.0, 2.0, 3.5, 5.5),
]


def clip_plan(**changes: object) -> ScenePlan:
    plan = ScenePlan(
        canvas=Size(1920, 1080),
        content=Box(100, 120, 1200, 750),
        background="#0f172a",
        blurred_background=False,
        source=ClipSource(Path("clips/my clip é/video.mp4"), 6.0, Size(1172, 2532)),
        segments=PLAY_HOLD_FAST,
        blur=[BlurBox(10, 20, 200, 40, 0.0, None)],
        zoom=0.0,
        stills=[
            Still(Path("frame.png"), 92, 68),
            Still(Path("cap0.png"), 1400, 300, 0.0, 1.5),
        ],
        audio=[
            AudioPiece(Path("voice/search__l1.wav"), 0.0, 1.6, 0.75),
            AudioPiece(Path("voice/search__l1.wav"), 1.8, 4.0, 2.5),
        ],
        duration=5.5,
        tail=0.4,
    )
    return plan if not changes else ScenePlan(**{**plan.__dict__, **changes})  # type: ignore[arg-type]


def graph_of(args: list[str]) -> str:
    return args[args.index("-filter_complex") + 1]


def test_segments_play_hold_and_speed_up() -> None:
    chains = segment_filters(PLAY_HOLD_FAST, "in", "out", clip_duration=6.0, fps=30)
    text = ";".join(chains)
    assert text.startswith("[in]split=3[seg0][seg1][seg2]")
    assert "[seg0]trim=start=0:end=2,setpts=PTS-STARTPTS[part0]" in text
    assert (
        "[seg1]trim=start_frame=60:end_frame=61,setpts=PTS-STARTPTS,"
        "tpad=stop_mode=clone:stop_duration=1.5,trim=duration=1.5[part1]"
    ) in text
    assert "[seg2]trim=start=2:end=6,setpts=(PTS-STARTPTS)/2[part2]" in text
    assert text.endswith("[part0][part1][part2]concat=n=3:v=1:a=0,fps=30[out]")


def test_a_hold_at_the_very_end_uses_the_last_real_frame() -> None:
    segments = [Segment("play", 0.0, 6.0, 1.0, 0.0, 6.0), Segment("hold", 6.0, 6.0, 1.0, 6.0, 7.0)]
    text = ";".join(segment_filters(segments, "in", "out", clip_duration=6.0, fps=30))
    assert "start_frame=179:end_frame=180" in text


def test_one_segment_needs_no_split() -> None:
    chains = segment_filters([Segment("play", 0.0, 3.0, 1.0, 0.0, 3.0)], "a", "b", 3.0, 30)
    assert chains == ["[a]trim=start=0:end=3,setpts=PTS-STARTPTS,fps=30[b]"]


def test_audio_is_cut_per_phrase_and_placed_with_adelay() -> None:
    chains = audio_filters([0, 1], clip_plan().audio, total=5.9)
    text = ";".join(chains)
    assert "[0:a]atrim=start=0:end=1.6,asetpts=PTS-STARTPTS" in text
    assert "adelay=750:all=1[voice0]" in text
    assert "[1:a]atrim=start=1.8:end=4" in text
    assert "adelay=2500:all=1[voice1]" in text
    assert "[voice0][voice1]amix=inputs=2:normalize=0:duration=longest" in text
    assert text.endswith("apad,atrim=duration=5.9[aout]")


def test_no_narration_gives_silence_of_the_right_length() -> None:
    assert audio_filters([], [], total=3.0) == ["anullsrc=r=48000:cl=stereo,atrim=duration=3[aout]"]


def test_clip_scene_args() -> None:
    args = scene_args(clip_plan(), Encode("medium", 18), Path("build/scenes/search-abc.mp4"))
    graph = graph_of(args)
    assert args[:2] == ["-i", str(Path("clips/my clip é/video.mp4"))]
    # stills are single images read literally, never as a numbered pattern
    assert ["-f", "image2", "-pattern_type", "none", "-i", "frame.png"] == args[2:8]
    assert "[0:v]fps=30,scale=1172:2532,setsar=1,format=yuv420p[raw]" in graph
    assert "crop=200:40:10:20" in graph  # blur comes before the timeline
    assert graph.index("crop=200:40:10:20") < graph.index("concat=n=3")
    assert "color=c=0x0f172a:s=1920x1080:r=30:d=5.9[bg]" in graph
    assert "scale=1200:750,setsar=1[content]" in graph
    assert "[bg][content]overlay=100:120[layer0]" in graph
    assert "[layer0][1:v]overlay=92:68[layer1]" in graph
    assert "[layer1][2:v]overlay=1400:300:enable='between(t,0,1.5)'[layer2]" in graph
    assert "tpad=stop_mode=clone:stop_duration=5.9,trim=duration=5.9" in graph
    assert args[args.index("-preset") + 1] == "medium"
    assert args[args.index("-crf") + 1] == "18"
    assert args[-1] == str(Path("build/scenes/search-abc.mp4"))
    assert ["-map", "[vout]", "-map", "[aout]"] == args[args.index("-map") : args.index("-map") + 4]


def test_phone_scene_gets_a_blurred_copy_as_background() -> None:
    graph = graph_of(
        scene_args(clip_plan(blurred_background=True), Encode("fast", 20), Path("o.mp4"))
    )
    assert "[src]split[srcmain][srcbg]" in graph
    assert "boxblur" in graph.split("[srcbg]")[2]
    assert "color=c=0x0f172a@0.75:s=1920x1080" in graph
    assert "[bgblur][veil]overlay=0:0:shortest=1[bg]" in graph


def test_slide_scene_steps_fade_in_and_zoom_slowly() -> None:
    plan = clip_plan(
        source=SlideSource(
            [SlideStep(Path("s_step1.png"), 0.0), SlideStep(Path("s_step2.png"), 2.05)]
        ),
        segments=[Segment("play", 0.0, 5.5, 1.0, 0.0, 5.5)],
        blur=[],
        zoom=0.05,
        content=Box(0, 0, 1920, 1080),
    )
    args = scene_args(plan, Encode("ultrafast", 28), Path("o.mp4"))
    graph = graph_of(args)
    assert args[:12] == [
        "-f",
        "image2",
        "-pattern_type",
        "none",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "5.9",
        "-i",
        "s_step1.png",
    ]
    assert "fade=t=in:st=2.05:d=0.3:alpha=1" in graph
    assert "overlay=0:0:enable='gte(t,2.05)'" in graph
    assert "eval=frame" in graph and "crop=1920:1080" in graph
    assert "concat=" not in graph and ",trim=start=" not in graph
