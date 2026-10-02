# Security policy

## Supported versions

We support security fixes for the **latest minor release** of reelsmith on PyPI. Older minors are not maintained. Upgrade to the current release before reporting if you can.

## Reporting a vulnerability

**Do not** open a public GitHub issue for security problems.

Use GitHub **private vulnerability reporting** on this repository:

1. Go to https://github.com/mz-real/reelsmith/security/advisories
2. Choose **Report a vulnerability** (or use the Security tab on the repo and **Report a vulnerability**)

Include:

- A clear description of the issue and the impact you expect
- Steps to reproduce, or a minimal proof of concept if you have one
- Your reelsmith version (`reelsmith --version`) and OS
- Whether you are willing to be credited in a future advisory (optional)

We aim to reply within **7 days**. We will work with you on a fix and coordinate disclosure when a release is ready.

## Design notes relevant to security

reelsmith is **local only**. It does not upload your demos, recordings or voice samples to a reelsmith server. Voice models (Kokoro, faster-whisper, optional Chatterbox) are fetched from their official distribution paths into your user cache when you first use them.

**Voice cloning** with Chatterbox is opt in, through the `clone` extra and your spec. reelsmith refuses to clone a voice unless `spec.yaml` records consent: your own voice, or a voice used with permission. The Chatterbox watermark stays on.

Third party tools (ffmpeg, Playwright, Maestro) run on your machine with your privileges. Keep them updated and install them from sources you trust.
