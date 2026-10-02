"""Layout of a reelsmith demo folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DemoPaths:
    root: Path
    spec: Path
    brand: Path
    script: Path
    flows: Path
    clips: Path
    voice: Path
    slides: Path
    build: Path
    qa: Path
    out: Path

    @classmethod
    def at(cls, root: Path) -> DemoPaths:
        capture = root / "capture"
        return cls(
            root=root,
            spec=root / "spec.yaml",
            brand=root / "brand.yaml",
            script=root / "script.yaml",
            flows=capture / "flows",
            clips=capture / "clips",
            voice=root / "voice",
            slides=root / "slides",
            build=root / "build",
            qa=root / "qa",
            out=root / "out",
        )
