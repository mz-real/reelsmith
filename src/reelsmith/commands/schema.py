"""`reelsmith schema export`: write the JSON schemas for every file format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from reelsmith.fsutil import backup_existing
from reelsmith.models import BrandModel, ClipModel, ScriptModel, SlidesModel, SpecModel
from reelsmith.result import Result, Status, emit

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "spec": SpecModel,
    "brand": BrandModel,
    "clip": ClipModel,
    "script": ScriptModel,
    "slides": SlidesModel,
}


def build_schemas() -> dict[str, str]:
    """File name to JSON text for each published schema."""
    files: dict[str, str] = {}
    for name, model in SCHEMA_MODELS.items():
        schema = {"$schema": SCHEMA_DIALECT, **model.model_json_schema()}
        files[f"{name}.schema.json"] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    return files


def export_schemas(out_dir: Path) -> tuple[list[str], list[str]]:
    """Write the schemas, backing up changed files. Returns (written, unchanged)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    unchanged: list[str] = []
    for name, text in build_schemas().items():
        path = out_dir / name
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            unchanged.append(name)
            continue
        backup_existing(path)
        path.write_text(text, encoding="utf-8")
        written.append(name)
    return written, unchanged


def register(app: typer.Typer) -> None:
    schema_app = typer.Typer(help="Work with the JSON schemas of the file formats.")

    @schema_app.command("export")
    def export(
        out: Annotated[Path, typer.Option("--out", help="Folder to write the schemas to.")] = Path(
            "schemas"
        ),
    ) -> int:
        """Write spec, brand, clip, script and slides schemas as JSON files."""
        written, unchanged = export_schemas(out)
        return emit(
            Result(
                status=Status.OK,
                message=f"Schemas in {out}: {len(written)} written, {len(unchanged)} unchanged",
                details=[f"wrote {name}" for name in written],
            )
        )

    app.add_typer(schema_app, name="schema")
