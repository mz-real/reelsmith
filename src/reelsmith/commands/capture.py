"""reelsmith capture: import or record clips."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from reelsmith.capture.importer import import_recording
from reelsmith.capture.mobile import run_mobile_flow
from reelsmith.capture.web import run_web_flow
from reelsmith.commands._common import DemoDirArgument, DemoDirOption, demo_dir, validate_id_option
from reelsmith.paths import DemoPaths
from reelsmith.result import Result, Status, emit

capture_app = typer.Typer(help="Import or record capture clips.")


def register(app: typer.Typer) -> None:
    @capture_app.command("import")
    def import_cmd(
        source: Annotated[Path, typer.Argument(help="Video file to import.")],
        clip_id: Annotated[str, typer.Option("--id", help="Clip id for this recording.")],
        directory: DemoDirArgument = None,
        demo_option: DemoDirOption = None,
    ) -> None:
        """Normalise a recording into capture/clips/<id>/."""
        clip_id = validate_id_option(clip_id)
        paths = DemoPaths.at(demo_dir(directory, demo_option))
        clip = import_recording(source, clip_id, paths.clips)
        raise typer.Exit(
            emit(
                Result(
                    status=Status.OK,
                    message=f"Imported clip '{clip_id}'",
                    details=[
                        f"video: {paths.clips / clip_id / clip.video}",
                        f"{clip.width}x{clip.height} at {clip.fps:g} fps, {clip.duration:.1f} s",
                    ],
                    next_step=f"reelsmith detect --clip {clip_id}",
                )
            )
        )

    @capture_app.command("web")
    def web_cmd(
        flow: Annotated[Path, typer.Argument(help="Python file with async def flow(page, log).")],
        clip_id: Annotated[str, typer.Option("--id", help="Clip id for this recording.")],
        headed: Annotated[
            bool,
            typer.Option("--headed", help="Show the browser window while recording."),
        ] = False,
        size: Annotated[
            str,
            typer.Option("--size", help="Viewport size, WIDTHxHEIGHT."),
        ] = "1280x720",
        directory: DemoDirArgument = None,
        demo_option: DemoDirOption = None,
    ) -> None:
        """Record a Playwright flow into capture/clips/<id>/."""
        clip_id = validate_id_option(clip_id)
        paths = DemoPaths.at(demo_dir(directory, demo_option))
        clip = run_web_flow(
            flow,
            clip_id,
            paths.clips,
            headed=headed,
            size=size,
        )
        event_count = len(clip.events)
        raise typer.Exit(
            emit(
                Result(
                    status=Status.OK,
                    message=f"Recorded clip '{clip_id}' with {event_count} event"
                    f"{'' if event_count == 1 else 's'}",
                    details=[f"video: {paths.clips / clip_id / clip.video}"],
                    next_step="reelsmith script check",
                )
            )
        )

    @capture_app.command("mobile")
    def mobile_cmd(
        flow: Annotated[Path, typer.Argument(help="Maestro flow YAML file.")],
        clip_id: Annotated[str, typer.Option("--id", help="Clip id for this recording.")],
        platform: Annotated[
            Literal["ios", "android"],
            typer.Option("--platform", help="ios or android."),
        ],
        device: Annotated[
            str | None,
            typer.Option("--device", help="adb device serial for Android."),
        ] = None,
        directory: DemoDirArgument = None,
        demo_option: DemoDirOption = None,
    ) -> None:
        """Record a Maestro flow into capture/clips/<id>/."""
        clip_id = validate_id_option(clip_id)
        paths = DemoPaths.at(demo_dir(directory, demo_option))
        result = run_mobile_flow(
            flow,
            clip_id,
            paths.clips,
            platform_name=platform,
            device=device,
        )
        event_count = len(result.clip.events)
        status = Status.WARN if result.warnings else Status.OK
        details = [f"video: {paths.clips / clip_id / result.clip.video}"]
        details.extend(result.warnings)
        raise typer.Exit(
            emit(
                Result(
                    status=status,
                    message=f"Recorded clip '{clip_id}' with {event_count} event"
                    f"{'' if event_count == 1 else 's'}",
                    details=details,
                    next_step="reelsmith script check",
                )
            )
        )

    app.add_typer(capture_app, name="capture")
