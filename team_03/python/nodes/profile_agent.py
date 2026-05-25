from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import call_llm_simple
from knowledge.loader import load_knowledge


# ---------------------------------------------------------------------------
# Default profile values — used when the LLM call fails or returns nothing.
# ---------------------------------------------------------------------------

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "wheelchair_user": {
        "profile_type": "wheelchair_user",
        "reach_height_min": 0.38,
        "reach_height_max": 1.22,
        "reach_radius": 0.60,
        "min_path_width": 0.90,
        "turning_radius": 0.75,
        "seated_height": 1.10,
        "notes": "Standard manual wheelchair user (ADA baseline).",
    },
    "elderly": {
        "profile_type": "elderly",
        "reach_height_min": 0.50,
        "reach_height_max": 1.50,
        "reach_radius": 0.55,
        "min_path_width": 0.85,
        "turning_radius": 0.60,
        "seated_height": None,
        "notes": "Reduced reach and balance; may use a cane or walker.",
    },
    "stroller": {
        "profile_type": "stroller",
        "reach_height_min": 0.40,
        "reach_height_max": 1.60,
        "reach_radius": 0.50,
        "min_path_width": 0.90,
        "turning_radius": 0.65,
        "seated_height": None,
        "notes": "Parent pushing a standard baby stroller.",
    },
    "autistic": {
        "profile_type": "autistic",
        "reach_height_min": 0.40,
        "reach_height_max": 1.60,
        "reach_radius": 0.60,
        "min_path_width": 0.80,
        "turning_radius": 0.50,
        "seated_height": None,
        "notes": "Sensitive to spatial complexity and dead ends; prefers clear sightlines.",
    },
    "visually_impaired": {
        "profile_type": "visually_impaired",
        "reach_height_min": 0.40,
        "reach_height_max": 1.60,
        "reach_radius": 0.60,
        "min_path_width": 0.90,
        "turning_radius": 0.60,
        "seated_height": None,
        "notes": "Relies on tactile cues, consistent layout, and landmark rooms.",
    },
    "forklift": {
        "profile_type": "forklift",
        "reach_height_min": 0.00,
        "reach_height_max": 6.00,
        "reach_radius": 1.20,
        "min_path_width": 3.05,
        "turning_radius": 2.50,
        "seated_height": 1.50,
        "notes": "Standard 2-3 ton counterbalance forklift.",
    },
    "crane": {
        "profile_type": "crane",
        "reach_height_min": 0.00,
        "reach_height_max": 12.00,
        "reach_radius": 2.00,
        "min_path_width": 5.00,
        "turning_radius": 5.00,
        "seated_height": None,
        "notes": "Overhead bridge crane — requires wide clearance lanes.",
    },
}


# ---------------------------------------------------------------------------
# System prompt for the profile agent LLM call.
# ---------------------------------------------------------------------------

PROFILE_SYSTEM_PROMPT = """You are an accessibility profiling expert for architectural floor plans.

Given a user's description of their needs, mobility aids, and physical constraints,
produce a structured JSON profile that downstream tools will use for clearance checks,
path analysis, reachability tests, and collision detection.

## Knowledge base (reference data):
{knowledge_context}

## Output format — ONLY valid JSON, no extra text:
{{
  "profile_type": "string — e.g. wheelchair_user, elderly, stroller, autistic, visually_impaired, forklift, crane, or custom",
  "reach_height_min": 0.0,
  "reach_height_max": 0.0,
  "reach_radius": 0.0,
  "min_path_width": 0.0,
  "turning_radius": 0.0,
  "seated_height": null,
  "notes": "brief explanation of the profile constraints"
}}

Rules:
- All numeric values in METERS.
- If the user does not specify a profile, default to wheelchair_user.
- Use the knowledge base facts to ground your values (ADA, ISO, Neufert).
- seated_height is null for standing users.
"""


# ---------------------------------------------------------------------------
# Keywords used to detect profile type from the user prompt.
# ---------------------------------------------------------------------------

_PROFILE_KEYWORDS: dict[str, list[str]] = {
    "wheelchair_user": ["wheelchair", "silla de ruedas", "wc user"],
    "elderly": ["elderly", "senior", "old", "aged", "anciano"],
    "stroller": ["stroller", "pram", "buggy", "baby", "carriola"],
    "autistic": ["autistic", "autism", "asd", "autismo"],
    "visually_impaired": ["blind", "visually impaired", "visual", "low vision", "ciego"],
    "forklift": ["forklift", "montacargas", "pallet truck"],
    "crane": ["crane", "overhead crane", "grua", "bridge crane"],
}


def _detect_profile_type(prompt: str) -> str:
    """Extract the most likely profile type from the user prompt."""
    prompt_lower = prompt.lower()
    for profile_type, keywords in _PROFILE_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return profile_type
    return "wheelchair_user"


# ---------------------------------------------------------------------------
# Node builder — follows the project's build_<name>_node pattern.
# ---------------------------------------------------------------------------

def build_profile_agent_node(llm: Any, knowledge_dir: Path):
    """Return a LangGraph node that profiles the user's accessibility needs."""

    def profile_agent_node(state: dict) -> dict:
        print("\nProfiler agent — analysing user needs...")

        # 1. Extract prompt from conversation messages
        user_msg = ""
        for msg in reversed(state.get("messages", [])):
            # Handle both plain dicts and LangChain HumanMessage/AIMessage objects.
            # After the Annotated[add_messages] fix, LangGraph stores messages as
            # message objects rather than dicts, so both forms must be supported.
            if isinstance(msg, dict):
                role    = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role    = getattr(msg, "type", "")
                content = getattr(msg, "content", "")
            if role in ("user", "human"):
                user_msg = content
                break

        # 2. Detect profile type for keyword-based RAG lookup
        detected_type = _detect_profile_type(user_msg)

        # 3. Load relevant knowledge
        rag_keywords = ["accessibility", "clearance", "ergonomics", "ada"]
        knowledge_text = load_knowledge(knowledge_dir, "general", rag_keywords)
        if not knowledge_text:
            knowledge_text = "(no knowledge files found — use your training data)"

        # 4. Call LLM
        system = PROFILE_SYSTEM_PROMPT.format(knowledge_context=knowledge_text)
        result = call_llm_simple(llm, system, user_msg)

        # 5. Validate or fall back — handle nested LLM responses
        #    LLM sometimes wraps the profile in extra layers like
        #    {"accessibility_analysis": {"profile": {"profile_type": ...}}}
        if result and isinstance(result, dict) and "profile_type" not in result:
            # Search one or two levels deep for a dict with "profile_type"
            for v in result.values():
                if isinstance(v, dict):
                    if "profile_type" in v:
                        result = v
                        break
                    for v2 in v.values():
                        if isinstance(v2, dict) and "profile_type" in v2:
                            result = v2
                            break

        if result and isinstance(result, dict) and "profile_type" in result:
            profile_config = result
            print(f"  [profile_agent] Using LLM-generated profile: {result.get('profile_type')}")
        else:
            profile_config = DEFAULT_PROFILES.get(
                detected_type, DEFAULT_PROFILES["wheelchair_user"]
            )
            print(f"  [profile_agent] LLM result invalid, falling back to default: {detected_type}")

        ptype = profile_config.get("profile_type", "unknown")
        mpath = profile_config.get("min_path_width", "?")
        turn = profile_config.get("turning_radius", "?")
        print(f"  Profile: {ptype} (min_path: {mpath}m, turning: {turn}m)")
        return {"profile_config": profile_config}

    return profile_agent_node
