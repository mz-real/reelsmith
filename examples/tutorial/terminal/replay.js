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

  var CHAR_MS = 55; // average typing pace, with a small fixed jitter
  var LINE_MS = 70; // pause between output lines
  var AUTO_PAUSE_MS = 1500; // gap between steps when playing on its own

  var screen = document.getElementById("screen");
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
    var match = /^assistant:/.exec(text);
    if (match) {
      var label = document.createElement("span");
      label.className = "assistant";
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

  async function runStep(n) {
    var step = session.steps[n - 1];
    if (!step) throw new Error("No step " + n + " in session " + name);

    if (step.note) {
      var note = document.createElement("div");
      note.className = "note";
      note.textContent = step.note;
      screen.appendChild(note);
    }

    var line = document.createElement("div");
    line.className = "cmd";
    line.setAttribute("data-testid", "cmd-" + n);
    var prompt = document.createElement("span");
    var promptText = step.prompt || "$";
    prompt.className = promptText === "$" ? "prompt" : "prompt you";
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
    for (var i = 0; i < step.cmd.length; i++) {
      typed.textContent += step.cmd[i];
      var code = step.cmd.charCodeAt(i);
      await sleep(CHAR_MS - 12 + ((code * 7 + i * 13) % 25));
    }
    await sleep(step.delay || 400);
    line.removeChild(caret);

    var out = document.createElement("div");
    out.className = "out";
    out.setAttribute("data-testid", "out-" + n);
    screen.appendChild(out);
    var key = step.key || 0;
    for (var k = 0; k < step.out.length; k++) {
      var row = outputLine(step.out[k]);
      if (k === key) row.setAttribute("data-testid", "key-" + n);
      out.appendChild(row);
      scroll();
      await sleep(LINE_MS);
    }

    finished += 1;
    if (finished === session.steps.length) window.replayDone = true;
  }

  window.replay = {
    session: name,
    steps: session ? session.steps.length : 0,
    // Starts step n (1 based) and returns at once, so a flow can log the
    // moment it starts and then wait for its output.
    start: function (n) {
      runStep(n);
      return true;
    },
  };

  if (!session) {
    screen.textContent = "Unknown session: " + name;
    return;
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
