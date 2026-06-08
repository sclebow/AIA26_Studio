from __future__ import annotations

from typing import Any, Callable
from design_state import DesignWorkflowState


def create_suggestion_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Process suggestions from the suggest action.
    Updates design state with new suggestions.
    """
    
    def suggestion_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][suggest] Processing suggestions")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            if "suggestions" not in state["design_state"]:
                state["design_state"]["suggestions"] = []
            state["design_state"]["suggestions"].append(tool_result)
            state["suggestions"].append(tool_result)
        
        dbg("[workflow][suggest] Suggestions updated")
        return state
    
    return suggestion_node


def create_evaluation_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Process evaluation results from the evaluate action.
    Updates scores and metrics in design state.
    """
    
    def evaluation_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][evaluate] Processing evaluation")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            try:
                import json
                scores = json.loads(tool_result)
                if isinstance(scores, dict):
                    state["evaluation_scores"].update(scores)
                    state["design_state"]["scores"] = scores
            except:
                state["design_state"]["evaluation"] = tool_result
        
        dbg("[workflow][evaluate] Evaluation scores updated")
        return state
    
    return evaluation_node


def create_optimization_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Process optimization results.
    Updates modified shape and design parameters.
    """
    
    def optimization_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][optimize] Processing optimization")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            state["design_state"]["modified_shape"] = tool_result
            state["optimizations_applied"].append(tool_result)
            state["design_iterations"] += 1
        
        dbg("[workflow][optimize] Optimization applied")
        return state
    
    return optimization_node


def create_explanation_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Process explanation output.
    Stores reasoning for the design.
    """
    
    def explanation_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][explain] Processing explanation")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            state["design_state"]["explanation"] = tool_result
            state["explanations"].append(tool_result)
        
        dbg("[workflow][explain] Explanation stored")
        return state
    
    return explanation_node


def create_visualization_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Process visualization output.
    Stores visual representation of current design.
    """
    
    def visualization_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][visualize] Processing visualization")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            state["design_state"]["visualization"] = tool_result
            state["visualizations"].append(tool_result)
        
        dbg("[workflow][visualize] Visualization stored")
        return state
    
    return visualization_node


def create_constraint_check_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Check design constraints.
    Updates constraint state with violations or compliance.
    """
    
    def constraint_check_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][constraints] Checking constraints")
        
        tool_result = state.get("last_tool_result", "")
        if tool_result:
            state["constraint_state"]["last_check"] = tool_result
            if "violations" not in state["constraint_state"]:
                state["constraint_state"]["violations"] = []
            
            # Parse for violations
            if "violation" in tool_result.lower() or "fail" in tool_result.lower():
                state["constraint_state"]["violations"].append(tool_result)
        
        dbg("[workflow][constraints] Constraint check complete")
        return state
    
    return constraint_check_node


def create_user_feedback_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Collect user feedback from the notebook or terminal.
    Only prompt when the workflow produced multiple candidate options.
    """
    
    def user_feedback_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][feedback] Ready for user feedback")

        generated_options = state.get("design_state", {}).get("generated_options", [])
        if not isinstance(generated_options, list) or len(generated_options) <= 1:
            dbg("[workflow][feedback] Single result, skipping prompt")
            state["pending_action"] = "final"
            return state

        locked_shape_type = _extract_locked_shape_type(state)
        display_options = _format_generated_options(generated_options, locked_shape_type)

        if display_options:
            print("\nMultiple options were generated:")
            for index, option in enumerate(display_options, start=1):
                print(f"  {index}. {option}")

        try:
            feedback = input("Enter your choice or feedback to continue the workflow: ").strip()
        except EOFError:
            dbg("[workflow][feedback] No interactive input available")
            return state

        if feedback:
            if "feedback_history" not in state or not isinstance(state.get("feedback_history"), list):
                state["feedback_history"] = []
            state["feedback_history"].append(feedback)

        state["pending_action"] = "ask_user"
        
        dbg("[workflow][feedback] Awaiting user input")
        return state
    
    return user_feedback_node


def _extract_locked_shape_type(state: DesignWorkflowState) -> str:
    shape_generation = state.get("shape_generation", {})
    if not isinstance(shape_generation, dict):
        shape_generation = {}

    planning_context = state.get("design_state", {}).get("planning_json", {})
    if not isinstance(planning_context, dict):
        planning_context = state.get("design_state", {}).get("planning", {})
    if not isinstance(planning_context, dict):
        planning_context = {}

    for candidate in (
        shape_generation.get("locked_shape_type"),
        shape_generation.get("selected_shape_type"),
        planning_context.get("selected_shape_type"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower().replace(" ", "_")
    return ""


def _format_generated_options(options: list[Any], locked_shape_type: str) -> list[str]:
    display_options: list[str] = []
    seen: set[str] = set()

    for option in options:
        label = str(option).strip()
        if not label:
            continue

        normalized_label = label
        if locked_shape_type and "(" not in label:
            normalized_label = f"{label} ({locked_shape_type})"

        if normalized_label not in seen:
            seen.add(normalized_label)
            display_options.append(normalized_label)

    return display_options
