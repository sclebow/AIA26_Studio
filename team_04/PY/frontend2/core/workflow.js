// Workflow state machine — the single authority for stage transitions, the
// center view per stage, and what the Copilot should ask next. Every stage
// change must go through advanceTo()/tryAdvance() so the stage, center view,
// explorer, and copilot stay synchronized and stages can't run out of order.
//
//   SITE → BOUNDARY → SHAPES → SHAPE_EDIT → OPTIMIZE → COMPARE → DECISION → EXPORT
//
// Each stage declares:
//   view        — the canonical center view when this stage is active
//   canEnter(s) — entry guard: are this stage's prerequisites met?
//   isComplete  — completion condition (used to allow forward navigation)
//   nextPrompt  — the Copilot message shown when this stage becomes active

import { getState, setState, pushMessage, setStatus } from "./store.js";
import { STAGES } from "./stages.js";

export const WORKFLOW = {
  [STAGES.SITE]: {
    view: "map",
    canEnter: () => true,
    isComplete: (s) => !!s.locationSaved || (!!s.location && !!s.boundarySaved),
    next: STAGES.BOUNDARY,
  },
  [STAGES.BOUNDARY]: {
    view: "map",
    canEnter: (s) => !!s.location || !!s.locationSaved,
    isComplete: (s) => !!s.boundarySaved,
    next: STAGES.CONTEXT,
  },
  [STAGES.CONTEXT]: {
    view: "context",
    canEnter: (s) => !!s.boundarySaved,
    // Context is complete once it's been analyzed (scores present). The user can
    // still proceed if the OSM fetch failed (contextError) so they're never stuck.
    isComplete: (s) => !!(s.context && s.context.scores) || !!s.contextError,
    next: STAGES.SHAPES,
  },
  [STAGES.SHAPES]: {
    view: "shapes",
    canEnter: (s) => !!s.boundarySaved,
    // SHAPES is complete once the user has SELECTED a shape (not merely generated
    // some). selectedShapeType is set by confirmShapeSelection.
    isComplete: (s) => !!s.selectedShapeType,
    next: STAGES.SHAPE_EDIT,
  },
  [STAGES.SHAPE_EDIT]: {
    view: "viewer",
    // Manipulation only after a shape is chosen + placed.
    canEnter: (s) => !!s.selectedShapeType && (s.buildings || []).length > 0,
    isComplete: (s) => (s.buildings || []).length > 0, // editing is optional
    next: STAGES.OPTIMIZE,
  },
  [STAGES.OPTIMIZE]: {
    view: "optimize",
    // HARD GATE: optimization can never run until a shape has been selected. This
    // is what stops the app jumping from the shape prompt straight to optimization.
    canEnter: (s) => !!s.selectedShapeType && (s.buildings || []).length > 0,
    isComplete: (s) => !!s.optimizationResult && (s.options || []).length > 0,
    next: STAGES.COMPARE,
  },
  [STAGES.COMPARE]: {
    view: "compare",
    // Allow Compare when EITHER a main-optimize run produced options OR the saved-shapes
    // optimizer populated comparisonOptions (originals + variants). The latter path made
    // "Compare" wrongly say "Run optimization first" even though results existed.
    canEnter: (s) => ((!!s.optimizationResult && (s.options || []).length > 0)
                      || (s.comparisonOptions || []).length > 0),
    isComplete: (s) => (s.compareSelection || []).length >= 2,
    next: STAGES.DECISION,
  },
  [STAGES.DECISION]: {
    view: "decision",
    canEnter: (s) => (s.decisionGraph?.nodes || []).length > 0 || (s.buildings || []).length > 0,
    isComplete: () => true,
    next: STAGES.EXPORT,
  },
  [STAGES.EXPORT]: {
    view: "viewer",
    canEnter: (s) => (s.buildings || []).length > 0,
    isComplete: () => true,
    next: null,
  },
};

// The Copilot's guiding question when a stage becomes active. Returned as
// { text, actions } so the caller can push it into the chat.
export function nextPromptFor(stage) {
  const s = getState();
  switch (stage) {
    case STAGES.SITE:
      return {
        text:
          "Enter a site location to begin — a place name (e.g. *Bangalore*), an " +
          "address, or coordinates like *12.9716, 77.5946*.",
        actions: [],
      };
    case STAGES.BOUNDARY:
      return {
        text: "Now **draw your site boundary** on the map, then save it.",
        actions: [{ label: "Draw Boundary", message: "draw boundary", intent: "draw_boundary" }],
      };
    case STAGES.CONTEXT:
      return {
        text: "Analyzing the surrounding urban context (roads, transit, amenities, green space) within 2 km…",
        actions: [],
      };
    case STAGES.SHAPES: {
      // Context-aware question once context scores exist; otherwise the plain one.
      const ctx = s.context;
      if (ctx && ctx.scores) {
        return {
          text:
            "I've analyzed the surrounding urban context. Based on the site's accessibility, " +
            "amenities, transportation network, and context scores, **what type of building " +
            "would you like me to generate?**",
          actions: [
            { label: "A commercial building", message: "I want to build a commercial building" },
            { label: "A residential block", message: "I'd like a residential building of about 5 floors" },
            { label: "Mixed-use development", message: "I want a mixed-use building" },
          ],
        };
      }
      return {
        text:
          "What would you like to design on this site? Tell me about the project — " +
          "the kind of building and roughly how big — and I'll explore a few massing options.",
        actions: [
          { label: "A commercial building", message: "I want to build a commercial building" },
          { label: "A residential block", message: "I'd like a residential building of about 5 floors" },
          { label: "An office tower", message: "I want to explore an office building" },
        ],
      };
    }
    case STAGES.SHAPE_EDIT:
      return {
        text:
          "Your shape is placed. Refine it by typing — e.g. *'move 5m north'*, " +
          "*'rotate 30'*, *'make it 10 floors'*, *'add 2 floors on the right wing'*, " +
          "*'move toward metro'*, *'face the park'* — or just say how it should feel " +
          "(*'more daylight'*, *'a larger courtyard'*). **Evaluate** to check " +
          "performance without changing geometry, or **Optimize** for alternatives.",
        actions: [
          { label: "Evaluate Design", message: "evaluate design", intent: "evaluate" },
          { label: "Optimize", message: "optimize", intent: "optimize", primary: true },
        ],
      };
    case STAGES.OPTIMIZE:
      return {
        text: "Running view optimization to generate ranked options…",
        actions: [],
      };
    case STAGES.COMPARE: {
      const n = (s.options || []).length;
      return {
        text: `I generated **${n} ranked options**. Select options in the Comparison panel to compare them side by side.`,
        actions: [{ label: "Compare options", message: "compare", intent: "compare" }],
      };
    }
    case STAGES.DECISION:
      return {
        text: "Would you like to **review the decision tree** of how the design evolved, or **export** the project?",
        actions: [
          { label: "Decision tree", message: "decision tree", intent: "decision" },
          { label: "Export", message: "export", intent: "export" },
        ],
      };
    case STAGES.EXPORT:
      return {
        text: "Ready to **export**. I can produce GeoJSON now (native Rhino/Revit needs the MCP server).",
        actions: [{ label: "Export GeoJSON", message: "export", intent: "export" }],
      };
    default:
      return { text: "", actions: [] };
  }
}

// Move to a stage, setting the canonical center view and (optionally) emitting
// the Copilot's guiding prompt. Returns true if the move happened.
export function enterStage(stage, { announce = true, extraState = {} } = {}) {
  const def = WORKFLOW[stage];
  if (!def) return false;
  setState({ stage, centerView: def.view, ...extraState });
  if (announce) {
    const { text, actions } = nextPromptFor(stage);
    if (text) pushMessage("assistant", text, actions);
  }
  return true;
}

// Guarded forward navigation: only enter `stage` if its prerequisites are met.
// If not, tell the user what's still needed and stay put. Returns true on success.
export function tryAdvance(stage, { announce = true } = {}) {
  const s = getState();
  const def = WORKFLOW[stage];
  if (!def) return false;
  if (!def.canEnter(s)) {
    pushMessage("assistant", _blockedReason(stage));
    return false;
  }
  return enterStage(stage, { announce });
}

// When the current stage completes, advance to the next stage automatically and
// have the Copilot ask the next question. Call this after a stage's work lands.
export function completeAndAdvance(fromStage) {
  const def = WORKFLOW[fromStage];
  if (!def || !def.next) return false;
  return tryAdvance(def.next);
}

// Can the user open a given stage right now? (Used to enable/disable stepper steps.)
export function canEnter(stage) {
  const def = WORKFLOW[stage];
  return !!def && def.canEnter(getState());
}

function _blockedReason(stage) {
  switch (stage) {
    case STAGES.BOUNDARY:
      return "Confirm a site location first, then I can open the boundary tool.";
    case STAGES.CONTEXT:
      return "Save your site boundary first, then I'll analyze the urban context.";
    case STAGES.SHAPES:
      return "Draw and save your site boundary first.";
    case STAGES.SHAPE_EDIT:
      return "Pick a shape from the Shape Library first.";
    case STAGES.OPTIMIZE:
      return "Select a shape from the Shape Library first — optimization runs on your chosen shape.";
    case STAGES.COMPARE:
      return "Run optimization first so there are ranked options to compare.";
    case STAGES.DECISION:
      return "There's no design history yet — generate a building first.";
    case STAGES.EXPORT:
      return "Generate a building before exporting.";
    default:
      return "That step isn't available yet.";
  }
}
