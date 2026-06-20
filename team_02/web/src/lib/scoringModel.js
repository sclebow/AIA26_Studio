// Frontend mirror of the REAL comfort-scoring constants in
// `python/comfort/sense_model.py`. The persona reveal explains the model to the
// user, so it must match the engine — keep these in sync with sense_model.py.
// (Single source of truth lives in Python; this is the read-only echo for copy.)

export const VETO_WEIGHT = 0.5;     // C(room) = (1−V)·weightedMean + V·worstSense
export const PERSONALITY_K = 0.15;  // stimulation-sense shift per personality unit
export const CONTEXT_K = 0.16;      // max household-context deficit nudge per sense

// threshold_from_weight(w) = clamp(base + span·w, lo, hi) — the conflict bar that
// rises with how much the user weights a sense.
export const THRESHOLD = { base: 0.35, span: 0.40, lo: 0.35, hi: 0.75 };

// The deviation flag the reveal itself uses for preference-vs-baseline gap cards.
export const BASELINE_GAP = 0.25;
