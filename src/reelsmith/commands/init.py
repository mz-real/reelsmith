"""reelsmith init: create a new demo folder."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit


def _starter_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "starter"


def _is_empty_dir(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        raise ReelsmithError(f"{path} is not a directory.")
    return not any(path.iterdir())


def init_demo(root: Path, *, force: bool) -> int:
    """Create the demo tree and copy starter YAML files."""
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
    starter = _starter_dir()
    if not starter.is_dir():
        raise ReelsmithError("Starter templates are missing from the install.")

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
    for name in ("spec.yaml", "brand.yaml", "script.yaml"):
        src = starter / name
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
    details.extend(backup_notes)

    return emit(
        Result(
            status=Status.OK,
            message=f"Demo folder ready at {root}",
            details=details,
            next_step=f"cd {root} and edit spec.yaml",
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
    ) -> None:
        """Create a demo folder with starter spec, brand and script files."""
        raise typer.Exit(init_demo(directory, force=force))
