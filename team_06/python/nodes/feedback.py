from typing import Any
import json

def build_feedback_node() -> Any:
    """Display layout summary with daylight breakdown and ask user feedback."""
    
    def feedback(state: dict) -> dict:
        iteration = state.get("iteration", 0)

        # --- Append current user prompt to feedback_history ---
        user_prompt = state.get("user_prompt", "")
        feedback_history = state.get("feedback_history", [])
        if user_prompt and user_prompt.strip():
            feedback_history = list(feedback_history)
            feedback_history.append(user_prompt.strip())
        # ---

        clarification = state.get("clarification")
        if clarification:
            feedback_message = clarification
        else:
            feedback_message = "How would you like to proceed? (Type 'end' to exit or write a new request)"

        return {
            "final_response": feedback_message,
            "iteration": iteration + 1,
            "feedback_history": feedback_history,
            "needs_user_input": True,
            "clarification": None
        }

    return feedback