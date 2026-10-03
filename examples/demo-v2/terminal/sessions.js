// Terminal sessions for demo v2 chapter 10. Every output line is real captured text.
window.SESSIONS = {
  install: {
    title: "terminal",
    steps: [
      {
        cmd: "claude plugin marketplace add mz-real/reelsmith",
        delay: 500,
        key: 3,
        out: [
          "Refreshing marketplace cache (timeout: 120s)…",
          "Cloning repository (timeout: 120s): https://github.com/mz-real/reelsmith.git",
          "Clone complete, validating marketplace…",
          "✔ Successfully added marketplace: reelsmith (declared in user settings)",
        ],
      },
      {
        cmd: "claude plugin install reelsmith@reelsmith",
        delay: 500,
        key: 1,
        out: [
          'Installing plugin "reelsmith@reelsmith"...',
          "✔ Successfully installed plugin: reelsmith@reelsmith (scope: user)",
        ],
      },
      {
        cmd: "claude plugin list",
        delay: 400,
        key: 3,
        out: [
          "  ❯ reelsmith@reelsmith",
          "    Version: 0.1.0",
          "    Scope: user",
          "    Status: ✔ enabled",
        ],
      },
    ],
  },

  firstrun: {
    title: "Claude Code · ~/my-app",
    steps: [
      {
        prompt: "you:",
        cmd: "make a demo video of my app",
        delay: 600,
        out: [],
      },
      {
        chatOnly: true,
        delay: 300,
        key: 1,
        out: [
          "claude: I'll use the reelsmith skill to make the demo video. It runs entirely on your machine.",
          "claude: I looked at your app. It's Recipe Box, a static web app (index.html + app.js) with built-in recipes, favourites and custom recipes saved in local storage. Automated web capture should work well for it.",
        ],
      },
      {
        chatOnly: true,
        delay: 300,
        key: 5,
        out: [
          "claude: The reelsmith CLI isn't installed yet. You already have uv, so the install is one command:",
          "          uv tool install reelsmith",
          "claude: Should I install it?",
          "          1. Yes, the standard install (default)",
          "          2. Yes, with voice cloning",
          "          3. No, I'll install it myself",
        ],
      },
      {
        prompt: "you:",
        cmd: "1",
        delay: 500,
        out: [],
      },
      {
        chatOnly: true,
        delay: 300,
        key: 0,
        out: [
          "claude: Setup looks good: reelsmith 0.1.0 is installed and doctor passed. Its one warning is that Maestro is missing, but that's only needed for mobile capture.",
        ],
      },
      {
        chatOnly: true,
        delay: 300,
        key: 2,
        out: [
          "claude: First question: do you already have a recording you just want narrated, or should we produce a full demo?",
          "          1. Narrate my recording",
          "          2. Produce a full demo (default): I record the app automatically with Playwright and add intro slides and a voiceover",
        ],
      },
    ],
  },

  othertools: {
    title: "terminal",
    steps: [
      {
        cmd: "reelsmith agent install codex",
        delay: 600,
        key: 10,
        out: [
          "[OK] reelsmith instructions for codex installed in ~/my-app",
          "  - wrote AGENTS.md",
          "  - wrote reelsmith-guides/capture-mobile.md",
          "  - wrote reelsmith-guides/capture-web.md",
          "  - wrote reelsmith-guides/interview.md",
          "  - wrote reelsmith-guides/narrate.md",
          "  - wrote reelsmith-guides/qa.md",
          "  - wrote reelsmith-guides/script-writing.md",
          "  - wrote reelsmith-guides/troubleshooting.md",
          "  - wrote reelsmith-guides/voice.md",
          'Next: ask your AI tool to "make a demo video of my app"',
        ],
      },
    ],
  },
};
