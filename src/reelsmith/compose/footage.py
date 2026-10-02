"""Dress a footage scene: Studio background, polished frame, points panel,
zoom, cursor and click pulses.

Everything here works out where and when things go, and draws the PNGs
they need into the scene work folder. graph.py turns the result into
ffmpeg filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from reelsmith.compose.frames import (
    draw_frame,
    draw_mask,
    draw_status_bar,
    draw_underlay,
    top_colour,
)
from reelsmith.compose.graph import Overlay, Reveal, Still
from reelsmith.compose.layouts import Box, Layout, Size, ThemeColors, even, fit_band, plan_layout
from reelsmith.compose.motion import (
    Click,
    Key,
    clicks_of,
    cursor_keys,
    track_expr,
    zoom_keys,
    zoom_moment,
    zoom_windows,
)
from reelsmith.compose.panel import (
    REVEAL_RISE,
    REVEAL_SECONDS,
    PanelColors,
    PanelContent,
    Piece,
    draw_piece,
    panel_layout,
    reveal_times,
)
from reelsmith.compose.pointer import (
    CURSOR_HEIGHT,
    PULSE_RADIUS,
    PulseKind,
    Sprite,
    draw_cursor,
    pulse_frames,
    pulse_pattern,
)
from reelsmith.compose.studio import Backdrop, draw_backdrop
from reelsmith.compose.typeface import Faces
from reelsmith.errors import ReelsmithError

if TYPE_CHECKING:
    from reelsmith.compose.inputs import SceneSource
    from reelsmith.compose.scene import Look

ENTRANCE_RISE = 10  # at 1080p
PORTRAIT_BOOST = 1.15  # panel text is a little larger in 9:16, as on the Studio slides
CURSOR_LAYOUTS = ("browser", "full")


def has_points(scene: SceneSource) -> bool:
    """True for a footage scene that shows curated panel text."""
    return scene.clip is not None and scene.spec.has_panel


def is_studio(scene: SceneSource, look: Look) -> bool:
    """Footage scenes use the Studio look with the studio theme or with points."""
    return scene.clip is not None and (look.studio or has_points(scene))


def scene_colors(scene: SceneSource, look: Look) -> ThemeColors:
    return look.studio_colors if is_studio(scene, look) else look.colors


def wants_subtitles(scene: SceneSource, look: Look) -> bool:
    """Spoken subtitles beside points only when spec.yaml asks for burned captions."""
    return look.captions and look.captions_set


def status_bar_on(scene: SceneSource, look: Look) -> bool:
    """Web pages recorded at phone size have no status bar of their own, so the
    phone frame draws one. Real device recordings keep theirs."""
    return scene.clip is not None and scene.spec.layout == "phone" and look.web


def footage_box(layout: Layout) -> Box:
    """Where the footage itself sits on the canvas."""
    inset, content = layout.inset, layout.content
    if inset is None:
        return content
    return Box(content.x + inset.x, content.y + inset.y, inset.w, inset.h)


def footage_layout(scene: SceneSource, look: Look) -> Layout:
    clip = scene.clip
    src = Size(even(clip.width), even(clip.height)) if clip else look.canvas
    bar = status_bar_on(scene, look)
    if not has_points(scene):
        return plan_layout(
            scene.spec.layout, look.fmt, look.canvas, src, captions=look.captions, status_bar=bar
        )
    layout = plan_layout(
        scene.spec.layout,
        look.fmt,
        look.canvas,
        src,
        captions=look.captions,
        points=True,
        subtitles=wants_subtitles(scene, look),
        status_bar=bar,
    )
    if layout.panel_kind != "band" or layout.panel is None:
        return layout
    pieces = panel_pieces(scene, layout, look)
    used = max((p.box.y + p.box.h for p in pieces), default=layout.panel.y) - layout.panel.y
    return fit_band(layout, used)


def _faces(look: Look) -> Faces:
    from reelsmith.compose.typeface import Face

    if look.faces is not None:
        return look.faces
    return Faces(Face(look.font), Face(look.font), Face(look.font, fake_bold=True))


def panel_pieces(scene: SceneSource, layout: Layout, look: Look) -> list[Piece]:
    """Where the eyebrow, title and points go, and when each appears."""
    if not has_points(scene) or layout.panel is None or layout.panel_kind is None:
        return []
    spec = scene.spec
    line_ids = [phrase.line_id for phrase in scene.phrases]
    times = reveal_times(spec.points, line_ids, scene.timeline.placements, spec.id)
    content = PanelContent(
        spec.eyebrow, spec.title, [(p.text, t) for p, t in zip(spec.points, times, strict=True)]
    )
    canvas = layout.canvas
    unit = layout.unit * (PORTRAIT_BOOST if canvas.height > 1.5 * canvas.width else 1.0)
    return panel_layout(content, layout.panel, layout.panel_kind, _faces(look), unit)


@dataclass
class Dressing:
    """What a footage scene adds around and on top of the footage."""

    backdrop: Backdrop | None = None
    underlays: list[Still] = field(default_factory=list)
    frame: list[Still] = field(default_factory=list)
    panel: list[Still] = field(default_factory=list)
    view: list[Key] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    mask: Path | None = None
    pad_color: str = "#ffffff"
    status_bar: Path | None = None


def dress(scene: SceneSource, layout: Layout, look: Look, work: Path) -> Dressing:
    """Draw everything a footage scene needs and say where it goes."""
    dressing = Dressing()
    studio = is_studio(scene, look)
    colors = scene_colors(scene, look)
    if studio:
        dressing.backdrop = draw_backdrop(look.canvas, colors, work / "studio")
    _frame(dressing, layout, look, work, studio)
    unit = layout.unit
    faces = _faces(look)
    panel_colors = PanelColors(colors.text, colors.accent, colors.background)
    for piece in panel_pieces(scene, layout, look):
        image = draw_piece(piece, faces, panel_colors, unit, work / f"panel_{piece.name}.png")
        rise = round((REVEAL_RISE if piece.kind == "point" else ENTRANCE_RISE) * unit)
        reveal = Reveal(piece.start, REVEAL_SECONDS, rise)
        dressing.panel.append(Still(image, piece.box.x, piece.box.y, reveal=reveal))
    if layout.inset is not None and scene.clip is not None and scene.clip_dir is not None:
        video = scene.clip_dir / scene.clip.video
        dressing.pad_color = top_colour(video, work / "top_frame.png")
        size = Size(layout.content.w, layout.inset.y)
        dressing.status_bar = draw_status_bar(
            size, dressing.pad_color, unit, work / "status_bar.png"
        )
    dressing.view = scene_view(scene)
    dressing.overlays = _pointer_overlays(scene, layout, look, colors, dressing.view, work)
    return dressing


def _frame(dressing: Dressing, layout: Layout, look: Look, work: Path, studio: bool) -> None:
    unit = layout.unit
    if layout.frame is not None and layout.frame_kind is not None:
        frame = layout.frame
        size = Size(frame.w, frame.h)
        name = f"{layout.frame_kind}_{size.width}x{size.height}"
        image = draw_frame(
            layout.frame_kind, size, unit, dark=look.dark or studio, dest=work / f"frame_{name}.png"
        )
        under, pad = draw_underlay(layout.frame_kind, size, unit, work / f"under_{name}.png")
        dressing.underlays.append(Still(under, frame.x - pad, frame.y - pad))
        dressing.frame.append(Still(image, frame.x, frame.y))
        screen = Size(layout.content.w, layout.content.h)
        dressing.mask = draw_mask(layout.frame_kind, screen, unit, work / f"mask_{name}.png")
        return
    if studio and layout.content.w < layout.canvas.width:
        box = layout.content
        size = Size(box.w, box.h)
        under, pad = draw_underlay(None, size, unit, work / "under_full.png")
        dressing.underlays.append(Still(under, box.x - pad, box.y - pad))
        dressing.mask = draw_mask(None, size, unit, work / "mask_full.png")


def scene_view(scene: SceneSource) -> list[Key]:
    """Zoom keyframes for the scene, empty when it has no zoom."""
    clip = scene.clip
    if clip is None or not scene.spec.zoom:
        return []
    segments = scene.timeline.segments
    moments = []
    for zoom in scene.spec.zoom:
        try:
            moments.append((zoom_moment(zoom, clip, segments), zoom))
        except ValueError as exc:
            raise ReelsmithError(
                f"Scene '{scene.spec.id}' has a zoom at {zoom.at!r}, but {exc}",
                fix="Use an event id from clip.json, or seconds inside the clip",
            ) from None
    return zoom_keys(zoom_windows(moments, scene.timeline.duration))


def cursor_on(scene: SceneSource, look: Look) -> bool:
    if scene.clip is None or scene.spec.layout not in CURSOR_LAYOUTS:
        return False
    if scene.spec.cursor is not None:
        return scene.spec.cursor
    return look.web


def cursor_clicks(scene: SceneSource, look: Look) -> list[Click]:
    if scene.clip is None or not cursor_on(scene, look):
        return []
    return clicks_of(scene.clip, scene.timeline.segments, ("click",))


def _place(view: list[Key], width: int, height: int, x: str, y: str) -> tuple[str, str]:
    """Expressions for where footage fractions x, y land after the zoom, in pixels."""
    if not view:
        return f"{width}*({x})", f"{height}*({y})"
    left = track_expr(view, lambda v: v[0])
    top = track_expr(view, lambda v: v[1])
    right = track_expr(view, lambda v: v[2])
    bottom = track_expr(view, lambda v: v[3])
    return (
        f"{width}*(({x})-({left}))/(({right})-({left}))",
        f"{height}*(({y})-({top}))/(({bottom})-({top}))",
    )


def _pointer_overlays(
    scene: SceneSource,
    layout: Layout,
    look: Look,
    colors: ThemeColors,
    view: list[Key],
    work: Path,
) -> list[Overlay]:
    clip = scene.clip
    if clip is None:
        return []
    box = footage_box(layout)
    overlays: list[Overlay] = []
    if look.highlight_clicks:
        kind: PulseKind = "tap" if scene.spec.layout == "phone" else "click"
        pulse: Sprite | None = None
        for click in clicks_of(clip, scene.timeline.segments, ("click", "tap")):
            if pulse is None:
                radius = round(PULSE_RADIUS * layout.unit)
                pulse = pulse_frames(radius, colors.accent, kind, work / f"pulse_{kind}")
            x, y = _place(view, box.w, box.h, f"{click.x:.4f}", f"{click.y:.4f}")
            overlays.append(
                Overlay(
                    pulse_pattern(pulse),
                    f"{x}-{pulse.hot_x}",
                    f"{y}-{pulse.hot_y}",
                    sequence_start=click.t,
                )
            )
    keys = cursor_keys(cursor_clicks(scene, look))
    if keys:
        cursor = draw_cursor(round(CURSOR_HEIGHT * layout.unit), work / "cursor.png")
        cx = track_expr(keys, lambda v: v[0])
        cy = track_expr(keys, lambda v: v[1])
        x, y = _place(view, box.w, box.h, cx, cy)
        overlays.append(Overlay(cursor.image, f"{x}-{cursor.hot_x}", f"{y}-{cursor.hot_y}"))
    return overlays
