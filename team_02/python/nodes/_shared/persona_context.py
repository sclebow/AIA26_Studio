"""
persona_context.py — the SINGLE SOURCE OF TRUTH for turning a compiled persona
profile into the two things layout mode needs from it:

  1. format_persona_for_prompt(profile)  — the human context string every
     conversational/LLM node feeds to the model. Before this, each node hand-rolled
     its own _format_persona with a *different* subset, so facts captured at
     onboarding (household members, pets, age, non-negotiables, notes) were silently
     dropped on the way to the work. One formatter → nothing is lost.

  2. persona_scoring_args(profile) / derive_context(profile) — the persona-derived
     arguments for the comfort engine, including the household-context flags
     (elderly / children / pets) that apply_context() uses to weigh deficits for
     vulnerable occupants.

Keep this pure: no LLM calls, no MCP calls, no state mutation.
"""

from __future__ import annotations
import json

from nodes._shared.utils import persona_display_label

SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


# ── Scoring side ──────────────────────────────────────────────────────────────

def personality_value(profile: dict) -> float:
    """Coerce the persona's personality axis to a float in [-1, 1] (introvert↔extrovert).
    Accepts the legacy string form ('introvert'/'extrovert') too. 0.0 when absent."""
    pers = (profile or {}).get("personality", 0)
    if isinstance(pers, str):
        pers = {"introvert": -1.0, "extrovert": 1.0}.get(pers.strip().lower(), 0.0)
    try:
        return max(-1.0, min(1.0, float(pers or 0)))
    except (TypeError, ValueError):
        return 0.0


# Surface words (in household_members / age_group / household_type) that imply each
# vulnerability flag. Kept here so scoring, comparison and the reveal all agree.
_ELDERLY_WORDS  = ("grandparent", "grandmother", "grandfather", "grandma", "grandpa",
                   "granny", "elder", "elderly", "senior", "retired")
_CHILD_WORDS    = ("child", "children", "kid", "kids", "baby", "toddler", "infant",
                   "son", "daughter", "newborn")
_PET_WORDS      = ("pet", "pets", "dog", "dogs", "puppy", "cat", "cats", "kitten",
                   "bird", "rabbit", "bunny", "fish", "hamster")


def derive_context(profile: dict) -> dict:
    """Normalise the persona's structured occupancy facts into the household-context
    flags the comfort engine understands: {"elderly": bool, "children": bool, "pets": bool}.
    Reads age_group, household_type AND the free household_members list (where pets and
    relatives land), so a stated grandmother or cat becomes a real scoring signal.
    Returns only the True flags (empty dict → apply_context is a no-op)."""
    if not profile:
        return {}
    age = str(profile.get("age_group") or "").lower()
    members = " ".join(str(m).lower() for m in (profile.get("household_members") or []))

    # children requires an ACTUAL child signal (age or a named child) — not just
    # household_type "family", which is ambiguous (a multi-gen home with a grandparent
    # is "family" too) and is already reflected in the onboarding comfort_weights.
    elderly  = age == "elderly" or any(w in members for w in _ELDERLY_WORDS)
    children = age == "child" or any(w in members for w in _CHILD_WORDS)
    pets     = any(w in members for w in _PET_WORDS)

    ctx = {}
    if elderly:
        ctx["elderly"] = True
    if children:
        ctx["children"] = True
    if pets:
        ctx["pets"] = True
    return ctx


def persona_scoring_args(profile: dict) -> dict:
    """The persona-derived arguments for a compute_comfort_scores call: the display
    label, the onboarding comfort_weights, the personality axis, and the household
    context. Merge with the caller's tool-specific args (layout_json, room_ids).
    Used by the analyze and preview nodes so every scoring call carries the same
    persona — no field is dropped, no number is faked."""
    profile = profile or {}
    args = {
        "persona":     persona_display_label(profile),
        "personality": personality_value(profile),
    }
    weights = profile.get("comfort_weights")
    if weights:
        args["weights_override"] = json.dumps(weights)
    ctx = derive_context(profile)
    if ctx:
        args["context"] = json.dumps(ctx)
    return args


# ── Prompt side ───────────────────────────────────────────────────────────────

def _members_clause(profile: dict) -> str:
    """A short 'household members: grandmother, a cat' clause, or '' if none stated."""
    members = [str(m).strip() for m in (profile.get("household_members") or []) if str(m).strip()]
    if members:
        return "household members: " + ", ".join(members)
    return ""


def format_persona_for_prompt(profile: dict, *, level: str = "full") -> str:
    """Render the FULL human context for an LLM node — the single formatter every
    conversational node uses, so household/pets/age/non-negotiables/notes always reach
    the model.

    level="full"  → the rich, multi-clause summary (interpreter, respond, follow-up).
    level="line"  → a compact one-liner that still carries the load-bearing fidelity
                    facts (who they live with + top senses), for tight prompts.
    """
    if not profile:
        return ("neutral adult, no specific sensory sensitivities"
                if level == "full" else "no specific persona")

    name = str(profile.get("name") or "").strip()
    role = str(profile.get("role") or "").strip()
    desc = str(profile.get("description") or "").strip()
    head = f"{name} ({role})" if name and role else (name or role)
    members = _members_clause(profile)
    priorities = profile.get("sensory_priorities") or []

    if level == "line":
        bits = [head or desc or "someone"]
        if members:
            bits.append(members)
        if priorities:
            bits.append("cares most about " + ", ".join(priorities[:3]))
        return "; ".join(b for b in bits if b)

    parts = []
    if head:
        parts.append(head)
    if desc and desc.lower() != (head or "").lower():
        parts.append(desc)
    if profile.get("age_group"):
        parts.append(f"age group: {profile['age_group']}")
    if profile.get("household_type"):
        parts.append(f"household: {profile['household_type']}")
    if members:
        parts.append(members)
    if priorities:
        parts.append(f"sensory priorities: {', '.join(priorities)}")
    if profile.get("sensory_sensitivities"):
        parts.append(f"sensitivities: {', '.join(profile['sensory_sensitivities'])}")
    if profile.get("key_requirements"):
        parts.append(f"non-negotiables: {'; '.join(profile['key_requirements'])}")
    aesthetic = str(profile.get("aesthetic_preferences") or "").strip()
    if aesthetic:
        # keep it short — the aesthetic paragraph can be long
        parts.append(f"aesthetic: {aesthetic[:200].rstrip()}")
    notes = str(profile.get("notes") or "").strip()
    if notes and not notes.lower().startswith("profile built from"):
        parts.append(f"notes: {notes}")
    return "; ".join(parts) if parts else "no profile"
