"""Every command module is found without a hand kept list."""

from __future__ import annotations

import pkgutil

import reelsmith.commands
from reelsmith.cli import app, command_modules


def test_every_command_module_is_discovered() -> None:
    on_disk = {m.name for m in pkgutil.iter_modules(reelsmith.commands.__path__)}
    assert set(command_modules()) == on_disk


def test_discovered_commands_are_registered() -> None:
    names = {c.name for c in app.registered_commands} | {g.name for g in app.registered_groups}
    for expected in ("doctor", "init", "slides", "capture"):
        assert expected in names
