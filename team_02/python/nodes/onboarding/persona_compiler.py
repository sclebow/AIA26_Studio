"""
PERSONA_COMPILER node — end of onboarding.

Runs once, immediately after INSPIRE completes.
Synthesises all quiz answers + inspire summary into a structured persona
profile JSON, saves it to disk, and unlocks layout mode.

State consumed:   quiz_answers (dict), inspire_summary (str)
State produced:   persona_profile (dict), user_type (str),
                  onboarding_complete (True), final_response (str)

Output file:  team_02/personas/persona.json
              (resolved as ctx.layout_input_dir.parent / "personas" / "persona.json")

Robustness layers (in order of application):
  1. LLM call → JSON profile (happy path)
  2. <think> tag stripper — removes Qwen3/DeepSeek-R1 reasoning blocks before parsing
  3. Markdown fence stripper — handles ```json … ``` wrapping
  4. Brace-counting JSON extractor — handles prose before/after the JSON block
  5. Minimal-profile fallback if all parsing fails
  6. Q3 sensory patch (unconditional) — guarantees q3 senses ≥ 0.75, repairs priorities
  7. Quiz fallback patch — extracts lifestyle, age_group, household_type,
     aesthetic_preferences, key_requirements directly from quiz_answers when LLM skips them
"""

from __future__ import annotations
import json
import os
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are Sensi's persona compiler.

Synthesise the quiz answers and aesthetic summary below into a single,
structured comfort persona profile. This profile will drive all comfort
analysis and response personalisation for this user.

INPUT you will receive:
  QUIZ ANSWERS — keys q0 (intro / who are you?) through q5 (ideal space)
  INSPIRE SUMMARY — a paragraph describing aesthetic and sensory preferences

OUTPUT — return ONLY this JSON schema, no explanation, no markdown fences:

{
  "name": "<first name if given, else User>",
  "role": "architect" | "client" | "student",
  "description": "<one sentence: who they are and their comfort situation>",
  "age_group": "child" | "young_adult" | "adult" | "elderly" | null,
  "household_type": "single" | "dual" | "family" | null,
  "sensory_priorities": [
    "<ranked list — most important first — from: thermal, visual, acoustic, spatial, olfactory, tactile>"
  ],
  "sensory_sensitivities": [
    "<specific sensitivities or intolerances mentioned by the user>"
  ],
  "comfort_weights": {
    "thermal":   <0.0-1.0>,
    "visual":    <0.0-1.0>,
    "acoustic":  <0.0-1.0>,
    "spatial":   <0.0-1.0>,
    "olfactory": <0.0-1.0>,
    "tactile":   <0.0-1.0>
  },
  "aesthetic_preferences": "<concise distillation of their sensory aesthetic world>",
  "lifestyle": "<how they mainly use their home>",
  "key_requirements": ["<up to 3 non-negotiables the user explicitly stated>"],
  "notes": "<anything else relevant that does not fit above>"
}

comfort_weights rules:
  - Derive from sensory priorities and explicit sensitivities.
  - High sensitivity to a sense -> weight closer to 1.0 (flags issues more aggressively).
  - Sense explicitly stated as non-priority -> weight 0.3.
  - Sense not mentioned -> default 0.5.
  - All six senses must appear.
  - IMPORTANT: q3 contains the user's explicit sensory bothers. Any sense named
    there must receive a weight of at least 0.75. Do not default these to 0.5.

STATED PREFERENCES vs RESEARCH BASELINES:
After deriving comfort_weights from the user's stated preferences, compare each
weight against these evidence-based research baselines. Where the user's stated
weight deviates by more than 0.25, note it in preference_vs_baseline.

Research baselines (evidence-based minimum comfort thresholds):
  thermal:   0.70  -- thermal discomfort is the #1 cause of occupant complaints
  visual:    0.60  -- adequate daylighting is linked to productivity and sleep
  acoustic:  0.65  -- chronic noise exposure causes measurable stress responses
  spatial:   0.50  -- spatial adequacy affects psychological restoration
  olfactory: 0.40  -- air quality threshold; lower risk unless sensitivity stated
  tactile:   0.35  -- lowest baseline; only flagged for explicit sensitivities

Add this field to the JSON output:
  "preference_vs_baseline": {
    "<sense>": "<brief note if user's weight differs from baseline by >0.25>"
    // omit senses where user and baseline are aligned
  }

Return ONLY the JSON object. Nothing else.
"""

_COMFORT_BASELINES: dict = {
    "thermal":   0.70,
    "visual":    0.60,
    "acoustic":  0.65,
    "spatial":   0.50,
    "olfactory": 0.40,
    "tactile":   0.35,
}

_ALL_SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]

_MINIMAL_PROFILE: dict = {
    "name": "User",
    "role": "client",
    "description": "User with unspecified comfort preferences",
    "age_group": None,
    "household_type": None,
    "sensory_priorities": _ALL_SENSES[:],
    "sensory_sensitivities": [],
    "comfort_weights": {s: 0.5 for s in _ALL_SENSES},
    "aesthetic_preferences": "",
    "lifestyle": "",
    "key_requirements": [],
    "preference_vs_baseline": {},
    "notes": "",
}

# Keywords used by the q3 direct-extraction fallback.
# The UI sends: "The senses that pull me out of comfort: thermal, acoustic, visual."
# so sense names appear verbatim — keyword scan is a reliable match.
_SENSE_KEYWORDS: dict[str, list[str]] = {
    "thermal":   ["thermal", "temperature", "hot", "cold", "heat", "warm"],
    "visual":    ["visual", "light", "glare", "bright", "lighting", "sunlight", "daylight"],
    "acoustic":  ["acoustic", "noise", "sound", "loud", "quiet"],
    "spatial":   ["spatial", "cramped", "crowded", "small", "tight"],
    "olfactory": ["olfactory", "smell", "odor", "odour", "air quality", "ventilation"],
    "tactile":   ["tactile", "texture", "material", "surface"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """
    Remove <think>...</think> reasoning blocks from LLM output before JSON
    parsing.  call_llm_simple() strips these automatically for normal text
    responses, but persona_compiler calls it and then further processes the
    raw string as JSON — so we keep this local copy for the JSON parse path.
    """
    import re
    try:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    except Exception:
        return text


def _extract_json_object(text: str) -> str | None:
    """
    Find the first balanced {…} block that parses as valid JSON.
    Iterates over every top-level {…} block (handles prose like
    "Here's the profile {name}: {...}" where a non-JSON brace appears first).
    Returns the first candidate that json.loads() accepts, or None.
    """
    import json as _json
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i + 1]
                try:
                    _json.loads(candidate)
                    return candidate          # first valid JSON object wins
                except _json.JSONDecodeError:
                    start = -1              # not valid — keep scanning
    return None


def _senses_from_q3(q3_text: str) -> list[str]:
    """Return the sense names explicitly mentioned in the q3 answer."""
    t = q3_text.lower()
    return [s for s, kws in _SENSE_KEYWORDS.items() if any(kw in t for kw in kws)]


def _apply_q3_sensory_patch(persona_profile: dict, quiz_answers: dict) -> dict:
    """
    Guarantee that any sense explicitly named in q3 (the user's comfort bothers)
    has a weight of at least 0.75 in the final profile.

    This runs unconditionally — even when the LLM succeeded and returned
    differentiated weights.  The logic is:
      - If the LLM already gave a q3 sense ≥ 0.75 → leave it alone (it did its job).
      - If the LLM gave a q3 sense < 0.75, or the LLM fell back to defaults
        and left everything at 0.5 → boost it to 0.80.

    Also repairs sensory_priorities and sensory_sensitivities when the LLM
    left them as generic defaults (all-senses list or empty).
    """
    q3 = quiz_answers.get("q3", "")
    if not q3:
        return persona_profile

    bothered_senses = _senses_from_q3(q3)
    if not bothered_senses:
        return persona_profile

    weights = persona_profile.get("comfort_weights", {})

    boosted = []
    for sense in bothered_senses:
        if weights.get(sense, 0.5) < 0.75:
            weights[sense] = 0.80
            boosted.append(sense)

    if boosted:
        print(f"[persona_compiler] q3 patch — boosted under-weighted senses to 0.80: {boosted}")

    persona_profile["comfort_weights"] = weights

    # Repair sensory_priorities if the LLM left it as the generic all-senses default
    # (i.e. not ordered by what the user actually said).
    current_priorities = persona_profile.get("sensory_priorities", [])
    all_equal_priority = (
        not current_priorities
        or set(current_priorities) == set(_ALL_SENSES)
           and current_priorities[:len(bothered_senses)] != bothered_senses
    )
    if all_equal_priority:
        other = [s for s in _ALL_SENSES if s not in bothered_senses]
        persona_profile["sensory_priorities"] = bothered_senses + other
        print(f"[persona_compiler] q3 patch — reordered sensory_priorities: {bothered_senses} first")

    # Repair sensory_sensitivities if the LLM left it empty
    if not persona_profile.get("sensory_sensitivities"):
        persona_profile["sensory_sensitivities"] = bothered_senses
        print(f"[persona_compiler] q3 patch — set sensory_sensitivities from q3: {bothered_senses}")

    return persona_profile


# Age-group keywords for q4 deterministic extraction
_AGE_GROUP_KEYWORDS: dict[str, list[str]] = {
    "child":       ["child", "kid", "toddler", "baby", "under 18"],
    "young_adult": ["20s", "30s", "young adult", "student", "uni", "university", "college"],
    "adult":       ["40s", "50s", "adult", "mid", "middle age"],
    "elderly":     ["60s", "70s", "80s", "senior", "elder", "retired", "grandma", "grandpa",
                    "grandmother", "grandfather"],
}

# Household keywords for q4 deterministic extraction
_HOUSEHOLD_KEYWORDS: dict[str, list[str]] = {
    "single": ["alone", "by myself", "on my own", "solo", "just me"],
    "dual":   ["partner", "spouse", "husband", "wife", "girlfriend", "boyfriend",
               "roommate", "flatmate", "grandma", "grandpa", "grandmother", "grandfather"],
    "family": ["kids", "children", "family", "parents", "siblings", "baby", "toddler",
               "son", "daughter"],
}


def _apply_quiz_fallback_patch(persona_profile: dict, quiz_answers: dict,
                               inspire_summary: str) -> dict:
    """
    Deterministic extraction of persona fields from raw quiz_answers.
    Applied when the LLM fallback fires, so the minimal profile is enriched
    with as much direct user data as possible.

    Fields recovered:
      description      — built from name + role + q3 bothers
      aesthetic_preferences — from inspire_summary (already synthesised) or q2
      lifestyle        — from q2 (space story gives a strong lifestyle hint)
      age_group        — keyword-matched from q4
      household_type   — keyword-matched from q4
      key_requirements — q5 non-negotiable, up to 3 items
    """
    q2 = quiz_answers.get("q2", "")
    q4 = quiz_answers.get("q4", "")
    q5 = quiz_answers.get("q5", "")
    name = persona_profile.get("name", "User")
    role = persona_profile.get("role", "client")
    bothers = persona_profile.get("sensory_sensitivities", [])

    # ── description ──────────────────────────────────────────────────────────
    if not persona_profile.get("description") or \
            persona_profile["description"] == "User with unspecified comfort preferences":
        bother_str = ", ".join(bothers) if bothers else "general comfort"
        persona_profile["description"] = (
            f"{name} is a {role} whose primary sensory concerns are {bother_str}."
        )

    # ── aesthetic_preferences ─────────────────────────────────────────────────
    if not persona_profile.get("aesthetic_preferences"):
        persona_profile["aesthetic_preferences"] = (
            inspire_summary.strip() if inspire_summary.strip()
            else q2.strip()
        )

    # ── lifestyle ─────────────────────────────────────────────────────────────
    if not persona_profile.get("lifestyle"):
        persona_profile["lifestyle"] = q2.strip() if q2 else ""

    # ── age_group ─────────────────────────────────────────────────────────────
    if persona_profile.get("age_group") is None and q4:
        t = q4.lower()
        for group, keywords in _AGE_GROUP_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                persona_profile["age_group"] = group
                break

    # ── household_type ────────────────────────────────────────────────────────
    if persona_profile.get("household_type") is None and q4:
        t = q4.lower()
        for htype, keywords in _HOUSEHOLD_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                persona_profile["household_type"] = htype
                break

    # ── key_requirements ─────────────────────────────────────────────────────
    if not persona_profile.get("key_requirements") and q5:
        # q5 is a single non-negotiable — store it as the first requirement
        persona_profile["key_requirements"] = [q5.strip()]

    return persona_profile


# ---------------------------------------------------------------------------
# Holistic weight patch
# ---------------------------------------------------------------------------

# Keyword → sense signal map.
# Each keyword contributes a small nudge to the weight of its sense.
# Stronger signals (q5 non-negotiable, q3 bothers) use higher deltas;
# softer signals (q2 story, inspire aesthetic) use smaller deltas.
_SENSE_SIGNALS: dict[str, list[str]] = {
    "visual":    [
        "light", "natural light", "daylight", "sunlight", "sunshine", "window", "sky",
        "view", "bright", "glare", "shadow", "darkness", "color", "colour", "skylight",
        "luminous", "daylighting", "visual", "lighting", "illuminate",
    ],
    "thermal":   [
        "warm", "warmth", "cold", "cool", "hot", "heat", "temperature", "cozy", "cosy",
        "breeze", "draft", "draught", "thermal", "humid", "stuffy", "fresh air",
    ],
    "acoustic":  [
        "quiet", "silence", "silent", "noise", "sound", "loud", "calm", "peaceful",
        "acoustic", "echo", "reverberation", "hum", "music", "voice", "tranquil",
    ],
    "spatial":   [
        "open", "openness", "space", "spacious", "airy", "high ceiling", "flow",
        "connection", "layout", "proportion", "scale", "cramped", "tight", "narrow",
        "volume", "room", "height", "spatial", "vast", "expansive", "intimate",
    ],
    "olfactory": [
        "smell", "scent", "fragrance", "fresh", "air quality", "ventilation",
        "nature", "earthy", "musty", "clean air", "olfactory", "odor", "odour",
        "perfume", "pine", "floral",
    ],
    "tactile":   [
        "texture", "material", "surface", "soft", "rough", "smooth", "warm material",
        "wood", "stone", "fabric", "concrete", "linen", "wool", "tactile", "touch",
        "haptic", "cushion", "carpet", "timber",
    ],
}


def _signals_from_text(text: str) -> dict[str, int]:
    """
    Count how many keyword signals each sense has in a block of text.
    Returns {sense: hit_count}.
    """
    t = text.lower()
    return {
        sense: sum(1 for kw in keywords if kw in t)
        for sense, keywords in _SENSE_SIGNALS.items()
    }


def _apply_holistic_weight_patch(
    persona_profile: dict,
    quiz_answers: dict,
    inspire_summary: str,
    inspire_sense_picks: dict | None = None,
) -> dict:
    """
    Derive comfort_weight adjustments from ALL quiz answers, inspire_summary,
    and moodboard sense picks.

    Signal sources and their contribution strength:
      q5  non-negotiable  → strong   (+0.18 per hit, cap 0.90)
          The user's single most important requirement — highest signal weight.
      q3  bothers         → already handled by _apply_q3_sensory_patch (0.80 floor).
          This function does NOT re-process q3 to avoid double-counting.
      inspire_summary     → medium   (+0.08 per hit, cap 0.80)
          Synthesised aesthetic world — reliable source of sensory preferences.
      q2  space story     → soft     (+0.05 per hit, cap 0.75)
          Implicit preferences from the space description.
      q4  household       → context  (fixed boosts for specific household types)
          Multi-person households: acoustic +0.07, spatial +0.05.
      inspire_sense_picks → visual signal (+0.05 per image pick per sense, max +0.20)
          Moodboard image selections — each image is tagged with its dominant senses,
          so repeated picks for a sense category are a strong aesthetic signal.

    Weights are only ever INCREASED by this patch, never lowered. If the LLM
    already gave a sense a high weight, it stays. If it left a sense at 0.5
    despite strong signals in the text, this corrects it.
    """
    weights = persona_profile.get("comfort_weights", {})
    q2 = quiz_answers.get("q2", "")
    q4 = quiz_answers.get("q4", "")
    q5 = quiz_answers.get("q5", "")

    adjustments: dict[str, float] = {s: 0.0 for s in _ALL_SENSES}

    # ── q5 non-negotiable (strongest signal) ─────────────────────────────────
    if q5:
        hits = _signals_from_text(q5)
        for sense, count in hits.items():
            if count > 0:
                adjustments[sense] += 0.18 * min(count, 2)   # max +0.36

    # ── inspire_summary (medium signal) ──────────────────────────────────────
    if inspire_summary:
        hits = _signals_from_text(inspire_summary)
        for sense, count in hits.items():
            if count > 0:
                adjustments[sense] += 0.08 * min(count, 3)   # max +0.24

    # ── q2 space story (soft signal) ──────────────────────────────────────────
    if q2:
        hits = _signals_from_text(q2)
        for sense, count in hits.items():
            if count > 0:
                adjustments[sense] += 0.05 * min(count, 2)   # max +0.10

    # ── q4 household context (fixed contextual boosts) ────────────────────────
    if q4:
        q4_lower = q4.lower()
        multi_person = any(kw in q4_lower for kw in [
            "partner", "spouse", "husband", "wife", "girlfriend", "boyfriend",
            "roommate", "flatmate", "grandma", "grandpa", "grandmother", "grandfather",
            "kids", "children", "family", "son", "daughter", "siblings",
        ])
        if multi_person:
            adjustments["acoustic"] += 0.07   # shared spaces → noise matters more
            adjustments["spatial"]  += 0.05   # shared spaces → volume matters more

    # ── moodboard sense picks (visual preference signal) ─────────────────────
    # Each image in the moodboard is tagged with its dominant senses in JS.
    # When the user repeatedly selects images of a sense category, that is a
    # clear aesthetic preference signal. We cap contribution at 4 picks per
    # sense (+0.20 max) to avoid a single sweep dominating the formula.
    if inspire_sense_picks:
        moodboard_boosts = []
        for sense, count in inspire_sense_picks.items():
            if sense in _ALL_SENSES and count > 0:
                adjustments[sense] += 0.05 * min(count, 4)   # max +0.20
                moodboard_boosts.append(f"{sense}×{count}")
        if moodboard_boosts:
            print(f"[persona_compiler] moodboard sense picks: {moodboard_boosts}")

    # ── Apply adjustments (only upward, never downward) ───────────────────────
    boosted = []
    for sense in _ALL_SENSES:
        delta = adjustments[sense]
        if delta > 0.0:
            current = weights.get(sense, 0.5)
            # Caps: q3 senses already at 0.80 can reach 0.90; others cap at 0.80
            cap = 0.90 if current >= 0.75 else 0.80
            new_val = min(round(current + delta, 2), cap)
            if new_val > current:
                weights[sense] = new_val
                boosted.append(f"{sense}: {current:.2f}→{new_val:.2f}")

    persona_profile["comfort_weights"] = weights

    if boosted:
        print(f"[persona_compiler] holistic weight patch — adjustments: {boosted}")
    else:
        print("[persona_compiler] holistic weight patch — no adjustments needed")

    # ── Re-rank sensory_priorities to match updated weights ───────────────────
    # Only re-rank if q3 bothers are still correctly in the top slots,
    # to avoid overriding a good LLM ordering.
    q3_bothers = _senses_from_q3(quiz_answers.get("q3", ""))
    current_priorities = persona_profile.get("sensory_priorities", [])
    top_match = current_priorities[:len(q3_bothers)] == q3_bothers if q3_bothers else True

    if not top_match or not current_priorities:
        # Re-rank by weight descending, keeping q3 bothers at the top
        non_bother = [s for s in _ALL_SENSES if s not in q3_bothers]
        non_bother_sorted = sorted(non_bother, key=lambda s: weights.get(s, 0.5), reverse=True)
        persona_profile["sensory_priorities"] = q3_bothers + non_bother_sorted
        print(f"[persona_compiler] priorities re-ranked: {persona_profile['sensory_priorities']}")

    return persona_profile


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------

def build_persona_compiler_node(llm, persona_output_path: str):
    """
    Return the persona_compiler node function.

    Args:
        llm               : plain LLM instance (llm_simple from Context)
        persona_output_path: absolute path where persona.json will be saved
    """

    def persona_compiler_node(state: dict) -> dict:
        quiz_answers: dict        = state.get("quiz_answers") or {}
        inspire_summary: str      = state.get("inspire_summary", "")
        inspire_sense_picks: dict = state.get("inspire_sense_picks") or {}
        user_name: str            = state.get("user_name", "") or ""
        preliminary_role: str     = state.get("preliminary_role", "client") or "client"

        print("[persona_compiler] Compiling full persona profile...")
        print(f"[persona_compiler] quiz_answers keys: {list(quiz_answers.keys())}")
        print(f"[persona_compiler] q3 (sensory bothers): {quiz_answers.get('q3', '(none)')[:120]}")
        print(f"[persona_compiler] inspire_summary ({len(inspire_summary)} chars): "
              f"{inspire_summary[:80].strip() or '(empty)'}...")
        print(f"[persona_compiler] user_name={user_name!r}  role={preliminary_role!r}")

        if not quiz_answers:
            print("[persona_compiler] WARNING: quiz_answers is empty — sensory data will be minimal")

        # ── Build the input message for the LLM ──────────────────────────
        quiz_block = "\n".join(
            f"  {k}: {v}" for k, v in sorted(quiz_answers.items())
        ) or "  (no answers recorded)"

        user_message = (
            "QUIZ ANSWERS:\n"
            + quiz_block
            + "\n\nINSPIRE SUMMARY:\n"
            + (inspire_summary.strip() or "(no aesthetic summary provided)")
        )

        # ── Call LLM ──────────────────────────────────────────────────────
        persona_profile: dict = {}
        try:
            raw = call_llm_simple(llm, _SYSTEM_PROMPT, user_message)
            print(f"[persona_compiler] LLM response: {len(raw)} chars")

            clean = raw.strip()
            # Strip <think>...</think> reasoning blocks (Qwen3, DeepSeek-R1, etc.)
            # Must happen BEFORE markdown fence stripping so the fence check
            # sees the actual content, not the opening of a think block.
            clean = _strip_think_tags(clean)
            # Strip markdown fences if the model wrapped the JSON
            if clean.startswith("```"):
                lines = clean.splitlines()
                clean = "\n".join(lines[1:-1]).strip()

            # Attempt 1: direct parse
            try:
                persona_profile = json.loads(clean)
            except json.JSONDecodeError:
                # Attempt 2: brace-counting extractor (handles prose around JSON)
                extracted = _extract_json_object(clean)
                if extracted:
                    persona_profile = json.loads(extracted)
                    print("[persona_compiler] JSON extracted via brace-counting fallback")
                else:
                    raise ValueError("No JSON object found in LLM response")

            print(f"[persona_compiler] Profile compiled for: {persona_profile.get('name', '?')}")

        except Exception as exc:
            print(f"[persona_compiler] LLM/parse error ({exc}) — using minimal profile")
            print(f"[persona_compiler] quiz_answers available: {list(quiz_answers.keys())}")
            persona_profile = dict(_MINIMAL_PROFILE)
            persona_profile["notes"] = "Profile built from direct quiz answers (LLM synthesis unavailable)."

        # ── Ensure all required keys exist ────────────────────────────────
        for key, default in _MINIMAL_PROFILE.items():
            if key not in persona_profile:
                persona_profile[key] = default

        # Ensure all six comfort_weights are present
        weights = persona_profile.get("comfort_weights", {})
        for sense in _ALL_SENSES:
            if sense not in weights:
                weights[sense] = 0.5
        persona_profile["comfort_weights"] = weights

        # ── Patch name / role FIRST so all downstream patches read correct values
        stored_name = persona_profile.get("name", "")
        if not stored_name or stored_name.lower() in ("user", "there", ""):
            if user_name and user_name.lower() not in ("there", ""):
                persona_profile["name"] = user_name.strip().capitalize()
                print(f"[persona_compiler] Name patched from session: {persona_profile['name']}")

        stored_role = persona_profile.get("role", "client")
        if stored_role == "client" and preliminary_role not in ("client", "", None):
            persona_profile["role"] = preliminary_role
            print(f"[persona_compiler] Role patched from session: {preliminary_role}")

        # ── Q3 sensory patch — always runs ───────────────────────────────
        # Guarantees any sense named in q3 has weight ≥ 0.75, and repairs
        # sensory_priorities / sensory_sensitivities if the LLM left defaults.
        persona_profile = _apply_q3_sensory_patch(persona_profile, quiz_answers)

        # ── Holistic weight patch — always runs ───────────────────────────
        # Boosts weights for senses that appear as strong signals in q5
        # (non-negotiable), q2 (space story), inspire_summary, and q4
        # (household context). Weights only ever go up, never down.
        # This runs after the q3 patch so q3 floors are already in place.
        persona_profile = _apply_holistic_weight_patch(
            persona_profile, quiz_answers, inspire_summary, inspire_sense_picks
        )

        # ── Quiz fallback patch — fills empty narrative fields ────────────
        # Deterministically extracts lifestyle, aesthetic_preferences,
        # age_group, household_type, key_requirements from raw quiz_answers
        # whenever the LLM left them blank. Runs after role is patched so
        # the description reads the correct role.
        persona_profile = _apply_quiz_fallback_patch(
            persona_profile, quiz_answers, inspire_summary
        )

        # ── Recompute preference_vs_baseline ─────────────────────────────
        pvb = persona_profile.get("preference_vs_baseline") or {}
        if not pvb:
            weights = persona_profile.get("comfort_weights", {})
            for sense, baseline in _COMFORT_BASELINES.items():
                user_w = weights.get(sense, 0.5)
                delta  = user_w - baseline
                if abs(delta) > 0.25:
                    direction = "above" if delta > 0 else "below"
                    note = (
                        "User rates this highly -- aligns well with research."
                        if delta > 0 else
                        "User rates this low -- research flags it as a consistent comfort risk."
                    )
                    pvb[sense] = (
                        f"Stated weight {user_w:.2f} is {direction} research "
                        f"baseline {baseline:.2f} (delta {delta:+.2f}). {note}"
                    )
        persona_profile["preference_vs_baseline"] = pvb
        if pvb:
            print(f"[persona_compiler] Preference vs baseline deviations: {list(pvb.keys())}")

        # ── Save to disk ──────────────────────────────────────────────────
        save_ok = False
        try:
            os.makedirs(os.path.dirname(persona_output_path), exist_ok=True)
            with open(persona_output_path, "w", encoding="utf-8") as f:
                json.dump(persona_profile, f, indent=2, ensure_ascii=False)
            save_ok = True
            print(f"[persona_compiler] Persona saved -> {persona_output_path}")
            weights_summary = {s: round(persona_profile["comfort_weights"].get(s, 0.5), 2) for s in _ALL_SENSES}
            print(f"[persona_compiler] Weights: {weights_summary}")
        except Exception as exc:
            print(f"[persona_compiler] WARNING: could not save persona file: {exc}")

        if not save_ok:
            print(f"[persona_compiler] Save path was: {persona_output_path!r}")

        # ── Build final response ──────────────────────────────────────────
        name = persona_profile.get("name", "you")
        role = persona_profile.get("role", "client")
        priorities = persona_profile.get("sensory_priorities", [])
        top_senses = ", ".join(priorities[:3]) if priorities else "comfort overall"

        response = (
            f"Your profile is ready, {name}! "
            f"I now know you as a {role} who cares most about {top_senses}. "
            "I've saved your comfort profile so you won't need to set this up again. "
            "\n\n"
            "Whenever you're ready, tell me which layout you'd like to explore "
            "(201, 202, or 203) and we'll get started."
        )

        return {
            **state,
            "persona_profile":     persona_profile,
            "user_type":           role,
            "onboarding_complete": True,
            "final_response":      response,
        }

    return persona_compiler_node
