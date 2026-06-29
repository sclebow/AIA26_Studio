import json
from pathlib import Path
from typing import Any
from functools import lru_cache

# Fusion weights — adjust freely and restart the server to test.
DESCRIPTION_WEIGHT = 0.65
GRAPH_WEIGHT = 0.35

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _get_description_index():
    from tools.embedding_matcher import DescriptionIndex
    descriptions_dir = _REPO_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions"
    try:
        graph_index = _get_graph_searcher()._embedder.index
    except Exception:
        graph_index = None
    return DescriptionIndex(descriptions_dir, graph_index=graph_index)


@lru_cache(maxsize=1)
def _get_graph_searcher():
    from tools.graph_searcher import GraphSearcher
    graphs_path = _REPO_ROOT / "layout_inputs" / "planfinder_graphs.json"
    return GraphSearcher(str(graphs_path))


def _parse_search_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json:
        return {}
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _programs_from_search_payload(payload: dict[str, Any]) -> list[str]:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    programs = graph_payload.get("programs")
    if not isinstance(programs, list):
        return []
    return [p.strip().lower() for p in programs if isinstance(p, str) and p.strip()]


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


def _float_from_search_payload(payload: dict[str, Any], key: str) -> float | None:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    value = graph_payload.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _str_from_search_payload(payload: dict[str, Any], key: str) -> str | None:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    value = graph_payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _centrality_list_from_search_payload(payload: dict[str, Any]) -> list[tuple[str, str]]:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    centrality_list = graph_payload.get("centrality")
    if not isinstance(centrality_list, list):
        return []
    result = []
    for item in centrality_list:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        program, level = item
        if isinstance(program, str) and program.strip() and isinstance(level, str) and level.strip():
            result.append((program.strip().lower(), level.strip().lower()))
    return result


def _window_list_from_search_payload(payload: dict[str, Any]) -> list[tuple[str, int]]:
    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    window_list = graph_payload.get("windows")
    if not isinstance(window_list, list):
        return []
    result = []
    for item in window_list:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        program, count = item
        if isinstance(program, str) and program.strip() and isinstance(count, int):
            result.append((program.strip().lower(), count))
    return result


def _description_from_search_payload(payload: dict[str, Any]) -> str:
    description = payload.get("description")
    if isinstance(description, str):
        return description.strip()
    return ""


_PET_RELATIONSHIPS = {"dog", "cat", "puppy", "kitty", "feline", "pet", "bird", "rabbit", "hamster"}

def _infer_programs_from_household(payload: dict[str, Any]) -> list[str]:
    """When no explicit programs are given, derive a minimum room list from household size."""
    household = payload.get("household")
    if not isinstance(household, list) or not household:
        return []
    people = [
        m for m in household
        if isinstance(m, dict)
        and (m.get("relationship") or m.get("name") or "").strip().lower() not in _PET_RELATIONSHIPS
        and (m.get("relationship") or "").strip().lower() not in _PET_RELATIONSHIPS
    ]
    n = len(people)
    if n == 0:
        return []
    # Rough rule: couples share, children/twins may share → about 0.6 beds per person
    beds = max(1, round(n * 0.6))
    baths = max(1, n // 3)
    return ["bed"] * beds + ["living"] + ["bath"] * baths


def _load_layout_by_id(layout_id: str, repo_root: Path) -> dict[str, Any] | None:
    pf_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if not pf_path.exists():
        return None
    try:
        return json.loads(pf_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_search_node() -> Any:
    """Search layouts using pre-built description and graph indices.

    Fusion strategy:
      - Graph search (structural): used as hard room-count filter + soft structural score.
      - Description search (semantic): primary ranking signal.
      - Final score = DESCRIPTION_WEIGHT * desc_score + GRAPH_WEIGHT * graph_score
        (graph_score is 0.0 for layouts that had no structural constraints to score).
    """

    def search(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("graph_top_k") or 4
        search_payload_json = state.get("topology_graph_json_string")
        payload = _parse_search_payload(search_payload_json)

        programs          = _programs_from_search_payload(payload)
        if not programs:
            programs = _infer_programs_from_household(payload)
        access_pairs      = _pair_list_from_search_payload(payload, "access_pairs")
        adjacency_pairs   = _pair_list_from_search_payload(payload, "adjacency_pairs")
        not_adjacency_pairs = _pair_list_from_search_payload(payload, "not_adjacency_pairs")
        centrality        = _centrality_list_from_search_payload(payload)
        windows           = _window_list_from_search_payload(payload)
        shape             = _str_from_search_payload(payload, "shape")
        total_area        = _float_from_search_payload(payload, "total_area")
        aspect_ratio      = _float_from_search_payload(payload, "aspect_ratio")
        compactness       = _float_from_search_payload(payload, "compactness")
        description_query = _description_from_search_payload(payload)

        if not programs and not description_query:
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "embedding_map_json_string": None,
                "clarification": "No search input found. Please describe the rooms or layout preferences you need.",
                "iteration": iteration + 1,
            }

        try:
            repo_root = _REPO_ROOT
            description_index = _get_description_index()
            graph_searcher = _get_graph_searcher()

            # ------------------------------------------------------------------
            # 1) Graph pass: hard filter (room count >=) + structural score.
            #    Run with a large top_k so we get ALL valid layouts, not just top K.
            # ------------------------------------------------------------------
            graph_score_map: dict[str, float] = {}
            valid_ids: set[str] | None = None

            if programs:
                graph_results = graph_searcher.search_by_embedding(
                    programs,
                    access_pairs=access_pairs or None,
                    adjacency_pairs=adjacency_pairs or None,
                    not_adjacency_pairs=not_adjacency_pairs or None,
                    centrality=centrality or None,
                    windows=windows or None,
                    shape=shape,
                    total_area=total_area,
                    aspect_ratio=aspect_ratio,
                    compactness=compactness,
                    top_k=None,  # return all that pass hard filters
                )
                graph_score_map = {lid: score for lid, score in graph_results}
                valid_ids = set(graph_score_map.keys())

            # ------------------------------------------------------------------
            # 2) Description pass: semantic ranking, restricted to valid_ids.
            # ------------------------------------------------------------------
            desc_results: list[tuple[str, float]] = []
            query_coord: dict[str, float] | None = None

            if description_query:
                desc_results = description_index.search(
                    description_query,
                    candidate_ids=valid_ids,
                )
                # Build graph query vector so the query projects into the same
                # combined (desc+graph) space as the layout dots.
                graph_query_vec: list[float] | None = None
                if programs:
                    from utils.graph_embedder import build_query_vector
                    graph_query_vec = build_query_vector(
                        programs,
                        access_pairs=access_pairs or None,
                        adjacency_pairs=adjacency_pairs or None,
                        centrality=centrality or None,
                        windows=windows or None,
                        shape=shape,
                    )
                query_coord = description_index.project(description_query, graph_vec=graph_query_vec)
            elif valid_ids is not None:
                # No description query — rank valid layouts by graph score only.
                desc_results = [(lid, 0.0) for lid in valid_ids]

            # ------------------------------------------------------------------
            # 3) Direct score fusion.
            # ------------------------------------------------------------------
            candidates: list[dict[str, Any]] = []
            for layout_id, desc_score in desc_results:
                graph_score = graph_score_map.get(layout_id, 0.0)
                fused = DESCRIPTION_WEIGHT * desc_score + GRAPH_WEIGHT * graph_score
                candidates.append({
                    "id": layout_id,
                    "score": round(fused, 6),
                    "graph_score": round(graph_score, 3) if graph_score else None,
                    "description_score": round(desc_score, 3),
                })

            candidates.sort(key=lambda c: c["score"], reverse=True)
            candidates = candidates[:top_k]

            if not candidates:
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "embedding_map_json_string": None,
                    "clarification": "No matching layout found. How would you like to proceed?",
                    "iteration": iteration + 1,
                }

            # ------------------------------------------------------------------
            # 4) Build embedding map payload (all layout coords + query position).
            # ------------------------------------------------------------------
            result_ids = [c["id"] for c in candidates]
            embedding_map = {
                "all_coords": description_index.coords,
                "descriptions": description_index.descriptions,
                "query_coord": query_coord,
                "result_ids": result_ids,
            }

            top_layout_id = candidates[0]["id"]

            return {
                "search_result": "select",
                "search_results_json_string": json.dumps(candidates),
                "embedding_map_json_string": json.dumps(embedding_map),
                "layout_id": top_layout_id,
                "evaluation_json_string": None,
                "routine_json_string": None,
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "embedding_map_json_string": None,
                "clarification": f"Search failed: {str(e)}. How would you like to proceed?",
                "iteration": iteration + 1,
            }

    return search
