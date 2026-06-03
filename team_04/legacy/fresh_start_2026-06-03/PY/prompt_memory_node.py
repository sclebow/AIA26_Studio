from __future__ import annotations

from typing import Any, Callable

from design_state import DesignWorkflowState, build_prompt_memory_state, save_prompt_memory_state


def create_prompt_memory_node(dbg: Callable[[str], None]) -> Callable[[DesignWorkflowState], DesignWorkflowState]:
    """
    Create the prompt-memory node that keeps the original shape prompt and later manipulations together.
    """

    def prompt_memory_node(state: DesignWorkflowState, /) -> DesignWorkflowState:
        dbg("[workflow][memory] Enter node")

        # Read the current prompt from graph state and merge it with any previously saved memory.
        existing_memory: dict[str, Any] = {
            "original_shape_prompt": state.get("original_shape_prompt", ""),
            "latest_user_prompt": state.get("latest_user_prompt", state.get("user_prompt", "")),
            "latest_manipulation_prompt": state.get("latest_manipulation_prompt", ""),
            "manipulation_history": state.get("manipulation_history", {}),
            "merged_mcp_prompt": state.get("merged_mcp_prompt", ""),
            "intent_type": state.get("intent_type", "generation"),
            "active_shape_type": state.get("active_shape_type", ""),
            "active_manipulation_type": state.get("active_manipulation_type", ""),
            "memory_status": state.get("memory_status", "empty"),
            "explanation": state.get("explanation", ""),
        }

        prompt_memory = build_prompt_memory_state(
            user_prompt=state.get("user_prompt", ""),
            existing_memory=existing_memory,
            shape_hint=state.get("shape_generation", {}),
        )

        state["latest_user_prompt"] = prompt_memory["latest_user_prompt"]
        state["original_shape_prompt"] = prompt_memory["original_shape_prompt"]
        state["latest_manipulation_prompt"] = prompt_memory["latest_manipulation_prompt"]
        state["manipulation_history"] = prompt_memory["manipulation_history"]
        state["merged_mcp_prompt"] = prompt_memory["merged_mcp_prompt"]
        state["intent_type"] = prompt_memory["intent_type"]
        state["active_shape_type"] = prompt_memory["active_shape_type"]
        state["active_manipulation_type"] = prompt_memory["active_manipulation_type"]
        state["memory_status"] = prompt_memory["memory_status"]
        state["explanation"] = prompt_memory["explanation"]

        # Keep the prompt memory inside design_state so the rest of the graph can see it.
        if "design_state" not in state or not isinstance(state.get("design_state"), dict):
            state["design_state"] = {}
        state["design_state"]["prompt_memory"] = prompt_memory
        state["design_state"]["prompt_memory_json"] = prompt_memory
        state["design_state"]["original_shape_prompt"] = prompt_memory["original_shape_prompt"]
        state["design_state"]["latest_manipulation_prompt"] = prompt_memory["latest_manipulation_prompt"]
        state["design_state"]["manipulation_history"] = prompt_memory["manipulation_history"]
        state["design_state"]["merged_mcp_prompt"] = prompt_memory["merged_mcp_prompt"]
        state["design_state"]["intent_type"] = prompt_memory["intent_type"]
        state["design_state"]["active_shape_type"] = prompt_memory["active_shape_type"]
        state["design_state"]["active_manipulation_type"] = prompt_memory["active_manipulation_type"]
        state["design_state"]["memory_status"] = prompt_memory["memory_status"]
        state["design_state"]["explanation"] = prompt_memory["explanation"]

        # Persist the updated memory snapshot so the next prompt can reuse it.
        save_prompt_memory_state(prompt_memory)

        dbg(
            f"[workflow][memory] intent={prompt_memory['intent_type']} | "
            f"manipulation={prompt_memory['active_manipulation_type']} | "
            f"status={prompt_memory['memory_status']}"
        )
        return state

    return prompt_memory_node
