import json
import networkx as nx
from pathlib import Path
from typing import Any
import logging
from tools.graph_searcher import GraphSearcher

logger = logging.getLogger(__name__)

def build_search_node() -> Any:
    """Search using topology graph from state."""
    def search(state: dict) -> dict:
        topology_json = state.get("topology_graph_json_string")
        iteration = state.get("iteration", 0)
        
        if not topology_json:
            logger.error("❌ No topology graph provided")
            return {
                "search_results_json_string": json.dumps([]),
                "final_response": "No topology graph provided.",
                "iteration": iteration + 1
            }
        
        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
            
            topology = nx.node_link_graph(json.loads(topology_json))
            logger.info(f"📊 Topology graph nodes: {list(topology.nodes(data=True))}")
            logger.info(f"📊 Topology graph edges: {list(topology.edges())}")
            
            searcher = GraphSearcher(str(graphs_path))
            results = searcher.search_by_graph_similarity(topology, method="jaccard")

            # Also search Planfinder graphs if available
            planfinder_graphs_path = repo_root / "layout_inputs" / "planfinder_graphs.json"
            if planfinder_graphs_path.exists():
                pf_searcher = GraphSearcher(str(planfinder_graphs_path))
                pf_results = pf_searcher.search_by_graph_similarity(topology, method="jaccard")
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
                    "final_response": "No matching layouts found.",
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
                "final_response": f"Search failed: {str(e)}",
                "iteration": iteration + 1,
            }
        
    return search