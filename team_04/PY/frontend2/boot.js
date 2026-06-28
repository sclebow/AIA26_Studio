// Boot sequence: play splash animation, then mount the three-panel workspace.

import { initExplorer } from "./panels/explorer.js";
import { initStepper } from "./panels/stepper.js";
import { initCopilot } from "./panels/copilot.js";
import { initCenter } from "./panels/center.js";
import { initHealthDashboard } from "./panels/healthDashboard.js";
import { sendMessage, greet } from "./copilotClient.js";
import { getState } from "./core/store.js";
import { watchBoundary } from "./core/contextController.js";

// expose for debugging / automated verification
window.__store = getState;

function mountWorkspace() {
  const ws = document.getElementById("workspace");
  ws.classList.remove("hidden");
  initExplorer();
  initStepper();
  initCenter();
  initCopilot(sendMessage);
  initHealthDashboard();  // floating live Design Health panel (additive)
  // Urban Context Analysis: auto-run once the site boundary is confirmed (the
  // controller installs a one-time store watcher that fires runContextAnalysis).
  watchBoundary();
  greet();
}

function runSplash(remount = false) {
  const splash = document.getElementById("splash");
  if (!splash) return;
  splash.classList.remove("fade-out");
  // total splash time ~2.6s, matching the load-bar + title animations
  const HOLD = remount ? 1800 : 2600;
  setTimeout(() => {
    splash.classList.add("fade-out");
    if (!remount) mountWorkspace();
    setTimeout(() => { if (!remount) splash.remove(); }, 850);
  }, HOLD);
}

// "Return Home" replays the animated landing screen, then reloads a clean app.
window.addEventListener("terrapilot:go-home", () => {
  const splash = document.getElementById("splash");
  if (splash) {
    splash.classList.remove("fade-out");
    splash.style.display = "flex";
  }
  setTimeout(() => window.location.reload(), 1900);
});

window.addEventListener("DOMContentLoaded", () => runSplash(false));
