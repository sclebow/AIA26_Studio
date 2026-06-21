from typing import Any
from tools.layout_utils import save_layout
import json
import re
from pathlib import Path


def _load_layout_by_id(layout_id: str, repo_root: Path) -> dict | None:
    pf_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if not pf_path.exists():
        return None
    try:
        return json.loads(pf_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_candidates(search_results_json_string: str | None) -> list[dict]:
    if not search_results_json_string:
        return []
    try:
        data = json.loads(search_results_json_string)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [candidate for candidate in data if isinstance(candidate, dict) and candidate.get("id")]


def _has_valid_outline(layout_data: dict) -> bool:
    outline = layout_data.get("outline")
    return isinstance(outline, list) and len(outline) >= 3


def _composed_adapted_layout_id(input_layout: dict, selected_layout_id: str | None) -> str:
    input_layout_id = input_layout.get("layoutId") if isinstance(input_layout.get("layoutId"), str) and input_layout.get("layoutId") else "input-layout"
    selected_layout_id = selected_layout_id or "selected-layout"
    return f"{input_layout_id}__{selected_layout_id}"


def _append_layout_candidate(layouts_to_try: list[tuple[str | None, dict]], layout_id: str | None, layout_data: dict | None) -> None:
    if not isinstance(layout_data, dict):
        return
    for existing_layout_id, _ in layouts_to_try:
        if existing_layout_id == layout_id:
            return
    layouts_to_try.append((layout_id, layout_data))


def _call_adapt_tool(mcp_client: Any, layout_data: dict, input_layout: dict) -> tuple[dict | None, str | None]:
    result = mcp_client.call_tool("adapt_layout_06", {
        "layout_json": layout_data,
        "input_layout": input_layout
    })

    if not result or (isinstance(result, str) and result.startswith("Error")):
        return None, str(result) if result else "The adaptation tool returned no result."

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return None, "The adaptation tool returned a non-JSON response."

    if isinstance(result, dict) and "error" in result:
        return None, str(result.get("error") or "The adaptation tool returned an error.")
    if not isinstance(result, dict):
        return None, "The adaptation tool returned an unexpected response."

    adapted = result.get("adapted_layout") if isinstance(result.get("adapted_layout"), dict) else result
    if not isinstance(adapted, dict) or not adapted:
        return None, "The adaptation tool did not return an adapted layout."

    return adapted, None


def build_adapt_node(mcp_client: Any) -> Any:
    """Adapt layout using MCP tool adapt_layout_06."""

    def _final_failure_message(reasons: list[str]) -> str:
        cleaned = [reason.strip() for reason in reasons if isinstance(reason, str) and reason.strip()]
        meaningful = [reason for reason in cleaned if not reason.startswith("Trying layout ")]

        if not meaningful:
            return (
                "Sorry, your request could not be satisfied within the uploaded boundary. "
                "Would you like to refine the brief, continue without the boundary, or continue with the selected layout?"
            )

        first_reason = meaningful[0]
        match = re.match(r"Layout (.+?) failed adaptation in the MCP tool: (.+)", first_reason)
        if match:
            layout_id, tool_reason = match.groups()
            base_reason = f"The selected layout {layout_id} could not fit inside the uploaded boundary."
            tool_reason = tool_reason.strip()
            if tool_reason and tool_reason.lower() not in {"unknown tool error.", "the adaptation tool returned no result."}:
                base_reason = f"{base_reason} Reason: {tool_reason}"
        else:
            base_reason = first_reason

        return (
            "Sorry, your request could not be satisfied within the uploaded boundary. "
            f"{base_reason} "
            "Would you like to refine the brief, continue without the boundary, or continue with the selected layout?"
        )

    def adapt(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        current_layout_id = state.get("layout_id")
        input_layout_json = state.get("input_layout_json_string")
        iteration = state.get("iteration", 0)

        try:
            if input_layout_json:
                if isinstance(input_layout_json, str):
                    input_layout = json.loads(input_layout_json)
                else:
                    input_layout = input_layout_json
            else:
                input_layout = {}

            has_input_outline = _has_valid_outline(input_layout)

            repo_root = Path(__file__).resolve().parent.parent.parent
            candidates = _parse_candidates(state.get("search_results_json_string"))
            attempt_logs: list[str] = []
            fallback_layout_id = current_layout_id
            fallback_layout_json = layout_json

            layouts_to_try: list[tuple[str | None, dict]] = []

            current_layout_data: dict | None = None
            if layout_json:
                if isinstance(layout_json, str):
                    current_layout_data = json.loads(layout_json)
                elif isinstance(layout_json, dict):
                    current_layout_data = layout_json

            _append_layout_candidate(layouts_to_try, current_layout_id, current_layout_data)

            if candidates:
                for candidate in candidates:
                    candidate_id = candidate.get("id")
                    if not isinstance(candidate_id, str):
                        continue
                    candidate_layout = _load_layout_by_id(candidate_id, repo_root)
                    if candidate_layout:
                        _append_layout_candidate(layouts_to_try, candidate_id, candidate_layout)
                        if fallback_layout_json is None:
                            fallback_layout_id = candidate_id
                            fallback_layout_json = json.dumps(candidate_layout)

            if fallback_layout_json is None and current_layout_data is not None:
                fallback_layout_id = current_layout_id
                fallback_layout_json = json.dumps(current_layout_data)

            if not layouts_to_try:
                return {
                    "adapt_result": "failed",
                    "clarification": _final_failure_message(["No layout candidate was available for adaptation."]),
                    "adaptation_issues": ["No layout candidate available for adaptation."],
                    "adaptation_failed": True,
                    "iteration": iteration + 1,
                }

            if not has_input_outline:
                current_layout_id = state.get("layout_id")
                current_layout_json = layout_json
                if not current_layout_json and layouts_to_try:
                    current_layout_id, current_layout_data = layouts_to_try[0]
                    current_layout_json = json.dumps(current_layout_data)

                return {
                    "adapt_result": "daylight",
                    "layout_id": current_layout_id,
                    "layout_json_string": current_layout_json,
                    "clarification": None,
                    "adaptation_issues": [],
                    "adaptation_failed": False,
                    "iteration": iteration + 1,
                }

            for candidate_id, layout_data in layouts_to_try:
                candidate_label = candidate_id or "current layout"
                attempt_logs.append(f"Trying layout {candidate_label}.")
                candidate_input_layout = input_layout if isinstance(input_layout, dict) else {}

                adapted, adapt_error = _call_adapt_tool(mcp_client, layout_data, candidate_input_layout)
                if not adapted:
                    message = f"Layout {candidate_label} failed adaptation in the MCP tool: {adapt_error or 'unknown tool error.'}"
                    attempt_logs.append(message)
                    continue

                adapted_layout_id = _composed_adapted_layout_id(input_layout, candidate_id)

                # Stamp the workflow id onto the actual tool result before saving it.
                adapted["layoutId"] = adapted_layout_id

                edited_path = repo_root / "team_06_edited_layout.json"
                save_layout(adapted, state, edited_path)

                result = {
                    "adapt_result": "daylight",
                    "layout_id": adapted_layout_id,
                    "layout_json_string": json.dumps(adapted),
                    "adaptation_issues": [],
                    "adaptation_failed": False,
                    "iteration": iteration + 1,
                }

                return result

            return {
                "adapt_result": "fallback_selected" if fallback_layout_json else "failed",
                "clarification": None if fallback_layout_json else _final_failure_message(attempt_logs),
                "adaptation_issues": attempt_logs,
                "adaptation_failed": True,
                "layout_id": fallback_layout_id,
                "layout_json_string": fallback_layout_json,
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "adapt_result": "fallback_selected" if layout_json else "failed",
                "clarification": None if layout_json else _final_failure_message([f"Adaptation failed: {str(e)}"]),
                "adaptation_issues": [f"Adaptation failed: {str(e)}"],
                "adaptation_failed": True,
                "layout_id": current_layout_id,
                "layout_json_string": layout_json,
                "iteration": iteration + 1,
            }

    return adapt