# ============================================================================
# local_tools.py — Local Python tools executed directly in the graph.
#
# These are tools that don't go through MCP — they're called directly
# from the local_tool node for simpler, faster execution.
# ============================================================================

from __future__ import annotations
import json
from typing import Any

from tools.embedding_matcher import match_layouts
from tools.layout_filter import select_layout
from tools.boundary_analyzer import boundary_analyzer, get_boundary_analyzer_schema



# ---------------------------------------------------------------------------
# Local tools catalog — tools available directly (not via MCP).
# ---------------------------------------------------------------------------

def get_local_tools() -> list[dict[str, Any]]:
    """Return definitions of all local (non-MCP) tools."""
    return [
        get_boundary_analyzer_schema(),
        {
            "name": "layout_filter",
            "description": "Search and filter layouts by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "layout_id": {
                        "type": "string",
                        "description": "Search by layoutId (exact match)"
                    }
                },
                "required": ["layout_id"]
            }
        },
        {
            "name": "layout_matcher",
            "description": "Find best matching layouts using semantic search. Embed user query and compare to layout descriptions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User's natural language description of desired apartment (e.g., 'cozy 2-bedroom with open kitchen')"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top results to return (default: 3)",
                        "default": 3
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum similarity score 0-1 to include results (default: 0.3)",
                        "default": 0.3
                    }
                },
                "required": ["query"]
            }
        }
    ]


# ---------------------------------------------------------------------------
# Local tool node — executes local Python tools.
# ---------------------------------------------------------------------------

def build_local_tool_node():
    """Return a local tool node function ready to be added to a LangGraph StateGraph."""

    def local_tool_node(state):
        """Execute pending local tool calls and append results to conversation history."""

        remaining_calls = []  # Tools that aren't local (to pass to run_tool)
        
        # Iterate over the pending local tool calls
        for call in state["pending_tool_calls"]:
            tool_name = call["name"]
            
            # Skip non-local tools
            if tool_name not in ["layout_filter", "layout_matcher", "boundary_analyzer"]:
                remaining_calls.append(call)
                continue
            
            print(f"Calling local tool: {tool_name} with arguments: {call['arguments']}")

            # Cleanup any null values accidentally included by the LLM
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}

            # Execute the appropriate local tool
            if tool_name == "boundary_analyzer":
                tool_output = boundary_analyzer(
                    input_boundary=tool_args.get("input_boundary"),
                    dataset_path=tool_args.get("dataset_path"),
                    top_n_results=tool_args.get("top_n_results", 5)
                )
            elif tool_name == "layout_filter":
                tool_output = select_layout(
                    all_layouts=state["all_layouts"],
                    layout_id=tool_args.get("layout_id")
                )
            elif tool_name == "layout_matcher":
                tool_output = match_layouts(
                    query=tool_args.get("query"),
                    all_descriptions=state["all_descriptions"],  # Pass from state
                    top_k=tool_args.get("top_k", 3),
                    min_score=tool_args.get("min_score", 0.3)
                )
            else:
                tool_output = {"error": f"Unknown local tool: {tool_name}"}

            # Store results in state for downstream tool calls
            if tool_name == "layout_matcher" and isinstance(tool_output, dict):
                # Extract the best matching layout ID
                matches = tool_output.get("matches", [])
                if matches:
                    best_match = matches[0]
                    state["layout_id"] = best_match.get("layoutId")
            
            elif tool_name == "layout_filter" and isinstance(tool_output, dict):
                # Store the full layout schema
                state["layout_schema"] = tool_output
                state["layout_id"] = tool_output.get("layoutId")

            # Append the tool call and its result to the conversation history
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
                "content": f"Tool result: {json.dumps(tool_output)}",
            })
            print(f"Local tool result: {tool_output}")

        # Keep remaining (non-local) tool calls for the run_tool node
        state["pending_tool_calls"] = remaining_calls if remaining_calls else None
        return state

    return local_tool_node