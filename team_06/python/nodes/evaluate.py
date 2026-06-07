from typing import Any
import json
from tools.layout_evaluator import summarize_evaluation

FIXED_CLOSING_SENTENCE = (
    "If you are happy with this layout, we can keep it. Otherwise, you can select a different candidate layout or refine the search with more information."
)
 
SYSTEM_PROMPT = (
    "You are evaluating how well a residential layout matches a household's needs. "
    "Return valid JSON with exactly this shape: "
    '{"fit_score":0,"chat_summary":"","strengths":[],"concerns":[]}.'
    "\nRules:\n"
    "- fit_score is an integer from 0 to 100.\n"
    "- chat_summary is a short descriptive summary for the chat UI, usually 2 short sentences.\n"
    "- chat_summary should briefly explain what works, what does not work, and what potential the layout still has.\n"
    "- chat_summary should read naturally as chat text, not as tags or bullet fragments.\n"
    "- strengths is a list of short positive pill labels, maximum 2 to 4 words each.\n"
    "- concerns is a list of short negative pill labels, maximum 2 to 4 words each.\n"
    "- Pill labels must be tag-like, not sentence fragments, and must not repeat wording already used in chat_summary.\n"
    "- Example pill labels: coherent to brief, enough daylight, appropriate room size, bathroom without window.\n"
    "- Use the structured graph and description from the brief, and use the layout JSON as the source of truth for what exists now.\n"
    "- If daylight information is present in the layout, include it in the reasoning.\n"
    "- Treat a bathroom and a living space as baseline expected programs even if the user did not explicitly request them. Missing either should usually be a concern.\n"
    "- The dataset room categories are living, bed, bath, foyer, and extra. Interpret the layout using those categories.\n"
    "- Treat foyer as satisfying entry, entrance hall, or hall requests.\n"
    "- Treat extra as able to cover storage or circulation support.\n"
    "- If the brief asked for a study, an additional bedroom may satisfy it approximately when no separate study category exists; mention the approximation when relevant.\n"
    "- If the brief asked for a double bedroom, expect the corresponding bedroom to be relatively generous in size.\n"
    "- If the brief asked for a single bedroom, a medium or small bedroom can still be appropriate.\n"
    "- Ignore rooms whose program or name is 'extra' unless they create a clear disadvantage such as taking space away from essential rooms. Do not count 'extra' as satisfying a missing required program.\n"
    "- A bathroom does not require natural light by default. If the user did not ask for a bathroom window or daylight, do not treat lack of bathroom daylight alone as a hard failure. If window information is available and the bathroom has no window, highlight that it may require artificial ventilation.\n"
    "- If the brief explicitly asks for a bathroom window, ventilation, or daylight, then assess bathroom daylight as a requirement.\n"
    "- Comment on missing key programs, room sizes, and room proportions when the layout data suggests problems.\n"
    "- Distinguish between issues that came from candidate selection versus failure to fit the selected layout into the uploaded boundary.\n"
    "- Do not invent rooms or performance data that are not present.\n"
    "- Keep the response concise and easy to scan.\n"
    "- Do not return any extra keys.\n"
)


def _build_layout_evaluation_payload(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    summary = summarize_evaluation(layout_data, topology_json)
    rooms = layout_data.get("rooms") if isinstance(layout_data.get("rooms"), list) else []

    compact_rooms: list[dict[str, Any]] = []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        attributes = room.get("attributes") if isinstance(room.get("attributes"), dict) else {}
        geometry = room.get("geometry") if isinstance(room.get("geometry"), list) else []
        compact_rooms.append({
            "id": room.get("id"),
            "name": room.get("name"),
            "program": attributes.get("program"),
            "area": attributes.get("area"),
            "daylight": attributes.get("daylight"),
            "vertex_count": len(geometry),
        })

    apartment = layout_data.get("apartment") if isinstance(layout_data.get("apartment"), dict) else {}
    apartment_attributes = apartment.get("attributes") if isinstance(apartment.get("attributes"), dict) else {}

    return {
        "layoutId": layout_data.get("layoutId"),
        "apartment_area": apartment_attributes.get("area"),
        "apartment_description": apartment_attributes.get("description"),
        "brief": topology_json,
        "rooms": compact_rooms,
        "rule_issues": summary.get("evaluation_issues", []) if isinstance(summary, dict) else [],
        "daylight_stats": summary.get("daylight_stats", {}) if isinstance(summary, dict) else {},
    }


def _normalize_evaluation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "fit_score": 0,
            "chat_summary": "Evaluation unavailable.",
            "strengths": [],
            "concerns": ["Evaluation response could not be parsed."],
        }

    fit_score = value.get("fit_score")
    if not isinstance(fit_score, int):
        fit_score = 0

    def _string_list(field: str) -> list[str]:
        data = value.get(field)
        if not isinstance(data, list):
            return []
        return [item.strip() for item in data if isinstance(item, str) and item.strip()]

    strengths = _string_list("strengths")
    concerns = _string_list("concerns")

    chat_summary = value.get("chat_summary")
    if not isinstance(chat_summary, str) or not chat_summary.strip():
        summary_parts = []
        if strengths:
            summary_parts.append(f"It works best for {strengths[0].lower()}.")
        if concerns:
            summary_parts.append(f"The main issue is {concerns[0].lower()}.")
        summary_parts.append("It could improve with another iteration.")
        chat_summary = " ".join(summary_parts)

    def _normalize_pill_label(text: str, positive: bool) -> str:
        value = text.lower().strip()

        ordered_rules = [
            (("bathroom without window",), "bathroom without window"),
            (("without window", "no window"), "without window"),
            (("door", "connect", "access"), "poor access" if not positive else "good access"),
            (("daylight", "bright", "light"), "enough daylight" if positive else "low daylight"),
            (("size", "spacious", "large", "small", "tight"), "appropriate room size" if positive else "tight room size"),
            (("brief", "fit", "match"), "coherent to brief" if positive else "poor brief fit"),
            (("storage",), "storage"),
            (("circulation",), "circulation"),
            (("foyer", "entry", "hall"), "entry space"),
            (("bathroom", "bath"), "bathroom"),
            (("living",), "living"),
            (("bedroom", "bed"), "bedroom"),
            (("extra",), "storage" if positive else "extra space"),
            (("ventilation",), "ventilation"),
        ]

        for tokens, label in ordered_rules:
            if any(token in value for token in tokens):
                return label

        words = [word for word in value.split() if word]
        return " ".join(words[:4]).strip()

    def _compact_pills(field: str, sentence: str) -> list[str]:
        compact_items: list[str] = []
        sentence_words = set(sentence.lower().replace(",", " ").replace(".", " ").split())
        positive = field == "strengths"

        for item in _string_list(field)[:6]:
            compact = _normalize_pill_label(item, positive)
            if not compact:
                continue

            compact = " ".join(compact.split()[:4]).strip()

            compact_words = set(compact.split())
            if compact_words and compact_words.issubset(sentence_words):
                continue

            if compact not in compact_items:
                compact_items.append(compact)

            if len(compact_items) >= 4:
                break

        return compact_items

    return {
        "fit_score": max(0, min(100, fit_score)),
        "chat_summary": chat_summary.strip(),
        "strengths": _compact_pills("strengths", chat_summary),
        "concerns": _compact_pills("concerns", chat_summary),
    }


def _format_evaluation_message(evaluation: dict[str, Any]) -> str:
    parts = []
    if evaluation.get("chat_summary"):
        parts.append(evaluation["chat_summary"])
    parts.append(FIXED_CLOSING_SENTENCE)
    return "\n\n".join(parts)


def _merge_selected_layout_fallback(evaluation: dict[str, Any], adaptation_failed: bool) -> dict[str, Any]:
    if not adaptation_failed:
        return evaluation

    concerns = list(evaluation.get("concerns", []))
    fallback_note = "The selected layout could not be fitted into the uploaded boundary, so this review refers to the original selected layout instead."
    if fallback_note not in concerns:
        concerns.append(fallback_note)

    return {
        **evaluation,
        "concerns": concerns,
    }


def _merge_daylight_issues(evaluation: dict[str, Any], daylight_issues: list[str]) -> dict[str, Any]:
    issues = [issue.strip() for issue in daylight_issues if isinstance(issue, str) and issue.strip()]
    if not issues:
        return evaluation

    concerns = list(evaluation.get("concerns", []))
    for issue in issues:
        if issue not in concerns:
            concerns.append(issue)

    return {
        **evaluation,
        "concerns": concerns,
    }


def build_evaluate_node(llm: Any) -> Any:
    """Use the LLM to evaluate the current layout against the parsed brief."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        adaptation_failed = state.get("adaptation_failed", False)
        daylight_issues = state.get("daylight_issues") or []
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {
                "clarification": "No layout available for evaluation.",
                "iteration": iteration + 1,
            }

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            topology_json = state.get("topology_graph_json_string")
            evaluation_payload = _build_layout_evaluation_payload(layout_data, topology_json)
            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Parsed brief JSON: {topology_json}\n"
                    f"Layout evaluation payload: {json.dumps(evaluation_payload)}\n"
                    f"Adaptation failed completely: {json.dumps(adaptation_failed)}\n"
                    f"Daylight issues: {json.dumps(daylight_issues)}\n"
                    "Evaluate how well the layout matches the brief. Return only the compact score, one short chat sentence, and short pros/concerns pills."
                )}
            ]
            response = llm.invoke(llm_messages)
            evaluation_summary = _normalize_evaluation(json.loads(response.content.strip()))
            evaluation_summary = _merge_selected_layout_fallback(evaluation_summary, adaptation_failed)
            evaluation_summary = _merge_daylight_issues(evaluation_summary, daylight_issues)

            return {
                "evaluation_json_string": json.dumps(evaluation_summary),
                "clarification": _format_evaluation_message(evaluation_summary),
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "clarification": f"Evaluation failed: {str(e)}",
                "iteration": iteration + 1,
            }

    return evaluate