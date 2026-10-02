"""`reelsmith slides`: render slides.yaml to PNG images."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from reelsmith.commands._common import DEMO_DIR_HELP, demo_dir
from reelsmith.compose.layouts import format_slug
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
    paths.slides.mkdir(parents=True, exist_ok=True)
    first_fmt = spec.formats[0]
    details: list[str] = []
    for fmt in spec.formats:
        width, height = frame_size(spec, fmt)
        slug = format_slug(fmt)
        fmt_dir = paths.slides / slug
        written = render_slides_to_dir(
            slides,
            theme,
            fmt_dir,
            width=width,
            height=height,
        )
        details.append(f"{slug}: {len(written)} image(s) at {width}x{height}")
        if fmt == first_fmt:
            for name in written:
                shutil.copy2(fmt_dir / name, paths.slides / name)
                details.append(f"wrote slides/{name}")
    count = len(spec.formats)
    label = "format" if count == 1 else "formats"
    return Result(
        status=Status.OK,
        message=f"Rendered {len(slides.slides)} slide(s) in {count} {label}",
        details=details,
        next_step="reelsmith compose --preview",
    )


def register(app: typer.Typer) -> None:
    @app.command("slides")
    def slides_cmd(
        directory: Annotated[Path | None, typer.Argument(help=DEMO_DIR_HELP)] = None,
    ) -> int:
        """Render slides from slides.yaml using the spec format and brand file."""
        return emit(run_slides(demo_dir(directory, None)))
