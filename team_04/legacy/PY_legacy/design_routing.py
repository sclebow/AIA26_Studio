from __future__ import annotations

from typing import Any, Callable
from design_state import DesignWorkflowState


def create_route_after_central_reasoning(
    dbg: Callable[[str], None],
) -> Callable[[DesignWorkflowState], str]:
    """
    Route after central reasoning node decides the next action.
    Directs to appropriate action node based on pending_action.
    """

    def route_after_central_reasoning(state: DesignWorkflowState) -> str:
        action = state.get("pending_action", "ask_user")
        
        routing_map = {
            "suggest": "suggestion",
            "evaluate": "evaluation",
            "optimize": "optimization",
            "explain": "explanation",
            "visualize": "visualization",
            "tool": "design_tool",
            "ask_user": "user_feedback",
            "final": "finish",
        }

        target = routing_map.get(action, "user_feedback")
        dbg(f"[workflow][route] central_reason -> {target} (action={action})")
        
        return target

    return route_after_central_reasoning


def create_route_after_action_node(
    dbg: Callable[[str], None],
) -> Callable[[DesignWorkflowState], str]:
    """
    Route after an action node completes.
    Decides whether to:
    - Execute tools
    - Check constraints
    - Loop back to central reasoning
    - Finish
    """

    def route_after_action_node(state: DesignWorkflowState) -> str:
        pending_tools = state.get("pending_tool_calls", [])
        
        if pending_tools:
            dbg("[workflow][route] action -> design_tool")
            return "design_tool"
        
        # Check if we should validate constraints
        if state.get("constraint_state"):
            dbg("[workflow][route] action -> constraint_check")
            return "constraint_check"
        
        # Loop back to reasoning
        dbg("[workflow][route] action -> central_reason")
        return "central_reason"

    return route_after_action_node


def create_route_after_constraint_check(
    dbg: Callable[[str], None],
) -> Callable[[DesignWorkflowState], str]:
    """
    Route after constraint checking.
    If violations found, may need optimization.
    Otherwise, loop back to reasoning.
    """

    def route_after_constraint_check(state: DesignWorkflowState) -> str:
        violations = state.get("constraint_state", {}).get("violations", [])
        
        if violations:
            dbg("[workflow][route] constraint_check -> central_reason (violations found)")
            # Violations trigger reasoning to decide next step
            state["pending_action"] = "optimize"
        else:
            dbg("[workflow][route] constraint_check -> central_reason (no violations)")
        
        return "central_reason"

    return route_after_constraint_check


def create_route_after_tool_execution(
    dbg: Callable[[str], None],
) -> Callable[[DesignWorkflowState], str]:
    """
    Route after tool execution.
    Checks if we should continue or go back to reasoning.
    """

    def route_after_tool_execution(state: DesignWorkflowState) -> str:
        exec_count = state.get("tool_execution_count", 0)
        max_iters = state.get("max_iterations", 10)
        
        if exec_count >= max_iters:
            dbg("[workflow][route] design_tool -> finish (max iterations reached)")
            return "finish"
        
        # Route based on the action that created these tools
        action = state.get("pending_action", "suggest")
        
        routing_map = {
            "suggest": "suggestion",
            "evaluate": "evaluation",
            "optimize": "optimization",
            "explain": "explanation",
            "visualize": "visualization",
            "tool": "finish",
            "final": "finish",
        }
        
        target = routing_map.get(action, "central_reason")
        dbg(f"[workflow][route] design_tool -> {target}")
        
        return target

    return route_after_tool_execution


def create_route_after_user_feedback(
    dbg: Callable[[str], None],
) -> Callable[[DesignWorkflowState], str]:
    """
    Route after user provides feedback.
    Loops back to central reasoning with feedback context.
    """

    def route_after_user_feedback(state: DesignWorkflowState) -> str:
        dbg("[workflow][route] user_feedback -> central_reason")
        return "central_reason"

    return route_after_user_feedback
