import json
import re

# Global system prompt for LLM reliability
SYSTEM_PROMPT = (
    "You are an architect assistant preparing search input for layout retrieval. "
    "Return one JSON object with exactly this shape: "
    '{"latest_prompt_useful":true,"graph":{"programs":[],"access_pairs":[],"adjacency_pairs":[],"not_adjacency_pairs":[]},"household":[],"description":""}. '
    "Use only JSON, with no explanation.\n"
    "Rules:\n"
    "- Read the current graph and current description as the existing summary, then update that summary using the latest user input.\n"
    "- Return the full updated summary, not just a delta.\n"
    "- Set latest_prompt_useful to true only if the latest user input adds, corrects, or changes layout information enough to justify a new search.\n"
    "- Set latest_prompt_useful to false if the latest user input is only a greeting, acknowledgement, repetition, or otherwise does not add useful new layout information.\n"
    "- graph is the strict structured representation of spatial requirements.\n"
    "- graph.programs is a flat list with duplicates when counts matter, for example [\"bedroom\", \"bedroom\", \"kitchen\"].\n"
    "- The available room categories in the dataset are only: living, bed, bath, foyer, and extra.\n"
    "- Translate user wording into those dataset categories before filling graph.programs.\n"
    "- There are no apartments with a separate kitchen room in this dataset. Treat kitchen requests as part of the living area and preserve kitchen intent in description as furniture, open-plan use, or cooking/social preference, not as a separate room program.\n"
    "- If the user asks for entry, entrance hall, or hall, translate that to foyer.\n"
    "- If the user asks for storage, translate that to extra.\n"
    "- If the user asks for a study, office, or workspace, represent it as an additional bed in graph.programs, because the dataset does not have a separate study category.\n"
    "- If the user asks for a double bedroom, keep the room category as bed and record in description that this bedroom should be large.\n"
    "- If the user asks for a single bedroom, keep the room category as bed and record in description that this bedroom should be medium or small.\n"
    "- Use description to preserve size intent or functional reinterpretation when the dataset category is approximate.\n"
    "- graph.access_pairs contains pairs of program names that should be connected by doors.\n"
    "- graph.adjacency_pairs contains pairs of program names that should be adjacent.\n"
    "- graph.not_adjacency_pairs contains pairs of program names that should not be adjacent.\n"
    "- household is a flexible structured representation of occupants and person-specific facts.\n"
    "- household is a list of people or household members mentioned by the user. Each item must have exactly this shape: {\"name\":\"\",\"relationship\":\"\",\"info\":\"\"}.\n"
    "- Use household for names and simple person-level information such as age, role, relationship, or profession when the user gives it.\n"
    "- Keep household lightweight. If a field is unknown, return an empty string for that field instead of inventing details.\n"
    "- description is a concise natural-language summary of only the information that is not already represented in graph.\n"
    "- Give particular attention to household context excluding names, routine and daily schedule, space quality or feeling of space, and furniture or furnishing preferences.\n"
    "- Also include other non-graph facts such as pets, dislikes, work-from-home needs, cooking or social dynamics, and requested room intents that do not map directly to dataset rooms, such as office, study, workspace, or storage.\n"
    "- Keep description short and useful for search and later reasoning. Prefer a compact summary over a long explanation.\n"
    "- Do not restate room programs, room counts, adjacencies, access pairs, or separation rules in description when they are already represented in graph.\n"
    "- Do not repeat person names in description when they are already represented in household.\n"
    "- It is acceptable for description to summarize household facts in aggregate form, for example 'family of 3 with one child', 'lives alone', or 'one adult works from home'.\n"
    "- Avoid repeating the same fact in different wording.\n"
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


def _has_household_input(household: object) -> bool:
    return isinstance(household, list) and len(household) > 0


def _wants_evaluation(user_prompt: str) -> bool:
    if not isinstance(user_prompt, str):
        return False
    return any(re.search(pattern, user_prompt, flags=re.IGNORECASE) for pattern in EVALUATE_PATTERNS)


def _normalize_payload(value: object) -> dict:
    if not isinstance(value, dict):
        return {
            "latest_prompt_useful": False,
            "graph": _empty_graph(),
            "household": [],
            "description": "",
        }

    household_raw = value.get("household") if isinstance(value.get("household"), list) else []
    household: list[dict[str, str]] = []
    for member in household_raw:
        if not isinstance(member, dict):
            continue
        name = member.get("name", "") if isinstance(member.get("name"), str) else ""
        relationship = member.get("relationship", "") if isinstance(member.get("relationship"), str) else ""
        info = member.get("info", "") if isinstance(member.get("info"), str) else ""
        name = name.strip()
        relationship = relationship.strip()
        info = info.strip()
        if not name and not relationship and not info:
            continue
        household.append({
            "name": name,
            "relationship": relationship,
            "info": info,
        })

    return {
        "latest_prompt_useful": bool(value.get("latest_prompt_useful")),
        "graph": _normalize_graph(value.get("graph")),
        "household": household,
        "description": value.get("description", "").strip() if isinstance(value.get("description"), str) else "",
    }


def _apply_dataset_program_rules(user_prompt: str, payload: dict) -> dict:
    if not isinstance(user_prompt, str) or not isinstance(payload, dict):
        return payload

    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else _empty_graph()
    programs = list(graph.get("programs", [])) if isinstance(graph.get("programs"), list) else []
    description = payload.get("description", "") if isinstance(payload.get("description"), str) else ""
    prompt_lower = user_prompt.lower()

    mentions_study_alias = any(term in prompt_lower for term in ["study", "office", "workspace"])
    mentions_plural_bedrooms = bool(re.search(r"\b(two|2|three|3|multiple|another)\s+bed(room)?s?\b", prompt_lower)) or "bedrooms" in prompt_lower

    singular_double_bedroom = bool(re.search(r"\b(a|one)?\s*double bedroom\b", prompt_lower)) and "double bedrooms" not in prompt_lower
    singular_single_bedroom = bool(re.search(r"\b(a|one)?\s*single bedroom\b", prompt_lower)) and "single bedrooms" not in prompt_lower

    if (singular_double_bedroom or singular_single_bedroom) and not mentions_plural_bedrooms and not mentions_study_alias:
        bed_count = sum(1 for program in programs if program == "bed")
        if bed_count > 1:
            seen_bed = 0
            collapsed_programs: list[str] = []
            for program in programs:
                if program != "bed":
                    collapsed_programs.append(program)
                    continue
                seen_bed += 1
                if seen_bed == 1:
                    collapsed_programs.append(program)
            programs = collapsed_programs

    description_notes: list[str] = []
    if singular_double_bedroom and "large bedroom" not in description.lower():
        description_notes.append("large bedroom preferred")
    if singular_single_bedroom and not any(note in description.lower() for note in ["small bedroom", "medium bedroom"]):
        description_notes.append("medium or small bedroom preferred")

    if description_notes:
        description = "; ".join([text for text in [description.strip(), *description_notes] if text])

    return {
        **payload,
        "graph": {
            **graph,
            "programs": programs,
        },
        "description": description,
    }


def _greeting(household: list[dict]) -> str:
    names = [m.get("name", "").strip() for m in household if isinstance(m, dict) and m.get("name", "").strip()]
    if not names:
        return "Hi"
    if len(names) == 1:
        return f"Hi {names[0]}"
    return "Hi " + ", ".join(names[:-1]) + f" and {names[-1]}"


def _clarification_for_state(graph: dict, description: str, latest_prompt_useful: bool, household: list[dict]) -> str:
    greeting = _greeting(household)
    if not graph.get("programs") and not description.strip():
        return f"{greeting}, I am here to help you find the right layout. Could you describe the apartment you are looking for — rooms, connections, or lifestyle preferences?"
    if not graph.get("programs"):
        return "I did not get any room requirements. Could you tell me which rooms you need?"
    return "I need a bit more detail. Could you add room connections, household info, or other preferences?"


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
        existing_household = payload.get("household") if isinstance(payload.get("household"), list) else []
        existing_description = payload.get("description", "") if isinstance(payload.get("description"), str) else ""
        feedback_history = state.get("feedback_history", [])

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Current graph: {json.dumps(existing_graph)}\n"
                f"Current household: {json.dumps(existing_household)}\n"
                f"Current description: {json.dumps(existing_description)}\n"
                f"Feedback history: {json.dumps(feedback_history)}\n"
                f"User input: {user_prompt}\n"
                "Return the full updated search summary. Keep graph fields only for information that fits the graph structure. "
                "Keep people in household. Put all remaining non-graph information in description, including aggregate household facts without names. Do not summarize the graph again in prose."
            )}
        ]
        try:
            response = llm.invoke(llm_messages)
            response_json = json.loads(response.content.strip())
            # The LLM is constrained by the decision schema and wraps its answer
            # inside final_response as a string — unwrap it when that happens.
            if "final_response" in response_json and "latest_prompt_useful" not in response_json:
                response_json = json.loads(response_json["final_response"])
            parsed_payload = _normalize_payload(response_json)
            parsed_payload = _apply_dataset_program_rules(user_prompt, parsed_payload)
            latest_prompt_useful = parsed_payload["latest_prompt_useful"]
            updated_search_payload = {
                "graph": parsed_payload["graph"],
                "household": parsed_payload["household"],
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
                "household": existing_household,
                "description": existing_description,
            }

            if wants_evaluation and (_has_search_input(existing_graph, existing_description) or _has_household_input(existing_household)):
                return {
                    "iteration": iteration + 1,
                    "topology_graph_json_string": json.dumps(current_search_payload),
                    "clarification": None,
                    "reason_result": "evaluate",
                }

            if _has_household_input(parsed_payload["household"]):
                updated_household_payload = {
                    "graph": existing_graph,
                    "household": parsed_payload["household"],
                    "description": existing_description,
                }

                clarification = _clarification_for_state(
                    updated_household_payload["graph"],
                    updated_household_payload["description"],
                    latest_prompt_useful,
                    parsed_payload["household"],
                )

                return {
                    "iteration": iteration + 1,
                    "topology_graph_json_string": json.dumps(updated_household_payload),
                    "reason_result": "feedback",
                    "clarification": clarification,
                }

            clarification = _clarification_for_state(
                current_search_payload["graph"],
                current_search_payload["description"],
                latest_prompt_useful,
                parsed_payload["household"],
            )

            if wants_evaluation and not (_has_search_input(existing_graph, existing_description) or _has_household_input(existing_household)):
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