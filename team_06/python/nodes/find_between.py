from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_layout_by_id(layout_id: str) -> dict[str, Any] | None:
    path = _REPO_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_find_between_node() -> Any:
    def find_between(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("graph_top_k") or 4

        try:
            payload = json.loads(state.get("topology_graph_json_string") or "{}")
        except Exception:
            payload = {}

        ids = payload.get("in_between", [])
        if not isinstance(ids, list) or len(ids) < 2:
            return {
                "find_between_result": "feedback",
                "clarification": "Could not determine which layouts to search between.",
                "iteration": iteration + 1,
            }

        id_a, id_b = ids[0], ids[1]

        try:
            # Import from search to reuse the shared cached index
            from nodes.search import _get_description_index
            index = _get_description_index()
            coords = index.coords

            coord_a = coords.get(id_a)
            coord_b = coords.get(id_b)

            if not coord_a or not coord_b:
                missing = [lid for lid, c in [(id_a, coord_a), (id_b, coord_b)] if not c]
                return {
                    "find_between_result": "feedback",
                    "clarification": f"Could not find embedding coordinates for: {', '.join(missing)}.",
                    "iteration": iteration + 1,
                }

            mid_x = (coord_a["x"] + coord_b["x"]) / 2
            mid_y = (coord_a["y"] + coord_b["y"]) / 2

            # Rank all layouts by distance to midpoint, excluding the two source layouts
            exclude = {id_a, id_b}
            distances = sorted(
                (
                    (lid, ((c["x"] - mid_x) ** 2 + (c["y"] - mid_y) ** 2) ** 0.5)
                    for lid, c in coords.items()
                    if lid not in exclude
                ),
                key=lambda x: x[1],
            )

            max_dist = distances[-1][1] if distances else 1.0
            candidates = [
                {
                    "id": lid,
                    "score": round(1.0 - dist / max_dist, 6),
                    "graph_score": None,
                    "description_score": 0.0,
                }
                for lid, dist in distances[:top_k]
            ]

            top_id = candidates[0]["id"]
            embedding_map = {
                "all_coords": coords,
                "descriptions": index.descriptions,
                "query_coord": {"x": mid_x, "y": mid_y},
                "result_ids": [c["id"] for c in candidates],
            }

            has_input = bool(state.get("input_layout_json_string"))
            next_step = "adapt" if has_input else "select"

            result: dict[str, Any] = {
                "find_between_result": next_step,
                "layout_id": top_id,
                "search_results_json_string": json.dumps(candidates),
                "embedding_map_json_string": json.dumps(embedding_map),
                "evaluation_json_string": None,
                "routine_json_string": None,
                "iteration": iteration + 1,
            }

            if has_input:
                layout_data = _load_layout_by_id(top_id)
                if not layout_data:
                    return {
                        "find_between_result": "feedback",
                        "search_results_json_string": json.dumps(candidates),
                        "embedding_map_json_string": json.dumps(embedding_map),
                        "clarification": f"Layout {top_id} could not be loaded for adaptation.",
                        "iteration": iteration + 1,
                    }
                result["layout_json_string"] = json.dumps(layout_data)

            return result

        except Exception as e:
            return {
                "find_between_result": "feedback",
                "clarification": f"Find-between search failed: {e}",
                "iteration": iteration + 1,
            }

    return find_between
