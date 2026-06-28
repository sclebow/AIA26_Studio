import React from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/global.css";
import { hydrateCssTokens } from "./lib/tokens.js";
import App from "./App.jsx";
import DevPlan from "./canvas/DevPlan.jsx";

// Inject the JS-authored sense tokens onto :root before first paint so the
// stylesheet's var(--thermal)/var(--i-3)/… resolve. Single source: lib/senses.js.
hydrateCssTokens();

// DEV-ONLY: ?plan=<id> renders the SensePlan rendering harness (DevPlan) instead of the
// full app, to verify plan linework without the LLM/onboarding flow. Remove with DevPlan.
const Root = new URLSearchParams(location.search).has("plan") ? DevPlan : App;

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
