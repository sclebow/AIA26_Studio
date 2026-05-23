from typing import Any

# Central registry for design operation modes
DESIGN_REGISTRY: dict[str, dict[str, object]] = {
    "suggest": {
        "label": "Suggestion Layer",
        "description": "Generate design suggestions based on current state",
        "tool_name_contains": ["suggest", "generate"],
    },
    "evaluate": {
        "label": "Evaluation",
        "description": "Evaluate current design against criteria",
        "tool_name_contains": ["evaluate", "score", "assess"],
    },
    "optimize": {
        "label": "Optimization",
        "description": "Optimize design parameters",
        "tool_name_contains": ["optimize", "improve", "refine"],
    },
    "explain": {
        "label": "Explanation",
        "description": "Explain design reasoning and tradeoffs",
        "tool_name_contains": ["explain", "analyze", "report"],
    },
    "visualize": {
        "label": "Visualization",
        "description": "Create visual representations of design",
        "tool_name_contains": ["visualize", "render", "display"],
    },
}

AVAILABLE_ACTIONS: tuple[str, ...] = tuple(DESIGN_REGISTRY.keys())


def group_tools_by_action(tools: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Split MCP tools into design-action-specific collections.
    Tools containing specific keywords are grouped by action.
    """

    grouped_tools: dict[str, list[dict[str, Any]]] = {
        action: [] for action in AVAILABLE_ACTIONS
    }

    for tool in tools:
        tool_name = str(tool.get("name", "")).lower()
        for action_name in AVAILABLE_ACTIONS:
            action_config = DESIGN_REGISTRY[action_name]
            match_tokens = action_config.get("tool_name_contains", [])
            if not isinstance(match_tokens, list):
                continue
            if any(str(token).lower() in tool_name for token in match_tokens):
                grouped_tools[action_name].append(tool)
                break

    return grouped_tools


def build_design_prompt(action: str, user_prompt: str) -> str:
    """
    Build a focused prompt for a specific design action.
    """

    return (
        f"You are a {action} specialist in a building design workflow. "
        f"Focus only on {action} tasks related to the design.\n\n"
        f"Original user request:\n{user_prompt}"
    )
