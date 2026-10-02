# Contributing to reelsmith

Thanks for helping. This repo is MIT licensed. We use one pull request per change, squash merge, and Conventional Commits.

## Dev setup

You need [uv](https://docs.astral.sh/uv/), Python 3.11 to 3.13, and ffmpeg on your PATH.

```bash
git clone https://github.com/mz-real/reelsmith.git
cd reelsmith
uv sync
uv run playwright install chromium
```

Install ffmpeg for your OS:

- **Windows:** `winget install Gyan.FFmpeg` (or another build you trust)
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg` or `sudo dnf install ffmpeg`

Run `uv run reelsmith doctor` to see what is missing.

## Checks before you open a PR

Run this from the repo root:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q && uv run python scripts/check_dashes.py
```

CI runs the same steps on Windows, macOS and Linux.

## Tests that need real models

Some tests call Kokoro or Whisper and are skipped by default. To run them locally:

```bash
REELSMITH_TEST_MODELS=1 uv run pytest -q -m models
```

They download about 290 MB of models into your user cache the first time.

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org/) for PR titles (squash merge uses the title):

- `feat(voice): add pace retry for long lines`
- `fix(capture): handle clips with no audio track`
- `test: cover hold conflict when holds are off`
- `docs: clarify narrate workflow`
- `chore(ci): bump ruff`

Open one PR per logical change. Keep diffs focused.

## Writing style

Docs, CLI messages, issue text and comments should read like a person wrote them:

- Short sentences. Plain words. No marketing filler.
- No em dashes or en dashes. Use commas, colons or full stops. `scripts/check_dashes.py` enforces this in CI.

## Adding a CLI command

1. Add a module under `src/reelsmith/commands/`, for example `src/reelsmith/commands/foo.py`.
2. Implement `def register(app: typer.Typer) -> None:` and attach your subcommand with `@app.command(...)`.
3. That is all for registration. `reelsmith.cli` finds every module in `reelsmith.commands` on start.
4. Add tests under `tests/` mirroring the module layout.
5. End the command with the shared result block from `reelsmith.result` (see existing commands).

Look at `src/reelsmith/commands/doctor.py` for a small example.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind and professional.
