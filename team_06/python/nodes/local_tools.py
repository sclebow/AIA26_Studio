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

from tools.embedding_matcher import match_layouts
from tools.layout_filter import select_layout
from tools.graph_searcher import GraphSearcher, build_topology_graph
from tools.boundary_analyzer import boundary_analyzer, get_boundary_analyzer_schema


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
            "description": "This tool searches layouts by topology. Auto-loads the best match into state and returns all candidates so you can select a different one if needed.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "programs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of room types (e.g., ['bedroom', 'kitchen', 'living']). INCLUDE DUPLICATES for counts! For '2-bedroom': ['bedroom', 'bedroom', 'kitchen']. For '3 bathrooms': ['bathroom', 'bathroom', 'bathroom']. Count matters!"
                    },
                    "connection_type": {
                        "type": "string",
                        "enum": ["any", "connected"],
                        "description": "'any' = rooms exist (any edges), 'connected' = rooms must all be interconnected via doors"
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
                
                # Build topology graph from user intent
                topology_graph = build_topology_graph(programs, connection_type)
                
                # Search using graph similarity
                results = graph_searcher.search_by_graph_similarity(topology_graph, method="jaccard")
                
                # Format all candidates
                candidates = [
                    {"layoutId": layout_id, "score": similarity}
                    for layout_id, similarity in results
                ]
                
                # Load best match into state (if found)
                if results:
                    best_layout_id, best_similarity = results[0]
                    load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
                    tool_output = {
                        "pattern": f"Rooms: {', '.join(programs)}, connection: {connection_type}",
                        "best_match": best_layout_id,
                        "best_score": round(best_similarity, 2),
                        "all_candidates": candidates,
                        "total": len(candidates),
                        "message": f"Found {len(candidates)} matches. Auto-loaded best: {best_layout_id} (score: {round(best_similarity, 2)}). Ask me to switch to a different one if preferred."
                    }
                    print(f"[local_tool] Found {len(candidates)} matches, auto-loaded {best_layout_id}")
                else:
                    tool_output = {
                        "pattern": f"Rooms: {', '.join(programs)}, connection: {connection_type}",
                        "all_candidates": [],
                        "total": 0,
                        "message": "No layouts found matching this pattern."
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