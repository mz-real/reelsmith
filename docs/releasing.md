# Releasing reelsmith

This guide is for maintainers. Nothing here runs automatically except the GitHub Actions workflow when you push a version tag. Do not publish until you intend to.

## One time setup (repository owner)

1. Configure [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) for this GitHub repository.
2. Add a GitHub Actions environment named `pypi` and require your approval if you want a manual gate before upload.

The release workflow will not work until both are in place. See the comment at the top of `.github/workflows/release.yml`.

## Release steps

1. **Bump the version** in `pyproject.toml` (Semantic Versioning). For the first PyPI release, also set `published = true` under `[tool.reelsmith]`, so the generated instructions offer `uv tool install reelsmith` instead of the Git URL.

2. **Regenerate instruction files** so the plugin, marketplace manifest and every AI guide carry the same version:

   ```bash
   uv run python scripts/gen_instructions.py
   ```

3. **Update the changelog.** Move everything under `## [Unreleased]` into a new section:

   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD
   ```

   Use today's date in ISO form. Leave an empty `## [Unreleased]` section at the top for the next cycle.

4. **Run the full check suite** from the repo root (same as CI):

   ```bash
   uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q && uv run python scripts/check_dashes.py && uv run python scripts/gen_instructions.py --check && uv run python scripts/check_version.py
   ```

5. **Complete the manual checklist** below. Do not skip it for a public release.

6. **Open a pull request** with the version bump, regenerated files and changelog. Wait for green CI on Windows, macOS and Linux, then merge to `main`.

7. **Tag the release** on `main` (only after merge):

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

   The tag must match `pyproject.toml` (with a `v` prefix on the tag only).

8. **Let the release workflow run.** On tag push it verifies versions, runs tests, builds the wheel, publishes to PyPI with trusted publishing, and creates a GitHub Release. Release notes come from the matching `CHANGELOG.md` section.

9. **Attach the tutorial video** to the GitHub Release as an asset. The video is not stored in the repo. Use a Kokoro stock voice only, no personal voice clips.

## Manual checklist before you merge the release PR

Tick every box. These steps need real hardware, simulators or your own voice. CI does not cover them.

- [ ] **Chatterbox cloning (own voice, with consent in spec.yaml):** run `voice pick-reference`, `voice compare`, and `voice generate` on a recording you own. Confirm the watermark is present on cloned output.
- [ ] **Maestro mobile capture:** on a real iOS simulator and an Android emulator, run `capture mobile` for a short flow. Open the clip and check event timings against the frames.
- [ ] **Recipe Box end to end:** drive a full `examples/recipe-box` run from Claude Code, Codex and Gemini CLI using the shipped instruction files.
- [ ] **QA:** `reelsmith qa` reports clean (no FAIL lines you accept for release).
- [ ] **Human review:** watch the exported frames or video and transcribe every spoken line against `script.yaml`.
- [ ] **Privacy scan:** search the demo folder, script and output for personal data, employer names, API keys and secrets.
- [ ] **Clean install:** on a machine that never had reelsmith, install the plugin from the marketplace and confirm `reelsmith doctor` passes with the expected version.

## After release

- Confirm the PyPI package version matches the tag.
- Confirm the GitHub Release notes match the changelog section.
- Update the README preview link if the tutorial video URL changed.

Nothing is pushed to PyPI or tagged without the owner's explicit approval.
