# Voices

reelsmith has two voice engines behind one set of commands:

- **Kokoro** stock voices, the default. Small, fast on a CPU, no PyTorch.
- **Chatterbox** for your own voice. Optional, and only with consent.

You can also make a silent video with captions: set `voice.engine: none` in spec.yaml and skip the voice step.

Everything runs locally. No audio is sent anywhere.

## Kokoro stock voices

Good English voices:

| Voice | Accent |
|---|---|
| `af_heart` (default) | US female |
| `af_bella` | US female |
| `bf_emma` | UK female |
| `am_michael` | US male |
| `am_fenrir` | US male |
| `bm_george` | UK male |

Kokoro has more voices and other languages. English is the focus, other languages are best effort.

### Preview

Hear the same line in a few voices. Run it in the demo folder, or pass the folder as the first argument:

```
reelsmith voice preview --text "Type a dish into the search box." --voices af_heart,af_bella,bf_emma,am_michael
```

Each voice is written to `voice/preview/<voice>.wav`. Without `--voices` you get `af_heart`, `bf_emma` and `am_michael`.

### Pick one

Set it in spec.yaml:

```yaml
voice:
  engine: kokoro
  kokoro_voice: bf_emma
  speed: 1.0        # 0.9 is a bit slower, 1.1 a bit faster
```

Then voice every line of script.yaml:

```
reelsmith voice generate
reelsmith voice generate --only search/l1 --only intro/l2   # redo some lines
```

This writes `voice/<scene>__<line>.wav` and `voice/timings.json`. For each line reelsmith checks the pace (about 130 to 210 words a minute) and transcribes it locally to catch dropped words. A line that fails is tried again. Clicks and breaths after the last word are trimmed. Lines that did not change are skipped on the next run.

The first run downloads the Kokoro model (114 MB), its voices (28 MB) and the Whisper model for the word check (about 145 MB).

## Your own voice with Chatterbox

### Consent policy

- Only clone your own voice, or the voice of someone who gave you permission.
- spec.yaml records that answer as `consent: own` or `consent: permission`. With no consent, reelsmith refuses to clone. It checks again every time it voices a line, not only when it reads the file.
- The Chatterbox watermark is always on. There is no setting to turn it off, and reelsmith will not use a Chatterbox build without its watermarker.
- Nothing is uploaded. Your recording, the reference and the generated audio stay on your machine.

When an AI tool runs the interview, it asks the consent question itself and never fills in the answer for you.

### Install

Cloning needs the `clone` extra, which brings in PyTorch. Chatterbox runs on Python 3.11 or 3.12, not 3.13 yet.

```
uv tool install --python 3.12 "reelsmith[clone]"
```

It uses an NVIDIA GPU or Apple Silicon when there is one. On the CPU it works, but expect a minute or more per line. See the GPU notes in [install.md](install.md).

Cloning is supported and covered by tests that use stand ins for the model. A real Chatterbox run is part of the manual release checklist.

### Walkthrough

1. **Record yourself.** A minute or two of normal speech in a quiet room is plenty. Any audio or video format works.

2. **Pick the reference.** Chatterbox only uses about 10 seconds, so reelsmith finds the cleanest stretch for you:

   ```
   reelsmith voice pick-reference my-voice-note.m4a --out ref.wav
   ```

   It scores each stretch for speech, background noise, clipping and pace, and writes a 24 kHz mono wav. `--seconds` sets the length, from 5 to 30 (default 12). Listen to the result. If it warns that every stretch clips, record again a little further from the mic.

3. **Set the voice in spec.yaml.** The sample path is relative to the demo folder:

   ```yaml
   voice:
     engine: chatterbox
     sample: ref.wav
     consent: own        # own or permission
   ```

4. **Compare references (optional).** If you have more than one reference, for example two picks from different recordings:

   ```
   reelsmith voice compare --refs ref.wav,ref2.wav --lines 3
   ```

   Each reference reads the first few script lines. Each set is scored on voice similarity to its reference, pace, and whether the transcript matches the script. The output goes to `voice/compare/<reference>/`, with notes in `voice/compare/compare.md`, and the command recommends one. Put that file in `voice.sample`. This also needs consent in spec.yaml.

5. **Generate.**

   ```
   reelsmith voice generate
   ```

   The same pace and word checks run as for Kokoro. Changing the sample file regenerates every line.

To check the install, `reelsmith doctor --spec spec.yaml` adds a Chatterbox check when the spec uses it.

## Common problems

| Problem | Fix |
|---|---|
| `Cloning needs a voice sample and consent.` | Add `sample:` and `consent: own` or `consent: permission`, only if that is true. Otherwise use Kokoro. |
| `Own voice cloning needs the clone extra.` | Install with the `clone` extra, on Python 3.11 or 3.12. |
| `Own voice cloning needs Python 3.11 or 3.12.` | Reinstall with `--python 3.12`. |
| A line keeps failing for dropped words | Rewrite it more simply. Spell out numbers, acronyms and symbols. |
| A word is said wrong | Spell it the way it sounds in script.yaml, then regenerate that line with `--only`. |
| Voice too fast for the clicks | Lower `voice.speed`, or shorten the lines. |
