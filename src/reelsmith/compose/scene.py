"""Turn one scene's inputs into a ScenePlan for one format.

This step draws the PNG overlays (frame, captions, ripples, badges) into a
work folder and works out where and when each one shows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

from reelsmith.compose.blur import blur_boxes
from reelsmith.compose.captions import (
    Align,
    CaptionCue,
    CaptionStyle,
    VAlign,
    caption_cues,
    render_caption,
)
from reelsmith.compose.frames import draw_frame
from reelsmith.compose.graph import (
    AudioPiece,
    ClipSource,
    ScenePlan,
    SlideSource,
    SlideStep,
    Still,
)
from reelsmith.compose.inputs import SceneSource, slide_clip
from reelsmith.compose.layouts import (
    Box,
    Layout,
    Size,
    ThemeColors,
    even,
    plan_layout,
)
from reelsmith.compose.ripples import (
    BACK_SECONDS,
    RING_RADII,
    RING_STEP_SECONDS,
    back_cues,
    draw_back_badge,
    draw_ring,
    ripple_cues,
)
from reelsmith.models import BlurRegion
from reelsmith.timing import Placement

SLIDE_ZOOM = 0.05
CAPTION_BRIDGE = 0.6
BAND_BACKGROUND = "#000000b3"
SIDE_BACKING_OPACITY = 0.92
SIDE_PADDING = 32  # at 1080p


@dataclass(frozen=True)
class Look:
    """Everything about the look that is the same for every scene."""

    fmt: str
    canvas: Size
    colors: ThemeColors
    dark: bool
    font: Path | None
    captions: bool
    highlight_clicks: bool
    blur: list[BlurRegion]


def step_times(count: int, placements: Sequence[Placement], duration: float) -> list[float]:
    """When each slide build step appears: step n with phrase n.

    Steps beyond the phrases are spread evenly over the rest of the scene.
    """
    times = [0.0]
    for number in range(1, count):
        if number < len(placements):
            times.append(placements[number].out_start)
            continue
        last = times[-1]
        left = count - number
        times.append(last + (duration - last) / (left + 1))
    return times


def plan_for_scene(
    scene: SceneSource,
    look: Look,
    slides: list[Path],
    work: Path,
    tail: float,
) -> ScenePlan:
    """Build the full render plan for one scene, drawing its overlays."""
    timeline = scene.timeline
    clip = scene.clip
    layout = scene_layout(scene, look)
    src = Size(even(clip.width), even(clip.height)) if clip else look.canvas
    stills: list[Still] = []
    if layout.frame is not None and layout.frame_kind is not None:
        size = Size(layout.frame.w, layout.frame.h)
        path = work / f"frame_{layout.frame_kind}_{size.width}x{size.height}.png"
        image = draw_frame(layout.frame_kind, size, layout.unit, dark=look.dark, dest=path)
        stills.append(Still(image, layout.frame.x, layout.frame.y))
    if look.captions:
        stills += caption_stills(scene, layout, look, work)
    source: ClipSource | SlideSource
    if clip is not None and scene.clip_dir is not None:
        if look.highlight_clicks:
            stills += ripple_stills(scene, layout, look, work)
        stills += back_stills(scene, layout, look, work)
        source = ClipSource(scene.clip_dir / clip.video, clip.duration, src)
        blur = blur_boxes(look.blur, clip.id, src.width, src.height)
    else:
        times = step_times(len(slides), timeline.placements, timeline.duration)
        source = SlideSource(
            [SlideStep(p, t, slide_clip(p)) for p, t in zip(slides, times, strict=True)]
        )
        blur = []
    audio = [
        AudioPiece(p.wav, p.audio_start, p.audio_end, placement.out_start)
        for p, placement in zip(scene.phrases, timeline.placements, strict=True)
        if p.wav is not None
    ]
    return ScenePlan(
        canvas=look.canvas,
        content=layout.content,
        background=look.colors.background,
        blurred_background=layout.blurred_background,
        source=source,
        segments=timeline.segments,
        blur=blur,
        zoom=SLIDE_ZOOM if clip is None else 0.0,
        stills=stills,
        audio=audio,
        duration=timeline.duration,
        tail=tail,
    )


@dataclass(frozen=True)
class CaptionSlot:
    """One caption image: its text, where it goes and when it shows."""

    name: str
    text: str
    box: Box  # the box the text is drawn into, in canvas pixels
    panel: Box
    start: float | None  # None means the whole scene
    end: float | None
    style: CaptionStyle
    align: Align
    valign: VAlign
    start_size: int


def scene_layout(scene: SceneSource, look: Look) -> Layout:
    clip = scene.clip
    src = Size(even(clip.width), even(clip.height)) if clip else look.canvas
    return plan_layout(scene.spec.layout, look.fmt, look.canvas, src, captions=look.captions)


def caption_slots(scene: SceneSource, layout: Layout, look: Look) -> list[CaptionSlot]:
    """Where and when every caption shows. Pure: nothing is drawn here."""
    panel = layout.panel
    if panel is None or not look.captions:
        return []
    texts = [p.text for p in scene.phrases]
    cues = caption_cues(texts, scene.timeline.placements, bridge=CAPTION_BRIDGE)
    if layout.panel_kind == "band":
        return _band_slots(scene, panel, cues, look, layout.unit)
    return _side_slots(scene, panel, cues, look, layout.unit)


def _band_slots(
    scene: SceneSource, panel: Box, cues: Sequence[CaptionCue], look: Look, unit: float
) -> list[CaptionSlot]:
    style = CaptionStyle(look.font, "#ffffff", BAND_BACKGROUND)
    size = round(42 * unit)
    if not cues and scene.caption:
        return [
            CaptionSlot(
                "band", scene.caption, panel, panel, None, None, style, "center", "middle", size
            )
        ]
    return [
        CaptionSlot(
            f"band_{n}", cue.text, panel, panel, cue.start, cue.end, style, "center", "middle", size
        )
        for n, cue in enumerate(cues)
    ]


def _side_slots(
    scene: SceneSource, panel: Box, cues: Sequence[CaptionCue], look: Look, unit: float
) -> list[CaptionSlot]:
    pad = round(SIDE_PADDING * unit)
    x, width = panel.x + pad, panel.w - 2 * pad
    top = panel.y + round(panel.h * 0.14)
    bottom = panel.y + panel.h - pad
    slots: list[CaptionSlot] = []
    if scene.caption:
        box = Box(x, top, width, round(panel.h * 0.24))
        style = CaptionStyle(look.font, look.colors.accent)
        slots.append(
            CaptionSlot(
                "heading", scene.caption, box, panel, None, None, style, "left", "top",
                round(64 * unit),
            )
        )  # fmt: skip
        top = box.y + box.h + round(24 * unit)
    body = Box(x, top, width, bottom - top)
    style = CaptionStyle(look.font, look.colors.text)
    for n, cue in enumerate(cues):
        slots.append(
            CaptionSlot(
                f"side_{n}", cue.text, body, panel, cue.start, cue.end, style, "left", "top",
                round(46 * unit),
            )
        )  # fmt: skip
    return slots


def caption_stills(scene: SceneSource, layout: Layout, look: Look, work: Path) -> list[Still]:
    """Draw the caption images, with a backing behind a side panel."""
    slots = caption_slots(scene, layout, look)
    stills: list[Still] = []
    panel = layout.panel
    if slots and panel is not None and layout.panel_kind == "side":
        stills.append(Still(_side_backing(panel, look, layout.unit, work), panel.x, panel.y))
    for slot in slots:
        image = render_caption(
            slot.text,
            Size(slot.box.w, slot.box.h),
            slot.style,
            work / f"{slot.name}.png",
            align=slot.align,
            valign=slot.valign,
            start_size=slot.start_size,
        )
        stills.append(Still(image, slot.box.x, slot.box.y, slot.start, slot.end))
    return stills


def _side_backing(panel: Box, look: Look, unit: float, work: Path) -> Path:
    """A theme coloured card behind the side panel, so text reads on any footage."""
    image = Image.new("RGBA", (panel.w, panel.h), (0, 0, 0, 0))
    red, green, blue = ImageColor.getrgb(look.colors.background)[:3]
    alpha = round(255 * SIDE_BACKING_OPACITY)
    radius = max(2, round(24 * unit))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, panel.w - 1, panel.h - 1), radius, fill=(red, green, blue, alpha)
    )
    dest = work / "side_backing.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def ripple_stills(scene: SceneSource, layout: Layout, look: Look, work: Path) -> list[Still]:
    assert scene.clip is not None
    box = layout.content
    rings = []
    for step, radius in enumerate(RING_RADII):
        opacity = 0.95 - 0.2 * step
        path = work / f"ring_{step}.png"
        rings.append(
            (
                draw_ring(max(4, round(radius * layout.unit)), look.colors.accent, opacity, path),
                step,
            )
        )
    stills: list[Still] = []
    for cue in ripple_cues(scene.clip.events, scene.timeline.segments):
        cx = box.x + cue.x * box.w
        cy = box.y + cue.y * box.h
        for image, step in rings:
            side = _png_side(image)
            start = cue.t + step * RING_STEP_SECONDS
            stills.append(
                Still(
                    image,
                    round(cx - side / 2),
                    round(cy - side / 2),
                    start,
                    start + RING_STEP_SECONDS,
                )
            )
    return stills


def back_stills(scene: SceneSource, layout: Layout, look: Look, work: Path) -> list[Still]:
    assert scene.clip is not None
    times = back_cues(scene.clip.events, scene.timeline.segments)
    if not times:
        return []
    image = draw_back_badge(layout.unit, look.font, work / "back.png")
    width, height = _png_size(image)
    box = layout.content
    x = box.x + (box.w - width) // 2
    y = box.y + box.h - height - round(40 * layout.unit)
    return [Still(image, x, y, t, t + BACK_SECONDS) for t in times]


def _png_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _png_side(path: Path) -> int:
    return _png_size(path)[0]
