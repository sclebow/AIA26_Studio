import json
import networkx as nx
from pathlib import Path
from typing import Any
import logging
from tools.graph_searcher import GraphSearcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search strategies — add new entries here to expose a new method.
# Each strategy receives (searcher, topology) and returns a normalised dict:
#   {"best_list": [(id, score), ...], "exact_ids": set[str], "log": str}
# ---------------------------------------------------------------------------

def _strategy_pipeline(searcher: GraphSearcher, topology: nx.Graph) -> dict:
    result = searcher.search_by_pipeline(topology)
    stages = result["pipeline_stages"]
    best_list = result["exact"] or result["approximate"]
    exact_ids = {lid for lid, _ in result["exact"]}
    log = (
        f"Pipeline: {stages['total_layouts']} layouts → "
        f"embedding {stages['embedding_candidates']} → "
        f"similarity {stages['similarity_candidates']} → "
        f"exact {stages['exact_matches']}"
    )
    return {"best_list": best_list, "exact_ids": exact_ids, "log": log}


def _strategy_similarity(searcher: GraphSearcher, topology: nx.Graph) -> dict:
    results = searcher.search_by_graph_similarity(topology, method="jaccard")
    log = f"Similarity (jaccard): {len(results)} candidates"
    return {"best_list": results, "exact_ids": set(), "log": log}


def _strategy_embedding(searcher: GraphSearcher, topology: nx.Graph) -> dict:
    programs = [topology.nodes[n].get("program", "") for n in topology.nodes()]
    results = searcher.search_by_embedding(programs)
    log = f"Embedding: {len(results)} candidates"
    return {"best_list": results, "exact_ids": set(), "log": log}


def _strategy_subgraph(searcher: GraphSearcher, topology: nx.Graph) -> dict:
    result = searcher.search_hybrid(topology)
    best_list = result["exact"] or result["approximate"]
    exact_ids = {lid for lid, _ in result["exact"]}
    log = f"Subgraph: {len(result['exact'])} exact, {len(result['approximate'])} approximate"
    return {"best_list": best_list, "exact_ids": exact_ids, "log": log}


_STRATEGIES = {
    "pipeline":   _strategy_pipeline,
    "similarity": _strategy_similarity,
    "embedding":  _strategy_embedding,
    "subgraph":   _strategy_subgraph,
}
_DEFAULT_STRATEGY = "pipeline"


def build_search_node(strategy: str = _DEFAULT_STRATEGY) -> Any:
    """Search using topology graph from state.

    Args:
        strategy: one of "pipeline" | "similarity" | "embedding" | "subgraph".
                  Defaults to "pipeline".
    """
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
            graphs_path = repo_root / "layout_inputs" / "RPLAN_Dataset_R-NB" / "graphs.json"

            topology = nx.node_link_graph(json.loads(topology_json))
            logger.info(f"📊 Topology graph nodes: {list(topology.nodes(data=True))}")
            logger.info(f"📊 Topology graph edges: {list(topology.edges())}")

            searcher = GraphSearcher(str(graphs_path))

            # Strategy selection — falls back to pipeline for unknown values.
            run_strategy = _STRATEGIES.get(strategy, _STRATEGIES[_DEFAULT_STRATEGY])
            if strategy not in _STRATEGIES:
                logger.warning(f"⚠️  Unknown search strategy '{strategy}', using '{_DEFAULT_STRATEGY}'")

            result = run_strategy(searcher, topology)
            logger.info(f"🔍 {result['log']}")

            best_list = result["best_list"]
            exact_ids = result["exact_ids"]
            candidates = [
                {
                    "id": lid,
                    "score": round(s, 2),
                    "match_type": "exact" if lid in exact_ids else "approximate",
                    "description": f"Layout {lid}",
                }
                for lid, s in best_list[:3]
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