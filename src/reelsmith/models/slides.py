"""The slides.yaml model: slide definitions for produce mode.

Every text field accepts ``*accent*`` markup: the words between stars are
drawn in the accent colour. Write ``\\*`` for a plain star.

Build steps are numbered from 1 in slides.yaml, the way the narration
counts them: step 1 shows at the start of the slide, step 2 with the next
phrase, and so on.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import AfterValidator, ConfigDict, Field, WithJsonSchema, model_validator

from reelsmith.models.common import Fraction, Identifier, StrictModel, check_unique
from reelsmith.slides.icons import ICON_NAMES

SlideKind = Literal[
    "title",
    "flow",
    "chart",
    "bullets",
    "cards",
    "architecture",
    "code",
    "timeline",
    "compare",
    "stats",
    "gallery",
]
StepStyle = Literal["dim", "reveal"]
MAX_STEPS = 24


def _check_icon(name: str) -> str:
    if name not in ICON_NAMES:
        raise ValueError(f"Unknown icon '{name}'. Available icons: {', '.join(ICON_NAMES)}")
    return name


IconName = Annotated[
    str,
    AfterValidator(_check_icon),
    WithJsonSchema({"type": "string", "enum": list(ICON_NAMES)}),
]
"""A name from the built in line icon set."""


class SlideBase(StrictModel):
    """Fields every slide kind shares."""

    id: Identifier
    eyebrow: str | None = None  # small label above the title
    subtitle: str | None = None
    chapter: int | None = Field(default=None, ge=0, le=99)  # big faded number, top right
    step_style: StepStyle = "dim"  # future steps: dimmed, or hidden until they build in


class TitleSlide(SlideBase):
    kind: Literal["title"]
    title: str
    coming_up: list[str] = Field(default_factory=list, max_length=6)  # chips under the subtitle


class FlowStep(StrictModel):
    title: str
    detail: str | None = None
    accent: bool = False  # stays lit in the accent once it is reached


class FlowSlide(SlideBase):
    kind: Literal["flow"]
    title: str | None = None
    steps: list[str | FlowStep] = Field(min_length=1)
    exits: list[str] = Field(default_factory=list)

    def step_items(self) -> list[FlowStep]:
        """Every step as a card, turning plain strings into titles."""
        return [s if isinstance(s, FlowStep) else FlowStep(title=s) for s in self.steps]

    def step_titles(self) -> list[str]:
        return [item.title for item in self.step_items()]


class ChartSlide(SlideBase):
    kind: Literal["chart"]
    title: str | None = None
    chart_type: Literal["bars", "lines"]
    labels: list[str] = Field(min_length=1)
    values: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _labels_match_values(self) -> Self:
        if len(self.labels) != len(self.values):
            raise ValueError("Chart labels and values must be the same length")
        return self


class BulletsSlide(SlideBase):
    kind: Literal["bullets"]
    title: str | None = None
    items: list[str] = Field(min_length=1)


class Card(StrictModel):
    title: str
    detail: str | None = None
    icon: IconName | None = None
    number: str | None = None  # shown in the badge; 01, 02 and so on when left out
    chips: list[str] = Field(default_factory=list, max_length=6)
    accent: bool = False  # stays lit in the accent once it is in


class CardsSlide(SlideBase):
    """2 to 6 cards in a grid, one card per build step."""

    kind: Literal["cards"]
    title: str | None = None
    cards: list[Card] = Field(min_length=2, max_length=6)


class ArchNode(StrictModel):
    id: Identifier
    label: str
    detail: str | None = None
    icon: IconName | None = None
    chips: list[str] = Field(default_factory=list, max_length=8)  # a group of child parts


class ArchEdge(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: Identifier = Field(alias="from")
    to: Identifier
    label: str | None = None


class ArchitectureSlide(SlideBase):
    """Boxes in columns joined by arrows. Each node is one build step, in layout order."""

    kind: Literal["architecture"]
    title: str | None = None
    nodes: list[ArchNode] = Field(min_length=1, max_length=12)
    layout: list[list[Identifier]] = Field(min_length=1, max_length=6)  # columns of node ids
    edges: list[ArchEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _layout_matches_nodes(self) -> Self:
        check_unique((node.id for node in self.nodes), "Node")
        ids = {node.id for node in self.nodes}
        placed = [node_id for column in self.layout for node_id in column]
        check_unique(placed, "Layout node")
        if any(not column for column in self.layout):
            raise ValueError("Every layout column needs at least one node")
        unknown = [node_id for node_id in placed if node_id not in ids]
        if unknown:
            raise ValueError(f"Layout names node '{unknown[0]}', which is not in nodes")
        missing = [node.id for node in self.nodes if node.id not in placed]
        if missing:
            raise ValueError(f"Node '{missing[0]}' is not placed in layout")
        for edge in self.edges:
            for end in (edge.source, edge.to):
                if end not in ids:
                    raise ValueError(f"Edge names node '{end}', which is not in nodes")
            if edge.source == edge.to:
                raise ValueError(f"Edge from '{edge.source}' goes to itself")
        return self

    def ordered_ids(self) -> list[str]:
        """Node ids in build order: column by column, top to bottom."""
        return [node_id for column in self.layout for node_id in column]


class CodeSlide(SlideBase):
    """A terminal or file card. ``highlight`` brightens lines per build step."""

    kind: Literal["code"]
    title: str | None = None
    file: str = "terminal"  # the title bar label: a file name or "terminal"
    language: Literal["auto", "yaml", "json", "shell", "text"] = "auto"
    code: str = Field(min_length=1)
    highlight: list[tuple[int, list[int]]] = Field(default_factory=list)  # [step, [lines]]

    @model_validator(mode="after")
    def _highlights_fit(self) -> Self:
        count = len(self.lines())
        steps = [step for step, _ in self.highlight]
        check_unique((str(step) for step in steps), "Highlight step")
        for step, numbers in self.highlight:
            if not 1 <= step <= MAX_STEPS:
                raise ValueError(f"Highlight step {step} must be from 1 to {MAX_STEPS}")
            for number in numbers:
                if not 1 <= number <= count:
                    raise ValueError(f"Highlight line {number} is outside the code (1 to {count})")
        return self

    def lines(self) -> list[str]:
        return self.code.rstrip("\n").split("\n")

    def resolved_language(self) -> str:
        if self.language != "auto":
            return self.language
        name = self.file.lower()
        if name.endswith((".yaml", ".yml")):
            return "yaml"
        if name.endswith(".json"):
            return "json"
        if name == "terminal" or name.endswith((".sh", ".txt")) or "terminal" in name:
            return "shell"
        return "text"


class TimelineMarker(StrictModel):
    t: float = Field(ge=0.0)
    label: str
    id: Identifier | None = None  # what a phrase pin names; the label works too


class TimelinePhrase(StrictModel):
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)
    label: str
    pin: str | None = None  # a marker id or label this phrase snaps onto

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"Phrase '{self.label}' must end after it starts")
        return self


class TimelineHold(StrictModel):
    at: float = Field(ge=0.0)
    seconds: float = Field(gt=0.0)


class TimelineConflict(StrictModel):
    at: float = Field(ge=0.0)
    label: str


class TimelineSlide(SlideBase):
    """A track in seconds: clicks, phrases snapping onto them, holds and conflicts.

    Steps: the track first, then the phrases, then the holds, then the conflicts.
    """

    kind: Literal["timeline"]
    title: str | None = None
    duration: float | None = Field(default=None, gt=0.0)  # track length; fits the content
    markers: list[TimelineMarker] = Field(default_factory=list)
    phrases: list[TimelinePhrase] = Field(default_factory=list)
    holds: list[TimelineHold] = Field(default_factory=list)
    conflicts: list[TimelineConflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fits(self) -> Self:
        if not (self.markers or self.phrases or self.holds or self.conflicts):
            raise ValueError("A timeline needs at least one marker, phrase, hold or conflict")
        check_unique((m.id for m in self.markers if m.id), "Marker")
        names = {m.id for m in self.markers if m.id} | {m.label for m in self.markers}
        for phrase in self.phrases:
            if phrase.pin is not None and phrase.pin not in names:
                raise ValueError(f"Phrase '{phrase.label}' pins to '{phrase.pin}', not a marker")
        if self.duration is not None and self.content_end() > self.duration + 1e-6:
            raise ValueError(
                f"Timeline content runs to {self.content_end():g} s, past its duration"
                f" ({self.duration:g} s)"
            )
        return self

    def content_end(self) -> float:
        ends = [m.t for m in self.markers] + [p.end for p in self.phrases]
        ends += [h.at + h.seconds for h in self.holds] + [c.at for c in self.conflicts]
        return max(ends, default=0.0)

    def track_seconds(self) -> float:
        """The track length: duration, or the content rounded up to a whole second."""
        if self.duration is not None:
            return self.duration
        return float(int(self.content_end()) + 1)

    def marker_for(self, pin: str) -> TimelineMarker | None:
        by_id = next((m for m in self.markers if m.id == pin), None)
        return by_id or next((m for m in self.markers if m.label == pin), None)

    def stages(self) -> list[str]:
        """The build steps in order: track, phrases, holds, conflicts."""
        out = ["track"]
        out += ["phrases"] if self.phrases else []
        out += ["holds"] if self.holds else []
        out += ["conflicts"] if self.conflicts else []
        return out


class CompareRow(StrictModel):
    before: str
    now: str


class CompareSlide(SlideBase):
    """Before and now rows, one row per build step."""

    kind: Literal["compare"]
    title: str | None = None
    before_label: str = "Before"
    now_label: str = "Now"
    rows: list[CompareRow] = Field(min_length=1, max_length=6)


class StatsHero(StrictModel):
    value: float
    of: float | None = None  # shown as "value / of"
    label: str
    suffix: str = ""  # straight after the number, for example "s" or "%"


class StatsMetric(StrictModel):
    label: str
    value: str
    bar: Fraction | tuple[Fraction, Fraction] | None = None  # a fill, or a [from, to] band

    @model_validator(mode="after")
    def _band_in_order(self) -> Self:
        if isinstance(self.bar, tuple) and self.bar[1] <= self.bar[0]:
            raise ValueError(f"Metric '{self.label}': in a bar band [from, to], to must be larger")
        return self


class StatsSlide(SlideBase):
    """A hero number that counts up, then metric cards one per step, then chips."""

    kind: Literal["stats"]
    title: str | None = None
    hero: StatsHero
    metrics: list[StatsMetric] = Field(default_factory=list, max_length=4)
    chips: list[str] = Field(default_factory=list, max_length=12)

    def stages(self) -> list[str]:
        out = ["hero"] + [f"metric{i}" for i in range(len(self.metrics))]
        return out + (["chips"] if self.chips else [])


class GalleryImage(StrictModel):
    image: str  # a path relative to the demo folder
    label: str
    frame: Literal["auto", "phone", "browser", "plain"] = "auto"


class GallerySlide(SlideBase):
    """2 or 3 images in device frames, side by side. Each image is one build step."""

    kind: Literal["gallery"]
    title: str | None = None
    images: list[GalleryImage] = Field(min_length=2, max_length=3)


SlideItem = Annotated[
    TitleSlide
    | FlowSlide
    | ChartSlide
    | BulletsSlide
    | CardsSlide
    | ArchitectureSlide
    | CodeSlide
    | TimelineSlide
    | CompareSlide
    | StatsSlide
    | GallerySlide,
    Field(discriminator="kind"),
]


class SlidesModel(StrictModel):
    version: Literal[1] = 1
    slides: list[SlideItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_slide_ids(self) -> Self:
        check_unique((slide.id for slide in self.slides), "Slide")
        return self

    def slide(self, slide_id: str) -> SlideItem | None:
        return next((item for item in self.slides if item.id == slide_id), None)
