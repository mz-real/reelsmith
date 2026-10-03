// Replays one session from sessions.js. Pick it with the URL hash: #install.
//
// By default the page plays every step on its own. Add "?manual" to the URL
// to let a capture flow drive it: the flow calls window.replay.start(n) for
// each step, so the pauses between steps live in the flow.
//
// Test hooks: cmd-<n> is a command line, out-<n> its output block and
// key-<n> the output line the flow logs. window.replayDone is set to true
// when the last step has printed all of its output.
(function () {
  "use strict";

  var CHAR_MS = 55;
  var LINE_MS = 70;
  var AUTO_PAUSE_MS = 1500;

  var screen = document.getElementById("screen");
  var titleBar = document.querySelector(".bar");
  var name = (location.hash || "#install").slice(1);
  var session = (window.SESSIONS || {})[name];
  var manual = /(^|[?&])manual\b/.test(location.search);
  var finished = 0;

  window.replayDone = false;

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function scroll() {
    screen.scrollTop = screen.scrollHeight;
  }

  function lineClass(text) {
    if (/^\[OK\]|: PASS$|^  - OK /.test(text)) return "ok";
    if (/^\[WARN\]|: WARN$|^  - WARN /.test(text)) return "warn";
    if (/^\[ERROR\]|: FAIL$/.test(text)) return "error";
    return "";
  }

  function outputLine(text) {
    var div = document.createElement("div");
    var match = /^(claude:|assistant:)/.exec(text);
    if (match) {
      div.className = "claude-line";
      var label = document.createElement("span");
      label.className = "prompt claude";
      label.textContent = match[0];
      div.appendChild(label);
      div.appendChild(document.createTextNode(text.slice(match[0].length)));
    } else {
      div.textContent = text === "" ? " " : text;
      var cls = lineClass(text);
      if (cls) div.className = cls;
    }
    return div;
  }

  function promptClass(promptText) {
    if (promptText === "$") return "prompt";
    if (promptText === "you:") return "prompt you";
    if (promptText === "claude:") return "prompt claude";
    return "prompt";
  }

  async function runStep(n) {
    var step = session.steps[n - 1];
    if (!step) throw new Error("No step " + n + " in session " + name);

    if (step.note) {
      var note = document.createElement("div");
      note.className = "note";
      note.textContent = step.note;
      screen.appendChild(note);
    }

    var line = null;
    if (!step.chatOnly) {
      line = document.createElement("div");
      line.className = "cmd";
      line.setAttribute("data-testid", "cmd-" + n);
      var prompt = document.createElement("span");
      var promptText = step.prompt || "$";
      prompt.className = promptClass(promptText);
      prompt.textContent = promptText;
      var typed = document.createElement("span");
      var caret = document.createElement("span");
      caret.className = "caret";
      line.appendChild(prompt);
      line.appendChild(typed);
      line.appendChild(caret);
      screen.appendChild(line);
      scroll();

      await sleep(250);
      var cmd = step.cmd || "";
      for (var i = 0; i < cmd.length; i++) {
        typed.textContent += cmd[i];
        var code = cmd.charCodeAt(i);
        await sleep(CHAR_MS - 12 + ((code * 7 + i * 13) % 25));
      }
      await sleep(step.delay || 400);
      line.removeChild(caret);
    } else {
      await sleep(step.delay || 300);
    }

    var out = document.createElement("div");
    out.className = "out";
    out.setAttribute("data-testid", "out-" + n);
    screen.appendChild(out);
    var key = step.key !== undefined ? step.key : step.out.length ? step.out.length - 1 : 0;
    var lines = step.out || [];
    for (var k = 0; k < lines.length; k++) {
      var row = outputLine(lines[k]);
      if (k === key) row.setAttribute("data-testid", "key-" + n);
      out.appendChild(row);
      scroll();
      await sleep(LINE_MS);
    }
    if (lines.length === 0 && line) {
      line.setAttribute("data-testid", "key-" + n);
    }

    finished += 1;
    if (finished === session.steps.length) window.replayDone = true;
  }

  window.replay = {
    session: name,
    steps: session ? session.steps.length : 0,
    start: function (n) {
      runStep(n);
      return true;
    },
  };

  if (!session) {
    screen.textContent = "Unknown session: " + name;
    return;
  }

  if (titleBar && session.title) {
    titleBar.textContent = session.title;
  }

  if (manual) return;

  (async function () {
    await sleep(800);
    for (var n = 1; n <= session.steps.length; n++) {
      await runStep(n);
      if (n < session.steps.length) await sleep(AUTO_PAUSE_MS);
    }
  })();
})();
