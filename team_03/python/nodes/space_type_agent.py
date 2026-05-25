from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import call_llm_simple
from knowledge.loader import load_all_knowledge


# ---------------------------------------------------------------------------
# Default space configs — used when the LLM call fails.
# ---------------------------------------------------------------------------

DEFAULT_SPACE_CONFIGS: dict[str, dict[str, Any]] = {
    "residential": {
        "space_type": "residential",
        "priorities": ["path_analysis", "collision", "reachability", "visibility"],
        "clearance": 0.90,
        "tool_weights": {
            "collision": 0.25,
            "visibility": 0.20,
            "path": 0.25,
            "reachability": 0.25,
            "orientation": 0.05,
        },
        "use_clearance": True,
        "orientation_required": False,
    },
    "industrial": {
        "space_type": "industrial",
        "priorities": ["collision", "path_analysis", "visibility", "reachability"],
        "clearance": 1.20,
        "tool_weights": {
            "collision": 0.30,
            "visibility": 0.20,
            "path": 0.25,
            "reachability": 0.15,
            "orientation": 0.10,
        },
        "use_clearance": True,
        "orientation_required": True,
    },
}


# ---------------------------------------------------------------------------
# System prompt for the space type agent LLM call.
# ---------------------------------------------------------------------------

SPACE_TYPE_SYSTEM_PROMPT = """You are a spatial analysis expert for architectural floor plans.

Given the space type and layout metadata, determine the analysis priorities,
clearance requirements, and tool weights that an accessibility evaluation agent
should use.

## Knowledge base (reference data):
{knowledge_context}

## Output format — ONLY valid JSON, no extra text:
{{
  "space_type": "string — e.g. residential, industrial_workshop, restaurant_kitchen, office, warehouse",
  "priorities": ["list of analysis types ordered by importance: path_analysis, collision, visibility, reachability, orientation"],
  "clearance": 0.0,
  "tool_weights": {{
    "collision": 0.0,
    "visibility": 0.0,
    "path": 0.0,
    "reachability": 0.0,
    "orientation": 0.0
  }},
  "use_clearance": true,
  "orientation_required": false
}}

Rules:
- Clearance value in METERS — base it on the space type's code requirements.
- tool_weights must sum to 1.0.
- priorities list determines which analyses to run first.
- use_clearance: true if the space has tight passages or furniture obstacles.
- orientation_required: true for industrial/warehouse spaces where equipment facing matters.
- For residential: prioritise path_analysis and reachability (daily living).
- For industrial: prioritise collision and path_analysis (safety critical).
"""


# ---------------------------------------------------------------------------
# Keywords used to detect space category from prompt + layoutId.
# ---------------------------------------------------------------------------

_INDUSTRIAL_KEYWORDS = [
    "industrial", "warehouse", "factory", "workshop", "manufacturing",
    "production", "assembly", "loading", "fabrication", "processing",
    "distribution", "packaging", "inspection", "staging", "forklift",
    "crane", "almacen", "fabrica", "taller",
]

_RESIDENTIAL_KEYWORDS = [
    "residential", "house", "home", "apartment", "flat", "dwelling",
    "bedroom", "kitchen", "living room", "bathroom", "casa", "hogar",
    "vivienda", "departamento",
]


def _detect_space_category(prompt: str, layout_id: str) -> str:
    """Detect whether the space is residential or industrial."""
    combined = (prompt + " " + layout_id).lower()
    for kw in _INDUSTRIAL_KEYWORDS:
        if kw in combined:
            return "industrial"
    for kw in _RESIDENTIAL_KEYWORDS:
        if kw in combined:
            return "residential"
    return "residential"


# ---------------------------------------------------------------------------
# Node builder — follows the project's build_<name>_node pattern.
# ---------------------------------------------------------------------------

def build_space_type_agent_node(llm: Any, knowledge_dir: Path):
    """Return a LangGraph node that determines space priorities and weights."""

    def space_type_agent_node(state: dict) -> dict:
        print("\nSpace type agent — analysing space characteristics...")

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

        # 2. Try to get layoutId from the layout JSON in the state
        layout_id = ""
        layout_str = state.get("layout_json_string", "")
        if layout_str:
            try:
                layout_data = json.loads(layout_str)
                layout_id = layout_data.get("layoutId", "")
            except (json.JSONDecodeError, AttributeError):
                pass

        # 3. Detect space category
        category = _detect_space_category(user_msg, layout_id)

        # 4. Load ALL knowledge for this category (space agent needs full context)
        knowledge_text = load_all_knowledge(knowledge_dir, category)
        if not knowledge_text:
            knowledge_text = "(no knowledge files found — use your training data)"

        # 5. Build user message with space context
        agent_input = (
            f"Space category detected: {category}\n"
            f"Layout ID: {layout_id or '(not specified)'}\n\n"
            f"User request:\n{user_msg}"
        )

        # 6. Call LLM
        system = SPACE_TYPE_SYSTEM_PROMPT.format(knowledge_context=knowledge_text)
        result = call_llm_simple(llm, system, agent_input)

        # 7. Validate or fall back — handle nested LLM responses
        if result and isinstance(result, dict) and "space_type" not in result:
            for v in result.values():
                if isinstance(v, dict):
                    if "space_type" in v and "tool_weights" in v:
                        result = v
                        break
                    for v2 in v.values():
                        if isinstance(v2, dict) and "space_type" in v2 and "tool_weights" in v2:
                            result = v2
                            break

        if result and isinstance(result, dict) and "space_type" in result and "tool_weights" in result:
            space_config = result
            print(f"  [space_type_agent] Using LLM-generated config: {result.get('space_type')}")
        else:
            space_config = DEFAULT_SPACE_CONFIGS.get(
                category, DEFAULT_SPACE_CONFIGS["residential"]
            )
            print(f"  [space_type_agent] LLM result invalid, falling back to default: {category}")

        stype = space_config.get("space_type", "unknown")
        priorities = space_config.get("priorities", [])
        print(f"  Space: {stype} (priorities: {', '.join(priorities[:3])})")
        return {"space_config": space_config}

    return space_type_agent_node
