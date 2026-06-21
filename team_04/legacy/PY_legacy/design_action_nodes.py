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

        if generated_options:
            print("\nMultiple options were generated:")
            for index, option in enumerate(generated_options, start=1):
                print(f"  {index}. {option}")

        try:
            feedback = input("Enter your choice or feedback to continue the workflow: ").strip()
        except EOFError:
            dbg("[workflow][feedback] No interactive input available")
            return state

        if feedback:
            state["feedback_history"].append(feedback)

        state["pending_action"] = "ask_user"
        
        dbg("[workflow][feedback] Awaiting user input")
        return state
    
    return user_feedback_node
