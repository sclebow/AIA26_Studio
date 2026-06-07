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
    "- Comment on missing key programs, room sizes, and room proportions when the layout data suggests problems.\n"
    "- Distinguish between issues that came from candidate selection versus failure to fit the selected layout into the uploaded boundary.\n"
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


def _merge_selected_layout_fallback(evaluation: dict[str, Any], adaptation_failed: bool) -> dict[str, Any]:
    if not adaptation_failed:
        return evaluation

    concerns = list(evaluation.get("concerns", []))
    fallback_note = "The selected layout could not be fitted into the uploaded boundary, so this review refers to the original selected layout instead."
    if fallback_note not in concerns:
        concerns.append(fallback_note)

    summary = evaluation.get("summary", "").strip()
    if fallback_note not in summary:
        summary = f"{fallback_note} {summary}".strip()

    return {
        **evaluation,
        "summary": summary,
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

    summary = evaluation.get("summary", "").strip()
    prefix = "Daylight analysis was unavailable, so the fit score is based on the layout geometry and program only."
    if prefix not in summary:
        summary = f"{prefix} {summary}".strip()

    return {
        **evaluation,
        "summary": summary,
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
            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Parsed brief JSON: {topology_json}\n"
                    f"Layout JSON: {json.dumps(layout_data)}\n"
                    f"Adaptation failed completely: {json.dumps(adaptation_failed)}\n"
                    f"Daylight issues: {json.dumps(daylight_issues)}\n"
                    "Evaluate how well the layout matches the brief, including household needs, furniture needs, room relationships, and routine through the day."
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