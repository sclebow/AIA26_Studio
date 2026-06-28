// The workflow stage machine — single source of truth on the client side,
// mirroring the backend orchestrator. The Copilot drives transitions; the
// center panel + explorer react to `store.stage`.

export const STAGES = {
  SPLASH: "SPLASH",
  SITE: "SITE",
  BOUNDARY: "BOUNDARY",
  CONTEXT: "CONTEXT",
  SHAPES: "SHAPES",
  SHAPE_EDIT: "SHAPE_EDIT",
  OPTIMIZE: "OPTIMIZE",
  COMPARE: "COMPARE",
  DECISION: "DECISION",
  EXPORT: "EXPORT",
  EVOLUTION: "EVOLUTION",
  END: "END",
};

// Which center view each stage shows by default. The orchestrator can override
// via the `view` field in a /copilot response.
export const STAGE_VIEW = {
  [STAGES.SITE]: "map",
  [STAGES.BOUNDARY]: "map",
  [STAGES.CONTEXT]: "context",
  [STAGES.SHAPES]: "shapes",
  [STAGES.SHAPE_EDIT]: "viewer",
  // Optimization lands on the 3D VIEWER so all optimized options preview ON THE SITE
  // (each with a floating score card). The metric card-grid + comparison table are one
  // click away via "Compare details".
  [STAGES.OPTIMIZE]: "viewer",
  [STAGES.COMPARE]: "compare",
  [STAGES.DECISION]: "decision",
  [STAGES.EXPORT]: "viewer",
  [STAGES.EVOLUTION]: "evolution",
  [STAGES.END]: "viewer",
};

export const STAGE_ORDER = [
  STAGES.SITE,
  STAGES.BOUNDARY,
  STAGES.CONTEXT,
  STAGES.SHAPES,
  STAGES.OPTIMIZE,
  STAGES.COMPARE,
  STAGES.EXPORT,
];

export const STAGE_LABEL = {
  [STAGES.SITE]: "Site",
  [STAGES.BOUNDARY]: "Boundary",
  [STAGES.CONTEXT]: "Context",
  [STAGES.SHAPES]: "Shapes",
  [STAGES.SHAPE_EDIT]: "Editing",
  [STAGES.OPTIMIZE]: "Optimize",
  [STAGES.COMPARE]: "Compare",
  [STAGES.EXPORT]: "Export",
  [STAGES.EVOLUTION]: "Evolution",
  [STAGES.END]: "Complete",
};
