"""reelsmith init: create a new demo folder."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path
from typing import Annotated

import typer

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit

PRESETS: tuple[str, ...] = ("quick", "tour", "mobile", "release-notes", "narrate")
PRESET_NAMES = {
    "quick": "quick feature clip",
    "tour": "full app tour",
    "mobile": "mobile demo",
    "release-notes": "release notes video",
    "narrate": "narrated recording",
}


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def _starter_dir() -> Path:
    return _templates_dir() / "starter"


def _template_files(preset: str | None) -> list[Path]:
    """The files to copy: brand.yaml from the starter, the rest from the preset."""
    starter = _starter_dir()
    if not starter.is_dir():
        raise ReelsmithError("Starter templates are missing from the install.")
    if preset is None:
        return [starter / name for name in ("spec.yaml", "brand.yaml", "script.yaml")]
    if preset not in PRESETS:
        raise ReelsmithError(
            f"Unknown preset '{preset}'. Pick one of: {', '.join(PRESETS)}.",
            fix="reelsmith init DIR --preset quick",
        )
    folder = _templates_dir() / "presets" / preset
    names = ("spec.yaml", "script.yaml", "slides.yaml")
    return [starter / "brand.yaml", *(folder / name for name in names if (folder / name).is_file())]


def _is_empty_dir(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        raise ReelsmithError(f"{path} is not a directory.")
    return not any(path.iterdir())


def init_demo(root: Path, *, force: bool, preset: str | None = None) -> int:
    """Create the demo tree and copy the starter or preset YAML files."""
    root = root.resolve()
    if root.exists() and not root.is_dir():
        raise ReelsmithError(f"{root} exists and is not a folder.")
    if not _is_empty_dir(root):
        if not force:
            raise ReelsmithError(
                f"{root} is not empty. Use --force to init anyway.",
                fix=f"reelsmith init {root} --force",
            )
    paths = DemoPaths.at(root)
    sources = _template_files(preset)

    for folder in (
        paths.flows,
        paths.clips,
        paths.voice,
        paths.slides,
        paths.build,
        paths.qa,
        paths.out,
    ):
        folder.mkdir(parents=True, exist_ok=True)

    backup_notes: list[str] = []
    for src in sources:
        name = src.name
        dst = root / name
        if not src.is_file():
            raise ReelsmithError(f"Starter file missing: {name}")
        if dst.is_file() and dst.read_bytes() == src.read_bytes():
            continue
        if dst.exists():
            backed = backup_existing(dst)
            if backed is not None:
                backup_notes.append(f"backed up {name} to {backed.name}")
        shutil.copy2(src, dst)

    details = [
        f"spec: {paths.spec}",
        f"script: {paths.script}",
    ]
    if preset is not None:
        details.insert(0, f"preset: {PRESET_NAMES[preset]}")
        if (root / "slides.yaml").is_file():
            details.append(f"slides: {root / 'slides.yaml'}")
    details.extend(backup_notes)

    next_step = f"cd {root} and edit spec.yaml"
    if preset is not None:
        next_step = (
            f"Fill in {paths.spec} from the interview, then run: "
            f"reelsmith status {shlex.quote(str(root))}"
        )
    return emit(
        Result(
            status=Status.OK,
            message=f"Demo folder ready at {root}",
            details=details,
            next_step=next_step,
        )
    )


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init_cmd(
        directory: Annotated[Path, typer.Argument(help="Folder to create or use.")],
        force: Annotated[
            bool,
            typer.Option("--force", help="Init even if the folder is not empty."),
        ] = False,
        preset: Annotated[
            str | None,
            typer.Option(
                "--preset",
                help="Start from a ready spec: " + ", ".join(PRESETS) + ".",
            ),
        ] = None,
    ) -> None:
        """Create a demo folder with starter spec, brand and script files."""
        raise typer.Exit(init_demo(directory, force=force, preset=preset))
