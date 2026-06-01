import React from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/global.css";
import { hydrateCssTokens } from "./lib/tokens.js";
import App from "./App.jsx";

// Inject the JS-authored sense tokens onto :root before first paint so the
// stylesheet's var(--thermal)/var(--i-3)/… resolve. Single source: lib/senses.js.
hydrateCssTokens();

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
