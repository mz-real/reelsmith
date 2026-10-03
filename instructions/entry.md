# reelsmith: make a narrated demo video

These instructions expect reelsmith {{version}}.

## Goal

Help the user get a finished, narrated demo video of their app that they are happy to share. Everything runs on their machine. The `reelsmith` CLI does all the real work: you interview the user, write a few YAML files, run commands and read their results. Never write your own video, audio or ffmpeg code.

## Before you start

1. Run `reelsmith --version`. If the command is not found, tell the user and offer to install it: `{{install}}` (or `{{install_clone}}` if they want to clone their own voice later). If they have no uv, point them to https://docs.astral.sh/uv/ first.
2. Run `reelsmith doctor` with the expected version set, so it warns if the CLI and these instructions do not match:
   - macOS and Linux: `REELSMITH_EXPECTED_VERSION={{version}} reelsmith doctor`
   - Windows PowerShell: `$env:REELSMITH_EXPECTED_VERSION="{{version}}"; reelsmith doctor`
   Doctor checks what the demo needs. In a project folder it reads `spec.yaml` and only runs the matching checks. Fix any ERROR before going on. A WARN from a check in that profile must be fixed or explained before you continue. Use `reelsmith doctor --profile all` only when you are troubleshooting the whole machine.
3. Ask before installing anything. `reelsmith doctor --fix` asks yes or no in the terminal for each fix, so ask the user to run it themselves, or get their yes and run `reelsmith doctor --fix --yes`.

## How every command reports back

Every command ends with a result block. Read it after each run.

```
[OK] Voice generated for 12 lines
  - 2 lines regenerated for pace
Next: reelsmith compose --preview
```

`[OK]` and `[WARN]` exit with code 0, `[ERROR]` with code 1. The lines that start with `-` are details. `Next:` is the suggested next step. A WARN is not a pass: read the details and tell the user what they mean.

## Workflow

1. **Interview.** Follow `{{guides}}/interview.md`. The first question picks the mode: Narrate (they already have a recording) or Produce (a full demo).
2. **Plan.** Run `reelsmith init DIR` and fill in `DIR/spec.yaml` from the answers. Show it to the user. **Approval point 1: the user approves spec.yaml.**
3. **Footage.**
   - Narrate mode: `{{guides}}/narrate.md`.
   - Web app: `{{guides}}/capture-web.md`.
   - Mobile app: `{{guides}}/capture-mobile.md`.
   - Their own recordings in Produce mode: `reelsmith capture import` (see `{{guides}}/narrate.md`).
4. **Script.** Write `script.yaml` (and `slides.yaml` in Produce mode) with `{{guides}}/script-writing.md`, then run `reelsmith script check`. Show the full script to the user. **Approval point 2: the user approves script.yaml.** Nothing is voiced or rendered before this.
5. **Voice.** `reelsmith voice generate`, see `{{guides}}/voice.md`.
6. **Slides** (Produce mode only): `reelsmith slides`.
7. **Preview.** `reelsmith compose --preview`, show the user `build/master_16x9_preview.mp4` (the name follows the format), fix what they ask, then `reelsmith compose` for the full quality render.
8. **QA.** `reelsmith qa`, then follow `{{guides}}/qa.md` until every check passes.
9. **Export.** `reelsmith export` writes the videos, the narration track and the .srt file to `out/`.

When something breaks, read `{{guides}}/troubleshooting.md`.

Any step can be rerun on its own. If the user changes words, rerun from voice. If they change only the voice, rerun voice, compose, qa and export.

## Rules

{{rules}}
- Read a guide when you reach its step, not all at once.
- Nothing is uploaded. Do not suggest online voice or video services.

## Guides

{{guide_index}}
