"""The reelsmith file models. All pydantic v2, unknown fields forbidden."""

from __future__ import annotations

from reelsmith.models.brand import BrandColors, BrandFont, BrandModel
from reelsmith.models.clip import ClipModel, Event
from reelsmith.models.io import load_model, save_model
from reelsmith.models.script import Line, Phrase, ScriptModel, ScriptScene
from reelsmith.models.slides import (
    BulletsSlide,
    ChartSlide,
    FlowSlide,
    SlideItem,
    SlidesModel,
    TitleSlide,
)
from reelsmith.models.spec import (
    CLONE_CONSENT_MESSAGE,
    BlurRegion,
    Options,
    SceneSpec,
    SpecModel,
    VoiceSettings,
)

__all__ = [
    "CLONE_CONSENT_MESSAGE",
    "BlurRegion",
    "BrandColors",
    "BrandFont",
    "BrandModel",
    "ClipModel",
    "Event",
    "Line",
    "Options",
    "Phrase",
    "SceneSpec",
    "ScriptModel",
    "ScriptScene",
    "SlideItem",
    "SlidesModel",
    "SpecModel",
    "TitleSlide",
    "FlowSlide",
    "ChartSlide",
    "BulletsSlide",
    "VoiceSettings",
    "load_model",
    "save_model",
]
