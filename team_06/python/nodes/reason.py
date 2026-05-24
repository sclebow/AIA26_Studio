import json
from pathlib import Path

# Load dataset summary for dataset awareness
DATASET_SUMMARY_PATH = Path(__file__).parent.parent / "rules" / "dataset_summary.json"
if not DATASET_SUMMARY_PATH.exists():
    raise FileNotFoundError(str(DATASET_SUMMARY_PATH.resolve()))
DATASET_SUMMARY = json.loads(DATASET_SUMMARY_PATH.read_text(encoding="utf-8"))

# Build a minimal, dataset-aware system prompt
REASON_SYSTEM_PROMPT = (
    "You are an architect assistant. "
    "Given a user's description of their household and any previous feedback, infer the required apartment features. "
    f"Available room types: {', '.join(DATASET_SUMMARY['available_programs'])}. "
    f"Bedroom count: {DATASET_SUMMARY['bedroom_count_range']}. "
    f"Apartment size: {DATASET_SUMMARY['size_range_m2']} m2. "
    "Always output a JSON object: "
    "{\"parsed_prompt\": \"...\", \"requires_clarification\": false} "
    "If the input is too vague, set requires_clarification to true and add a 'clarification_needed' field with a suggestion. "
    "If you need more information, ask the user to describe their daily routine, who lives with them, or any special needs."
)

def build_reason_node(llm):
    def reason(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "")
        feedback_history = state.get("feedback_history", [])
        iteration = state.get("iteration", 0)

        # Combine feedback history for context
        history_str = "\n".join(f"Feedback {i+1}: {fb}" for i, fb in enumerate(feedback_history)) if feedback_history else ""
        llm_prompt = (
            f"{REASON_SYSTEM_PROMPT}\n"
            f"{'Previous feedback:\n' + history_str if history_str else ''}\n"
            f"User input: {user_prompt}\n"
            "Output:"
        )
        try:
            response = llm.invoke(llm_prompt)
            result = json.loads(response.content.strip())
            if not result.get("requires_clarification", False):
                return {
                    "iteration": iteration + 1,
                    "parsed_prompt": result.get("parsed_prompt", ""),
                    "reason_result": "success"
                }
            else:
                # Add a more engaging clarification question if not provided
                clarification = result.get(
                    "clarification_needed",
                    "Can you describe more about your daily routine, who lives with you, or any special needs for your apartment?"
                )
                return {
                    "iteration": iteration + 1,
                    "reason_result": "failed",
                    "clarification_needed": clarification
                }
        except Exception as e:
            return {
                "iteration": iteration + 1,
                "reason_result": "failed",
                "clarification_needed": f"Could not process your input: {e}"
            }
    return reason