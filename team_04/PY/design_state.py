from __future__ import annotations

import re
from typing import Any, Annotated, TypedDict


_SHAPE_TYPES = ["rectangle", "l_shape", "i_shape", "h_shape", "t_shape", "u_shape", "plus_shape"]


def _extract_shape_lock(user_prompt: str) -> str | None:
    prompt = (user_prompt or "").lower()
    aliases = {
        "l-shape": "l_shape",
        "i-shape": "i_shape",
        "h-shape": "h_shape",
        "t-shape": "t_shape",
        "u-shape": "u_shape",
        "plus-shape": "plus_shape",
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
        if re.search(rf"\b{re.escape(key)}\b", prompt):
            return value
    return None


def build_shape_generation_state(user_prompt: str) -> dict[str, Any]:
    locked_shape_type = _extract_shape_lock(user_prompt)
    return {
        "locked_shape_type": locked_shape_type,
        "allowed_shape_types": [locked_shape_type] if locked_shape_type else list(_SHAPE_TYPES),
        "allow_shape_exploration": locked_shape_type is None,
        "gene_defaults": {
            "length": 40.0,
            "width": 30.0,
            "height": 15.0,
            "rotation": 0.0,
        },
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
    feedback_history: list[str]
    
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

    return {
        "user_prompt": user_prompt,
        "feedback_history": [],
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
