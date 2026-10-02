"""Errors raised by reelsmith and shown to the user with a fix."""

from __future__ import annotations


class ReelsmithError(Exception):
    """An error with a message and an optional, exact fix command.

    The CLI catches this and prints an ERROR result block instead of a
    traceback.
    """

    def __init__(self, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix

    def __str__(self) -> str:
        return self.message
