"""Environment checks and optional fixes for reelsmith."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reelsmith.doctor.checks import Check, run_all_checks
from reelsmith.doctor.fixes import apply_fixes
from reelsmith.doctor.profiles import DoctorProfile, format_skipped_line, resolve_profile
from reelsmith.result import Result, Status, emit


def format_check_details(checks: list[Check]) -> list[str]:
    """Build result detail lines with status prefixes and fix hints."""
    lines: list[str] = []
    for check in checks:
        lines.append(f"{check.status.value} {check.name}: {check.found}")
        if check.status != Status.OK and check.fix:
            lines.append(f"    fix: {check.fix}")
    return lines


def run_doctor(
    *,
    spec_path: Path | None,
    profile: DoctorProfile | None,
    apply_fix: bool,
    yes: bool,
    ask_confirm: Callable[[str], bool],
) -> int:
    """Run checks, optionally apply fixes, and print the result block."""
    resolved_profile, resolved_spec = resolve_profile(profile, spec_path)
    checks = run_all_checks(resolved_spec, profile=resolved_profile)
    if apply_fix:
        checks = apply_fixes(
            checks,
            spec_path=resolved_spec,
            profile=resolved_profile,
            yes=yes,
            ask_confirm=ask_confirm,
        )

    errors = [c for c in checks if c.status == Status.ERROR]
    warns = [c for c in checks if c.status == Status.WARN]
    details = [f"profile: {resolved_profile.value}"]
    skipped = format_skipped_line(resolved_profile, resolved_spec)
    if skipped is not None:
        details.append(skipped)
    details.extend(format_check_details(checks))

    if errors:
        first = errors[0]
        return emit(
            Result(
                status=Status.ERROR,
                message=f"{len(errors)} check(s) failed.",
                details=details,
                next_step=first.fix,
            )
        )
    if warns:
        first = warns[0]
        return emit(
            Result(
                status=Status.WARN,
                message=f"{len(warns)} warning(s). You can still run most commands.",
                details=details,
                next_step=first.fix,
            )
        )
    return emit(
        Result(
            status=Status.OK,
            message="All checks passed.",
            details=details,
            next_step="reelsmith init my-demo",
        )
    )


__all__ = [
    "Check",
    "DoctorProfile",
    "format_check_details",
    "run_all_checks",
    "run_doctor",
]
