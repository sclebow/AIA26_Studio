from typing import Any
import json

def build_feedback_node() -> Any:
    """Display layout summary with daylight breakdown and ask user feedback."""
    
    def feedback(state: dict) -> dict:
        iteration = state.get("iteration", 0)

        # --- Append user feedback to feedback_history ---
        user_feedback = state.get("user_feedback")
        feedback_history = state.get("feedback_history", [])
        if user_feedback:
            feedback_history = list(feedback_history)  # ensure it's a list
            feedback_history.append(user_feedback)
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
            "clarification": None
        }

    return feedback