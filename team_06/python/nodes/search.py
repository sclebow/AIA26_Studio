import json
import networkx as nx
from pathlib import Path
from typing import Any
import logging
from tools.boundary_embedding_matcher import match_boundaries as boundary_match_boundaries
from team_06.python.nodes import topology

logger = logging.getLogger(__name__)

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

                candidates = [
                    {
                        "id": item.get("layoutId", "unknown"),
                        "score": float(item.get("score", 0.0)),
                        "description": f"Layout {item.get('layoutId', 'unknown')}",
                    }
                    for item in results
                ]

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
        
        if not topology_json:
            logger.error("❌ No topology graph provided")
            return {
                "search_results_json_string": json.dumps([]),
                "clarification": "No topology graph provided. Please describe your layout or try again.",
                "iteration": iteration + 1
            }
        
        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
            from tools.graph_searcher import GraphSearcher
            
            topology = nx.node_link_graph(json.loads(topology_json))
            logger.info(f"📊 Topology graph nodes: {list(topology.nodes(data=True))}")
            logger.info(f"📊 Topology graph edges: {list(topology.edges())}")
            
            # Extract program types from topology
            programs = [
                topology.nodes[node].get('program', '')
                for node in topology.nodes()
                if topology.nodes[node].get('program', '')
            ]
            
            searcher = GraphSearcher(str(graphs_path))
            results = searcher.search_by_embedding(programs, access=True, top_k=3)

            # Also search Planfinder graphs if available
            planfinder_graphs_path = repo_root / "layout_inputs" / "planfinder_graphs.json"
            if planfinder_graphs_path.exists():
                pf_searcher = GraphSearcher(str(planfinder_graphs_path))
                pf_results = pf_searcher.search_by_embedding(programs, access=True, top_k=3)
                results = sorted(results + pf_results, key=lambda x: x[1], reverse=True)
                logger.info(f"🔍 Combined search results (sample + planfinder): {results}")
            else:
                logger.info(f"🔍 Search results: {results}")

            candidates = [
                {"id": lid, "score": round(s, 2), "description": f"Layout {lid}"}
                for lid, s in results[:3]
            ]
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