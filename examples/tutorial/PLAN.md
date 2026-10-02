# Tutorial video plan (approval point 1)

About 3.5 minutes, 16:9 at 1080p, Kokoro af_heart, burned captions. Made with reelsmith itself.

| # | Scene | Layout | What is on screen | What the voice covers |
|---|---|---|---|---|
| 1 | hook | full | 8 s of the finished Recipe Box video | "This video was made by reelsmith. So was this one." |
| 2 | what | slide | One line pitch, three facts: local, your AI tool drives it, two approvals | What reelsmith is, and that nothing is uploaded |
| 3 | install | browser | A terminal replay: plugin install, `reelsmith doctor` output | Install for Claude Code, then for other tools, then doctor |
| 4 | interview | browser | Terminal replay: "make a demo of my app", the first questions | The interview, one question at a time, mode first |
| 5 | plan | slide | Flow: spec.yaml, then approve, then script.yaml, then approve, then render | The two approval points: nothing is voiced before you agree |
| 6 | capture | browser | Terminal replay: `capture web` with the event log, then `script check` | Flows, logged clicks, phrases pinned to events |
| 7 | pipeline | slide | Flow: voice, slides, compose, qa, export | What each step does, Kokoro by default |
| 8 | qa | browser | Terminal replay: `reelsmith qa` result and report excerpt | QA checks every word, sync, loudness, blur |
| 9 | result | full | The finished Recipe Box video, about 20 s | The output: three formats, captions, srt |
| 10 | voices | slide | Kokoro voices, own voice cloning with consent and watermark | Voice options and the consent policy |
| 11 | outro | slide | Repo link, `/plugin marketplace add mz-real/reelsmith` | Where to get it |

**Footage:** the terminal replays are a small local HTML page (examples/tutorial/terminal/) that types real commands and shows real output captured from today's runs. It is recorded with `reelsmith capture web` like any web app, and uses a generic terminal look, not any product's UI. The result clips come from the final Recipe Box render, imported with `capture import`.

**Truth rule:** every output shown comes from a real run. No invented numbers.

**Not included:** the owner's voice, any personal data, Maestro or Chatterbox demos on real devices (only described, until the manual checklist is done).
