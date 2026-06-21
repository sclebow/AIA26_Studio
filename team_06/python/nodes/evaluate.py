from typing import Any
import json
from pathlib import Path
from functools import lru_cache
from tools.layout_evaluator import summarize_evaluation, compute_daylight_score, compute_room_fit_score

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Weights for computing the overall fit_score from available subscores.
# Extend this dict when new subscores come online (they are added automatically).
_SUBSCORE_WEIGHTS: dict[str, float] = {
    "room_fit": 0.55,
    "lifestyle_fit": 0.45,
}

# Slots that will become available once the backend supports them.
_FUTURE_SUBSCORES: list[tuple[str, str]] = [
    ("adjacency_fit", "Adjacency fit"),
    ("access_fit", "Access fit"),
    ("circulation", "Circulation"),
    ("shape_size", "Shape & size"),
]


@lru_cache(maxsize=1)
def _get_description_index():
    from tools.embedding_matcher import DescriptionIndex
    descriptions_dir = _REPO_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions"
    return DescriptionIndex(descriptions_dir)


def _compute_lifestyle_fit(description_query: str, layout_id: str) -> dict | None:
    if not description_query or not layout_id:
        return None
    try:
        index = _get_description_index()
        results = index.search(description_query, candidate_ids={layout_id})
        for lid, cosine in results:
            if lid == layout_id:
                # Rescale: 0.30 → 0, 0.85 → 100 (typical cosine range for layout descriptions)
                score = max(0, min(100, round((cosine - 0.30) / 0.55 * 100)))
                return {"score": score}
    except Exception:
        pass
    return None

FIXED_CLOSING_SENTENCE = (
    "If you are happy with this layout, we can keep it. Otherwise, you can select a different candidate layout or refine the search with more information."
)
 
SYSTEM_PROMPT = (
    "You are evaluating how well a residential layout matches a household's needs. "
    "Numeric scores are already computed and provided to you — your job is to write the chat summary and pills only. "
    "Return valid JSON with exactly this shape: "
    '{"chat_summary":"","strengths":[],"concerns":[]}.'
    "\nRules:\n"
    "- chat_summary is a short descriptive summary for the chat UI, usually 2 short sentences.\n"
    "- chat_summary should briefly explain what works, what does not work, and what potential the layout still has.\n"
    "- chat_summary should be consistent with the numeric scores provided — do not contradict them.\n"
    "- chat_summary should read naturally as chat text, not as tags or bullet fragments.\n"
    "- strengths is a list of short positive pill labels, maximum 2 to 4 words each.\n"
    "- concerns is a list of short negative pill labels, maximum 2 to 4 words each.\n"
    "- Pill labels must be tag-like, not sentence fragments, and must not repeat wording already used in chat_summary.\n"
    "- Example pill labels: coherent to brief, enough daylight, appropriate room size, bathroom without window.\n"
    "- Use the structured graph and description from the brief, and use the layout JSON as the source of truth for what exists now.\n"
    "- If a Planfinder layout description is provided, use it as extra context about intended use or character, but do not let it override the actual layout JSON when they differ.\n"
    "- If daylight scores are provided, include a brief mention of daylight performance in chat_summary. If not provided, do not mention it.\n"
    "- Do not add daylight to strengths or concerns — it is shown separately.\n"
    "- Treat a bathroom and a living space as baseline expected programs even if the user did not explicitly request them. Missing either should usually be a concern.\n"
    "- The dataset room categories are living, bed, bath, wc, circulation, storage, walkincloset. Interpret the layout using those categories.\n"
    "- There are no apartments with a separate kitchen room in this dataset. Interpret kitchen as furnishing or open-plan use within the living area, not as a missing or expected standalone room.\n"
    "- Treat circulation as satisfying entry, entrance hall, hallway, or corridor requests.\n"
    "- Treat storage as satisfying storage room or utility requests.\n"
    "- Treat wc as a toilet room distinct from a full bathroom (bath).\n"
    "- If the brief asked for a study, an additional bedroom may satisfy it approximately when no separate study category exists; mention the approximation when relevant.\n"
    "- If the brief asked for a double bedroom, expect the corresponding bedroom to be relatively generous in size.\n"
    "- If the brief asked for a single bedroom, a medium or small bedroom can still be appropriate.\n"
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
    }


def _load_planfinder_description(layout_id: str | None) -> str | None:
    if not isinstance(layout_id, str) or not layout_id.strip():
        return None

    repo_root = Path(__file__).resolve().parent.parent.parent
    description_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions" / f"{layout_id.strip()}.json"
    if not description_path.exists():
        return None

    try:
        payload = json.loads(description_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        return None
    return description.strip()


def _normalize_llm_output(value: object) -> dict[str, Any]:
    """Normalise the LLM response — chat_summary and pills only, no fit_score."""
    if not isinstance(value, dict):
        return {
            "chat_summary": "Evaluation unavailable.",
            "strengths": [],
            "concerns": ["Evaluation response could not be parsed."],
        }

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
            (("door", "connect", "access"), "good connectivity" if positive else "poor connectivity"),
            (("circulation",), "good circulation" if positive else "poor circulation"),
            (("daylight", "bright", "light"), "enough daylight" if positive else "low daylight"),
            (("size", "spacious", "large", "small", "tight"), "appropriate room size" if positive else "tight room size"),
            (("brief", "fit", "match"), "coherent to brief" if positive else "poor brief fit"),
            (("storage",), "storage"),
            (("circulation",), "circulation"),
            (("circulation", "entry", "hall", "foyer"), "entry space"),
            (("bathroom", "bath"), "bathroom"),
            (("living",), "living"),
            (("bedroom", "bed"), "bedroom"),
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



def _build_subscores(room_fit: dict | None, lifestyle_fit: dict | None) -> tuple[int, list[dict]]:
    """Compute fit_score from available subscores and build the subscores list."""
    available: dict[str, dict | None] = {
        "room_fit": room_fit,
        "lifestyle_fit": lifestyle_fit,
    }

    # Weighted average over whichever subscores returned a result
    total_weight = 0.0
    weighted_sum = 0.0
    for id_, weight in _SUBSCORE_WEIGHTS.items():
        s = available.get(id_)
        if s is not None and s.get("score") is not None:
            weighted_sum += s["score"] * weight
            total_weight += weight
    fit_score = round(weighted_sum / total_weight) if total_weight > 0 else 0

    def _slot(id_: str, label: str, result: dict | None) -> dict:
        if result is None:
            return {"id": id_, "label": label, "score": None, "available": False, "details": None}
        return {"id": id_, "label": label, "score": result.get("score"), "available": True, "details": result.get("details")}

    subscores = [
        _slot("room_fit", "Room fit", room_fit),
        _slot("lifestyle_fit", "Lifestyle fit", lifestyle_fit),
    ] + [_slot(id_, label, None) for id_, label in _FUTURE_SUBSCORES]

    return fit_score, subscores


def build_evaluate_node(llm: Any) -> Any:
    """Evaluate the current layout against the parsed brief."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        adaptation_failed = state.get("adaptation_failed", False)
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {
                "clarification": "No layout available for evaluation.",
                "iteration": iteration + 1,
            }

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            topology_json = state.get("topology_graph_json_string")
            layout_id = state.get("layout_id")

            # --- Deterministic subscores ---
            room_fit = compute_room_fit_score(layout_data, topology_json)
            description_query = ""
            if topology_json:
                try:
                    description_query = json.loads(topology_json).get("description", "")
                except Exception:
                    pass
            lifestyle_fit = _compute_lifestyle_fit(description_query, layout_id or "")
            fit_score, subscores = _build_subscores(room_fit, lifestyle_fit)

            # --- Daylight (optional, deterministic) ---
            daylight_evaluation = compute_daylight_score(layout_data)

            # --- Layout context for the LLM ---
            evaluation_payload = _build_layout_evaluation_payload(layout_data, topology_json)
            evaluation_payload["planfinder_description"] = _load_planfinder_description(evaluation_payload.get("layoutId"))

            score_context = (
                f"Room fit score: {room_fit['score']}/100, details: {room_fit['details']}\n" if room_fit else ""
            ) + (
                f"Lifestyle fit score: {lifestyle_fit['score']}/100\n" if lifestyle_fit else ""
            ) + (
                f"Overall fit score: {fit_score}/100\n"
            ) + (
                f"Daylight evaluation: {json.dumps(daylight_evaluation)}\n" if daylight_evaluation else "Daylight data not available.\n"
            )

            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Parsed brief JSON: {topology_json}\n"
                    f"Layout evaluation payload: {json.dumps(evaluation_payload)}\n"
                    f"Adaptation failed completely: {json.dumps(adaptation_failed)}\n"
                    f"{score_context}"
                    "Write a short chat summary and pill labels consistent with the scores above."
                )}
            ]
            response = llm.invoke(llm_messages)
            response_json = json.loads(response.content.strip())
            if "final_response" in response_json and "chat_summary" not in response_json:
                response_json = json.loads(response_json["final_response"])
            llm_output = _normalize_llm_output(response_json)
            llm_output = _merge_selected_layout_fallback(llm_output, adaptation_failed)

            evaluation_summary: dict[str, Any] = {
                "fit_score": fit_score,
                "subscores": subscores,
                **llm_output,
            }
            if daylight_evaluation is not None:
                evaluation_summary["daylight_score"] = daylight_evaluation["score"]
                evaluation_summary["daylight_rooms"] = daylight_evaluation["rooms"]

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