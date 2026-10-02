# Installing reelsmith

reelsmith runs on Windows, macOS and Linux. CI runs the test suite on all three.

> 0.1.0 is not released yet, so reelsmith is not on PyPI. The commands below install it from source. Once it is published, swap `git+https://github.com/mz-real/reelsmith` for `reelsmith`.

## What you need

| Piece | Needed for | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | everything | installs reelsmith and, if needed, Python |
| Python 3.11 to 3.13 | everything | uv picks or downloads one |
| ffmpeg 6 or newer | everything | must be on your PATH |
| Chromium | web capture and slides | `reelsmith setup browser` |
| Java 17 or newer | mobile capture only | needed by Maestro |
| Maestro | mobile capture only | drives taps from a YAML flow |
| adb | Android capture only | from Android platform tools |
| Xcode | iOS capture only | macOS only |
| Python 3.11 or 3.12 | own voice cloning only | Chatterbox does not run on 3.13 yet |

Web capture and Narrate mode need only the first four rows.

## Install the CLI

```
uv tool install git+https://github.com/mz-real/reelsmith
reelsmith --version
```

With own voice cloning (see [voices.md](voices.md)):

```
uv tool install --python 3.12 "reelsmith[clone] @ git+https://github.com/mz-real/reelsmith"
```

Open a new terminal afterwards if `reelsmith` is not found, so the PATH picks up the uv tool folder. `uv tool update-shell` adds that folder to your PATH if it is missing.

Then install the browser and check the machine:

```
reelsmith setup browser
reelsmith doctor
```

doctor prints one line per check and a fix for your OS. `[WARN]` means something optional is missing, such as Maestro when you only capture web. `reelsmith doctor --fix` offers to run the fixes and asks yes or no before each one. `--fix --yes` runs them all without asking. doctor says when a fix needs `sudo`.

`reelsmith doctor --spec spec.yaml` also checks that Chatterbox is installed when the spec asks for it.

## Windows

```
winget install ffmpeg
reelsmith setup browser
```

For mobile capture (Android only on Windows):

```
winget install EclipseAdoptium.Temurin.17.JDK
winget install Google.PlatformTools
```

Install Maestro with the Windows steps in the [Maestro docs](https://docs.maestro.dev/). The `curl ... | bash` installer is for macOS and Linux.

Tips:

- Quote paths that contain spaces.
- In YAML files use forward slashes (`C:/Users/me/ref.wav`) or single quotes. Inside double quotes a backslash starts an escape.
- In PowerShell, set an environment variable with `$env:NAME="value"`, not `NAME=value command`.
- Models are cached in `%LOCALAPPDATA%\reelsmith`.

## macOS

```
brew install ffmpeg
reelsmith setup browser
```

For mobile capture:

```
brew install --cask temurin@17
curl -fsSL "https://get.maestro.mobile.dev" | bash
```

- iOS: install Xcode from the App Store, then run `xcode-select --install`. reelsmith records the simulator with `xcrun simctl`.
- Android: `brew install --cask android-platform-tools` for adb, plus an emulator or a USB device with debugging on.

Models are cached in `~/Library/Caches/reelsmith`.

## Linux

Debian or Ubuntu:

```
sudo apt install ffmpeg
reelsmith setup browser
```

Fedora:

```
sudo dnf install ffmpeg
reelsmith setup browser
```

If Chromium fails to start, it may be missing system libraries. `uvx playwright install-deps chromium` installs them (it asks for `sudo`).

For Android capture, install Java 17 or newer (your distro's OpenJDK 17 package works), adb (`sudo apt install adb` on Debian or Ubuntu), and Maestro:

```
curl -fsSL "https://get.maestro.mobile.dev" | bash
```

iOS capture needs macOS, so it is not available on Linux or Windows.

Models are cached in `~/.cache/reelsmith` (or under `$XDG_CACHE_HOME`).

## Models and disk space

Models download on first use, not at install time:

| Model | Size | Used by |
|---|---|---|
| Kokoro `kokoro-v1.0.int8.onnx` | 114 MB | stock voices |
| Kokoro `voices-v1.0.bin` | 28 MB | stock voices |
| faster-whisper `base.en` | about 145 MB | dropped word check and QA |
| Chatterbox | large, PyTorch plus the model weights | own voice cloning, only with the `clone` extra |

That is about 290 MB before you clone anything. doctor shows whether each model is cached.

## GPU notes for cloning

Kokoro and Whisper run fine on a laptop CPU. A GPU matters only for Chatterbox.

reelsmith picks the device in this order:

1. NVIDIA GPU with CUDA
2. Apple Silicon (MPS)
3. CPU, with a warning. Expect a minute or more per line.

Notes per OS:

- **macOS on Apple Silicon:** works out of the box through MPS. Intel Macs use the CPU.
- **Linux with NVIDIA:** install the NVIDIA driver so `nvidia-smi` works. The PyTorch wheels from PyPI include CUDA support on Linux.
- **Windows with NVIDIA:** the default PyTorch wheel on Windows is CPU only. If cloning is slow even though doctor shows your GPU, install a CUDA build of PyTorch into the reelsmith tool environment, following the [PyTorch install guide](https://pytorch.org/get-started/locally/).
- **AMD or Intel GPUs:** not used. Cloning runs on the CPU.

doctor's GPU line only tells you that a GPU is there (it looks for `nvidia-smi` or Apple Silicon). It does not prove that PyTorch can use it. The CPU warning during cloning is the reliable sign.

## Updating and removing

```
uv tool upgrade reelsmith
uv tool uninstall reelsmith
```

To free disk space, delete the model cache folder for your OS listed above. reelsmith downloads the models again when it needs them.
