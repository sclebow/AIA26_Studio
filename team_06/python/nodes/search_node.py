import json
from pathlib import Path
from typing import Any
import logging
from tools.graph_searcher import GraphSearcher

logger = logging.getLogger(__name__)


def _programs_from_search_payload(payload_json: str | None) -> list[str]:
    if not payload_json:
        return []

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, dict):
        return []

    rooms = payload.get("rooms")
    if not isinstance(rooms, list):
        return []

    programs: list[str] = []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        program = room.get("program")
        if isinstance(program, str) and program:
            programs.append(program)
    return programs


def _load_layout_descriptions(repo_root: Path) -> dict[str, str]:
    descriptions: dict[str, str] = {}

    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    if layouts_path.exists():
        layouts = json.loads(layouts_path.read_text(encoding="utf-8"))
        for layout in layouts:
            layout_id = layout.get("layoutId")
            description = layout.get("apartment", {}).get("attributes", {}).get("description")
            if layout_id and description:
                descriptions[layout_id] = description

    planfinder_dir = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons"
    if planfinder_dir.exists():
        for layout_file in planfinder_dir.glob("*.json"):
            try:
                layout = json.loads(layout_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            layout_id = layout.get("layoutId", layout_file.stem)
            description = layout.get("apartment", {}).get("attributes", {}).get("description")
            if layout_id and description:
                descriptions[layout_id] = description

    return descriptions


def build_search_node() -> Any:
    """Search layouts using the structured search payload from state."""
    def search(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("graph_top_k") or 4
        search_payload_json = state.get("topology_graph_json_string")
        programs = _programs_from_search_payload(search_payload_json)

        if not programs:
            logger.error("❌ No structured search payload provided")
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": "No search input found in the structured payload. Please describe the rooms you need or try again.",
                "iteration": iteration + 1
            }

        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
            descriptions = _load_layout_descriptions(repo_root)

            searcher = GraphSearcher(str(graphs_path))
            results = searcher.search_by_embedding(programs, top_k=top_k)

            planfinder_graphs_path = repo_root / "layout_inputs" / "planfinder_graphs.json"
            if planfinder_graphs_path.exists():
                pf_searcher = GraphSearcher(str(planfinder_graphs_path))
                pf_results = pf_searcher.search_by_embedding(programs, top_k=top_k)
                results = sorted(results + pf_results, key=lambda x: x[1], reverse=True)
                logger.info(f"🔍 Combined search results (sample + planfinder): {results}")
            else:
                logger.info(f"🔍 Search results: {results}")

            deduped_results: list[tuple[str, float]] = []
            seen_layout_ids: set[str] = set()
            for layout_id, score in results:
                if layout_id in seen_layout_ids:
                    continue
                seen_layout_ids.add(layout_id)
                deduped_results.append((layout_id, score))

            candidates = [
                {
                    "id": layout_id,
                    "score": round(score, 2),
                    "description": descriptions.get(layout_id, f"Layout {layout_id}"),
                }
                for layout_id, score in deduped_results[:top_k]
            ]
            logger.info(f"📌 Candidates: {candidates}")

            if not candidates:
                logger.warning("⚠️  No matching layouts found")
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No matching layout found. How would you like to proceed? (Type 'end' to exit or write a new request)",
                    "iteration": iteration + 1,
                }

            logger.info(f"✅ Found {len(candidates)} layouts")

            return {
                "search_result": "select",
                "search_results_json_string": json.dumps(candidates),
                "layout_id": candidates[0]["id"],
                "iteration": iteration + 1,
            }
        except Exception as e:
            logger.error(f"❌ Search failed: {str(e)}", exc_info=True)
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": f"Search failed: {str(e)}. How would you like to proceed?",
                "iteration": iteration + 1,
            }

    return search