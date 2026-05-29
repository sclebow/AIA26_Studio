// Shared constants — ported from the S/SC/SI/SENSES/etc. globals in index.html.

export const SC = {
  thermal: "#E8836A", visual: "#D4B96A", acoustic: "#9B8FD4",
  spatial: "#6AB8C8", olfactory: "#8BB88A", tactile: "#C4A882",
};

export const SI = {
  thermal: "△", visual: "○", acoustic: "∿",
  spatial: "□", olfactory: "≈", tactile: "∶",
};

export const SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"];

export const STEPS = ["hello", "role", "space", "senses", "life", "feel"];

export const STEP_LABELS = {
  hello: "welcome", role: "your role", space: "your space",
  senses: "senses", life: "lifestyle", feel: "how you feel",
};

// Research baselines (mirrors _COMFORT_BASELINES in persona_compiler.py)
export const BASELINES = {
  thermal: 0.70, visual: 0.60, acoustic: 0.65,
  spatial: 0.50, olfactory: 0.40, tactile: 0.35,
};

// Role-aware implications for the top-3 priority cards
export const IMPLICATIONS = {
  thermal:   { architect: "Thermal performance will be a primary metric in every room scored.", client: "A cold or overheated room will register before anything else.", student: "Thermal comfort directly affects focus — spaces will be evaluated against this." },
  visual:    { architect: "Daylighting quality will drive comfort scores across all rooms.", client: "Light quality shapes how every space feels to you.", student: "Visual comfort — light, contrast, glare — will be a strong factor in your analysis." },
  acoustic:  { architect: "Acoustic performance and noise transmission will be closely tracked.", client: "Background noise and sound bleed will flag consistently in your results.", student: "Acoustic comfort affects concentration — this sense will score sensitively for you." },
  spatial:   { architect: "Room proportions and adjacency quality will drive spatial scores.", client: "Cramped or poorly proportioned spaces will score low consistently.", student: "How spaces flow and feel proportionally will be a key dimension of analysis." },
  olfactory: { architect: "Ventilation and air quality metrics will be flagged at your weight level.", client: "Air freshness and ventilation adequacy matter to you — Sensi will track this.", student: "Air quality and odor transmission will be scored against your preferences." },
  tactile:   { architect: "Material texture and finish quality will contribute to comfort assessments.", client: "The physical feel of surfaces and materials registers in your comfort model.", student: "Material tactility and finish quality will feature in your layout analysis." },
};

// Rotating overlay phrases keyed by the first status string.
export const OVERLAY_PHRASES = {
  "reading your aesthetic...":        ["reading your aesthetic...", "feeling into your world...", "translating your sense of space..."],
  "gathering images...":              ["gathering images...", "curating your visual world...", "finding what feels right..."],
  "finding more images...":           ["refining the picture...", "going deeper...", "finding more..."],
  "building your comfort profile...": ["building your comfort profile...", "mapping your sensory world...", "putting it all together..."],
  "starting sensi...":                ["starting sensi...", "waking up..."],
};
