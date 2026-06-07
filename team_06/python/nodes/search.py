import json
from pathlib import Path
from typing import Any
from tools.graph_searcher import GraphSearcher
from tools.embedding_matcher import match_layouts


def _parse_search_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json:
        return {}

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _programs_from_search_payload(payload: dict[str, Any]) -> list[str]:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload

    programs = graph_payload.get("programs")
    if not isinstance(programs, list):
        return []

    return [program.strip().lower() for program in programs if isinstance(program, str) and program.strip()]


def _pair_list_from_search_payload(payload: dict[str, Any], key: str) -> list[tuple[str, str]]:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    pair_list = graph_payload.get(key)
    if not isinstance(pair_list, list):
        return []

    pairs: list[tuple[str, str]] = []
    for item in pair_list:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        left, right = item
        if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
            pairs.append((left.strip().lower(), right.strip().lower()))
    return pairs


def _description_from_search_payload(payload: dict[str, Any]) -> str:
    description = payload.get("description")
    if isinstance(description, str):
        return description.strip()
    return ""


def _load_layout_descriptions(repo_root: Path) -> dict[str, str]:
    descriptions: dict[str, str] = {}

    descriptions_dir = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions"
    if descriptions_dir.exists():
        for description_file in descriptions_dir.glob("*.json"):
            try:
                description_payload = json.loads(description_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            layout_id = description_payload.get("layoutId", description_file.stem)
            description = description_payload.get("description")
            if layout_id and description:
                descriptions[layout_id] = description

    return descriptions


def _load_layout_by_id(layout_id: str, repo_root: Path) -> dict[str, Any] | None:
    pf_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if not pf_path.exists():
        return None

    try:
        return json.loads(pf_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_graph_search(
    programs: list[str],
    access_pairs: list[tuple[str, str]],
    adjacency_pairs: list[tuple[str, str]],
    not_adjacency_pairs: list[tuple[str, str]],
    top_k: int,
    repo_root: Path,
) -> list[tuple[str, float]]:
    # Graph embedding search: embed the requested room programs and retrieve the
    # closest layout graphs from the Planfinder graph dataset.
    planfinder_graphs_path = repo_root / "layout_inputs" / "planfinder_graphs.json"
    searcher = GraphSearcher(str(planfinder_graphs_path))
    results = searcher.search_by_embedding(
        programs,
        access_pairs=access_pairs,
        adjacency_pairs=adjacency_pairs,
        not_adjacency_pairs=not_adjacency_pairs,
        top_k=top_k,
    )
    return results


def _run_description_search(description_query: str, descriptions: dict[str, str], top_k: int) -> list[tuple[str, float]]:
    # Description embedding search: embed the human-readable query and compare
    # it against stored layout descriptions using sentence embeddings.
    if not description_query:
        return []

    description_items = [
        {"layoutId": layout_id, "description": description}
        for layout_id, description in descriptions.items()
    ]
    result = match_layouts(description_query, description_items, top_k=top_k, min_score=0.0)
    matches = result.get("matches", [])
    return [(match["layoutId"], float(match["score"])) for match in matches if match.get("layoutId")]


def _rank_map(results: list[tuple[str, float]]) -> dict[str, int]:
    return {layout_id: rank for rank, (layout_id, _score) in enumerate(results, start=1)}


def _merge_ranked_results(
    graph_results: list[tuple[str, float]],
    description_results: list[tuple[str, float]],
    descriptions: dict[str, str],
    top_k: int,
) -> list[dict[str, Any]]:
    # Merge method: reciprocal rank fusion (RRF). We merge by rank instead of
    # averaging raw scores because graph and description scores are not on the
    # same scale.
    graph_ranks = _rank_map(graph_results)
    description_ranks = _rank_map(description_results)
    combined_ids = set(graph_ranks) | set(description_ranks)

    ranked_candidates = []
    for layout_id in combined_ids:
        graph_rank = graph_ranks.get(layout_id)
        description_rank = description_ranks.get(layout_id)
        graph_score = next((score for candidate_id, score in graph_results if candidate_id == layout_id), None)
        description_score = next((score for candidate_id, score in description_results if candidate_id == layout_id), None)

        fused_score = 0.0
        if graph_rank is not None:
            fused_score += 1.0 / (60 + graph_rank)
        if description_rank is not None:
            fused_score += 1.0 / (60 + description_rank)

        ranked_candidates.append(
            {
                "id": layout_id,
                "score": round(fused_score, 6),
                "graph_score": round(graph_score, 3) if graph_score is not None else None,
                "description_score": round(description_score, 3) if description_score is not None else None,
            }
        )

    ranked_candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
    return ranked_candidates[:top_k]


def build_search_node() -> Any:
    """Search layouts using the structured search payload from state."""
    def search(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("graph_top_k") or 4
        search_payload_json = state.get("topology_graph_json_string")
        search_payload = _parse_search_payload(search_payload_json)
        programs = _programs_from_search_payload(search_payload)
        access_pairs = _pair_list_from_search_payload(search_payload, "access_pairs")
        adjacency_pairs = _pair_list_from_search_payload(search_payload, "adjacency_pairs")
        not_adjacency_pairs = _pair_list_from_search_payload(search_payload, "not_adjacency_pairs")
        description_query = _description_from_search_payload(search_payload)

        if not programs and not access_pairs and not adjacency_pairs and not not_adjacency_pairs and not description_query:
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": "No search input found in the structured payload. Please describe the rooms or layout preferences you need and try again.",
                "iteration": iteration + 1
            }

        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            descriptions = _load_layout_descriptions(repo_root)

            # 1) Graph embedding retrieval from structured room programs.
            graph_results = _run_graph_search(
                programs,
                access_pairs,
                adjacency_pairs,
                not_adjacency_pairs,
                top_k,
                repo_root,
            ) if programs else []

            # 2) Description embedding retrieval from the human-readable query.
            description_results = _run_description_search(description_query, descriptions, top_k)

            # 3) Merge both ranked lists with reciprocal rank fusion.
            candidates = _merge_ranked_results(graph_results, description_results, descriptions, top_k)

            if not candidates:
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No matching layout found. How would you like to proceed? (Type 'end' to exit or write a new request)",
                    "iteration": iteration + 1,
                }

            top_layout_id = candidates[0]["id"]
            has_input_layout = bool(state.get("input_layout_json_string"))
            next_result = "adapt" if has_input_layout else "select"

            result_state = {
                "search_result": next_result,
                "search_results_json_string": json.dumps(candidates),
                "layout_id": top_layout_id,
                "iteration": iteration + 1,
            }

            if has_input_layout:
                selected_layout = _load_layout_by_id(top_layout_id, repo_root)
                if not selected_layout:
                    return {
                        "search_result": "failed",
                        "search_results_json_string": json.dumps(candidates),
                        "clarification": f"Selected layout {top_layout_id} could not be loaded for adaptation.",
                        "iteration": iteration + 1,
                    }
                result_state["layout_json_string"] = json.dumps(selected_layout)

            return result_state
        except Exception as e:
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": f"Search failed: {str(e)}. How would you like to proceed?",
                "iteration": iteration + 1,
            }

    return search