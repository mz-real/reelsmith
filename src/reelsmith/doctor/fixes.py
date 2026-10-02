"""Apply doctor fixes when the user agrees."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reelsmith.doctor.checks import Check
from reelsmith.result import Status


@dataclass(frozen=True)
class _FixPlan:
    check_name: str
    description: str
    command: list[str]
    needs_admin: bool


def apply_fixes(
    checks: list[Check],
    *,
    spec_path: Path | None,
    yes: bool,
    ask_confirm: Callable[[str], bool],
) -> list[Check]:
    """Re-run checks after optional fixes. Returns the latest check results."""
    fixable = [c for c in checks if c.status != Status.OK and c.fix and _plan_for(c)]
    if not fixable:
        return checks

    import typer

    typer.echo("Fixes reelsmith can run:")
    for check in fixable:
        plan = _plan_for(check)
        if plan is not None:
            typer.echo(f"  - {plan.description}: {' '.join(plan.command)}")

    applied = False
    for check in fixable:
        plan = _plan_for(check)
        if plan is None:
            continue
        prompt = _format_prompt(plan)
        if not yes and not ask_confirm(prompt):
            continue
        subprocess.run(plan.command, check=False)
        applied = True

    if not applied:
        return checks

    from reelsmith.doctor.checks import run_all_checks

    return run_all_checks(spec_path=spec_path)


def _format_prompt(plan: _FixPlan) -> str:
    cmd = " ".join(plan.command)
    admin = " (may need administrator rights)" if plan.needs_admin else ""
    return f"{plan.description}{admin}\nRun: {cmd} [y/N] "


def _plan_for(check: Check) -> _FixPlan | None:
    fix = check.fix
    if fix is None:
        return None
    builders: dict[str, Callable[[], _FixPlan | None]] = {
        "ffmpeg": _ffmpeg_plan,
        "chromium": _chromium_plan,
        "java": _java_plan,
        "maestro": _maestro_plan,
        "adb": _adb_plan,
    }
    builder = builders.get(check.name)
    if builder is not None:
        return builder()
    if check.name == "simctl":
        return None
    return None


def _ffmpeg_plan() -> _FixPlan:
    system = platform.system()
    if system == "Darwin":
        return _FixPlan(
            "ffmpeg",
            "Install ffmpeg with Homebrew",
            ["brew", "install", "ffmpeg"],
            False,
        )
    if system == "Windows":
        return _FixPlan(
            "ffmpeg",
            "Install ffmpeg with winget",
            ["winget", "install", "ffmpeg"],
            True,
        )
    if shutil.which("dnf"):
        return _FixPlan(
            "ffmpeg",
            "Install ffmpeg with dnf",
            ["sudo", "dnf", "install", "-y", "ffmpeg"],
            True,
        )
    return _FixPlan(
        "ffmpeg",
        "Install ffmpeg with apt",
        ["sudo", "apt", "install", "-y", "ffmpeg"],
        True,
    )


def _chromium_plan() -> _FixPlan:
    return _FixPlan(
        "chromium",
        "Install Playwright Chromium",
        [sys.executable, "-m", "playwright", "install", "chromium"],
        False,
    )


def _java_plan() -> _FixPlan:
    system = platform.system()
    if system == "Darwin":
        return _FixPlan(
            "java",
            "Install Temurin 17",
            ["brew", "install", "--cask", "temurin@17"],
            False,
        )
    if system == "Windows":
        return _FixPlan(
            "java",
            "Install Temurin 17",
            ["winget", "install", "EclipseAdoptium.Temurin.17.JDK"],
            True,
        )
    if shutil.which("dnf"):
        return _FixPlan(
            "java",
            "Install OpenJDK 17",
            ["sudo", "dnf", "install", "-y", "java-17-openjdk"],
            True,
        )
    return _FixPlan(
        "java",
        "Install Temurin 17",
        ["sudo", "apt", "install", "-y", "temurin-17-jdk"],
        True,
    )


def _maestro_plan() -> _FixPlan:
    script = 'curl -fsSL "https://get.maestro.mobile.dev" | bash'
    return _FixPlan(
        "maestro",
        "Install Maestro CLI",
        ["bash", "-c", script],
        False,
    )


def _adb_plan() -> _FixPlan:
    system = platform.system()
    if system == "Darwin":
        return _FixPlan(
            "adb",
            "Install Android platform tools",
            ["brew", "install", "--cask", "android-platform-tools"],
            False,
        )
    if system == "Windows":
        return _FixPlan(
            "adb",
            "Install Android platform tools",
            ["winget", "install", "Google.PlatformTools"],
            True,
        )
    return _FixPlan(
        "adb",
        "Install adb",
        ["sudo", "apt", "install", "-y", "adb"],
        True,
    )
