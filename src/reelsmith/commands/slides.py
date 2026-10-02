"""`reelsmith slides`: render slides.yaml to PNG images."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.errors import ReelsmithError
from reelsmith.models import BrandModel, SpecModel, load_model
from reelsmith.models.slides import SlidesModel
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit
from reelsmith.slides.render import render_slides_to_dir
from reelsmith.slides.themes import frame_size, resolve_theme


def run_slides(root: Path) -> Result:
    paths = DemoPaths.at(root.resolve())
    slides_path = paths.root / "slides.yaml"
    if not paths.spec.is_file():
        raise ReelsmithError(f"{paths.spec} not found", fix="reelsmith init")
    if not slides_path.is_file():
        raise ReelsmithError(f"{slides_path} not found", fix="Add slides.yaml to the demo folder")
    spec = load_model(paths.spec, SpecModel)
    slides = load_model(slides_path, SlidesModel)
    brand = BrandModel.model_validate({})
    if paths.brand.is_file():
        brand = load_model(paths.brand, BrandModel)
    theme = resolve_theme(spec, brand, paths.root)
    width, height = frame_size(spec)
    paths.slides.mkdir(parents=True, exist_ok=True)
    written = render_slides_to_dir(
        slides,
        theme,
        paths.slides,
        width=width,
        height=height,
    )
    return Result(
        status=Status.OK,
        message=f"Rendered {len(slides.slides)} slide(s) at {width}x{height}",
        details=[f"wrote slides/{name}" for name in written],
        next_step="reelsmith compose --preview",
    )


def register(app: typer.Typer) -> None:
    @app.command("slides")
    def slides_cmd(
        directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    ) -> int:
        """Render slides from slides.yaml using the spec format and brand file."""
        return emit(run_slides(demo_dir(directory, None)))
