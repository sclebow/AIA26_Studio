from typing import Any
from tools.layout_utils import save_layout
import json
from pathlib import Path
from tools.layout_evaluator import RULES, normalize_program


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


def _call_adapt_tool(mcp_client: Any, layout_data: dict, input_layout: dict) -> dict | None:
    result = mcp_client.call_tool("adapt_layout_06", {
        "layout_json": layout_data,
        "input_layout": input_layout
    })

    if not result or (isinstance(result, str) and result.startswith("Error")):
        return None
    if isinstance(result, dict) and "error" in result:
        return None
    if not isinstance(result, dict):
        return None

    adapted = result.get("adapted_layout", layout_data)
    if not adapted:
        return None

    return adapted


def _room_counts(layout_data: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for room in layout_data.get("rooms", []):
        program = normalize_program(room.get("attributes", {}).get("program", ""))
        if not program:
            continue
        counts[program] = counts.get(program, 0) + 1
    return counts


def _validate_adapted_layout(reference_layout: dict, adapted_layout: dict) -> list[str]:
    issues: list[str] = []
    reference_counts = _room_counts(reference_layout)
    adapted_counts = _room_counts(adapted_layout)

    for program, count in reference_counts.items():
        if adapted_counts.get(program, 0) < count:
            issues.append(f"Missing room(s) after adaptation: expected at least {count} {program}, found {adapted_counts.get(program, 0)}.")

    for room in adapted_layout.get("rooms", []):
        program = normalize_program(room.get("attributes", {}).get("program", ""))
        if program not in RULES:
            continue

        geom = room.get("geometry", [])
        area = room.get("attributes", {}).get("area", 0.0)
        room_name = room.get("name", room.get("id", "room"))
        rule = RULES[program]

        if isinstance(area, (int, float)) and area > 0 and area < rule["min_area"]:
            issues.append(f"Area too small after adaptation: {room_name} is {area:.1f} m2, minimum for {program} is {rule['min_area']} m2.")

        if geom and len(geom) >= 3:
            xs = [pt[0] for pt in geom]
            ys = [pt[1] for pt in geom]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            if width > 0 and height > 0:
                min_edge = min(width, height)
                ratio = max(width / height, height / width)
                if min_edge < rule["min_edge"]:
                    issues.append(f"Room edge too small after adaptation: {room_name} has min edge {min_edge:.1f}m, minimum for {program} is {rule['min_edge']}m.")
                if ratio > rule["max_ratio"]:
                    issues.append(f"Room proportion too stretched after adaptation: {room_name} has ratio {ratio:.1f}:1, maximum for {program} is {rule['max_ratio']}:1.")

    return issues

def build_adapt_node(mcp_client: Any) -> Any:
    """Adapt layout using MCP tool adapt_layout_06."""

    def adapt(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        print("[ADAPT] layout_json_string at adapt entry:", (layout_json[:300] if isinstance(layout_json, str) else str(layout_json)))
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

            layouts_to_try: list[tuple[str | None, dict]] = []
            if candidates:
                for candidate in candidates:
                    candidate_id = candidate.get("id")
                    if not isinstance(candidate_id, str):
                        continue
                    candidate_layout = _load_layout_by_id(candidate_id, repo_root)
                    if candidate_layout:
                        layouts_to_try.append((candidate_id, candidate_layout))

            if not layouts_to_try and layout_json:
                if isinstance(layout_json, str):
                    layout_data = json.loads(layout_json)
                else:
                    layout_data = layout_json
                layouts_to_try.append((state.get("layout_id"), layout_data))

            if not layouts_to_try:
                return {
                    "adapt_result": "failed",
                    "clarification": "No layout candidate available for adaptation.",
                    "iteration": iteration + 1,
                }

            if not has_input_outline:
                current_layout_id = state.get("layout_id")
                current_layout_json = layout_json
                if not current_layout_json and layouts_to_try:
                    current_layout_id, current_layout_data = layouts_to_try[0]
                    current_layout_json = json.dumps(current_layout_data)

                return {
                    "adapt_result": "success",
                    "layout_id": current_layout_id,
                    "layout_json_string": current_layout_json,
                    "clarification": None,
                    "iteration": iteration + 1,
                }

            for candidate_id, layout_data in layouts_to_try:
                candidate_label = candidate_id or "current layout"
                attempt_logs.append(f"Trying layout {candidate_label}.")
                print(f"[ADAPT] Trying layout {candidate_label}")
                candidate_input_layout = input_layout
                if not candidate_input_layout.get("rooms"):
                    candidate_input_layout = layout_data

                adapted = _call_adapt_tool(mcp_client, layout_data, candidate_input_layout)
                if not adapted:
                    message = f"Layout {candidate_label} failed adaptation in the MCP tool."
                    attempt_logs.append(message)
                    print(f"[ADAPT] {message}")
                    continue

                validation_issues = _validate_adapted_layout(layout_data, adapted)
                if validation_issues:
                    message = f"Layout {candidate_label} failed validation: {'; '.join(validation_issues)}"
                    attempt_logs.append(message)
                    print(f"[ADAPT] {message}")
                    continue

                adapted_layout_id = _composed_adapted_layout_id(input_layout, candidate_id)

                # Stamp the workflow id onto the actual tool result before saving it.
                adapted["layoutId"] = adapted_layout_id

                edited_path = repo_root / "team_06_edited_layout.json"
                save_layout(adapted, state, edited_path)

                return {
                    "adapt_result": "success",
                    "layout_id": adapted_layout_id,
                    "layout_json_string": json.dumps(adapted),
                    "iteration": iteration + 1,
                }

            return {
                "adapt_result": "failed",
                "clarification": "\n".join(attempt_logs + ["None of the retrieved layouts could be adapted to the input boundary. You can ignore the boundary or select another layout."]),
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "adapt_result": "failed",
                "clarification": f"Adaptation failed: {str(e)}",
                "iteration": iteration + 1,
            }

    return adapt