"""Tests for `reelsmith schema export` and the published schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelsmith.cli import app, run
from reelsmith.commands.schema import SCHEMA_MODELS, build_schemas

REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def test_every_format_has_a_schema() -> None:
    assert set(build_schemas()) == {
        "spec.schema.json",
        "brand.schema.json",
        "clip.schema.json",
        "script.schema.json",
    }
    assert set(SCHEMA_MODELS) == {"spec", "brand", "clip", "script"}


@pytest.mark.parametrize("name", sorted(build_schemas()))
def test_published_schemas_match_the_models(name: str) -> None:
    path = REPO_SCHEMAS / name
    assert path.exists(), f"Run `reelsmith schema export` to write {name}"
    assert path.read_text(encoding="utf-8") == build_schemas()[name], (
        f"{name} is out of date. Run `reelsmith schema export`."
    )


def test_schemas_are_valid_json_and_forbid_extra_fields() -> None:
    spec = json.loads(build_schemas()["spec.schema.json"])
    assert spec["additionalProperties"] is False
    assert spec["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_export_writes_the_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "schemas"

    code = run(app, ["schema", "export", "--out", str(out_dir)])

    assert code == 0
    assert capsys.readouterr().out.startswith("[OK]")
    for name, text in build_schemas().items():
        assert (out_dir / name).read_text(encoding="utf-8") == text


def test_export_backs_up_a_changed_file_and_skips_same_ones(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "schemas"
    run(app, ["schema", "export", "--out", str(out_dir)])
    (out_dir / "spec.schema.json").write_text("{}\n", encoding="utf-8")
    capsys.readouterr()

    run(app, ["schema", "export", "--out", str(out_dir)])

    out = capsys.readouterr().out
    backups = list(out_dir.glob("spec.schema.json.bak-*"))
    assert len(backups) == 1
    assert "1 written, 3 unchanged" in out
