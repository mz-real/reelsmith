"""Build the ffmpeg arguments that render one scene.

Every function here is pure: it takes a ScenePlan and returns strings. The
order of work is source, blur, timeline (play, hold, speed), layout, then
overlays (frame, captions, ripples, badges), then narration.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from reelsmith.compose.blur import BlurBox, blur_filters
from reelsmith.compose.layouts import Box, Size, even, num
from reelsmith.timing import Segment

FPS = 30
STEP_FADE = 0.3
SAMPLE_RATE = 48000
BACKGROUND_VEIL = 0.75


@dataclass(frozen=True)
class ClipSource:
    video: Path
    clip_duration: float
    size: Size  # even size the clip is normalised to before anything else


@dataclass(frozen=True)
class SlideStep:
    image: Path  # the finished still of this build step
    start: float
    clip: Path | None = None  # the intro of this step, played at start, then the still holds


@dataclass(frozen=True)
class SlideSource:
    steps: list[SlideStep]


@dataclass(frozen=True)
class Still:
    """A still image laid on the canvas, for the whole scene or a window."""

    image: Path
    x: int
    y: int
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class AudioPiece:
    """A slice of a narration wav, placed at an output time."""

    wav: Path
    start: float
    end: float
    at: float


@dataclass(frozen=True)
class Encode:
    preset: str
    crf: int


@dataclass(frozen=True)
class ScenePlan:
    canvas: Size
    content: Box
    background: str
    blurred_background: bool
    source: ClipSource | SlideSource
    segments: list[Segment]
    blur: list[BlurBox]
    zoom: float  # extra scale reached at the end of a slide, 0 for none
    stills: list[Still]
    audio: list[AudioPiece]
    duration: float  # the timeline duration
    tail: float  # extra held frames at the end, for the cross fade

    @property
    def total(self) -> float:
        return self.duration + self.tail


@dataclass
class _Graph:
    inputs: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    count: int = 0

    def add_input(self, *args: str) -> int:
        self.inputs.extend(args)
        self.count += 1
        return self.count - 1


def _image_input(path: Path, loop_seconds: float | None = None) -> list[str]:
    args = ["-f", "image2", "-pattern_type", "none"]
    if loop_seconds is not None:
        args += ["-loop", "1", "-framerate", str(FPS), "-t", num(loop_seconds)]
    return [*args, "-i", str(path)]


def segment_filters(
    segments: Sequence[Segment], src: str, out: str, clip_duration: float, fps: int
) -> list[str]:
    """Cut the clip into play and hold parts and join them back up."""
    last_frame = max(0, round(clip_duration * fps) - 1)
    parts = [_segment_filter(seg, last_frame, fps) for seg in segments]
    if len(parts) == 1:
        return [f"[{src}]{parts[0]},fps={fps}[{out}]"]
    labels = "".join(f"[seg{i}]" for i in range(len(parts)))
    chains = [f"[{src}]split={len(parts)}{labels}"]
    chains += [f"[seg{i}]{part}[part{i}]" for i, part in enumerate(parts)]
    joined = "".join(f"[part{i}]" for i in range(len(parts)))
    chains.append(f"{joined}concat=n={len(parts)}:v=1:a=0,fps={fps}[{out}]")
    return chains


def _segment_filter(seg: Segment, last_frame: int, fps: int) -> str:
    if seg.kind == "hold":
        frame = min(round(seg.src_start * fps), last_frame)
        length = num(seg.out_end - seg.out_start)
        return (
            f"trim=start_frame={frame}:end_frame={frame + 1},setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={length},trim=duration={length}"
        )
    pts = "PTS-STARTPTS" if abs(seg.speed - 1.0) < 1e-9 else f"(PTS-STARTPTS)/{num(seg.speed)}"
    return f"trim=start={num(seg.src_start)}:end={num(seg.src_end)},setpts={pts}"


def _clip_source(graph: _Graph, plan: ScenePlan, source: ClipSource) -> None:
    index = graph.add_input("-i", str(source.video))
    size = source.size
    graph.chains.append(
        f"[{index}:v]fps={FPS},scale={size.width}:{size.height},setsar=1,format=yuv420p[raw]"
    )
    graph.chains += blur_filters(plan.blur, "raw", "clean")
    graph.chains += segment_filters(plan.segments, "clean", "src", source.clip_duration, FPS)


def _slide_source(graph: _Graph, plan: ScenePlan, source: SlideSource) -> None:
    w, h = plan.canvas.width, plan.canvas.height
    fit = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{plan.background.lstrip('#')},setsar=1"
    )
    if any(step.clip is not None for step in source.steps):
        current = _slide_clip_steps(graph, plan, source, fit)
    else:
        current = _slide_still_steps(graph, plan, source, fit)
    if plan.zoom <= 0:
        graph.chains.append(f"[{current}]null[src]")
        return
    grow = f"(1+{num(plan.zoom)}*t/{num(plan.total)})"
    graph.chains.append(
        f"[{current}]scale=w='2*trunc({w}*{grow}/2)':h='2*trunc({h}*{grow}/2)':eval=frame,"
        f"crop={w}:{h},setsar=1[src]"
    )


def _slide_clip_steps(graph: _Graph, plan: ScenePlan, source: SlideSource, fit: str) -> str:
    """Each step plays its intro clip at its cue, then holds its still until the next."""
    steps = source.steps
    norm = f"{fit},fps={FPS},format=yuv420p,setpts=PTS-STARTPTS"
    for number, step in enumerate(steps):
        end = steps[number + 1].start if number + 1 < len(steps) else plan.total
        length = num(max(end - step.start, 1 / FPS))
        still = graph.add_input(*_image_input(step.image, float(length)))
        if step.clip is None:
            graph.chains.append(f"[{still}:v]{norm},trim=duration={length}[sp{number}]")
            continue
        clip = graph.add_input("-i", str(step.clip))
        graph.chains.append(f"[{clip}:v]{norm}[sclip{number}]")
        graph.chains.append(f"[{still}:v]{norm}[shold{number}]")
        graph.chains.append(
            f"[sclip{number}][shold{number}]concat=n=2:v=1:a=0,"
            f"trim=duration={length},setpts=PTS-STARTPTS[sp{number}]"
        )
    if len(steps) == 1:
        return "sp0"
    joined = "".join(f"[sp{number}]" for number in range(len(steps)))
    graph.chains.append(f"{joined}concat=n={len(steps)}:v=1:a=0[slides]")
    return "slides"


def _slide_still_steps(graph: _Graph, plan: ScenePlan, source: SlideSource, fit: str) -> str:
    """Older slides without clips: each step fades in over the one before."""
    current = ""
    for number, step in enumerate(source.steps):
        index = graph.add_input(*_image_input(step.image, plan.total))
        if number == 0:
            graph.chains.append(f"[{index}:v]{fit},format=yuv420p[slide0]")
            current = "slide0"
            continue
        start = num(step.start)
        graph.chains.append(
            f"[{index}:v]{fit},format=rgba,"
            f"fade=t=in:st={start}:d={num(STEP_FADE)}:alpha=1[step{number}]"
        )
        graph.chains.append(
            f"[{current}][step{number}]overlay=0:0:enable='gte(t,{start})'[slide{number}]"
        )
        current = f"slide{number}"
    return current


def _layout(graph: _Graph, plan: ScenePlan) -> str:
    w, h = plan.canvas.width, plan.canvas.height
    box = plan.content
    color = plan.background.lstrip("#")
    if plan.blurred_background:
        sw, sh = even(w / 8), even(h / 8)
        graph.chains.append("[src]split[srcmain][srcbg]")
        graph.chains.append(
            f"[srcbg]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
            f"boxblur=4:2,scale={w}:{h},setsar=1[bgblur]"
        )
        # A theme coloured veil keeps captions readable on any footage.
        graph.chains.append(
            f"color=c=0x{color}@{num(BACKGROUND_VEIL)}:s={w}x{h}:r={FPS}:d={num(plan.total)},"
            f"format=rgba[veil]"
        )
        graph.chains.append("[bgblur][veil]overlay=0:0:shortest=1[bg]")
        main = "srcmain"
    else:
        graph.chains.append(f"color=c=0x{color}:s={w}x{h}:r={FPS}:d={num(plan.total)}[bg]")
        main = "src"
    graph.chains.append(f"[{main}]scale={box.w}:{box.h},setsar=1[content]")
    graph.chains.append(f"[bg][content]overlay={box.x}:{box.y}[layer0]")
    current = "layer0"
    for number, still in enumerate(plan.stills, start=1):
        index = graph.add_input(*_image_input(still.image))
        target = f"layer{number}"
        graph.chains.append(
            f"[{current}][{index}:v]overlay={still.x}:{still.y}{_window(still)}[{target}]"
        )
        current = target
    total = num(plan.total)
    graph.chains.append(
        f"[{current}]format=yuv420p,tpad=stop_mode=clone:stop_duration={total},"
        f"trim=duration={total},setpts=PTS-STARTPTS[vout]"
    )
    return "vout"


def _window(still: Still) -> str:
    if still.start is None and still.end is None:
        return ""
    start = num(still.start or 0.0)
    if still.end is None:
        return f":enable='gte(t,{start})'"
    return f":enable='between(t,{start},{num(still.end)})'"


def audio_filters(indexes: Sequence[int], pieces: Sequence[AudioPiece], total: float) -> list[str]:
    """Cut each phrase from its wav and place it at its out_start."""
    length = num(total)
    if not pieces:
        return [f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length}[aout]"]
    chains = []
    for number, (index, piece) in enumerate(zip(indexes, pieces, strict=True)):
        delay = round(piece.at * 1000)
        chains.append(
            f"[{index}:a]atrim=start={num(piece.start)}:end={num(piece.end)},"
            f"asetpts=PTS-STARTPTS,aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay}:all=1[voice{number}]"
        )
    labels = "".join(f"[voice{i}]" for i in range(len(pieces)))
    mix = f"amix=inputs={len(pieces)}:normalize=0:duration=longest," if len(pieces) > 1 else ""
    chains.append(f"{labels}{mix}apad,atrim=duration={length}[aout]")
    return chains


def scene_args(plan: ScenePlan, encode: Encode, out: Path) -> list[str]:
    """All ffmpeg arguments (after the program name) to render one scene."""
    graph = _Graph()
    if isinstance(plan.source, ClipSource):
        _clip_source(graph, plan, plan.source)
    else:
        _slide_source(graph, plan, plan.source)
    video = _layout(graph, plan)
    indexes = [graph.add_input("-i", str(piece.wav)) for piece in plan.audio]
    graph.chains += audio_filters(indexes, plan.audio, plan.total)
    return [
        *graph.inputs,
        "-filter_complex",
        ";".join(graph.chains),
        "-map",
        f"[{video}]",
        "-map",
        "[aout]",
        *encode_args(encode),
        "-t",
        num(plan.total),
        str(out),
    ]


def encode_args(encode: Encode) -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        encode.preset,
        "-crf",
        str(encode.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(SAMPLE_RATE),
        "-movflags",
        "+faststart",
    ]
