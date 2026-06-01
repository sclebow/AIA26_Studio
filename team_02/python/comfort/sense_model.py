"""
sense_model.py — Canonical sensory-comfort coupling model.

SINGLE SOURCE OF TRUTH for both the scoring formula (compute_comfort_scores.py)
and the sense / room graphs. Grounded in:
  - deep-research run wf_f759900a-7ac (24 sources, 18/25 claims confirmed via
    3-vote adversarial verification), for the four mainstream IEQ senses and
    their perceptual couplings;
  - standard room-acoustics (Sabine, RT60 = 0.161·V/A) and material physics
    (thermal effusivity √(kρc); acoustic absorption coefficients), for the
    spatial and tactile senses (which the IEQ literature barely covers).

Every coupling carries a `tier`:
  - "verified" — peer-reviewed + adversarially fact-checked in the research run.
  - "inferred" — standard physics / engineering, not separately verified.
The graphs render verified edges solid and inferred edges dashed, so the model
shows its own confidence rather than pretending the formula is ground truth.

Headline research finding: overall comfort is NON-ADDITIVE — "one-vote veto" +
negativity bias, with context-dependent (not fixed) weights. A plain mean is
structurally wrong; use aggregate_comfort() below.
"""

SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]

# ── Design-lever → sense couplings (CAUSAL — what an edit moves) ──────────────
# (lever, sense, sign, tier, mechanism)
#   sign: "+" improves, "-" degrades, "±" context-dependent / trade-off
LEVER_SENSE = [
    ("glazing_ratio",  "visual",    "+",  "verified", "daylight admission (residential daylight, not commercial DF/DA/UDI)"),
    ("glazing_ratio",  "thermal",   "±",  "inferred", "solar gain / winter heat loss — larger glazing, bigger thermal swing"),
    ("glazing_type",   "thermal",   "+",  "inferred", "triple > double > single insulation"),
    ("glazing_ratio",  "acoustic",  "-",  "verified", "more glazing area weakens facade sound insulation"),
    ("orientation",    "thermal",   "±",  "inferred", "solar orientation (S warm, N cool)"),
    ("ventilation",    "olfactory", "+",  "verified", "dilution / removal of contaminants"),
    ("ventilation",    "acoustic",  "-",  "verified", "open-window ventilation lowers sound insulation (trade-off)"),
    ("room_volume",    "spatial",   "+",  "inferred", "perceived spaciousness rises with volume / ceiling height"),
    ("room_volume",    "acoustic",  "-",  "inferred", "RT60 = 0.161·V/A — larger volume lengthens reverberation"),
    ("surface_material","tactile",  "+",  "inferred", "low-effusivity (wood, carpet, cork) feels warm; high (stone, metal) feels cold"),
    ("surface_material","acoustic", "+",  "inferred", "soft/porous materials absorb sound; hard materials reflect"),
    ("surface_material","thermal",  "±",  "inferred", "material effusivity shifts contact thermal sensation"),
    ("adjacency_noisy","acoustic",  "-",  "verified", "flanking / transmission from kitchen & living"),
    ("adjacency_wet",  "olfactory", "-",  "verified", "odor / contaminant migration from kitchen & bathroom"),
    ("plants",         "olfactory", "+",  "inferred", "weak / no verified evidence — optional"),
    ("plants",         "visual",    "+",  "inferred", "biophilic — weak evidence — optional"),
]

# ── Perceptual sense ↔ sense couplings (how the experience COMBINES) ──────────
# (a, b, direction, sign, tier, mechanism)
#   direction: "both" undirected, "a->b" directed
SENSE_SENSE = [
    ("acoustic", "thermal",   "both", "±", "verified", "strongest evidenced cross-modal coupling (bidirectional, context-dependent)"),
    ("acoustic", "visual",    "a->b", "-", "verified", "noise significantly degrades visual comfort"),
    ("visual",   "acoustic",  "a->b", "0", "verified", "light has ~no effect on acoustic comfort (asymmetry)"),
    ("thermal",  "olfactory", "both", "+", "verified", "TSV ↔ ASV association (encode conservatively)"),
    ("spatial",  "acoustic",  "both", "-", "inferred", "room volume drives reverberation (Sabine)"),
    ("tactile",  "acoustic",  "both", "+", "inferred", "surface absorption controls reverberation"),
    ("tactile",  "thermal",   "both", "±", "inferred", "material effusivity → contact thermal sensation"),
]

# ── Transmission between adjacent rooms (via doors / openings) ────────────────
TRANSMISSIVE = ["acoustic", "olfactory", "thermal"]   # propagate to neighbours
ROOM_LOCAL   = ["spatial", "tactile", "visual"]        # stay within the room

# Room types that act as designed contaminant / noise sources for neighbours.
NOISY_ROOM_TYPES = ["kitchen", "living"]
WET_ROOM_TYPES   = ["kitchen", "bathroom"]

# ── Per-room acoustic targets — BS 8233:2014 (dB L_Aeq), usable as thresholds ─
ACOUSTIC_TARGETS_DB = {
    "living": 35, "dining": 40, "bedroom_day": 35, "bedroom_night": 30,
}

# ── Aggregation ──────────────────────────────────────────────────────────────
# Overall comfort is NON-ADDITIVE: a single failing sense should drag the room
# down (one-vote veto + negativity bias). We blend a (preference-weighted) mean
# with the worst sense. VETO_WEIGHT tunes how much the worst sense dominates:
#   0.0 = plain weighted mean (old behaviour) ... 1.0 = pure worst-sense veto.
VETO_WEIGHT = 0.5


# ── Cross-modal modifier ("mix of both") ─────────────────────────────────────
# Research (multi-sensory thermal-comfort review, 2025): comfort is "dynamically
# moderated by visual, acoustic, olfactory and tactile stimuli — additive,
# synergistic, or compensatory cross-modal effects." So a failing sense should
# nudge its coupled partner's *effective* comfort by a small, LABELLED amount —
# visible in the UI and graph, never silent. Magnitudes are tunable.
CROSS_MODAL_LOW = 0.50      # a source sense at/below this is "contributing discomfort"
CROSS_MODAL_DELTA = {"-": -0.06, "±": -0.05, "+": 0.0, "0": 0.0}

# ── Symmetric (positive) ripple ──────────────────────────────────────────────
# Comfort should ALSO spread, not just discomfort: a STRONG source sense lifts its
# synergistic ("+") partners. Research backs this — the 2025 multisensory thermal-
# comfort review names cross-modal effects as "additive, SYNERGISTIC, or
# compensatory", and congruent stimuli bond (Spence). The positive magnitude is
# deliberately SMALLER than the negative (negativity bias) and capped per target so
# positives can't stack into inflation; the non-additive veto in aggregate_comfort()
# still floors the room by its worst sense, so a lifted partner can't mask a deficit.
CROSS_MODAL_HIGH = 0.70     # a source at/above this "radiates comfort" along "+" edges
CROSS_MODAL_POS = {"+": 0.04}
CROSS_MODAL_POS_CAP = 0.08  # max cumulative positive nudge per target sense


# tier → human-facing basis label (so the UI can mark each adjustment's provenance)
BASIS = {"verified": "research", "inferred": "physics"}


def apply_cross_modal(scores: dict, tiers=("verified", "inferred")):
    """Nudge each sense by its coupled (failing) partners. Returns
    (effective_scores, adjustments) where adjustments is a list of labelled deltas
    {sense, delta, from, mechanism, tier, basis} for display. `basis` is
    "research" (peer-reviewed/verified) or "physics" (standard/inferred) so the UI
    can mark which is which. Default applies BOTH tiers (Option 2); the graph shows
    every edge regardless.
    """
    eff = dict(scores)
    adj = []
    pos_total = {}   # cumulative positive nudge already applied per target (cap enforcement)

    def nudge(src, tgt, sign, tier, mech):
        src_val = scores.get(src, 1.0)
        if src_val < CROSS_MODAL_LOW:
            # Discomfort spreads from a FAILING source (unchanged behaviour).
            delta = CROSS_MODAL_DELTA.get(sign, 0.0)
        elif src_val >= CROSS_MODAL_HIGH and sign == "+":
            # Comfort spreads from a STRONG source along synergy ("+") edges, capped.
            delta = CROSS_MODAL_POS.get(sign, 0.0)
            room = CROSS_MODAL_POS_CAP - pos_total.get(tgt, 0.0)
            if room <= 0:
                return
            delta = min(delta, room)
        else:
            return
        if delta:
            eff[tgt] = round(max(0.0, min(1.0, eff[tgt] + delta)), 2)
            if delta > 0:
                pos_total[tgt] = pos_total.get(tgt, 0.0) + delta
            adj.append({"sense": tgt, "delta": delta, "from": src,
                        "mechanism": mech, "tier": tier, "basis": BASIS.get(tier, tier)})

    for (a, b, direction, sign, tier, mech) in SENSE_SENSE:
        if tier not in tiers:
            continue
        if direction == "a->b":
            nudge(a, b, sign, tier, mech)
        elif direction == "both":
            nudge(a, b, sign, tier, mech)
            nudge(b, a, sign, tier, mech)
    return eff, adj


# ── Personality / arousal layer ──────────────────────────────────────────────
# Eysenck arousal theory (R5): introverts have higher baseline arousal → prefer
# LOW environmental stimulation; extroverts prefer HIGH. Comfort = fit between a
# room's stimulation and the person's preference. Only stimulation-linked senses
# are affected (confirmed mapping): acoustic (quiet = low stimulation → use
# 1−score), visual (bright = high → use score), spatial (open = high → use score).
# thermal / olfactory / tactile are not stimulation axes.
PERSONALITY_K = 0.15   # strength; tunable
_STIM_SENSES = {"acoustic": "inverse", "visual": "direct", "spatial": "direct"}


def apply_personality(scores: dict, personality: float = 0.0):
    """personality in [-1 introvert .. +1 extrovert]. Returns (effective, adjustments).

    For each stimulation sense, stim_level ∈ [0,1] (acoustic = 1−score; visual/
    spatial = score). delta = K · personality · (stim_level − 0.5): an extrovert
    gains comfort in high-stimulation rooms and loses it in low; an introvert the
    reverse. personality 0 (or absent) → no effect.
    """
    eff = dict(scores)
    adj = []
    if not personality:
        return eff, adj
    for s, mode in _STIM_SENSES.items():
        v = scores.get(s)
        if v is None:
            continue
        stim = (1.0 - v) if mode == "inverse" else v
        delta = round(PERSONALITY_K * personality * (stim - 0.5), 2)
        if delta:
            eff[s] = round(max(0.0, min(1.0, eff[s] + delta)), 2)
            adj.append({"sense": s, "delta": delta, "from": "personality",
                        "mechanism": ("extrovert prefers stimulation" if personality > 0
                                      else "introvert prefers calm"),
                        "tier": "inferred", "basis": "personality"})
    return eff, adj


def threshold_from_weight(w, base: float = 0.35, span: float = 0.40,
                          lo: float = 0.35, hi: float = 0.75) -> float:
    """Conflict threshold for a sense, from the user's PERSONAL comfort weight (0..1).

    Higher weight = the user cares more / is more sensitive = a HIGHER bar, so the
    sense is flagged sooner. Linear: threshold = base + span·w, clamped to [lo, hi].
    e.g. w=0.3 → 0.47 (lenient), w=0.5 → 0.55 (default), w=0.9 → 0.71 (strict).
    This replaces the fixed per-category threshold tables so detection reflects the
    real onboarding persona, not a bucket.
    """
    try:
        w = float(w)
    except (TypeError, ValueError):
        w = 0.5
    return round(max(lo, min(hi, base + span * w)), 2)


def priority_order(weights: dict | None) -> list:
    """Senses ranked by the user's personal weight, highest first (ties keep SENSES
    order). Replaces the fixed per-category suggestion-priority tables."""
    if not weights:
        return list(SENSES)
    return sorted(SENSES, key=lambda s: (-float(weights.get(s, 0.5)), SENSES.index(s)))


def aggregate_comfort(scores: dict, weights: dict | None = None, veto: float = VETO_WEIGHT) -> float:
    """Non-additive overall comfort from per-sense scores.

    Persona/preference `weights` apply HERE (to each sense's contribution),
    not as inflation of the per-sense scores themselves — so the displayed
    per-sense scores stay objective while preferences shape the overall.
    """
    vals = [scores[s] for s in SENSES if s in scores and scores[s] is not None]
    if not vals:
        return 0.0
    w = weights or {}
    num = sum(scores[s] * w.get(s, 1.0) for s in SENSES if s in scores)
    den = sum(w.get(s, 1.0) for s in SENSES if s in scores) or 1.0
    weighted_mean = num / den
    worst = min(vals)
    return round((1.0 - veto) * weighted_mean + veto * worst, 2)
