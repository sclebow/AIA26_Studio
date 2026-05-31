import json
import networkx as nx
from pathlib import Path
from typing import Any
import logging
from tools.boundary_embedding_matcher import match_boundaries as boundary_match_boundaries

logger = logging.getLogger(__name__)


def _load_layout_candidates(repo_root: Path) -> tuple[Path, Path | None]:
    sample_graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    planfinder_graphs_path = repo_root / "layout_inputs" / "planfinder_graphs.json"
    if not planfinder_graphs_path.exists():
        planfinder_graphs_path = None
    return sample_graphs_path, planfinder_graphs_path


def _build_candidate_rows(results: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [
        {
            "id": lid,
            "score": round(score, 3),
            "description": f"Layout {lid}",
        }
        for lid, score in results
    ]


def _normalize_scores(results: list[tuple[str, float]]) -> dict[str, float]:
    if not results:
        return {}
    max_score = max(score for _, score in results)
    if max_score <= 0:
        return {layout_id: 0.0 for layout_id, _ in results}
    return {layout_id: score / max_score for layout_id, score in results}


def _fuse_rankings(
    boundary_results: list[tuple[str, float]],
    graph_results: list[tuple[str, float]],
    boundary_weight: float = 0.5,
    graph_weight: float = 0.5,
) -> list[tuple[str, float]]:
    boundary_scores = _normalize_scores(boundary_results)
    graph_scores = _normalize_scores(graph_results)
    all_layout_ids = set(boundary_scores) | set(graph_scores)

    fused = []
    for layout_id in all_layout_ids:
        fused_score = (
            boundary_weight * boundary_scores.get(layout_id, 0.0)
            + graph_weight * graph_scores.get(layout_id, 0.0)
        )
        fused.append((layout_id, fused_score))

    fused.sort(key=lambda item: item[1], reverse=True)
    return fused

def build_search_node() -> Any:
    """Search using topology graph from state."""
    def search(state: dict) -> dict:
        search_mode = state.get("search_mode", "boundary_only")
        topology_json = state.get("topology_graph_json_string")
        input_layout_json = state.get("input_layout_json_string") or state.get("layout_json_string")
        iteration = state.get("iteration", 0)

        if search_mode == "boundary_only":
            if not input_layout_json:
                logger.error("❌ No input layout provided for boundary search")
                return {
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No input layout was provided for boundary search. Please load a layout JSON with an outline.",
                    "iteration": iteration + 1,
                }

            try:
                repo_root = Path(__file__).resolve().parent.parent.parent
                dataset_path = repo_root / "layout_inputs" / "sample_layouts.json"
                input_layout = json.loads(input_layout_json)
                input_coords = input_layout.get("outline", [])

                if not input_coords:
                    logger.error("❌ Input layout does not contain an outline")
                    return {
                        "search_results_json_string": json.dumps([]),
                        "clarification": "The input layout does not contain an outline to search with.",
                        "iteration": iteration + 1,
                    }

                results = boundary_match_boundaries(
                    input_coords=input_coords,
                    dataset_path=str(dataset_path),
                    top_k=3,
                    min_score=0.0,
                ).get("matches", [])

                candidates = _build_candidate_rows(
                    [(item.get("layoutId", "unknown"), float(item.get("score", 0.0))) for item in results]
                )

                logger.info(f"🔍 Boundary search results: {candidates}")

                if not candidates:
                    logger.warning("⚠️  No matching layouts found in boundary-only search")
                    return {
                        "search_result": "failed",
                        "search_results_json_string": json.dumps([]),
                        "clarification": "No matching layout found with boundary-only search. How would you like to proceed?",
                        "iteration": iteration + 1,
                    }

                return {
                    "search_result": "success",
                    "search_results_json_string": json.dumps(candidates),
                    "iteration": iteration + 1,
                }
            except Exception as e:
                logger.error(f"❌ Boundary-only search failed: {str(e)}", exc_info=True)
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": f"Boundary-only search failed: {str(e)}. How would you like to proceed?",
                    "iteration": iteration + 1,
                }
        
        if search_mode not in {"graph_only", "hybrid"}:
            search_mode = "graph_only"

        if not topology_json:
            logger.error("❌ No topology graph provided")
            return {
                "search_results_json_string": json.dumps([]),
                "clarification": "No topology graph provided. Please describe your layout or try again.",
                "iteration": iteration + 1
            }
        
        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            graphs_path, planfinder_graphs_path = _load_layout_candidates(repo_root)
            from tools.graph_searcher import GraphSearcher

            topology = nx.node_link_graph(json.loads(topology_json))
            logger.info(f"📊 Topology graph nodes: {list(topology.nodes(data=True))}")
            logger.info(f"📊 Topology graph edges: {list(topology.edges())}")

            programs = [
                topology.nodes[node].get('program', '')
                for node in topology.nodes()
                if topology.nodes[node].get('program', '')
            ]

            searcher = GraphSearcher(str(graphs_path))
            graph_results = searcher.search_by_embedding(programs, access=True, top_k=3)

            if planfinder_graphs_path is not None:
                pf_searcher = GraphSearcher(str(planfinder_graphs_path))
                pf_results = pf_searcher.search_by_embedding(programs, access=True, top_k=3)
                graph_results = sorted(graph_results + pf_results, key=lambda x: x[1], reverse=True)
                logger.info(f"🔍 Combined graph search results (sample + planfinder): {graph_results}")
            else:
                logger.info(f"🔍 Graph search results: {graph_results}")

            if search_mode == "graph_only":
                results = graph_results
            else:
                if not input_layout_json:
                    logger.error("❌ No input layout provided for hybrid search")
                    return {
                        "search_results_json_string": json.dumps([]),
                        "clarification": "No input layout was provided for hybrid search. Please load a layout JSON with an outline.",
                        "iteration": iteration + 1,
                    }

                input_layout = json.loads(input_layout_json)
                input_coords = input_layout.get("outline", [])
                if not input_coords:
                    logger.error("❌ Input layout does not contain an outline for hybrid search")
                    return {
                        "search_results_json_string": json.dumps([]),
                        "clarification": "The input layout does not contain an outline to search with.",
                        "iteration": iteration + 1,
                    }

                boundary_results_raw = boundary_match_boundaries(
                    input_coords=input_coords,
                    dataset_path=str(repo_root / "layout_inputs" / "sample_layouts.json"),
                    top_k=3,
                    min_score=0.0,
                ).get("matches", [])
                boundary_results = [
                    (item.get("layoutId", "unknown"), float(item.get("score", 0.0)))
                    for item in boundary_results_raw
                ]

                fused = _fuse_rankings(boundary_results, graph_results, boundary_weight=0.5, graph_weight=0.5)
                results = fused
                logger.info(f"🔍 Hybrid search fused results: {results}")

            candidates = _build_candidate_rows(results[:3])
            logger.info(f"📌 Candidates: {candidates}")
            
            if not candidates:
                logger.warning(f"⚠️  No matching layouts found")
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No matching layout found. How would you like to proceed? (Type 'end' to exit or write a new request)",
                    "iteration": iteration + 1,
                }
            
            logger.info(f"✅ Found {len(candidates)} layouts")
            
            return {
                "search_result": "success",
                "search_results_json_string": json.dumps(candidates),
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