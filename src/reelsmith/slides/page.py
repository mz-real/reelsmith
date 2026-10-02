"""One Studio page per slide state: pick the kind's builder and fill the template."""

from __future__ import annotations

from reelsmith.models.slides import (
    ArchitectureSlide,
    BulletsSlide,
    CardsSlide,
    ChartSlide,
    CodeSlide,
    CompareSlide,
    FlowSlide,
    GallerySlide,
    SlideItem,
    StatsSlide,
    TimelineSlide,
    TitleSlide,
)
from reelsmith.slides import code, diagram, grid
from reelsmith.slides.studio import (
    Frame,
    Parts,
    _base_css,
    _bullets_parts,
    _chapter,
    _chart_parts,
    _flow_parts,
    _footer,
    _motion_css,
    _title_parts,
)
from reelsmith.slides.themes import SlideTheme


def step_count(slide: SlideItem) -> int:
    """How many build states a slide has. Each one gets a clip and a still."""
    if isinstance(slide, FlowSlide):
        return len(slide.steps)
    if isinstance(slide, BulletsSlide):
        return len(slide.items)
    if isinstance(slide, CardsSlide):
        return len(slide.cards)
    if isinstance(slide, ArchitectureSlide):
        return len(slide.nodes)
    if isinstance(slide, CodeSlide):
        return max((step for step, _ in slide.highlight), default=1)
    if isinstance(slide, TimelineSlide | StatsSlide):
        return len(slide.stages())
    if isinstance(slide, CompareSlide):
        return len(slide.rows)
    if isinstance(slide, GallerySlide):
        return len(slide.images)
    return 1


def _parts(slide: SlideItem, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    if isinstance(slide, TitleSlide):
        return _title_parts(slide, theme, frame)
    if isinstance(slide, FlowSlide):
        return _flow_parts(slide, theme, frame, active)
    if isinstance(slide, BulletsSlide):
        return _bullets_parts(slide, theme, frame, active)
    if isinstance(slide, ChartSlide):
        return _chart_parts(slide, theme, frame)
    if isinstance(slide, CardsSlide):
        return grid.cards_parts(slide, theme, frame, active)
    if isinstance(slide, CompareSlide):
        return grid.compare_parts(slide, theme, frame, active)
    if isinstance(slide, StatsSlide):
        return grid.stats_parts(slide, theme, frame, active)
    if isinstance(slide, GallerySlide):
        return grid.gallery_parts(slide, theme, frame, active)
    if isinstance(slide, ArchitectureSlide):
        return diagram.architecture_parts(slide, theme, frame, active)
    if isinstance(slide, TimelineSlide):
        return diagram.timeline_parts(slide, theme, frame, active)
    return code.code_parts(slide, theme, frame, active)


def studio_values(
    slide: SlideItem, theme: SlideTheme, *, active: int, width: int, height: int
) -> dict[str, str]:
    """Template values for one build state of a slide, with that state's intro."""
    frame = Frame(width, height)
    parts = _parts(slide, theme, frame, active)
    body_class = f"kind-{parts.kind}" + (" intro" if active == 0 else "")
    return {
        "styles": _base_css(theme, frame) + parts.css + _motion_css(theme, frame),
        "body_class": body_class,
        "chapter": _chapter(slide),
        "head": parts.head,
        "body": parts.body,
        "footer": _footer(theme),
    }
