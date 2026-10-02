"""The spec.yaml model: the plan for a demo."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from reelsmith.models.common import Fraction, Identifier, StrictModel, check_unique

CLONE_CONSENT_MESSAGE = "Cloning needs a voice sample and consent."

Layout = Literal["slide", "phone", "browser", "full"]
VideoFormat = Literal["16:9", "9:16", "1:1"]
TransitionKind = Literal["fade", "slide", "push", "zoom"]


def _default_formats() -> list[VideoFormat]:
    return ["16:9"]


class VoiceSettings(StrictModel):
    engine: Literal["kokoro", "chatterbox", "none"] = "kokoro"
    kokoro_voice: str = "af_heart"
    speed: float = Field(default=1.0, gt=0.0)
    sample: str | None = None
    consent: Literal["own", "permission"] | None = None
    # Product names and other rare words, passed to the speech model as hints.
    vocabulary: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _clone_needs_consent(self) -> Self:
        if self.engine == "chatterbox" and (not self.sample or self.consent is None):
            raise ValueError(CLONE_CONSENT_MESSAGE)
        return self


class Options(StrictModel):
    allow_holds: bool = True
    speed_up_waits: bool = False
    captions: Literal["none", "burned", "srt", "both"] = "burned"
    highlight_clicks: bool = True
    transition: TransitionKind = "fade"


class SceneSpec(StrictModel):
    id: Identifier
    layout: Layout
    slide: str | None = None
    clip: str | None = None
    transition: TransitionKind | None = None

    @model_validator(mode="after")
    def _source_matches_layout(self) -> Self:
        if self.layout == "slide" and not self.slide:
            raise ValueError(f"Scene '{self.id}' has layout slide, so it needs a slide")
        if self.layout != "slide" and not self.clip:
            raise ValueError(f"Scene '{self.id}' has layout {self.layout}, so it needs a clip")
        return self


class BlurRegion(StrictModel):
    clip: Identifier
    box: tuple[Fraction, Fraction, Fraction, Fraction]  # x, y, w, h
    start: float = Field(default=0.0, ge=0.0)
    end: float | None = None  # None means to the end of the clip

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end is not None and self.end <= self.start:
            raise ValueError("Blur end must be after its start")
        return self


class SpecModel(StrictModel):
    version: Literal[1] = 1
    mode: Literal["narrate", "produce"] = "produce"
    goal: str = ""
    audience: str = ""
    target_seconds: float = Field(default=90, gt=0)
    formats: list[VideoFormat] = Field(default_factory=_default_formats, min_length=1)
    quality: Literal["1080p", "4k"] = "1080p"
    theme: Literal["dark", "light", "minimal"] = "dark"
    footage: Literal["import", "web", "mobile"] = "web"
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    options: Options = Field(default_factory=Options)
    scenes: list[SceneSpec] = Field(default_factory=list)
    blur: list[BlurRegion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_scene_ids(self) -> Self:
        check_unique((scene.id for scene in self.scenes), "Scene")
        return self

    def scene(self, scene_id: str) -> SceneSpec | None:
        return next((s for s in self.scenes if s.id == scene_id), None)
