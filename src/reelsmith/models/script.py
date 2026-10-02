"""The script.yaml model: narration per scene, split into phrases."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from reelsmith.models.common import Identifier, StrictModel, check_unique

PhraseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Phrase(StrictModel):
    text: PhraseText  # what the captions and the srt show
    say: PhraseText | None = None  # what the voice reads, when it differs from text
    pin: Identifier | None = None  # an event id in this scene's clip

    @property
    def spoken(self) -> str:
        """The words the voice reads: say when given, otherwise text."""
        return self.say if self.say is not None else self.text


class Line(StrictModel):
    id: Identifier
    phrases: list[Phrase] = Field(min_length=1)

    @property
    def text(self) -> str:
        """The whole line as one string, as the captions show it."""
        return " ".join(phrase.text for phrase in self.phrases)

    @property
    def spoken_text(self) -> str:
        """The whole line as one string, as the voice engine reads it."""
        return " ".join(phrase.spoken for phrase in self.phrases)

    @property
    def has_say(self) -> bool:
        return any(phrase.say is not None for phrase in self.phrases)


class ScriptScene(StrictModel):
    id: Identifier
    caption: str | None = None
    lines: list[Line] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_line_ids(self) -> Self:
        check_unique((line.id for line in self.lines), "Line")
        return self


class ScriptModel(StrictModel):
    version: Literal[1] = 1
    scenes: list[ScriptScene] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_scene_ids(self) -> Self:
        check_unique((scene.id for scene in self.scenes), "Scene")
        return self

    def scene(self, scene_id: str) -> ScriptScene | None:
        return next((s for s in self.scenes if s.id == scene_id), None)
