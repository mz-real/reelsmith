// Terminal sessions replayed by replay.js, one per tutorial scene.
//
// Truth rule: every output below was copied from a real run of the command
// on a development machine, then trimmed. Absolute paths were replaced with
// "~". The two /plugin lines are typed inside Claude Code, so their
// confirmations are short neutral summaries, not a copy of any UI.
//
// Step fields:
//   cmd     the text that is typed
//   prompt  shown before the command ("$" when left out)
//   note    a dim comment line printed before the prompt (optional)
//   delay   ms between the end of typing and the first output line
//   out     output lines, printed one by one
//   key     index of the output line the flow logs (0 when left out)
window.SESSIONS = {
  install: {
    steps: [
      {
        note: "# in Claude Code",
        cmd: "/plugin marketplace add mz-real/reelsmith",
        delay: 400,
        out: ["Marketplace added: reelsmith (mz-real/reelsmith)"],
      },
      {
        cmd: "/plugin install reelsmith@reelsmith",
        delay: 400,
        out: ["Plugin installed: reelsmith"],
      },
      {
        note: "# in your terminal",
        cmd: "reelsmith --version",
        delay: 300,
        out: ["reelsmith 0.1.0"],
      },
      {
        cmd: "reelsmith doctor",
        delay: 600,
        out: [
          "[WARN] 1 warning(s). You can still run most commands.",
          "  - OK python: Python 3.13.12",
          "  - OK ffmpeg: version 9",
          "  - OK chromium: Playwright Chromium installed",
          "  - OK java: Java 21",
          "  - WARN maestro: not on PATH (needed for mobile capture)",
          '  -     fix: curl -fsSL "https://get.maestro.mobile.dev" | bash',
          "  - OK simctl: xcrun simctl available",
          "  - OK adb: adb on PATH",
          "  - OK kokoro model: cached locally",
          "  - OK whisper model: base.en cached",
          "  - OK gpu: Apple Silicon",
          "  - OK plugin version: not checked",
          'Next: curl -fsSL "https://get.maestro.mobile.dev" | bash',
        ],
      },
    ],
  },

  interview: {
    steps: [
      {
        prompt: "you:",
        cmd: "make a demo of my app",
        delay: 800,
        out: [
          "assistant: Do you already have a recording you just want narrated, or should we produce a full demo?",
          "  1. Narrate my recording",
          "  2. Produce a full demo (default)",
        ],
      },
      {
        prompt: "you:",
        cmd: "2",
        delay: 700,
        out: [
          "assistant: Want a preset? It fills in most answers at once.",
          "  1. Quick feature clip, 30 to 60 s",
          "  2. Full app tour, 3 to 5 min",
          "  3. Mobile demo, 30 to 90 s",
          "  4. Release notes video, 1 to 2 min",
          "  5. No preset, ask me each question",
        ],
      },
    ],
  },

  capture: {
    steps: [
      {
        cmd: "reelsmith init demo",
        delay: 1000,
        out: [
          "[OK] Demo folder ready at ~/demo",
          "  - spec: ~/demo/spec.yaml",
          "  - script: ~/demo/script.yaml",
          "Next: cd ~/demo and edit spec.yaml",
        ],
      },
      {
        cmd: "reelsmith capture web examples/recipe-box/flows/search.py demo --id search --size 1280x720",
        delay: 800,
        out: [
          "[OK] Recorded clip 'search' with 3 events",
          "  - video: ~/demo/capture/clips/search/video.mp4",
          "Next: reelsmith script check",
        ],
      },
      {
        cmd: "jq -c '.events[] | {id, type, label}' demo/capture/clips/search/clip.json",
        delay: 300,
        out: [
          '{"id":"e1","type":"screen","label":"all recipes"}',
          '{"id":"e2","type":"click","label":"type tomato in search"}',
          '{"id":"e3","type":"screen","label":"filtered tomato recipes"}',
        ],
      },
      {
        cmd: "reelsmith script check recipe-box",
        delay: 1500,
        out: ["[OK] Script checked: 7 scenes, 21 lines, 14 pins", "Next: reelsmith voice generate"],
      },
    ],
  },

  qa: {
    steps: [
      {
        cmd: "reelsmith qa recipe-box",
        delay: 1200,
        out: [
          "[WARN] QA checked format 16x9: 8 passed, 1 warned, 0 failed",
          "  - Transcript vs script: WARN",
          "  - Sync: PASS",
          "  - Cut off lines: PASS",
          "  - End of line noise: PASS",
          "  - Loudness: PASS",
          "  - Hold limits: PASS",
          "  - Captions: PASS",
          "  - Blur: PASS",
          "  - Contact sheets: PASS",
          "Next: Review the WARNs in qa/report.md",
        ],
      },
      {
        cmd: "sed -n '1,12p' recipe-box/qa/report.md",
        delay: 300,
        out: [
          "# QA report",
          "",
          "Generated: 2026-10-02 11:22:53",
          "Format: 16x9",
          "Master: build/master_16x9.mp4 (89.47s)",
          "Voice: kokoro / af_heart",
          "",
          "## 1. Transcript vs script - WARN",
          "- scene 'create' line 'create-4' phrase 0 at 76.06s: singular/plural only, not a failure: [\"'detail' heard as 'details'\"].",
          "",
          "## 2. Sync - PASS",
          "- Every pinned phrase starts inside its sync window.",
        ],
      },
    ],
  },
};
