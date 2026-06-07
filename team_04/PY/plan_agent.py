from __future__ import annotations

import json
import re
from typing import Any, Callable

from design_state import build_prompt_memory_state, build_shape_generation_state


PLAN_AGENT_PROMPT = """
You are the Plan Agent for an architectural generative design workflow.

Your job is to analyze the user's prompt before the existing workflow starts.
Do not generate geometry.
Do not optimize geometry.
Do not replace the existing workflow.

You must output ONLY valid JSON with this structure:
{
  "requires_clarification": false,
  "clarification_question": "",
  "human_friendly_explanation": "Short plain-English explanation of the design strategy.",
  "building_type": "string",
    "selected_shape_type": "string",
    "tree_policy": {
        "tree_count": 0,
        "tree_positions_provided": false,
        "preferred_edge": "string",
        "placement_mode": "string",
          "inferred_tree_points": [],
          "inferred_tree_sizes": []
    },
  "optimization_targets": ["string"],
  "constraints": ["string"],
  "parameter_ranges": {
    "rotation": [0, 0],
    "offset_x": [0, 0],
    "offset_y": [0, 0]
  },
  "fitness_weights": {
    "fit": 0.0,
    "constraints": 0.0,
    "efficiency": 0.0,
    "open_space": 0.0
  },
  "optimization_settings": {
    "max_iterations": 0,
    "population_size": 0,
    "mutation_rate": 0.0,
    "termination": "string"
  },
  "grasshopper_inputs_outputs": {
    "inputs": ["string"],
    "outputs": ["string"]
  },
  "handoff": {
    "mode": "automatic",
    "target": "existing_workflow",
    "notes": "string"
  }
}

Rules:
- If the prompt is missing essential information, set "requires_clarification" to true and ask exactly one short question in "clarification_question".
- Prefer the existing workflow's shape hint, site context, and constraint language when available.
- If the user provides only a tree count, infer a tree placement policy and relative tree positions from the site context instead of asking for coordinates.
- Keep the explanation simple and practical.
- Keep numeric values conservative if the prompt does not specify them.
- Return valid JSON only, with no markdown fences.
""".strip()


_TREE_COUNT_PATTERNS = [
    (r"\b(one|1)\s+tree\b", 1),
    (r"\b(two|2)\s+trees?\b", 2),
    (r"\b(three|3)\s+trees?\b", 3),
    (r"\b(four|4)\s+trees?\b", 4),
    (r"\b(five|5)\s+trees?\b", 5),
    (r"\b(six|6)\s+trees?\b", 6),
    (r"\b(seven|7)\s+trees?\b", 7),
    (r"\b(eight|8)\s+trees?\b", 8),
    (r"\b(nine|9)\s+trees?\b", 9),
    (r"\b(ten|10)\s+trees?\b", 10),
]


def _extract_tree_count(user_prompt: str) -> int:
    prompt = (user_prompt or "").lower()
    for pattern, count in _TREE_COUNT_PATTERNS:
        if re.search(pattern, prompt):
            return count

    match = re.search(r"\b(\d+)\s+trees?\b", prompt)
    if match:
        try:
            return max(0, int(match.group(1)))
        except ValueError:
            return 0

    return 0


def _parse_wing_areas(user_prompt: str) -> dict[str, float]:
    """
    Parse wing/arm area specifications from user prompt.
    
    Supports formats like:
    - "one wing of 75sq m" / "arm of 75sq m"
    - "75 sqm"
    - "wing area 75 m2" / "arm area 75 m2"
    - "first wing 75sq m, second wing 50sqm"
    - "left arm 100 sqm, right arm 80 sqm"
    
    Returns dict with keys like 'left_wing_area', 'right_wing_area', 'avg_wing_area'
    or 'left_arm_area', 'right_arm_area', 'avg_arm_area'
    """
    prompt = (user_prompt or "").lower()
    areas: list[float] = []
    component_type = "wing"  # default
    
    # Check if prompt mentions "arm" instead of "wing"
    if "arm" in prompt and "wing" not in prompt:
        component_type = "arm"
    
    # Match patterns like "75sq m", "75 sqm", "75m2", "75sq.m", etc.
    patterns = [
        r"(\d+(?:\.\d+)?)\s*sq\.?\s*m(?!eter)",  # "75sq m", "75 sqm", "75sq.m"
        r"(\d+(?:\.\d+)?)\s*m2\b",                  # "75m2"
        r"(\d+(?:\.\d+)?)\s*square\s+meters?\b",    # "75 square meters"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, prompt)
        for match in matches:
            try:
                areas.append(float(match))
            except ValueError:
                continue
    
    if not areas:
        return {}
    
    result = {}
    if len(areas) >= 2:
        result[f"left_{component_type}_area"] = areas[0]
        result[f"right_{component_type}_area"] = areas[1]
        result[f"avg_{component_type}_area"] = sum(areas[:2]) / 2.0
    elif len(areas) == 1:
        result[f"{component_type}_area"] = areas[0]
        result[f"avg_{component_type}_area"] = areas[0]
    
    return result


def _extract_tree_edge_hint(user_prompt: str) -> str:
    prompt = (user_prompt or "").lower()
    for edge in ("north", "south", "east", "west", "top", "bottom", "left", "right"):
        if re.search(rf"\b{re.escape(edge)}\b", prompt):
            return edge
    return ""


def _infer_default_shape_type(user_prompt: str) -> str:
    prompt = (user_prompt or "").lower()

    if any(keyword in prompt for keyword in ("residential", "housing", "apartment", "dorm", "home")):
        return "l_shape"

    if any(keyword in prompt for keyword in ("school", "campus", "university", "academic")):
        return "u_shape"

    if any(keyword in prompt for keyword in ("office", "mixed-use", "mixed use", "commercial", "retail", "workspace")):
        return "rectangle"

    if any(keyword in prompt for keyword in ("hotel", "hospital", "clinic", "medical")):
        return "rectangle"

    return "rectangle"


def _detect_user_intent(user_prompt: str) -> str:
    prompt = (user_prompt or "").lower()

    if any(keyword in prompt for keyword in ("reset", "new design", "new_design", "start over", "clear previous", "fresh design")):
        return "reset_new_design"

    if any(keyword in prompt for keyword in ("explain result", "generate report", "summarize optimization", "why this placement", "report", "summarize")):
        return "report_only"

    if any(keyword in prompt for keyword in ("add trees", "move trees", "shift trees", "change tree count", "change tree size", "resize trees", "tree update")):
        return "tree_update"

    if any(keyword in prompt for keyword in ("scale", "resize", "enlarge", "shrink", "stretch", "bigger", "larger", "smaller", "increase", "decrease", "wider", "narrower", "expand", "contract")):
        return "scale_building"

    if any(keyword in prompt for keyword in ("rotate", "rotation", "turn building", "turn it", "change orientation")):
        return "rotate_building"

    if (
        any(keyword in prompt for keyword in ("move", "shift", "translate"))
        and any(keyword in prompt for keyword in ("left", "right", "front", "back", "north", "south", "east", "west"))
    ):
        return "move_building"

    # also accept up/down keywords as move intent
    if any(keyword in prompt for keyword in ("move", "shift", "translate")) and any(
        keyword in prompt for keyword in ("up", "down", "top", "bottom", "above", "below")
    ):
        return "move_building"

    if any(keyword in prompt for keyword in ("optimize", "find best location", "generate best layout", "place building automatically", "create optimized massing", "generate", "regenerate", "create new layout", "best placement", "best location")):
        return "optimize_layout"

    return "optimize_layout"


def _parse_distance_meters(user_prompt: str, default_value: float = 0.0) -> float:
    prompt = (user_prompt or "").lower()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres)\b", prompt)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return default_value
    return default_value


def _parse_angle_degrees(user_prompt: str, default_value: float = 15.0) -> float:
    prompt = (user_prompt or "").lower()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*degrees?\b", prompt)
    if match:
        try:
            return abs(float(match.group(1)))
        except ValueError:
            return default_value
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*deg\b", prompt)
    if match:
        try:
            return abs(float(match.group(1)))
        except ValueError:
            return default_value
    return default_value


def _extract_explicit_tree_count(user_prompt: str) -> int:
    prompt = (user_prompt or "").lower()
    match = re.search(r"\b(\d+)\s+trees?\b", prompt)
    if match:
        try:
            return max(0, int(match.group(1)))
        except ValueError:
            return 0
    return 0


def _build_move_plan(user_prompt: str) -> dict[str, Any]:
    distance = _parse_distance_meters(user_prompt, 5.0)
    prompt = (user_prompt or "").lower()

    # determine direction and map to argument key used by downstream tools
    direction = None
    if any(keyword in prompt for keyword in ("left", "west")):
        direction = "move_left"
    elif any(keyword in prompt for keyword in ("right", "east")):
        direction = "move_right"
    elif any(keyword in prompt for keyword in ("front", "forward", "north")):
        direction = "move_front"
    elif any(keyword in prompt for keyword in ("back", "backward", "south", "down")):
        # treat 'down' and 'south' as negative Y / back movement
        direction = "move_back"
    elif any(keyword in prompt for keyword in ("up", "top", "above")):
        direction = "move_front"

    movement: dict[str, Any] = {
        "move_left": 0.0,
        "move_right": 0.0,
        "move_front": 0.0,
        "move_back": 0.0,
        "apply_move": True,
    }

    if direction:
        movement[direction] = float(distance)

    # Provide an initial_tool_calls entry so the workflow can immediately execute the move
    initial_tool_calls = []
    move_call_args = {}
    if direction:
        move_call_args[direction] = float(distance)
    else:
        # default: move_back by distance
        move_call_args["move_back"] = float(distance)

    initial_tool_calls.append({"name": "move", "arguments": move_call_args})

    human_expl = f"Move the building {distance:g} meters"
    if direction:
        human_expl += f" ({direction})"
    human_expl += ", then validate against the site boundary and tree overlap."

    return {
        "requires_clarification": False,
        "intent": "move_building",
        "tool_to_run": "building_move_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "move_distance_meters": float(distance),
        "movement": movement,
        "initial_tool_calls": initial_tool_calls,
        "validation": {
            "check_site_boundary": True,
            "check_tree_overlap": True,
        },
        "human_friendly_explanation": human_expl,
        "handoff": {
            "mode": "automatic",
            "target": "existing_move_tool",
        },
    }


def _build_rotate_plan(user_prompt: str) -> dict[str, Any]:
    prompt = (user_prompt or "").lower()
    direction = "clockwise"
    if any(keyword in prompt for keyword in ("anticlockwise", "counterclockwise", "counter-clockwise", "ccw")):
        direction = "anticlockwise"
    angle_degrees = _parse_angle_degrees(user_prompt, 15.0)

    return {
        "requires_clarification": False,
        "intent": "rotate_building",
        "tool_to_run": "building_rotate_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "rotation": {
            "direction": direction,
            "angle_degrees": angle_degrees,
            "apply_rotation": True,
        },
        "validation": {
            "check_site_boundary": True,
            "check_tree_overlap": True,
        },
        "human_friendly_explanation": (
            f"I will rotate the already optimized building {direction} by {angle_degrees:g} degrees and validate it against the site boundary and tree overlap."
        ),
        "handoff": {
            "mode": "automatic",
            "target": "existing_rotate_tool",
        },
    }


def _build_tree_update_plan(user_prompt: str) -> dict[str, Any]:
    prompt = (user_prompt or "").lower()
    tree_count = _extract_explicit_tree_count(user_prompt)
    tree_size = _parse_distance_meters(user_prompt, 0.0)

    action = "update"
    if "add" in prompt:
        action = "add"
    elif any(keyword in prompt for keyword in ("move trees", "shift trees")):
        action = "move"
    elif "size" in prompt or "sizes" in prompt:
        action = "size"
    elif "count" in prompt:
        action = "count"

    return {
        "requires_clarification": False,
        "intent": "tree_update",
        "tool_to_run": "tree_update_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "tree_update": {
            "action": action,
            "tree_count": tree_count,
            "tree_size": tree_size if tree_size > 0 else None,
            "apply_update": True,
        },
        "human_friendly_explanation": "I will update the tree-related inputs without regenerating the full optimization plan.",
        "handoff": {
            "mode": "automatic",
            "target": "existing_tree_tool",
        },
    }


def _build_report_plan() -> dict[str, Any]:
    return {
        "requires_clarification": False,
        "intent": "report_only",
        "tool_to_run": "report_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "report": {
            "include_summary": True,
            "include_reasoning": True,
            "include_metrics": True,
        },
        "human_friendly_explanation": "I will summarize the existing result without changing the design.",
        "handoff": {
            "mode": "automatic",
            "target": "existing_report_tool",
        },
    }


def _build_optimize_plan(user_prompt: str, tools: list[dict[str, Any]], layout_schema: dict[str, Any]) -> dict[str, Any]:
    shape_hint = build_shape_generation_state(user_prompt)
    tree_policy = _build_tree_policy(user_prompt)
    tool_catalog_text = _build_tool_catalog(tools)
    prompt = _build_plan_prompt(user_prompt, tool_catalog_text, layout_schema, shape_hint, tree_policy)

    # Try the LLM first, but keep the deterministic fallback so the workflow remains stable.
    try:
        llm_result = None
        return {}
    except Exception:
        pass

    plan = _fallback_plan(user_prompt, shape_hint)
    plan["intent"] = "optimize_layout"
    plan["tool_to_run"] = "existing_optimization_workflow"
    plan["run_optimizer"] = True
    plan["run_shape_generator"] = True
    return plan


def _infer_tree_points(tree_count: int, preferred_edge: str) -> list[list[float]]:
    if tree_count <= 0:
        return []

    # Relative points are placeholders for the downstream workflow.
    # They describe an even spread along the indicated edge until actual site geometry is available.
    if preferred_edge in {"north", "top"}:
        y_value = 0.92
        x_positions = [round((index + 1) / (tree_count + 1), 3) for index in range(tree_count)]
        return [[x, y_value] for x in x_positions]

    if preferred_edge in {"south", "bottom"}:
        y_value = 0.08
        x_positions = [round((index + 1) / (tree_count + 1), 3) for index in range(tree_count)]
        return [[x, y_value] for x in x_positions]

    if preferred_edge in {"east", "right"}:
        x_value = 0.92
        y_positions = [round((index + 1) / (tree_count + 1), 3) for index in range(tree_count)]
        return [[x_value, y] for y in y_positions]

    if preferred_edge in {"west", "left"}:
        x_value = 0.08
        y_positions = [round((index + 1) / (tree_count + 1), 3) for index in range(tree_count)]
        return [[x_value, y] for y in y_positions]

    if tree_count == 1:
        return [[0.5, 0.85]]

    if tree_count == 2:
        return [[0.33, 0.85], [0.67, 0.85]]

    return [[round((index + 1) / (tree_count + 1), 3), 0.85] for index in range(tree_count)]


def _infer_tree_sizes(tree_count: int, preferred_edge: str) -> list[float]:
    if tree_count <= 0:
        return []

    base_sizes = {
        "north": 5.5,
        "top": 5.5,
        "south": 4.5,
        "bottom": 4.5,
        "east": 5.0,
        "right": 5.0,
        "west": 5.0,
        "left": 5.0,
    }
    base_size = base_sizes.get(preferred_edge, 5.0)

    if tree_count == 1:
        return [base_size]

    if tree_count == 2:
        return [round(base_size * 0.9, 2), round(base_size * 1.1, 2)]

    mid_index = (tree_count - 1) / 2.0
    sizes: list[float] = []
    for index in range(tree_count):
        offset = abs(index - mid_index) / max(mid_index, 1.0)
        scale = 1.0 - (0.15 * offset)
        sizes.append(round(base_size * scale, 2))
    return sizes


def _build_tree_policy(user_prompt: str) -> dict[str, Any]:
    tree_count = _extract_tree_count(user_prompt)
    preferred_edge = _extract_tree_edge_hint(user_prompt)
    tree_positions_provided = bool(re.search(r"\b(\[|\(|point|x\s*=|y\s*=|coords?|coordinates?)\b", (user_prompt or "").lower()))

    tree_count_source = "user"
    if tree_count <= 0:
        tree_count = 2
        tree_count_source = "default"

    if tree_count > 0:
        placement_mode = "relative_inferred" if not tree_positions_provided else "explicit"
    else:
        placement_mode = "none"

    if tree_count > 0 and preferred_edge:
        notes = f"Distribute {tree_count} trees evenly near the {preferred_edge} edge and keep them inside the site boundary."
    elif tree_count > 0:
        notes = f"Distribute {tree_count} trees evenly inside the site boundary using the available site context."
    else:
        notes = "No tree constraint specified."

    if tree_count_source == "default" and not preferred_edge:
        preferred_edge = "north"

    return {
        "tree_count": tree_count,
        "tree_count_source": tree_count_source,
        "tree_positions_provided": tree_positions_provided,
        "preferred_edge": preferred_edge,
        "placement_mode": placement_mode,
        "tree_points": _infer_tree_points(tree_count, preferred_edge),
        "tree_sizes": _infer_tree_sizes(tree_count, preferred_edge),
        "inferred_tree_points": _infer_tree_points(tree_count, preferred_edge),
        "inferred_tree_sizes": _infer_tree_sizes(tree_count, preferred_edge),
        "notes": notes,
    }


def _build_scale_plan(user_prompt: str) -> dict[str, Any]:
    prompt = (user_prompt or "").lower()
    scale_factor = 1.0
    percentage_match = re.search(r"(\d+(?:\.\d+)?)\s*%", prompt)
    multiplier_match = re.search(r"(\d+(?:\.\d+)?)\s*times?", prompt)
    if percentage_match:
        try:
            percentage_value = float(percentage_match.group(1)) / 100.0
            if any(keyword in prompt for keyword in ("shrink", "smaller", "reduce", "decrease", "narrower", "contract")):
                scale_factor = max(0.1, 1.0 - percentage_value)
            else:
                scale_factor = 1.0 + percentage_value
        except ValueError:
            scale_factor = 1.0
    elif multiplier_match:
        try:
            multiplier_value = float(multiplier_match.group(1))
            if any(keyword in prompt for keyword in ("shrink", "smaller", "reduce", "decrease", "narrower", "contract")):
                scale_factor = max(0.1, 1.0 - multiplier_value)
            else:
                scale_factor = 1.0 + multiplier_value
        except ValueError:
            scale_factor = 1.0
    elif any(keyword in prompt for keyword in ("enlarge", "bigger", "expand", "increase", "wider", "larger")):
        scale_factor = 1.1
    elif any(keyword in prompt for keyword in ("shrink", "smaller", "reduce", "decrease", "narrower", "contract")):
        scale_factor = 0.9

    return {
        "requires_clarification": False,
        "intent": "scale_building",
        "tool_to_run": "building_scale_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "scale": {
            "scale_factor": scale_factor,
            "apply_scale": True,
        },
        "validation": {
            "check_site_boundary": True,
            "check_tree_overlap": True,
        },
        "human_friendly_explanation": (
            f"I will scale the previously generated building by a factor of {scale_factor:g} and keep the original shape memory intact."
        ),
        "handoff": {
            "mode": "automatic",
            "target": "existing_scale_tool",
        },
    }


def _build_reset_plan(user_prompt: str, shape_hint: dict[str, Any]) -> dict[str, Any]:
    fallback_shape_hint = build_shape_generation_state(user_prompt)
    if not isinstance(shape_hint, dict) or not shape_hint.get("locked_shape_type"):
        shape_hint = {**(shape_hint if isinstance(shape_hint, dict) else {}), **fallback_shape_hint}

    return {
        "requires_clarification": False,
        "intent": "reset_new_design",
        "tool_to_run": "existing_workflow",
        "run_optimizer": True,
        "run_shape_generator": True,
        "building_type": shape_hint.get("locked_shape_type") or _infer_default_shape_type(user_prompt),
        "selected_shape_type": shape_hint.get("locked_shape_type") or _infer_default_shape_type(user_prompt),
        "human_friendly_explanation": (
            "The previous shape memory will be cleared so the next generation starts a new design, not a manipulation of the old one."
        ),
        "handoff": {
            "mode": "automatic",
            "target": "existing_workflow",
            "notes": "Prompt memory will be reset before any new generation prompt is stored.",
        },
    }


def _apply_prompt_memory_to_plan(
    plan: dict[str, Any],
    user_prompt: str,
    memory_state: dict[str, Any] | None,
    shape_hint: dict[str, Any],
) -> dict[str, Any]:
    prompt_memory = build_prompt_memory_state(user_prompt, memory_state, shape_hint)

    plan["latest_user_prompt"] = prompt_memory["latest_user_prompt"]
    plan["original_shape_prompt"] = prompt_memory["original_shape_prompt"]
    plan["latest_manipulation_prompt"] = prompt_memory["latest_manipulation_prompt"]
    plan["manipulation_history"] = prompt_memory["manipulation_history"]
    plan["merged_mcp_prompt"] = prompt_memory["merged_mcp_prompt"]
    plan["intent_type"] = prompt_memory["intent_type"]
    plan["active_shape_type"] = prompt_memory["active_shape_type"]
    plan["active_manipulation_type"] = prompt_memory["active_manipulation_type"]
    plan["memory_status"] = prompt_memory["memory_status"]

    # Ensure the plan's selected shape reflects the prompt memory when present.
    # This prevents deterministic fallbacks from defaulting to an unrelated shape type
    # (for example: 'rectangle') when the memory indicates a different active shape.
    active_shape = prompt_memory.get("active_shape_type")
    if isinstance(active_shape, str) and active_shape.strip():
        resolved_shape = active_shape.strip()
        plan["selected_shape_type"] = resolved_shape
        plan["building_type"] = resolved_shape
    else:
        # keep any existing selected_shape_type in the plan, or leave as-is
        plan.setdefault("selected_shape_type", plan.get("selected_shape_type", ""))

    explanation = prompt_memory["explanation"]
    if explanation:
        plan["explanation"] = explanation
    else:
        plan["explanation"] = "The prompt memory was updated in the graph state and merged before MCP execution."

    return plan


def _normalize_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    return str(content)


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    if not lines[-1].strip().startswith("```"):
        return stripped

    return "\n".join(lines[1:-1]).strip()


def _parse_json_response(content: str) -> dict[str, Any]:
    parsed = json.loads(_strip_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("Plan Agent response must be a JSON object")
    return parsed


def _build_tool_catalog(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return "none"

    lines: list[str] = []
    for tool in tools:
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        description = str(tool.get("description", "")).strip()
        input_schema = tool.get("inputSchema", {})
        lines.append(
            f"- {name}: {description} | inputSchema={json.dumps(input_schema, ensure_ascii=True)}"
        )

    return "\n".join(lines) if lines else "none"


def _build_plan_prompt(
    user_prompt: str,
    tool_catalog_text: str,
    layout_schema: dict[str, Any],
    shape_hint: dict[str, Any],
    tree_policy: dict[str, Any],
) -> str:
    return (
        f"{PLAN_AGENT_PROMPT}\n\n"
        f"User prompt:\n{user_prompt.strip()}\n\n"
        f"Existing shape hint from the current workflow:\n{json.dumps(shape_hint, indent=2)}\n\n"
        f"Tree policy inference:\n{json.dumps(tree_policy, indent=2)}\n\n"
        f"Layout schema:\n{json.dumps(layout_schema, indent=2)}\n\n"
        f"Available tools:\n{tool_catalog_text}\n"
    )


def _fallback_plan(
    user_prompt: str,
    shape_hint: dict[str, Any],
    prompt_memory_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = user_prompt.strip()
    if not isinstance(shape_hint, dict):
        shape_hint = {}

    fallback_shape_hint = build_shape_generation_state(user_prompt)
    if not shape_hint.get("locked_shape_type"):
        shape_hint = {**shape_hint, **fallback_shape_hint}

    locked_shape_type = shape_hint.get("locked_shape_type")
    building_type = locked_shape_type or "architectural massing"
    tree_policy = _build_tree_policy(user_prompt)
    selected_shape_type = locked_shape_type or _infer_default_shape_type(user_prompt)

    is_vague = len(prompt.split()) < 4
    clarification_question = "What building type or site should I plan for?" if is_vague else ""

    plan = {
        "requires_clarification": is_vague,
        "clarification_question": clarification_question,
        "human_friendly_explanation": (
            f"I will prepare an optimization plan for {building_type} using the existing workflow, then hand it to the downstream Grasshopper and Python pipeline."
        ),
        "building_type": building_type,
        "selected_shape_type": selected_shape_type,
        "tree_policy": tree_policy,
        "optimization_targets": ["fit the site", "respect constraints", "improve spatial efficiency"],
        "constraints": ["site boundary", "existing workflow constraints", f"default tree assumption: {tree_policy['tree_count']} trees near the {tree_policy['preferred_edge'] or 'north'} edge"],
        "parameter_ranges": {
            "rotation": [0, 360],
            "offset_x": [-10, 10],
            "offset_y": [-10, 10],
        },
        "fitness_weights": {
            "fit": 0.35,
            "constraints": 0.35,
            "efficiency": 0.2,
            "open_space": 0.1,
        },
        "optimization_settings": {
            "max_iterations": 10,
            "population_size": 20,
            "mutation_rate": 0.15,
            "termination": "Use the existing downstream optimizer settings",
        },
        "grasshopper_inputs_outputs": {
            "inputs": ["site boundary", "building footprint", "rotation", "offset", "constraints"],
            "outputs": ["candidate massing", "fitness summary", "constraint report"],
        },
        "handoff": {
            "mode": "automatic",
            "target": "existing_workflow",
            "notes": "Plan stored in workflow state for the current central reasoning node to consume.",
        },
    }

    return _apply_prompt_memory_to_plan(plan, user_prompt, prompt_memory_state, shape_hint)


def generate_plan_agent_payload(
    llm: Any,
    user_prompt: str,
    tools: list[dict[str, Any]],
    layout_schema: dict[str, Any],
    memory_state: dict[str, Any] | None,
    dbg: Callable[[str], None],
) -> dict[str, Any]:
    """
    Create a structured planning payload before the existing workflow starts.
    """

    intent = _detect_user_intent(user_prompt)

    if intent == "reset_new_design":
        shape_hint = build_shape_generation_state(user_prompt)
        plan = _build_reset_plan(user_prompt, shape_hint)
        plan["shape_hint"] = shape_hint
        return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, shape_hint)

    if intent == "move_building":
        plan = _build_move_plan(user_prompt)
        return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, build_shape_generation_state(user_prompt))

    if intent == "rotate_building":
        plan = _build_rotate_plan(user_prompt)
        return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, build_shape_generation_state(user_prompt))

    if intent == "scale_building":
        plan = _build_scale_plan(user_prompt)
        return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, build_shape_generation_state(user_prompt))

    if intent == "tree_update":
        plan = _build_tree_update_plan(user_prompt)
        return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, build_shape_generation_state(user_prompt))

    if intent == "report_only":
        plan = _build_report_plan()
        existing_memory = memory_state if isinstance(memory_state, dict) else {}
        empty_history = {
            "move": "",
            "rotate": "",
            "scale": "",
            "tree_update": "",
            "general_adjustment": "",
        }
        plan["latest_user_prompt"] = user_prompt
        plan["original_shape_prompt"] = str(existing_memory.get("original_shape_prompt", "")).strip()
        plan["latest_manipulation_prompt"] = str(existing_memory.get("latest_manipulation_prompt", "")).strip()
        plan["manipulation_history"] = existing_memory.get("manipulation_history", empty_history)
        plan["merged_mcp_prompt"] = str(existing_memory.get("merged_mcp_prompt", "")).strip()
        plan["intent_type"] = str(existing_memory.get("intent_type", "generation")).strip() or "generation"
        plan["active_shape_type"] = str(existing_memory.get("active_shape_type", "")).strip()
        plan["active_manipulation_type"] = str(existing_memory.get("active_manipulation_type", "")).strip()
        plan["memory_status"] = str(existing_memory.get("memory_status", "empty")).strip() or "empty"
        plan["explanation"] = "This is a report-only request, so the stored shape memory is preserved and not overwritten."
        return plan

    shape_hint = build_shape_generation_state(user_prompt)
    tree_policy = _build_tree_policy(user_prompt)
    tool_catalog_text = _build_tool_catalog(tools)
    prompt = _build_plan_prompt(user_prompt, tool_catalog_text, layout_schema, shape_hint, tree_policy)

    dbg("[plan-agent] Requesting structured plan")
    result = llm.invoke([
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_prompt},
    ])
    content = _normalize_text(getattr(result, "content", result))

    try:
        plan = _parse_json_response(content)
    except Exception:
        dbg("[plan-agent] Falling back to deterministic plan")
        plan = _fallback_plan(user_prompt, shape_hint)

    plan.setdefault("requires_clarification", False)
    plan.setdefault("clarification_question", "")
    plan.setdefault("human_friendly_explanation", "")
    plan.setdefault("building_type", shape_hint.get("locked_shape_type") or "architectural massing")
    plan.setdefault("selected_shape_type", shape_hint.get("locked_shape_type") or _infer_default_shape_type(user_prompt))
    plan.setdefault("tree_policy", tree_policy)
    plan.setdefault("optimization_targets", [])
    plan.setdefault("constraints", [])
    plan.setdefault("parameter_ranges", {})
    plan.setdefault("fitness_weights", {})
    plan.setdefault("optimization_settings", {})
    plan.setdefault("grasshopper_inputs_outputs", {})
    plan.setdefault("handoff", {"mode": "automatic", "target": "existing_workflow", "notes": ""})
    plan["shape_hint"] = shape_hint
    plan["tree_policy"] = tree_policy if not isinstance(plan.get("tree_policy"), dict) else {**tree_policy, **plan["tree_policy"]}

    locked_shape_type = shape_hint.get("locked_shape_type")
    if isinstance(locked_shape_type, str) and locked_shape_type.strip():
        resolved_shape_type = locked_shape_type.strip().lower().replace(" ", "_")
        plan["selected_shape_type"] = resolved_shape_type
        plan["building_type"] = resolved_shape_type

    tree_policy_data = plan.get("tree_policy", {})
    if isinstance(tree_policy_data, dict):
        plan["tree_count"] = tree_policy_data.get("tree_count", 0)
        plan["tree_points"] = tree_policy_data.get("tree_points", tree_policy_data.get("inferred_tree_points", []))
        plan["tree_sizes"] = tree_policy_data.get("tree_sizes", tree_policy_data.get("inferred_tree_sizes", []))
        plan["tree_positions_provided"] = tree_policy_data.get("tree_positions_provided", False)
        plan["preferred_edge"] = tree_policy_data.get("preferred_edge", "")
        plan["placement_mode"] = tree_policy_data.get("placement_mode", "")
        plan["tree_policy"]["tree_points"] = plan["tree_points"]
        plan["tree_policy"]["tree_sizes"] = plan["tree_sizes"]

    if not isinstance(plan.get("selected_shape_type"), str) or not plan["selected_shape_type"].strip():
        plan["selected_shape_type"] = shape_hint.get("locked_shape_type") or _infer_default_shape_type(user_prompt)

    plan["intent"] = "optimize_layout"
    plan["tool_to_run"] = "existing_optimization_workflow"
    plan["run_optimizer"] = True
    plan["run_shape_generator"] = True
    return _apply_prompt_memory_to_plan(plan, user_prompt, memory_state, shape_hint)


def format_plan_agent_response(plan: dict[str, Any]) -> str:
    """
    Render the plan as a two-part user-facing response.
    """

    explanation = str(plan.get("human_friendly_explanation", "")).strip()
    intent = str(plan.get("intent", "")).strip()
    intent_type = str(plan.get("intent_type", "")).strip()
    memory_status = str(plan.get("memory_status", "")).strip()
    active_manipulation_type = str(plan.get("active_manipulation_type", "")).strip()
    memory_explanation = str(plan.get("explanation", "")).strip()
    latest_user_prompt = str(plan.get("latest_user_prompt", "")).strip()
    latest_manipulation_prompt = str(plan.get("latest_manipulation_prompt", "")).strip()
    merged_mcp_prompt = str(plan.get("merged_mcp_prompt", "")).strip()

    header_line = ""
    if intent:
        header_line = f"Intent: {intent}\n"

    memory_line = ""
    if intent_type or memory_status or active_manipulation_type:
        details: list[str] = []
        if intent_type:
            details.append(f"intent_type={intent_type}")
        if active_manipulation_type:
            details.append(f"active_manipulation_type={active_manipulation_type}")
        if memory_status:
            details.append(f"memory_status={memory_status}")
        memory_line = f"Memory: {', '.join(details)}\n"

    lock_line = ""
    selected_shape_type = str(plan.get("selected_shape_type", "")).strip()
    if intent == "optimize_layout" and selected_shape_type:
        lock_line = f"Shape lock: {selected_shape_type}\n"

    tree_line = ""
    tree_policy = plan.get("tree_policy", {})
    tree_count = tree_policy.get("tree_count") if isinstance(tree_policy, dict) else None
    if intent == "optimize_layout" and isinstance(tree_count, int) and tree_count > 0:
        tree_line = f"Tree assumption: {tree_count} trees\n"

    explanation_line = ""
    if memory_explanation:
        explanation_line = f"{memory_explanation}\n"

    prompt_lines = []
    if latest_user_prompt:
        prompt_lines.append(f"Latest user prompt: {latest_user_prompt}")
    if latest_manipulation_prompt:
        prompt_lines.append(f"Latest manipulation prompt: {latest_manipulation_prompt}")
    if merged_mcp_prompt:
        prompt_lines.append(f"Merged MCP prompt: {merged_mcp_prompt}")

    prompt_block = ""
    if prompt_lines:
        prompt_block = "Prompt Memory\n" + "\n".join(prompt_lines) + "\n"

    plan_json = json.dumps(plan, indent=2, ensure_ascii=True)
    return (
        f"PART A - Human-Friendly Planning Explanation\n"
        f"{header_line}"
        f"{memory_line}"
        f"{lock_line}"
        f"{tree_line}"
        f"{explanation_line}"
        f"{prompt_block}"
        f"{explanation}\n\n"
        f"PART B - Machine-Readable JSON Plan\n{plan_json}"
    )


def should_request_clarification(plan: dict[str, Any]) -> bool:
    value = plan.get("requires_clarification")
    return bool(value)
