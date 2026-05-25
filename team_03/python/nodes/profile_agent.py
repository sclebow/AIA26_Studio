from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import call_llm_simple
from knowledge.loader import load_knowledge
from prompts import PROFILE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Industrial profiles — the only profiles this system supports.
# ---------------------------------------------------------------------------

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "standard_worker": {
        "profile_type":    "standard_worker",
        "reach_height_min": 0.40,
        "reach_height_max": 1.80,
        "reach_radius":     0.60,
        "min_path_width":   0.915,
        "turning_radius":   0.30,
        "seated_height":    None,
        "notes": "Standard standing industrial worker — OSHA general industry baseline.",
    },
    "forklift": {
        "profile_type":    "forklift",
        "reach_height_min": 0.00,
        "reach_height_max": 6.00,
        "reach_radius":     1.20,
        "min_path_width":   3.05,
        "turning_radius":   2.50,
        "seated_height":    1.50,
        "notes": "Standard 2-3 ton counterbalance forklift — ANSI B56.1.",
    },
    "crane": {
        "profile_type":    "crane",
        "reach_height_min": 0.00,
        "reach_height_max": 12.00,
        "reach_radius":     2.00,
        "min_path_width":   5.00,
        "turning_radius":   5.00,
        "seated_height":    None,
        "notes": "Overhead bridge crane — requires wide clearance lanes. OSHA 1910.179.",
    },
    "pallet_jack": {
        "profile_type":    "pallet_jack",
        "reach_height_min": 0.00,
        "reach_height_max": 0.30,
        "reach_radius":     0.80,
        "min_path_width":   1.52,
        "turning_radius":   1.20,
        "seated_height":    None,
        "notes": "Manual or electric pallet jack — narrower than forklift, lower clearance.",
    },
    "maintenance_worker": {
        "profile_type":    "maintenance_worker",
        "reach_height_min": 0.30,
        "reach_height_max": 2.00,
        "reach_radius":     0.70,
        "min_path_width":   0.760,
        "turning_radius":   0.40,
        "seated_height":    None,
        "notes": "Maintenance technician — needs access to rear and sides of machinery. Neufert / OSHA.",
    },
}

# Default when no profile is detected — standard worker covers the broadest case
DEFAULT_PROFILE_KEY = "standard_worker"


# ---------------------------------------------------------------------------
# Keyword detection — industrial profiles only.
# ---------------------------------------------------------------------------

_PROFILE_KEYWORDS: dict[str, list[str]] = {
    "forklift":          ["forklift", "fork lift", "montacargas", "pallet truck", "reach truck"],
    "crane":             ["crane", "overhead crane", "bridge crane", "grua", "hoist"],
    "pallet_jack":       ["pallet jack", "pallet mover", "transpaleta", "hand truck"],
    "maintenance_worker":["maintenance", "technician", "repair", "service", "mantenimiento"],
    "standard_worker":   ["worker", "operator", "staff", "person", "employee", "trabajador"],
}


def _detect_profile_type(prompt: str) -> str:
    """Detect the most likely industrial profile type from the user prompt."""
    prompt_lower = prompt.lower()
    for profile_type, keywords in _PROFILE_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return profile_type
    return DEFAULT_PROFILE_KEY


# ---------------------------------------------------------------------------
# Node builder
# ---------------------------------------------------------------------------

def build_profile_agent_node(llm: Any, knowledge_dir: Path):
    """Return a LangGraph node that profiles the industrial movement agent."""

    def profile_agent_node(state: dict) -> dict:
        print("\nProfiler agent — detecting industrial movement profile...")

        # 1. Extract user prompt
        user_msg = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, dict):
                role    = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role    = getattr(msg, "type", "")
                content = getattr(msg, "content", "")
            if role in ("user", "human"):
                user_msg = content
                break

        # 2. Detect profile type for knowledge lookup
        detected_type = _detect_profile_type(user_msg)

        # 3. Load industrial ergonomics and machinery knowledge
        rag_keywords = ["ergonomics", "forklift", "machinery", "osha", "worker"]
        knowledge_text = load_knowledge(knowledge_dir, "industrial", rag_keywords)
        if not knowledge_text:
            knowledge_text = "(no knowledge files found — use OSHA/ISO/ANSI training data)"

        # 4. Call LLM
        system = PROFILE_SYSTEM_PROMPT.format(knowledge_context=knowledge_text)
        result = call_llm_simple(llm, system, user_msg)

        # 5. Validate — unwrap nested responses if needed
        if result and isinstance(result, dict) and "profile_type" not in result:
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
            if not result.get("turning_radius") or result["turning_radius"] < 0.25:
                result["turning_radius"] = DEFAULT_PROFILES.get(
                    result["profile_type"], DEFAULT_PROFILES[DEFAULT_PROFILE_KEY]
                    ).get("turning_radius", 0.30)
            profile_config = result
            print(f"  [profile_agent] LLM profile: {result.get('profile_type')}")
        else:
            profile_config = DEFAULT_PROFILES[detected_type]
            print(f"  [profile_agent] LLM result invalid — using default: {detected_type}")

        ptype  = profile_config.get("profile_type", "unknown")
        mpath  = profile_config.get("min_path_width", "?")
        turn   = profile_config.get("turning_radius", "?")
        print(f"  Profile: {ptype} | min_path: {mpath}m | turning: {turn}m")

        # Derive a sanitized placement profile — vehicle profiles apply to
        # circulation analysis only; equipment placement always uses standard_worker.
        _VEHICLE_PROFILES = {"forklift", "crane", "pallet_jack"}
        placement_type = (
            profile_config.get("profile_type", "standard_worker")
            if profile_config.get("profile_type") not in _VEHICLE_PROFILES
            else "standard_worker"
        )
        placement_profile = DEFAULT_PROFILES.get(
            placement_type, DEFAULT_PROFILES["standard_worker"]
        )
        print(f"  Placement profile: {placement_type}")

        return {
            "profile_config":    profile_config,
            "placement_profile": placement_profile,
        }

    return profile_agent_node
