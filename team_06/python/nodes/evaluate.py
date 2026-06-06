from typing import Any
import json

FIXED_CLOSING_SENTENCE = (
    "If you are happy with this layout, we can keep it. Otherwise, you can select a different candidate layout or refine the search with more information."
)
 
SYSTEM_PROMPT = (
    "You are evaluating how well a residential layout matches a household's needs. "
    "Return valid JSON with exactly this shape: "
    '{"fit_score":0,"summary":"","strengths":[],"concerns":[],"routine_analysis":""}.'
    "\nRules:\n"
    "- fit_score is an integer from 0 to 100.\n"
    "- summary is a short paragraph summarizing the overall match.\n"
    "- strengths is a list of concise positive points.\n"
    "- concerns is a list of concise mismatch or risk points.\n"
    "- routine_analysis explains how the layout may support daily life across the day based on the brief.\n"
    "- Use the structured graph and description from the brief, and use the layout JSON as the source of truth for what exists now.\n"
    "- If daylight information is present in the layout, include it in the reasoning.\n"
    "- Do not invent rooms or performance data that are not present.\n"
)


def _normalize_evaluation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "fit_score": 0,
            "summary": "Could not evaluate the layout.",
            "strengths": [],
            "concerns": ["Evaluation response could not be parsed."],
            "routine_analysis": "",
        }

    fit_score = value.get("fit_score")
    if not isinstance(fit_score, int):
        fit_score = 0

    def _string_list(field: str) -> list[str]:
        data = value.get(field)
        if not isinstance(data, list):
            return []
        return [item.strip() for item in data if isinstance(item, str) and item.strip()]

    return {
        "fit_score": max(0, min(100, fit_score)),
        "summary": value.get("summary", "").strip() if isinstance(value.get("summary"), str) else "",
        "strengths": _string_list("strengths"),
        "concerns": _string_list("concerns"),
        "routine_analysis": value.get("routine_analysis", "").strip() if isinstance(value.get("routine_analysis"), str) else "",
    }


def _format_evaluation_message(evaluation: dict[str, Any]) -> str:
    parts = []
    parts.append(f"Fit score: {evaluation['fit_score']}/100")
    if evaluation["summary"]:
        parts.append(evaluation["summary"])
    if evaluation["strengths"]:
        parts.append("Strengths: " + "; ".join(evaluation["strengths"]))
    if evaluation["concerns"]:
        parts.append("Concerns: " + "; ".join(evaluation["concerns"]))
    if evaluation["routine_analysis"]:
        parts.append("Routine: " + evaluation["routine_analysis"])
    parts.append(FIXED_CLOSING_SENTENCE)
    return "\n\n".join(parts)


def build_evaluate_node(llm: Any) -> Any:
    """Use the LLM to evaluate the current layout against the parsed brief."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {
                "clarification": "No layout available for evaluation.",
                "iteration": iteration + 1,
            }

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            topology_json = state.get("topology_graph_json_string")
            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Parsed brief JSON: {topology_json}\n"
                    f"Layout JSON: {json.dumps(layout_data)}\n"
                    "Evaluate how well the layout matches the brief, including household needs, furniture needs, room relationships, and routine through the day."
                )}
            ]
            response = llm.invoke(llm_messages)
            evaluation_summary = _normalize_evaluation(json.loads(response.content.strip()))

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