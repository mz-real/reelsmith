"""The shared result block every reelsmith command ends with.

By default it is printed as text. With the global `reelsmith --json` flag it
is printed as one compact JSON object instead, so an AI tool can read it
without parsing text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

import typer


class Status(StrEnum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class Result:
    status: Status
    message: str
    details: list[str] = field(default_factory=list)
    next_step: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "message": self.message,
            "details": list(self.details),
            "next": self.next_step,
        }


_json_mode = False


def set_json_mode(on: bool) -> None:
    """Print result blocks as JSON (True) or as text (False)."""
    global _json_mode
    _json_mode = on


def json_mode() -> bool:
    return _json_mode


def print_json(data: object) -> None:
    """Print one compact JSON object on one line."""
    typer.echo(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def emit(result: Result) -> int:
    """Print the result block and return the process exit code.

    Returns 0 for OK and WARN, 1 for ERROR.
    """
    if _json_mode:
        print_json(result.to_json())
    else:
        typer.echo(f"[{result.status.value}] {result.message}")
        for detail in result.details:
            typer.echo(f"  - {detail}")
        if result.next_step is not None:
            typer.echo(f"Next: {result.next_step}")
    return 1 if result.status == Status.ERROR else 0
