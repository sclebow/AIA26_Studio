# ============================================================================
# local_tools.py — Local Python tools executed directly in the graph.
#
# These are tools that don't go through MCP — they're called directly
# from the local_tool node for simpler, faster execution.
# ============================================================================

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from functools import lru_cache

import networkx as nx

from tools.embedding_matcher import match_layouts
from tools.layout_filter import select_layout
from tools.graph_searcher import GraphSearcher, build_topology_graph
from tools.boundary_analyzer import boundary_analyzer, get_boundary_analyzer_schema
from tools.rule_based_embedder import RuleBasedEmbedder


# ---------------------------------------------------------------------------
# File loading — cache JSON files to avoid repeated disk reads.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_all_layouts() -> list[dict[str, Any]]:
    """Load all layouts from sample_layouts.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    return json.loads(layouts_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_all_descriptions() -> list[dict[str, Any]]:
    """Load layout descriptions from sample_descriptions.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    descriptions_path = repo_root / "layout_inputs" / "sample_descriptions.json"
    return json.loads(descriptions_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _get_graph_searcher() -> GraphSearcher:
    """Initialize and cache GraphSearcher instance."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    return GraphSearcher(str(graphs_path))


@lru_cache(maxsize=1)
def _get_rule_based_embedder() -> RuleBasedEmbedder:
    """Build and cache the rule-based embedding index (runs once at startup)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    graphs_data = json.loads(graphs_path.read_text(encoding="utf-8"))
    layout_graphs = {lid: nx.node_link_graph(data) for lid, data in graphs_data.items()}
    return RuleBasedEmbedder(layout_graphs)


# ---------------------------------------------------------------------------
# Common layout loading helper
# ---------------------------------------------------------------------------

def _load_layout_to_state(state: dict, reference_layout_path: Path, layout_id: str) -> dict[str, Any]:
    """Load a layout by ID, update state, save to file.
    
    Returns: layout_output dict with status info.
    """
    all_layouts = _load_all_layouts()
    layout = select_layout(all_layouts, layout_id)
    
    # Update state
    state["layout_json_string"] = json.dumps(layout)
    
    # Write to file
    reference_layout_path.parent.mkdir(parents=True, exist_ok=True)
    reference_layout_path.write_text(
        json.dumps(layout, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    return {
        "layout_id": layout_id,
        "status": "loaded",
        "saved_to": str(reference_layout_path)
    }


# ---------------------------------------------------------------------------
# Local tools catalog — tools available directly (not via MCP).
# ---------------------------------------------------------------------------

def get_local_tools() -> list[dict[str, Any]]:
    """Return definitions of all local (non-MCP) tools."""
    return [
        get_boundary_analyzer_schema(),
        {
            "name": "layout_filter",
            "description": "This tool filters a specific layout by ID.Auto-loads the found layout into state",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "layoutId": {
                        "type": "string",
                        "description": "The layout ID (e.g., 'layout-1', 'layout-4')"
                    }
                },
                "required": ["layoutId"]
            }
        },
        {
            "name": "layout_graph_search",
            "description": "Search layouts by room topology. Auto-loads the best match and returns all candidates. Supports three search modes: (1) presence only, (2) specific connections via edges, (3) exact structural matching via search_method='subgraph' for symmetric patterns like 'each bedroom has its own bathroom'.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "programs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of room types. INCLUDE DUPLICATES for counts! '2 bedrooms + kitchen' -> ['bedroom','bedroom','kitchen']. Count matters!"
                    },
                    "connection_type": {
                        "type": "string",
                        "enum": ["any", "connected"],
                        "description": "'any' = rooms just need to exist. 'connected' = ALL rooms fully interconnected. Ignored when 'edges' is provided."
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "maxItems": 2
                        },
                        "description": "Specific connections as pairs. Two formats: (1) Program-level: [['bathroom','bedroom']] = any bathroom connects to any bedroom. (2) Instance-level: [['bedroom:1','office:1'],['bedroom:2','office:2']] = bedroom 1 connects to office 1 AND bedroom 2 connects to office 2 as separate pairs. Use instance-level + search_method='subgraph' for symmetric patterns."
                    },
                    "search_method": {
                        "type": "string",
                        "enum": ["jaccard", "subgraph", "embedding", "pipeline"],
                        "description": (
                            "'jaccard' (default) = program-level Jaccard ranking, always returns results. "
                            "'subgraph' = exact structural match via graph isomorphism — use with instance-level edges for symmetric patterns like 'each bedroom has its own private bathroom'. Falls back to jaccard when no exact match. "
                            "'embedding' = pre-built cosine similarity index; fastest for room-count + connectivity queries; use connection_type='connected' to require adjacency. Does not support explicit edges. "
                            "'pipeline' = embedding → jaccard → subgraph in sequence; best for specific queries against large layout sets (100+) — embedding pre-filters before expensive steps run."
                        )
                    }
                },
                "required": ["programs"]
            }
        }
    ]


# ---------------------------------------------------------------------------
# Local tool node — executes local Python tools.
# ---------------------------------------------------------------------------

def build_local_tool_node(reference_layout_path):
    """Return a local tool node function ready to be added to a LangGraph StateGraph."""

    def local_tool_node(state):
        """Execute pending local tool calls."""

        remaining_calls = []  # Tools that aren't local (to pass to run_tool)
        
        # Iterate over the pending local tool calls
        for call in state["pending_tool_calls"]:
            tool_name = call["name"]
            
            # Skip non-local tools
            if tool_name not in ["layout_filter", "layout_graph_search", "boundary_analyzer"]:
                remaining_calls.append(call)
                continue
            
            print(f"Calling local tool: {tool_name} with arguments: {call['arguments']}")

            # Cleanup any null values accidentally included by the LLM
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}

            # Execute layout_filter, layout_graph_search, or boundary_analyzer
            if tool_name == "boundary_analyzer":
                tool_output = boundary_analyzer(
                    input_boundary=tool_args.get("input_boundary"),
                    input_layout_path=tool_args.get("input_layout_path"),
                    dataset_path=tool_args.get("dataset_path"),
                    top_n_results=tool_args.get("top_n_results", 5)
                )
                print(f"[local_tool] Boundary analysis complete: {tool_output.get('status')}")
                
            elif tool_name == "layout_filter":
                layout_id = tool_args.get("layoutId")
                load_result = _load_layout_to_state(state, reference_layout_path, layout_id)
                tool_output = {
                    **load_result,
                    "message": f"Loaded layout {layout_id}."
                }
                print(f"[local_tool] {tool_output['message']}")
                
            elif tool_name == "layout_graph_search":
                graph_searcher = _get_graph_searcher()
                programs = tool_args.get("programs", [])
                connection_type = tool_args.get("connection_type", "any")
                edges = tool_args.get("edges", None)
                search_method = tool_args.get("search_method", "jaccard")

                # Build topology graph from user intent
                topology_graph = build_topology_graph(programs, connection_type, edges=edges)

                # Human-readable description of the requested pattern
                if edges is not None:
                    edges_str = ", ".join(f"{a}<->{b}" for a, b in edges)
                    pattern_desc = f"Rooms: {', '.join(programs)}, edges: {edges_str}"
                else:
                    pattern_desc = f"Rooms: {', '.join(programs)}, connection: {connection_type}"

                # embedding does not support explicit edges — demote to jaccard early
                # so the elif chain below routes correctly.
                if search_method == "embedding" and edges is not None:
                    print("[local_tool] WARNING: 'embedding' does not support explicit edges — falling back to jaccard")
                    search_method = "jaccard"

                if search_method == "embedding":
                    embedder = _get_rule_based_embedder()
                    want_connected = (connection_type == "connected")
                    results = embedder.search(
                        programs, connected=want_connected, top_k=len(embedder.index)
                    )
                    candidates = [
                        {"layoutId": lid, "score": round(s, 3)} for lid, s in results
                    ]
                    if results:
                        best_layout_id, best_score = results[0]
                        load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "embedding",
                            "best_match": best_layout_id,
                            "best_score": round(best_score, 3),
                            "all_candidates": candidates,
                            "total": len(candidates),
                            "message": (
                                f"Embedding search ranked {len(candidates)} layouts. "
                                f"Auto-loaded best: {best_layout_id} (cosine score: {round(best_score, 3)})."
                            ),
                        }
                        print(f"[local_tool] Embedding search: loaded {best_layout_id} (score={round(best_score, 3)})")
                    else:
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "embedding",
                            "all_candidates": [],
                            "total": 0,
                            "message": "No layouts found (empty index?).",
                        }

                elif search_method == "pipeline":
                    STAGE1_K = 50
                    STAGE2_K = 10

                    embedder = _get_rule_based_embedder()
                    searcher = _get_graph_searcher()
                    want_connected = (connection_type == "connected")

                    # Stage 1: embedding — dot products only, no graph traversal
                    stage1 = embedder.search(programs, connected=want_connected, top_k=STAGE1_K)
                    stage1_ids = {lid for lid, _ in stage1}
                    print(f"[pipeline] Stage 1 (embedding): {len(stage1_ids)} candidates from {len(embedder.index)} layouts")

                    # Stage 2: jaccard — graph traversal on survivors only
                    stage2 = searcher.search_by_graph_similarity(
                        topology_graph, method="jaccard", candidate_ids=stage1_ids
                    )
                    stage2_ids = {lid for lid, _ in stage2[:STAGE2_K]}
                    print(f"[pipeline] Stage 2 (jaccard): {len(stage2_ids)} candidates")

                    # Stage 3: subgraph isomorphism — VF2 on ≤STAGE2_K, not all layouts
                    if edges is not None:
                        hybrid = searcher.search_hybrid(topology_graph, candidate_ids=stage2_ids)
                        exact = hybrid["exact"]
                        approximate = hybrid["approximate"]
                        best_list = exact if exact else approximate
                        all_candidates = (
                            [{"layoutId": lid, "score": 1.0,         "match_type": "exact"}       for lid, _ in exact] +
                            [{"layoutId": lid, "score": round(s, 2), "match_type": "approximate"} for lid, s in approximate]
                        )
                        stage3_label = f"subgraph → {len(all_candidates)} final"
                    else:
                        best_list = stage2[:STAGE2_K]
                        all_candidates = [{"layoutId": lid, "score": round(s, 2)} for lid, s in best_list]
                        stage3_label = f"jaccard top-{STAGE2_K} (no edges specified)"

                    if best_list:
                        best_layout_id, best_score = best_list[0]
                        load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "pipeline",
                            "pipeline_stages": {
                                "embedding_candidates": len(stage1_ids),
                                "jaccard_candidates":   len(stage2_ids),
                                "final_candidates":     len(all_candidates),
                            },
                            "best_match": best_layout_id,
                            "best_score": round(best_score, 2),
                            "all_candidates": all_candidates,
                            "message": (
                                f"Pipeline: {len(embedder.index)} layouts → embedding → {len(stage1_ids)} "
                                f"→ jaccard → {len(stage2_ids)} → {stage3_label}. "
                                f"Auto-loaded {best_layout_id} (score: {round(best_score, 2)})."
                            ),
                        }
                        print(f"[pipeline] Best: {best_layout_id} (score={round(best_score, 2)})")
                    else:
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "pipeline",
                            "all_candidates": [],
                            "message": "No layouts found matching this pattern.",
                        }
                        print(f"[pipeline] No matches found for {programs}")

                elif search_method == "subgraph":
                    hybrid = graph_searcher.search_hybrid(topology_graph)
                    exact = hybrid["exact"]
                    approximate = hybrid["approximate"]

                    exact_candidates = [
                        {"layoutId": lid, "score": 1.0, "match_type": "exact"} for lid, _ in exact
                    ]
                    approx_candidates = [
                        {"layoutId": lid, "score": round(s, 2), "match_type": "approximate"}
                        for lid, s in approximate
                    ]
                    all_candidates = exact_candidates + approx_candidates
                    best_list = exact if exact else approximate

                    if best_list:
                        best_layout_id, best_score = best_list[0]
                        load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
                        match_note = "exact structural match" if exact else "no exact match — best approximate"
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "subgraph",
                            "exact_matches": len(exact),
                            "approximate_matches": len(approximate),
                            "best_match": best_layout_id,
                            "best_score": round(best_score, 2),
                            "all_candidates": all_candidates,
                            "message": (
                                f"Found {len(exact)} exact and {len(approximate)} approximate matches. "
                                f"Auto-loaded {best_layout_id} ({match_note})."
                            ),
                        }
                        print(f"[local_tool] Subgraph search: {len(exact)} exact, {len(approximate)} approx. Loaded {best_layout_id}")
                    else:
                        tool_output = {
                            "pattern": pattern_desc,
                            "search_method": "subgraph",
                            "exact_matches": 0,
                            "approximate_matches": 0,
                            "all_candidates": [],
                            "message": "No layouts found matching this pattern.",
                        }
                        print(f"[local_tool] No matches found for {programs}")

                else:
                    # Default: jaccard program-level ranking
                    results = graph_searcher.search_by_graph_similarity(topology_graph, method="jaccard")
                    candidates = [
                        {"layoutId": lid, "score": round(s, 2)} for lid, s in results
                    ]

                    if results:
                        best_layout_id, best_similarity = results[0]
                        load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
                        tool_output = {
                            "pattern": pattern_desc,
                            "best_match": best_layout_id,
                            "best_score": round(best_similarity, 2),
                            "all_candidates": candidates,
                            "total": len(candidates),
                            "message": f"Found {len(candidates)} matches. Auto-loaded best: {best_layout_id} (score: {round(best_similarity, 2)}). Ask me to switch to a different one if preferred.",
                        }
                        print(f"[local_tool] Found {len(candidates)} matches, auto-loaded {best_layout_id}")
                    else:
                        tool_output = {
                            "pattern": pattern_desc,
                            "all_candidates": [],
                            "total": 0,
                            "message": "No layouts found matching this pattern.",
                        }
                        print(f"[local_tool] No matches found for {programs}")
            else:
                tool_output = {"error": f"Unknown tool: {tool_name}"}

            # Append to conversation history
            state["messages"].append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": tool_args}],
                }),
            })
            
            state["messages"].append({
                "role": "user",
                "content": f"Tool result: {json.dumps(tool_output)}"
            })
            
            print(f"[local_tool] Result: {tool_output}")

        state["pending_tool_calls"] = remaining_calls if remaining_calls else None
        return state

    return local_tool_node