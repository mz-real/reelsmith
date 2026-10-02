## What

One or two sentences: what user-visible problem does this fix or what does it add?

## Changes

- Bullet list of the main code or doc changes

## Checks

- [ ] Tests added or updated for behaviour that changed
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q && uv run python scripts/check_dashes.py` passes locally
- [ ] No em dashes or en dashes in new text (CI runs `scripts/check_dashes.py`)
- [ ] Docs updated if CLI behaviour or user workflow changed

**PR title:** use a [Conventional Commit](https://www.conventionalcommits.org/) style title, for example `feat(capture): support import rotation metadata`. Squash merge uses this title.
