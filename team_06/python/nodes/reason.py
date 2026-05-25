import json
from pathlib import Path

# Load new parsed prompt schema
PARSED_PROMPT_SCHEMA_PATH = Path(__file__).parent.parent / "rules" / "parsed_prompt_schema.json"
if not PARSED_PROMPT_SCHEMA_PATH.exists():
    raise FileNotFoundError(str(PARSED_PROMPT_SCHEMA_PATH.resolve()))
PARSED_PROMPT_SCHEMA = json.loads(PARSED_PROMPT_SCHEMA_PATH.read_text(encoding="utf-8"))


# Define the question list (could be loaded from a questions.json file)
QUESTION_LIST = [
    "Please describe the people living in the household (name, age, relationship, special needs if any).",
    "Do you have any pets? If so, what type and size?",
    "What are the main activities at home (e.g., work, cook, hobbies)? When do they happen and who participates?",
    "Do you have preferences for rooms (type, size, connections, usage times, or who uses them)?"
]

# Global system prompt for LLM reliability
SYSTEM_PROMPT = (
    "You are an architect assistant. "
    "Given a user's description of their household and any previous feedback, "
    "extract as much structured information as possible as a JSON object matching this schema: "
    f"{json.dumps(PARSED_PROMPT_SCHEMA)}\n"
    "Always return a JSON object with only the fields from the schema. "
    "If you find no new information, return an empty JSON object: {}. "
    "Never return plain text, numbers, or explanations.\n"
    "\n"
    "Examples:\n"
    "User input: 'I am 36, my partner 32, our child 2 years old.'\n"
    "Output: {\"households\":[{\"id\":\"me\",\"age\":36,\"relationship\":\"me\"},{\"id\":\"partner\",\"age\":32,\"relationship\":\"partner\"},{\"id\":\"child\",\"age\":2,\"relationship\":\"child\"}]}\n"
    "User input: 'We have a big dog'\n"
    "Output: {\"pets\":[{\"type\":\"dog\",\"size\":\"big\"}]}\n"
    "User input: 'no pets'\n"
    "Output: {}\n"
)

def merge_parsed_prompt(existing, new):
    """Merge new extracted info into the existing parsed prompt dict. Handles dict/list/singletons robustly. Maps 'households' to 'users'."""
    print("[DEBUG] LLM returned:", new)
    # No mapping needed, use 'households' everywhere
    for key in PARSED_PROMPT_SCHEMA:
        if key in new and new[key] is not None:
            schema_is_list = isinstance(PARSED_PROMPT_SCHEMA[key], list)
            val = new[key]
            # If schema expects a list, coerce val to list
            if schema_is_list:
                if isinstance(val, list):
                    merged = existing.get(key, []) + val
                elif isinstance(val, dict):
                    merged = existing.get(key, []) + [val]
                else:
                    merged = existing.get(key, []) + ([val] if val is not None else [])
                # Remove empty dicts or None
                merged = [v for v in merged if v and v != {}]
                existing[key] = merged
            else:
                existing[key] = val
    # No post-processing needed, use 'households' everywhere
    # Only print the updated parsed_prompt if you want a single debug output
    # print("[DEBUG] Updated parsed_prompt:", existing)
    return existing

def build_reason_node(llm):

    def reason(state: dict) -> dict:

        user_prompt = state.get("user_prompt", "")
        iteration = state.get("iteration", 0)
        # Ensure parsed_prompt is always a dict with the correct structure
        raw_parsed = state.get("parsed_prompt")
        if not isinstance(raw_parsed, dict):
            parsed_prompt = {k: [] if isinstance(v, list) else None for k, v in PARSED_PROMPT_SCHEMA.items()}
        else:
            parsed_prompt = raw_parsed
        # No need to remap or remove 'households', use as is
        question_index = state.get("question_index", 0)
        retry_count = state.get("retry_count", 0)

        # Always start from the first unanswered question (households first)
        field_order = ["households", "pets", "activities", "rooms"]

        # Early exit for trivial or non-informative prompts
        if not user_prompt or user_prompt.strip().lower() in {"chat", "", "-", "n/a", "none"}:
            for idx, field in enumerate(field_order):
                val = parsed_prompt.get(field)
                if not (isinstance(val, list) and len(val) > 0):
                    question_index = idx
                    break
            else:
                # All fields filled, finish
                return {
                    "iteration": iteration + 1,
                    "parsed_prompt": parsed_prompt,
                    "question_index": len(field_order),
                    "clarification": None,
                    "retry_count": 0,
                    "reason_result": "complete"
                }
            current_question = QUESTION_LIST[question_index]
            return {
                "iteration": iteration + 1,
                "parsed_prompt": parsed_prompt,
                "question_index": question_index,
                "clarification": current_question,
                "retry_count": retry_count + 1,
                "reason_result": "uncomplete"
            }

        for idx, field in enumerate(field_order):
            val = parsed_prompt.get(field)
            # Advance if field is a non-empty list
            if not (isinstance(val, list) and len(val) > 0):
                question_index = idx
                break
        else:
            # All fields filled, finish
            return {
                "iteration": iteration + 1,
                "parsed_prompt": parsed_prompt,
                "question_index": len(field_order),
                "clarification": None,
                "retry_count": 0
            }

        current_question = QUESTION_LIST[question_index]

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Current parsed info: {json.dumps(parsed_prompt)}\n"
                f"Current question: {current_question}\n"
                f"User input: {user_prompt}\n"
                f"If you find info for any of these fields, output them as JSON. If not, output an empty JSON.\n"
                f"Use the exact field names from the schema above. Do not use synonyms."
            )}
        ]
        try:
            response = llm.invoke(llm_messages)
            new_info = json.loads(response.content.strip())
            parsed_prompt = merge_parsed_prompt(parsed_prompt, new_info)

            # Check if the current field is now filled
            if parsed_prompt.get(field_order[question_index]):
                # Move to next question, reset retry_count
                next_index = question_index + 1
                if next_index < len(QUESTION_LIST):
                    next_question = QUESTION_LIST[next_index]
                    return {
                        "iteration": iteration + 1,
                        "parsed_prompt": parsed_prompt,
                        "question_index": next_index,
                        "clarification": next_question,
                        "retry_count": 0
                    }
                else:
                    # All questions asked, return final result
                    return {
                        "iteration": iteration + 1,
                        "parsed_prompt": parsed_prompt,
                        "question_index": next_index,
                        "clarification": None,
                        "retry_count": 0
                    }
            else:
                # If too many retries, ask for clarification
                if retry_count >= 2:
                    return {
                        "iteration": iteration + 1,
                        "parsed_prompt": parsed_prompt,
                        "question_index": question_index,
                        "clarification": f"I couldn't understand your last answer. Could you clarify or rephrase?\n{current_question}",
                        "retry_count": 0
                    }
                else:
                    # Ask the same question again, increment retry_count
                    return {
                        "iteration": iteration + 1,
                        "parsed_prompt": parsed_prompt,
                        "question_index": question_index,
                        "clarification": current_question,
                        "retry_count": retry_count + 1
                    }
        except Exception as e:
            return {
                "iteration": iteration + 1,
                "reason_result": "failed",
                "clarification_needed": f"Could not process your input: {e}",
                "retry_count": retry_count
            }
    return reason