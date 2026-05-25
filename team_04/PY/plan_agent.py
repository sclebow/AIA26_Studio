from __future__ import annotations

import json
import re
from typing import Any, Callable

from design_state import build_shape_generation_state


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

    if any(keyword in prompt for keyword in ("explain result", "generate report", "summarize optimization", "why this placement", "report", "summarize")):
        return "report_only"

    if any(keyword in prompt for keyword in ("add trees", "move trees", "shift trees", "change tree count", "change tree size", "resize trees", "tree update")):
        return "tree_update"

    if any(keyword in prompt for keyword in ("rotate", "rotation", "turn building", "turn it", "change orientation")):
        return "rotate_building"

    if (
        any(keyword in prompt for keyword in ("move", "shift", "translate"))
        and any(keyword in prompt for keyword in ("left", "right", "front", "back", "north", "south", "east", "west"))
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
    distance_text = f"{distance:g}"
    prompt = (user_prompt or "").lower()

    movement = {
        "move_left": "0",
        "move_right": "0",
        "move_front": "0",
        "move_back": "0",
        "move_north": "0",
        "move_south": "0",
        "move_east": "0",
        "move_west": "0",
        "apply_move": True,
    }

    if any(keyword in prompt for keyword in ("left", "west")):
        movement["move_left"] = distance_text
        movement["move_west"] = distance_text
    elif any(keyword in prompt for keyword in ("right", "east")):
        movement["move_right"] = distance_text
        movement["move_east"] = distance_text
    elif any(keyword in prompt for keyword in ("front", "forward", "north")):
        movement["move_front"] = distance_text
        movement["move_north"] = distance_text
    elif any(keyword in prompt for keyword in ("back", "backward", "south")):
        movement["move_back"] = distance_text
        movement["move_south"] = distance_text

    return {
        "requires_clarification": False,
        "intent": "move_building",
        "tool_to_run": "building_move_tool",
        "run_optimizer": False,
        "run_shape_generator": False,
        "move_distance_meters": distance,
        "move_distance_text": distance_text,
        "movement": movement,
        "validation": {
            "check_site_boundary": True,
            "check_tree_overlap": True,
        },
        "human_friendly_explanation": (
            f"I will move the already optimized building {distance_text} meters to the left and validate it against the site boundary and tree overlap."
        ),
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


def _fallback_plan(user_prompt: str, shape_hint: dict[str, Any]) -> dict[str, Any]:
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

    return {
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


def generate_plan_agent_payload(
    llm: Any,
    user_prompt: str,
    tools: list[dict[str, Any]],
    layout_schema: dict[str, Any],
    dbg: Callable[[str], None],
) -> dict[str, Any]:
    """
    Create a structured planning payload before the existing workflow starts.
    """

    intent = _detect_user_intent(user_prompt)

    if intent == "move_building":
        return _build_move_plan(user_prompt)

    if intent == "rotate_building":
        return _build_rotate_plan(user_prompt)

    if intent == "tree_update":
        return _build_tree_update_plan(user_prompt)

    if intent == "report_only":
        return _build_report_plan()

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
    return plan


def format_plan_agent_response(plan: dict[str, Any]) -> str:
    """
    Render the plan as a two-part user-facing response.
    """

    explanation = str(plan.get("human_friendly_explanation", "")).strip()
    intent = str(plan.get("intent", "")).strip()

    header_line = ""
    if intent:
        header_line = f"Intent: {intent}\n"

    lock_line = ""
    selected_shape_type = str(plan.get("selected_shape_type", "")).strip()
    if intent == "optimize_layout" and selected_shape_type:
        lock_line = f"Shape lock: {selected_shape_type}\n"

    tree_line = ""
    tree_policy = plan.get("tree_policy", {})
    tree_count = tree_policy.get("tree_count") if isinstance(tree_policy, dict) else None
    if intent == "optimize_layout" and isinstance(tree_count, int) and tree_count > 0:
        tree_line = f"Tree assumption: {tree_count} trees\n"

    plan_json = json.dumps(plan, indent=2, ensure_ascii=True)
    return (
        f"PART A - Human-Friendly Planning Explanation\n"
        f"{header_line}"
        f"{lock_line}"
        f"{tree_line}"
        f"{explanation}\n\n"
        f"PART B - Machine-Readable JSON Plan\n{plan_json}"
    )


def should_request_clarification(plan: dict[str, Any]) -> bool:
    value = plan.get("requires_clarification")
    return bool(value)
