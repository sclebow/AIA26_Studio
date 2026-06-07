import json
import re

# Global system prompt for LLM reliability
SYSTEM_PROMPT = (
    "You are an architect assistant preparing search input for layout retrieval. "
    "Return one JSON object with exactly this shape: "
    '{"latest_prompt_useful":true,"graph":{"programs":[],"access_pairs":[],"adjacency_pairs":[],"not_adjacency_pairs":[]},"description":""}. '
    "Use only JSON, with no explanation.\n"
    "Rules:\n"
    "- Read the current graph and current description as the existing summary, then update that summary using the latest user input.\n"
    "- Return the full updated summary, not just a delta.\n"
    "- Set latest_prompt_useful to true only if the latest user input adds, corrects, or changes layout information enough to justify a new search.\n"
    "- Set latest_prompt_useful to false if the latest user input is only a greeting, acknowledgement, repetition, or otherwise does not add useful new layout information.\n"
    "- graph.programs is a flat list with duplicates when counts matter, for example [\"bedroom\", \"bedroom\", \"kitchen\"].\n"
    "- graph.access_pairs contains pairs of program names that should be connected by doors.\n"
    "- graph.adjacency_pairs contains pairs of program names that should be adjacent.\n"
    "- graph.not_adjacency_pairs contains pairs of program names that should not be adjacent.\n"
    "- For now, description is only for household information, furniture or furnishing preferences, and other non-graph constraints that do not fit the graph fields.\n"
    "- Do not restate room programs, room counts, or room relationships in description when they are already represented in graph.\n"
    "- If no summary exists yet, build it from the latest user input.\n"
    "- Do not invent missing information.\n"
)

EVALUATE_PATTERNS = [
    r"\bevaluate\b",
    r"\bevaluation\b",
    r"\bfeedback\b",
    r"\bassess\b",
    r"\bassessment\b",
    r"\breview\b",
    r"\bscore\b",
    r"\bsummar(?:ize|ise)\b.*\b(issue|issues|problem|problems)\b",
]


def _empty_graph() -> dict:
    return {
        "programs": [],
        "access_pairs": [],
        "adjacency_pairs": [],
        "not_adjacency_pairs": [],
    }


def _normalize_pair_list(value: object) -> list[list[str]]:
    if not isinstance(value, list):
        return []

    pairs: list[list[str]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        left, right = item
        if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
            pairs.append([left.strip().lower(), right.strip().lower()])
    return pairs


def _normalize_graph(value: object) -> dict:
    if not isinstance(value, dict):
        return _empty_graph()

    programs = value.get("programs") if isinstance(value.get("programs"), list) else []
    normalized_programs = [program.strip().lower() for program in programs if isinstance(program, str) and program.strip()]

    return {
        "programs": normalized_programs,
        "access_pairs": _normalize_pair_list(value.get("access_pairs")),
        "adjacency_pairs": _normalize_pair_list(value.get("adjacency_pairs")),
        "not_adjacency_pairs": _normalize_pair_list(value.get("not_adjacency_pairs")),
    }


def _has_search_input(graph: dict, description: str) -> bool:
    return any(graph.get(key) for key in graph) or bool(description.strip())


def _wants_evaluation(user_prompt: str) -> bool:
    if not isinstance(user_prompt, str):
        return False
    return any(re.search(pattern, user_prompt, flags=re.IGNORECASE) for pattern in EVALUATE_PATTERNS)


def _normalize_payload(value: object) -> dict:
    if not isinstance(value, dict):
        return {
            "latest_prompt_useful": False,
            "graph": _empty_graph(),
            "description": "",
        }

    return {
        "latest_prompt_useful": bool(value.get("latest_prompt_useful")),
        "graph": _normalize_graph(value.get("graph")),
        "description": value.get("description", "").strip() if isinstance(value.get("description"), str) else "",
    }


def _extract_household_names(user_prompt: str) -> list[str]:
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        return []

    patterns = [
        r"\bwe are\s+([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)*)",
        r"\bi am\s+([A-Z][a-z]+)",
        r"\bthis is\s+([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, user_prompt, flags=re.IGNORECASE)
        if not match:
            continue
        raw_names = match.group(1).strip()
        parts = [part.strip() for part in re.split(r"\s+(?:and|&)\s+", raw_names) if part.strip()]
        cleaned_names = []
        for part in parts:
            words = [word.capitalize() for word in part.split() if word]
            if words:
                cleaned_names.append(" ".join(words))
        if cleaned_names:
            return cleaned_names

    return []


def _personalized_intro(user_prompt: str) -> str:
    names = _extract_household_names(user_prompt)
    if not names:
        return "Hi, I am here to help you find the right layout. Can you start by describing which rooms you would like in your apartment?"

    if len(names) == 1:
        household = names[0]
    elif len(names) == 2:
        household = f"{names[0]} and {names[1]}"
    else:
        household = ", ".join(names[:-1]) + f", and {names[-1]}"

    return f"Hi {household}, I am here to help you find the right layout. Can you start by describing which rooms you would like in your apartment?"


def _clarification_for_state(graph: dict, description: str, latest_prompt_useful: bool, user_prompt: str) -> str:
    if not latest_prompt_useful:
        if not graph.get("programs") and not description.strip():
            return _personalized_intro(user_prompt)
        if not graph.get("programs"):
            return "I did not get any new room requirements. Please tell me which rooms you need."
        return "I did not get any new layout information. Please add room connections, household details, or furniture preferences."

    if not graph.get("programs") and not description.strip():
        return _personalized_intro(user_prompt)

    return "Please add a bit more detail about the rooms, household, or furniture preferences you need."


def build_reason_node(llm):
    def reason(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "")
        iteration = state.get("iteration", 0)
        wants_evaluation = _wants_evaluation(user_prompt)
        raw_payload = state.get("topology_graph_json_string")
        payload = {}
        if isinstance(raw_payload, str):
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                payload = {}
        elif isinstance(raw_payload, dict):
            payload = raw_payload

        existing_graph = _normalize_graph(payload.get("graph"))
        existing_description = payload.get("description", "") if isinstance(payload.get("description"), str) else ""
        feedback_history = state.get("feedback_history", [])

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Current graph: {json.dumps(existing_graph)}\n"
                f"Current description: {json.dumps(existing_description)}\n"
                f"Feedback history: {json.dumps(feedback_history)}\n"
                f"User input: {user_prompt}\n"
                "Return the full updated search summary. Keep graph fields only for information that fits the graph structure. "
                "Put only non-graph information in description. Do not summarize the graph again in prose."
            )}
        ]
        try:
            response = llm.invoke(llm_messages)
            parsed_payload = _normalize_payload(json.loads(response.content.strip()))
            latest_prompt_useful = parsed_payload["latest_prompt_useful"]
            updated_search_payload = {
                "graph": parsed_payload["graph"],
                "description": parsed_payload["description"],
            }

            if latest_prompt_useful:
                return {
                    "iteration": iteration + 1,
                    "topology_graph_json_string": json.dumps(updated_search_payload),
                    "clarification": None,
                    "reason_result": "evaluate" if wants_evaluation else "search",
                }

            current_search_payload = {
                "graph": existing_graph,
                "description": existing_description,
            }

            if wants_evaluation and _has_search_input(existing_graph, existing_description):
                return {
                    "iteration": iteration + 1,
                    "topology_graph_json_string": json.dumps(current_search_payload),
                    "clarification": None,
                    "reason_result": "evaluate",
                }

            clarification = _clarification_for_state(
                current_search_payload["graph"],
                current_search_payload["description"],
                latest_prompt_useful,
                user_prompt,
            )

            if wants_evaluation and not _has_search_input(existing_graph, existing_description):
                clarification = "I can evaluate the layout once I have your room requirements or household preferences. Please describe what you need first."

            return {
                "iteration": iteration + 1,
                "topology_graph_json_string": json.dumps(current_search_payload),
                "reason_result": "feedback",
                "clarification": clarification,
            }
        except Exception as e:
            return {
                "iteration": iteration + 1,
                "reason_result": "feedback",
                "clarification": f"Could not process your request for search: {e}",
            }
    return reason