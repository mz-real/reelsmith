"""The shared result block every reelsmith command ends with."""

from __future__ import annotations

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


def emit(result: Result) -> int:
    """Print the result block and return the process exit code.

    Returns 0 for OK and WARN, 1 for ERROR.
    """
    typer.echo(f"[{result.status.value}] {result.message}")
    for detail in result.details:
        typer.echo(f"  - {detail}")
    if result.next_step is not None:
        typer.echo(f"Next: {result.next_step}")
    return 1 if result.status == Status.ERROR else 0
