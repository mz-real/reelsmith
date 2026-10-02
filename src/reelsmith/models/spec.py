"""The spec.yaml model: the plan for a demo."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

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
    # A word (case insensitive, whole word) to the Kokoro or espeak phonemes
    # it should be read as, for words Kokoro reads wrong from plain text.
    pronounce: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _clone_needs_consent(self) -> Self:
        if self.engine == "chatterbox" and (not self.sample or self.consent is None):
            raise ValueError(CLONE_CONSENT_MESSAGE)
        return self

    @model_validator(mode="after")
    def _pronounce_keys_are_single_words(self) -> Self:
        for word in self.pronounce:
            if not word.strip() or len(word.split()) != 1:
                raise ValueError(
                    f"voice.pronounce key {word!r} must be a single word, not a phrase"
                )
        return self


class Options(StrictModel):
    allow_holds: bool = True
    speed_up_waits: bool = False
    captions: Literal["none", "burned", "srt", "both"] = "burned"
    highlight_clicks: bool = True
    transition: TransitionKind = "fade"


class PanelPoint(StrictModel):
    """A curated point beside the footage. It appears when its line starts."""

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    line: Identifier  # a script line id in the same scene


Seconds = Annotated[float, Field(ge=0.0)]


class ZoomSpec(StrictModel):
    """Ease in to a region of the footage around a moment, hold, then ease out."""

    box: tuple[Fraction, Fraction, Fraction, Fraction]  # x, y, w, h
    at: Seconds | Identifier  # an event id such as e3, or seconds in clip time
    hold: float = Field(default=1.5, ge=0.0)

    @model_validator(mode="after")
    def _box_fits(self) -> Self:
        x, y, w, h = self.box
        if w <= 0 or h <= 0:
            raise ValueError("A zoom box needs a width and a height above 0")
        if x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
            raise ValueError("A zoom box must stay inside the frame (x + w and y + h at most 1)")
        return self


class SceneSpec(StrictModel):
    id: Identifier
    layout: Layout
    slide: str | None = None
    clip: str | None = None
    transition: TransitionKind | None = None
    eyebrow: str | None = None
    title: str | None = None
    points: list[PanelPoint] = Field(default_factory=list)
    zoom: list[ZoomSpec] = Field(default_factory=list)
    cursor: bool | None = None  # None means on for web clips with clicks

    @model_validator(mode="after")
    def _source_matches_layout(self) -> Self:
        if self.layout == "slide" and not self.slide:
            raise ValueError(f"Scene '{self.id}' has layout slide, so it needs a slide")
        if self.layout != "slide" and not self.clip:
            raise ValueError(f"Scene '{self.id}' has layout {self.layout}, so it needs a clip")
        return self

    @model_validator(mode="after")
    def _motion_needs_footage(self) -> Self:
        if self.layout != "slide":
            return self
        used = [name for name in ("eyebrow", "title", "points", "zoom") if getattr(self, name)]
        if used:
            raise ValueError(
                f"Scene '{self.id}' is a slide, but {', '.join(used)} only work beside footage."
                " Put slide text in slides.yaml"
            )
        return self

    @property
    def has_panel(self) -> bool:
        """True when the scene shows curated panel text instead of spoken captions."""
        return bool(self.points or self.title or self.eyebrow)


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
    theme: Literal["studio", "dark", "light", "minimal"] = "studio"
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
