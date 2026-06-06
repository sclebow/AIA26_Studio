import json
from pathlib import Path

# Load new parsed prompt schema
PARSED_PROMPT_SCHEMA_PATH = Path(__file__).parent.parent / "rules" / "parsed_prompt_schema.json"
if not PARSED_PROMPT_SCHEMA_PATH.exists():
    raise FileNotFoundError(str(PARSED_PROMPT_SCHEMA_PATH.resolve()))
PARSED_PROMPT_SCHEMA = json.loads(PARSED_PROMPT_SCHEMA_PATH.read_text(encoding="utf-8"))

SYSTEM_PROMPT = (
    "You are an architect assistant preparing structured search input for layout retrieval. "
    "Extract as much layout-relevant information as possible from the user's request as a JSON object matching this schema: "
    f"{json.dumps(PARSED_PROMPT_SCHEMA)}\n"
    "Always return a JSON object with only the fields from the schema. "
    "If you find no new information, return an empty JSON object: {}. "
    "Never return plain text, numbers, or explanations.\n"
    "Prioritize room programs, room counts, room preferences, activities, and adjacency clues that help search layouts.\n"
    "\n"
    "Examples:\n"
    "User input: 'We need two bedrooms, one bathroom, and an open kitchen connected to the living room.'\n"
    "Output: {\"rooms\":[{\"id\":\"bedroom_1\",\"program\":\"bedroom\"},{\"id\":\"bedroom_2\",\"program\":\"bedroom\"},{\"id\":\"bathroom_1\",\"program\":\"bathroom\"},{\"id\":\"kitchen_1\",\"program\":\"kitchen\",\"connected_to\":[\"living_1\"]},{\"id\":\"living_1\",\"program\":\"living\",\"connected_to\":[\"kitchen_1\"]}]}\n"
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

def _has_searchable_rooms(parsed_prompt: dict) -> bool:
    rooms = parsed_prompt.get("rooms")
    if not isinstance(rooms, list):
        return False
    return any(isinstance(room, dict) and room.get("program") for room in rooms)


def build_reason_node(llm):
    def reason(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "")
        iteration = state.get("iteration", 0)
        raw_payload = state.get("topology_graph_json_string")
        if isinstance(raw_payload, str):
            try:
                parsed_prompt = json.loads(raw_payload)
            except json.JSONDecodeError:
                parsed_prompt = {k: [] if isinstance(v, list) else None for k, v in PARSED_PROMPT_SCHEMA.items()}
        elif isinstance(raw_payload, dict):
            parsed_prompt = raw_payload
        else:
            parsed_prompt = {k: [] if isinstance(v, list) else None for k, v in PARSED_PROMPT_SCHEMA.items()}
        feedback_history = state.get("feedback_history", [])

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Current parsed info: {json.dumps(parsed_prompt)}\n"
                f"Feedback history: {json.dumps(feedback_history)}\n"
                f"User input: {user_prompt}\n"
                "Extract structured search input. Focus on rooms, room counts, room relationships, and activities. "
                "If the request still lacks searchable room information, return an empty JSON object."
            )}
        ]
        try:
            response = llm.invoke(llm_messages)
            new_info = json.loads(response.content.strip())
            parsed_prompt = merge_parsed_prompt(parsed_prompt, new_info)

            if _has_searchable_rooms(parsed_prompt):
                return {
                    "iteration": iteration + 1,
                    "topology_graph_json_string": json.dumps(parsed_prompt),
                    "clarification": None,
                    "reason_result": "graph_search",
                }

            return {
                "iteration": iteration + 1,
                "topology_graph_json_string": json.dumps(parsed_prompt),
                "reason_result": "feedback",
                "clarification": "Please describe the rooms you need, for example: two bedrooms, one bathroom, and a kitchen connected to the living room.",
            }
        except Exception as e:
            return {
                "iteration": iteration + 1,
                "reason_result": "feedback",
                "clarification": f"Could not process your request for search: {e}",
            }
    return reason