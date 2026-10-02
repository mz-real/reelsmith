"""Load and save the file models as YAML or JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing

M = TypeVar("M", bound=BaseModel)

YAML_SUFFIXES = (".yaml", ".yml")


def load_model(path: Path, model: type[M]) -> M:
    """Read a YAML or JSON file (by suffix) into a model.

    Any problem becomes a ReelsmithError that names the file and the field.
    """
    data = _read_data(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ReelsmithError(
            f"{path.name} is not valid: {_describe(exc)}",
            fix=f"Edit {path} and run the command again",
        ) from None


def save_model(path: Path, obj: BaseModel) -> None:
    """Write a model as YAML or JSON (by suffix), backing up any old file."""
    suffix = _suffix(path)
    data = obj.model_dump(mode="json")
    if suffix == ".json":
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    else:
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing(path)
    path.write_text(text, encoding="utf-8")


def _suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in (*YAML_SUFFIXES, ".json"):
        raise ReelsmithError(f"{path.name} must be a YAML or JSON file")
    return suffix


def _read_data(path: Path) -> Any:
    suffix = _suffix(path)
    if not path.is_file():
        raise ReelsmithError(f"{path} not found")
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ReelsmithError(
            f"{path.name} could not be read: {exc}",
            fix=f"Fix the syntax in {path}",
        ) from None
    return {} if data is None else data


def _describe(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"]) or "file"
        message = error["msg"].removeprefix("Value error, ")
        parts.append(f"{where}: {message}")
    return "; ".join(parts)
