from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import call_llm_simple
from knowledge.loader import load_all_knowledge
from prompts import SPACE_TYPE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Default space config — industrial only.
# Used when the LLM call fails or returns an invalid response.
# ---------------------------------------------------------------------------

DEFAULT_INDUSTRIAL_CONFIG: dict[str, Any] = {
    "space_type": "industrial",
    "priorities": ["collision", "path_analysis", "visibility", "reachability", "orientation"],
    "clearance": 1.20,
    "tool_weights": {
        "collision":    0.30,
        "visibility":   0.20,
        "path":         0.25,
        "reachability": 0.15,
        "orientation":  0.10,
    },
    "use_clearance": True,
    "orientation_required": True,
}


# ---------------------------------------------------------------------------
# Node builder
# ---------------------------------------------------------------------------

def build_space_type_agent_node(llm: Any, knowledge_dir: Path):
    """Return a LangGraph node that determines industrial space priorities and weights."""

    def space_type_agent_node(state: dict) -> dict:
        print("\nSpace type agent — analysing industrial space characteristics...")

        # 1. Extract user prompt from conversation
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

        # 2. Get layoutId from state
        layout_id = ""
        layout_str = state.get("layout_json_string", "")
        if layout_str:
            try:
                layout_data = json.loads(layout_str)
                layout_id = layout_data.get("layoutId", "")
            except (json.JSONDecodeError, AttributeError):
                pass

        # 3. Load ALL industrial knowledge — always industrial, no detection needed
        knowledge_text = load_all_knowledge(knowledge_dir, "industrial")
        if not knowledge_text:
            knowledge_text = "(no knowledge files found — use OSHA/NFPA/ISO training data)"

        # 4. Build agent input
        agent_input = (
            f"Space category: industrial\n"
            f"Layout ID: {layout_id or '(not specified)'}\n\n"
            f"User request:\n{user_msg}"
        )

        # 5. Call LLM
        system = SPACE_TYPE_SYSTEM_PROMPT.format(knowledge_context=knowledge_text)
        result = call_llm_simple(llm, system, agent_input)

        # 6. Validate — unwrap nested responses if needed
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
            # Enforce orientation_required and use_clearance — always true for industrial
            result["orientation_required"] = True
            result["use_clearance"]        = True
            space_config = result
            print(f"  [space_type_agent] LLM config: {result.get('space_type')}")
        else:
            space_config = DEFAULT_INDUSTRIAL_CONFIG
            print(f"  [space_type_agent] LLM result invalid — using industrial default")

        stype      = space_config.get("space_type", "industrial")
        priorities = space_config.get("priorities", [])
        clearance  = space_config.get("clearance", 1.20)
        print(f"  Space: {stype} | clearance: {clearance}m | priorities: {', '.join(priorities[:3])}")
        return {"space_config": space_config}

    return space_type_agent_node
