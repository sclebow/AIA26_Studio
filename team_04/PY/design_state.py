from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Annotated, TypedDict


_SHAPE_TYPES = ["rectangle", "l_shape", "i_shape", "h_shape", "t_shape", "u_shape", "plus_shape"]
_MANIPULATION_TYPES = ("move", "rotate", "scale", "tree_update", "general_adjustment")

# Prompt memory is persisted on disk so the next prompt can reuse the previously generated shape.
_PROMPT_MEMORY_PATH = Path(__file__).with_name("_runtime") / "prompt_memory.json"


def _empty_manipulation_history() -> dict[str, str]:
    return {manipulation_type: "" for manipulation_type in _MANIPULATION_TYPES}


def _normalize_prompt_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _looks_like_reset_prompt(user_prompt: str) -> bool:
    prompt = (user_prompt or "").lower()
    return any(keyword in prompt for keyword in ("reset", "new design", "new_design", "start over", "clear previous", "fresh design"))


def _looks_like_generation_prompt(user_prompt: str) -> bool:
    prompt = (user_prompt or "").lower()
    return any(
        keyword in prompt
        for keyword in (
            "generate",
            "create",
            "new design",
            "new_design",
            "start a new",
            "start over",
            "fresh design",
            "build a new",
            "design a new",
            "rectangle",
            "l-shape",
            "l shape",
            "i-shape",
            "i shape",
            "h-shape",
            "h shape",
            "t-shape",
            "t shape",
            "u-shape",
            "u shape",
            "plus-shape",
            "plus shape",
        )
    )


def _looks_like_manipulation_prompt(user_prompt: str) -> bool:
    prompt = (user_prompt or "").lower()
    return any(
        keyword in prompt
        for keyword in (
            "move",
            "shift",
            "translate",
            "reposition",
            "relocate",
            "offset",
            "rotate",
            "rotation",
            "turn",
            "clockwise",
            "counterclockwise",
            "anticlockwise",
            "ccw",
            "scale",
            "resize",
            "enlarge",
            "shrink",
            "stretch",
            "bigger",
            "larger",
            "smaller",
            "increase",
            "decrease",
            "wider",
            "narrower",
            "expand",
            "contract",
            "tree update",
            "add trees",
            "move trees",
            "shift trees",
            "tree count",
            "tree size",
            "resize trees",
            "adjust",
            "adjustment",
            "edit",
            "modify",
            "tweak",
            "update",
            "revise",
            "refine",
            "change",
        )
    )


def _looks_like_report_prompt(user_prompt: str) -> bool:
    prompt = (user_prompt or "").lower()
    return any(keyword in prompt for keyword in ("report", "summarize", "summary", "explain result", "why this placement"))


def _classify_manipulation_type(user_prompt: str) -> str:
    prompt = (user_prompt or "").lower()

    if any(keyword in prompt for keyword in ("tree update", "add trees", "move trees", "shift trees", "tree count", "tree size", "resize trees", "trees")):
        return "tree_update"
    if any(keyword in prompt for keyword in ("move", "shift", "translate", "reposition", "relocate", "offset")):
        return "move"
    if any(keyword in prompt for keyword in ("rotate", "rotation", "turn", "clockwise", "counterclockwise", "anticlockwise", "ccw")):
        return "rotate"
    if any(keyword in prompt for keyword in ("scale", "resize", "enlarge", "shrink", "stretch", "bigger", "larger", "smaller", "increase", "decrease", "wider", "narrower", "expand", "contract")):
        return "scale"
    return "general_adjustment"


def _normalize_manipulation_history(history: dict[str, Any] | None) -> dict[str, str]:
    normalized = _empty_manipulation_history()
    if isinstance(history, dict):
        for key in normalized:
            value = history.get(key)
            if isinstance(value, str):
                normalized[key] = value.strip()
    return normalized


def _compose_merged_mcp_prompt(original_shape_prompt: str, manipulation_history: dict[str, str]) -> str:
    original = original_shape_prompt.strip()
    manipulations = [instruction.strip() for instruction in manipulation_history.values() if isinstance(instruction, str) and instruction.strip()]

    if not original:
        return " Then ".join(manipulations)
    if not manipulations:
        return original

    if original.endswith((".", "!", "?")):
        base_prompt = original
    else:
        base_prompt = f"{original}."

    return f"{base_prompt} Then {' Then '.join(manipulations)}"


def _normalize_prompt_memory_state(memory_state: dict[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "original_shape_prompt": "",
        "latest_user_prompt": "",
        "latest_manipulation_prompt": "",
        "manipulation_history": _empty_manipulation_history(),
        "merged_mcp_prompt": "",
        "intent_type": "generation",
        "active_shape_type": "",
        "active_manipulation_type": "",
        "memory_status": "empty",
        "explanation": "",
    }

    if isinstance(memory_state, dict):
        normalized["original_shape_prompt"] = _normalize_prompt_text(memory_state.get("original_shape_prompt"))
        normalized["latest_user_prompt"] = _normalize_prompt_text(memory_state.get("latest_user_prompt"))
        normalized["latest_manipulation_prompt"] = _normalize_prompt_text(memory_state.get("latest_manipulation_prompt"))
        normalized["manipulation_history"] = _normalize_manipulation_history(memory_state.get("manipulation_history"))
        normalized["merged_mcp_prompt"] = _normalize_prompt_text(memory_state.get("merged_mcp_prompt"))
        normalized["intent_type"] = _normalize_prompt_text(memory_state.get("intent_type")) or "generation"
        normalized["active_shape_type"] = _normalize_prompt_text(memory_state.get("active_shape_type"))
        normalized["active_manipulation_type"] = _normalize_prompt_text(memory_state.get("active_manipulation_type"))
        normalized["memory_status"] = _normalize_prompt_text(memory_state.get("memory_status")) or "empty"
        normalized["explanation"] = _normalize_prompt_text(memory_state.get("explanation"))

    if not normalized["merged_mcp_prompt"]:
        normalized["merged_mcp_prompt"] = _compose_merged_mcp_prompt(
            normalized["original_shape_prompt"],
            normalized["manipulation_history"],
        )

    return normalized


def load_prompt_memory_state() -> dict[str, Any]:
    """Load the last prompt-memory snapshot from disk."""
    try:
        raw_text = _PROMPT_MEMORY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _normalize_prompt_memory_state(None)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return _normalize_prompt_memory_state(None)

    return _normalize_prompt_memory_state(parsed if isinstance(parsed, dict) else None)


def save_prompt_memory_state(memory_state: dict[str, Any]) -> None:
    """Persist the current prompt-memory snapshot so the next run can reuse it."""
    normalized = _normalize_prompt_memory_state(memory_state)
    _PROMPT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROMPT_MEMORY_PATH.write_text(json.dumps(normalized, indent=2, ensure_ascii=True), encoding="utf-8")


def build_prompt_memory_state(
    user_prompt: str,
    existing_memory: dict[str, Any] | None = None,
    shape_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the graph prompt-memory snapshot.

    This is the shared state used to remember the original shape-generation prompt
    and merge later manipulations back into the MCP prompt.
    """
    prompt = _normalize_prompt_text(user_prompt)
    current_memory = _normalize_prompt_memory_state(existing_memory)
    current_shape_hint = shape_hint if isinstance(shape_hint, dict) else {}

    if _looks_like_report_prompt(prompt):
        # Report-only prompts read the remembered shape but do not replace it.
        current_memory["latest_user_prompt"] = prompt
        current_memory["memory_status"] = current_memory.get("memory_status", "preserved")
        current_memory["explanation"] = "This is a report-only request, so the stored shape memory is preserved and not overwritten."
        return current_memory

    has_existing_shape_memory = bool(current_memory.get("original_shape_prompt", "").strip())

    if _looks_like_reset_prompt(prompt):
        # When memory is reset we clear the stored shape and all manipulations first.
        current_memory = _normalize_prompt_memory_state(None)
        current_memory["intent_type"] = "reset/new_design"
        current_memory["memory_status"] = "reset"
        current_memory["latest_user_prompt"] = prompt

        if _looks_like_generation_prompt(prompt):
            # If the reset prompt also asks for a new shape, treat that prompt as the new shape seed.
            current_memory["original_shape_prompt"] = prompt
            current_memory["merged_mcp_prompt"] = prompt
            current_memory["active_shape_type"] = _normalize_prompt_text(current_shape_hint.get("locked_shape_type"))
            current_memory["memory_status"] = "reinitialized"
            current_memory["explanation"] = "Prompt memory was reset and a new generation prompt was stored."
        else:
            current_memory["merged_mcp_prompt"] = ""
            current_memory["explanation"] = "Prompt memory was reset before a new design request was created."
        return current_memory

    if _looks_like_generation_prompt(prompt):
        # A true generation request replaces the remembered shape.
        current_memory["original_shape_prompt"] = prompt
        current_memory["latest_user_prompt"] = prompt
        current_memory["latest_manipulation_prompt"] = ""
        current_memory["manipulation_history"] = _empty_manipulation_history()
        current_memory["merged_mcp_prompt"] = prompt
        current_memory["intent_type"] = "generation"
        current_memory["active_manipulation_type"] = ""
        current_memory["active_shape_type"] = _normalize_prompt_text(current_shape_hint.get("locked_shape_type") or current_shape_hint.get("selected_shape_type") or _extract_shape_lock(prompt))
        current_memory["memory_status"] = "reinitialized"
        current_memory["explanation"] = "This is a new shape-generation request, so the stored shape prompt was refreshed."
        return current_memory

    active_manipulation_type = _classify_manipulation_type(prompt)
    if has_existing_shape_memory or _looks_like_manipulation_prompt(prompt):
        shape_from_original_prompt = _extract_shape_lock(current_memory.get("original_shape_prompt", ""))
        if current_memory["latest_manipulation_prompt"]:
            current_memory["latest_manipulation_prompt"] = f"{current_memory['latest_manipulation_prompt']} Then {prompt}"
        else:
            current_memory["latest_manipulation_prompt"] = prompt
        current_memory["latest_user_prompt"] = prompt
        current_memory["intent_type"] = "manipulation"
        current_memory["active_manipulation_type"] = active_manipulation_type
        current_memory["memory_status"] = "preserved"

        # Keep one instruction per manipulation type so the latest move/rotate/scale/tree update replaces the previous one.
        current_memory["manipulation_history"][active_manipulation_type] = prompt
        current_memory["merged_mcp_prompt"] = _compose_merged_mcp_prompt(
            current_memory["original_shape_prompt"],
            current_memory["manipulation_history"],
        )
        current_memory["active_shape_type"] = _normalize_prompt_text(
            current_shape_hint.get("locked_shape_type")
            or current_shape_hint.get("selected_shape_type")
            or shape_from_original_prompt
            or current_memory.get("active_shape_type")
        )
        current_memory["explanation"] = (
            "This manipulation is being applied to the previously generated shape, not creating a new shape."
        )
        return current_memory

    # If we do not have a stored shape yet, keep the prompt as context but do not clear history.
    current_memory["latest_user_prompt"] = prompt
    current_memory["latest_manipulation_prompt"] = prompt if not current_memory["latest_manipulation_prompt"] else f"{current_memory['latest_manipulation_prompt']} Then {prompt}"
    current_memory["manipulation_history"]["general_adjustment"] = prompt
    current_memory["merged_mcp_prompt"] = prompt
    current_memory["intent_type"] = "manipulation"
    current_memory["active_manipulation_type"] = "general_adjustment"
    current_memory["active_shape_type"] = _normalize_prompt_text(
        current_memory.get("active_shape_type")
        or current_shape_hint.get("locked_shape_type")
        or current_shape_hint.get("selected_shape_type")
        or _extract_shape_lock(prompt)
    )
    current_memory["memory_status"] = "preserved"
    current_memory["explanation"] = "This prompt updates the existing design context instead of starting a new shape generation request."
    return current_memory


def _extract_shape_lock(user_prompt: str) -> str | None:
    prompt = re.sub(r"[-_]+", " ", (user_prompt or "").lower())
    aliases = {
        "l-shaped": "l_shape",
        "l-shape": "l_shape",
        "l shaped": "l_shape",
        "i-shaped": "i_shape",
        "i-shape": "i_shape",
        "i shaped": "i_shape",
        "h-shaped": "h_shape",
        "h-shape": "h_shape",
        "h shaped": "h_shape",
        "t-shaped": "t_shape",
        "t-shape": "t_shape",
        "t shaped": "t_shape",
        "u-shaped": "u_shape",
        "u-shape": "u_shape",
        "u shaped": "u_shape",
        "plus-shaped": "plus_shape",
        "plus-shape": "plus_shape",
        "plus shaped": "plus_shape",
        "cross shaped": "plus_shape",
        "cross-shape": "plus_shape",
        "rectangular": "rectangle",
        "rectangle": "rectangle",
        "l_shape": "l_shape",
        "i_shape": "i_shape",
        "h_shape": "h_shape",
        "t_shape": "t_shape",
        "u_shape": "u_shape",
        "plus_shape": "plus_shape",
    }
    for key, value in aliases.items():
        normalized_key = re.sub(r"[-_]+", " ", key.lower())
        if normalized_key in prompt:
            return value
    return None


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


def _calculate_wing_depth_from_area(wing_area: float, vertical_length: float = 40.0) -> float:
    """
    Calculate wing depth from wing area.
    
    For H-shape/L-shape: wing_area = wing_depth * vertical_length
    So: wing_depth = wing_area / vertical_length
    
    Clamps the result to reasonable architectural bounds (min 1.0 m, max 25.0 m).
    """
    if wing_area <= 0 or vertical_length <= 0:
        return 10.0  # default
    
    wing_depth = wing_area / vertical_length
    # Clamp to reasonable architectural bounds
    return max(1.0, min(wing_depth, 25.0))


def build_shape_generation_state(user_prompt: str) -> dict[str, Any]:
    locked_shape_type = _extract_shape_lock(user_prompt)
    
    # Parse wing/arm areas and calculate dimensions
    areas_dict = _parse_wing_areas(user_prompt)
    
    gene_defaults: dict[str, float] = {
        "length": 40.0,
        "width": 30.0,
        "height": 15.0,
        "rotation": 0.0,
    }
    
    avg_area = areas_dict.get("avg_wing_area") or areas_dict.get("avg_arm_area", 0.0)
    
    if avg_area > 0:
        # For H-shape and L-shape: calculate wing_depth from wing area
        if locked_shape_type in ("h_shape", "l_shape"):
            wing_depth = _calculate_wing_depth_from_area(avg_area, gene_defaults["length"])
            gene_defaults["wing_depth"] = wing_depth
            # For L-shape compatibility
            gene_defaults["arm_a_length"] = wing_depth
            gene_defaults["arm_b_length"] = wing_depth
        
        # For I-shape: calculate segment_width from arm area
        elif locked_shape_type == "i_shape":
            segment_width = _calculate_wing_depth_from_area(avg_area, gene_defaults["length"])
            gene_defaults["segment_width"] = segment_width
        
        # For T-shape: calculate stem_width or cap_width from arm area
        elif locked_shape_type == "t_shape":
            stem_width = _calculate_wing_depth_from_area(avg_area, gene_defaults["length"])
            gene_defaults["stem_width"] = stem_width
            gene_defaults["cap_width"] = stem_width * 2.0  # cap is wider than stem
        
        # For U-shape: calculate arm_length from arm area
        elif locked_shape_type == "u_shape":
            arm_length = _calculate_wing_depth_from_area(avg_area, gene_defaults["length"])
            gene_defaults["arm_length"] = arm_length
    
    return {
        "locked_shape_type": locked_shape_type,
        "allowed_shape_types": [locked_shape_type] if locked_shape_type else list(_SHAPE_TYPES),
        "allow_shape_exploration": locked_shape_type is None,
        "gene_defaults": gene_defaults,
        "wing_areas": areas_dict,  # Include parsed areas for reference
    }


def _merge_design_state(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge design state updates from multiple operations.
    """
    merged: dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


def _merge_constraint_state(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge constraint validation results.
    """
    merged: dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


class DesignWorkflowState(TypedDict):
    """
    The complete state for a site design optimization workflow.
    
    This tracks:
    - User input and feedback
    - Current design parameters
    - Evaluation scores
    - Constraint violations
    - Reasoning history
    - Action queue
    - Final outputs
    """

    # Input & feedback
    user_prompt: str
    latest_user_prompt: str
    feedback_history: list[str]
    original_shape_prompt: str
    latest_manipulation_prompt: str
    manipulation_history: dict[str, str]
    merged_mcp_prompt: str
    intent_type: str
    active_shape_type: str
    active_manipulation_type: str
    memory_status: str
    explanation: str
    
    # Design state (mutable, aggregated)
    design_state: Annotated[dict[str, Any], _merge_design_state]
    constraint_state: Annotated[dict[str, Any], _merge_constraint_state]
    layout_schema: dict[str, Any]
    layout_json_string: str
    shape_generation: dict[str, Any]
    
    # Current reasoning state
    pending_action: str
    pending_tool_calls: list[dict[str, Any]]
    last_reasoning: str
    next_step: str
    
    # Tool execution tracking
    last_tool_result: str | None
    tool_execution_count: int
    max_iterations: int
    
    # Output tracking
    suggestions: list[str]
    evaluation_scores: dict[str, float]
    optimizations_applied: list[str]
    explanations: list[str]
    visualizations: list[str]
    
    # Final outputs
    final_response: str | None
    design_iterations: int
    
    # Configuration
    api_key: str
    base_url: str
    llm_model: str
    timeout_seconds: float
    debug_graph: bool


class SceneState(TypedDict):
    """
    Represents the current scene/design context.
    Updated as design progresses.
    """
    
    site_dimensions: dict[str, float]
    buildings: list[dict[str, Any]]
    constraints: list[str]
    performance_metrics: dict[str, float]
    last_modified: str


def build_initial_workflow_state(
    user_prompt: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    debug_graph: bool,
    max_iterations: int,
    prompt_memory_state: dict[str, Any] | None = None,
) -> DesignWorkflowState:
    """
    Build the initial state for the design workflow.
    """
    
    import json
    from pathlib import Path

    layout_schema_path = Path(__file__).with_name("layout_schema.json")
    try:
        layout_schema = json.loads(layout_schema_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        layout_schema = {}

    shape_generation = build_shape_generation_state(user_prompt)
    prompt_memory = _normalize_prompt_memory_state(prompt_memory_state or load_prompt_memory_state())

    return {
        "user_prompt": user_prompt,
        "latest_user_prompt": user_prompt,
        "feedback_history": [],
        "original_shape_prompt": prompt_memory["original_shape_prompt"],
        "latest_manipulation_prompt": prompt_memory["latest_manipulation_prompt"],
        "manipulation_history": prompt_memory["manipulation_history"],
        "merged_mcp_prompt": prompt_memory["merged_mcp_prompt"],
        "intent_type": prompt_memory["intent_type"],
        "active_shape_type": prompt_memory["active_shape_type"],
        "active_manipulation_type": prompt_memory["active_manipulation_type"],
        "memory_status": prompt_memory["memory_status"],
        "explanation": prompt_memory["explanation"],
        "design_state": {},
        "constraint_state": {},
        "layout_schema": layout_schema,
        "layout_json_string": json.dumps(layout_schema),
        "shape_generation": shape_generation,
        "pending_action": "suggest",
        "pending_tool_calls": [],
        "last_reasoning": "",
        "next_step": "",
        "last_tool_result": None,
        "tool_execution_count": 0,
        "max_iterations": max_iterations,
        "suggestions": [],
        "evaluation_scores": {},
        "optimizations_applied": [],
        "explanations": [],
        "visualizations": [],
        "final_response": None,
        "design_iterations": 0,
        "api_key": api_key,
        "base_url": base_url,
        "llm_model": llm_model,
        "timeout_seconds": timeout_seconds,
        "debug_graph": debug_graph,
    }


def build_initial_scene_state() -> SceneState:
    """
    Build the initial scene state for the design.
    """
    
    return {
        "site_dimensions": {"width": 100, "length": 150, "area": 15000},
        "buildings": [],
        "constraints": [],
        "performance_metrics": {},
        "last_modified": "initial",
    }
