# Troubleshooting

## Goal

Get the user unstuck fast when a command fails. Read the result block first: the `[ERROR]` line says what went wrong and the `Next:` line is usually the exact fix. This guide covers the rest.

## Rules

{{rules}}

## What to ask or check

- Read the whole result block and anything printed above it. Quote the error to the user in plain words.
- Run `reelsmith doctor`. It checks Python, ffmpeg, the browser, Java and Maestro, the simulators, the voice models, Chatterbox and the GPU, and prints a fix for this OS.
- Check the version: `reelsmith --version`. These instructions expect reelsmith {{version}}.
- Ask before you install anything, and say when a fix needs admin rights (`sudo`, or an admin terminal on Windows).

## Commands

```
reelsmith --version
REELSMITH_EXPECTED_VERSION={{version}} reelsmith doctor
reelsmith doctor --spec spec.yaml        # also checks Chatterbox if spec.yaml asks for it
reelsmith setup browser                  # installs the Chromium build reelsmith uses
reelsmith script check                   # finds pin and scene id problems
```

On Windows PowerShell, set the version first: `$env:REELSMITH_EXPECTED_VERSION="{{version}}"; reelsmith doctor`.

`reelsmith doctor --fix` lists each fix and asks yes or no in the terminal before running it. Your tool may not be able to answer those prompts, so either ask the user to run it in their own terminal, or list the fixes to the user, get a yes for all of them, and then run `reelsmith doctor --fix --yes`.

Install or update reelsmith:

```
{{install}}
{{install_clone}}        # with own voice cloning, Python 3.11 or 3.12
uv tool upgrade reelsmith
```

## Reading the output

doctor prints one detail line per check and ends like this:

```
[ERROR] 1 check(s) failed.
  - ...
Next: brew install ffmpeg
```

`[WARN]` from doctor means something optional is missing (for example Maestro when you only capture web). You can carry on unless you need that piece. `[OK] All checks passed.` means the machine is ready.

Every other command works the same way: `[OK]` or `[WARN]` exit 0, `[ERROR]` exits 1, and `Next:` is the step to take. Errors never print a traceback on purpose, so if you see one, that is a bug: ask the user to report it at https://github.com/mz-real/reelsmith/issues with the command and the output.

## Common failures and fixes

| Problem | Fix |
|---|---|
| `reelsmith: command not found` | `{{install}}`. If uv itself is missing, see https://docs.astral.sh/uv/. Open a new terminal afterwards so the PATH updates. |
| doctor warns the plugin version does not match | Upgrade the CLI with `uv tool upgrade reelsmith`, or update the plugin or instruction files to match. |
| ffmpeg missing or older than 6 | macOS `brew install ffmpeg`, Windows `winget install ffmpeg`, Debian or Ubuntu `sudo apt install ffmpeg`, Fedora `sudo dnf install ffmpeg`. |
| Chromium missing | `reelsmith setup browser` |
| Java missing or older than 17 (mobile only) | Use the Temurin 17 command doctor prints. |
| Maestro missing (mobile only) | Use the install command doctor prints. |
| `xcrun simctl` missing (iOS only) | Install Xcode from the App Store, then `xcode-select --install`. |
| `... is not valid: ...` for a YAML or JSON file | The message names the field. Fix that field and rerun. |
| `... not found` with `Next: reelsmith init` | You are not in the demo folder. `cd` into it or pass the folder to the command. |
| `... is not empty. Use --force to init anyway.` | Use a new folder for the demo. |
| `Could not download ...` | Check the network and retry. The `Next:` line has a manual download link. Models are cached after the first download. |
| `Chatterbox voice cloning is not installed.` | `{{install_clone}}` with Python 3.11 or 3.12, or use a Kokoro voice. |
| compose says `slides/<id>.png, which is missing` | `reelsmith slides` |
| compose says a wav is missing | `reelsmith voice generate` |
| compose `[WARN]` with lines some seconds over | Shorten those lines, then `reelsmith voice generate` and `reelsmith compose`. |
| A command seems to hang | Rendering and the first model download take time. Long steps resume after a crash, so rerunning is safe. |
| Old output was replaced | It was not: reelsmith keeps the previous file as `<name>.bak-<date>-<time>` next to it. |

## Done when

- [ ] The failing command now ends with `[OK]`, or with a `[WARN]` the user understands and accepts.
- [ ] `reelsmith doctor` shows no ERROR for the pieces this demo needs.
- [ ] You went back to the step that failed and carried on with the workflow.
