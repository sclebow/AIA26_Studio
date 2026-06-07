from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from mcp_client import McpClient


def _extract_tree_payload(state: dict[str, Any]) -> dict[str, Any]:
    planning_state = state.get("design_state", {})
    if not isinstance(planning_state, dict):
        planning_state = {}

    planning_context = planning_state.get("planning_json")
    if not isinstance(planning_context, dict):
        planning_context = planning_state.get("planning")
    if not isinstance(planning_context, dict):
        planning_context = {}

    tree_policy = planning_context.get("tree_policy")
    if not isinstance(tree_policy, dict):
        tree_policy = {}

    inferred_tree_points = tree_policy.get("inferred_tree_points", [])
    inferred_tree_sizes = tree_policy.get("inferred_tree_sizes", [])

    tree_count = planning_context.get("tree_count", tree_policy.get("tree_count", 0))
    tree_points = planning_context.get("tree_points", tree_policy.get("tree_points", inferred_tree_points))
    tree_sizes = planning_context.get("tree_sizes", tree_policy.get("tree_sizes", inferred_tree_sizes))

    if not isinstance(tree_points, list):
        tree_points = []
    if not isinstance(tree_sizes, list):
        tree_sizes = []

    if not isinstance(tree_count, int):
        try:
            tree_count = int(tree_count)
        except (TypeError, ValueError):
            tree_count = 0

    normalized_tree_policy = dict(tree_policy)
    normalized_tree_policy.setdefault("tree_count", tree_count)
    normalized_tree_policy.setdefault("tree_points", tree_points)
    normalized_tree_policy.setdefault("tree_sizes", tree_sizes)
    normalized_tree_policy.setdefault("inferred_tree_points", inferred_tree_points)
    normalized_tree_policy.setdefault("inferred_tree_sizes", inferred_tree_sizes)
    normalized_tree_policy.setdefault("tree_count_source", planning_context.get("tree_count_source", "default"))
    normalized_tree_policy.setdefault("tree_positions_provided", bool(planning_context.get("tree_positions_provided", False)))
    normalized_tree_policy.setdefault("preferred_edge", planning_context.get("preferred_edge", ""))
    normalized_tree_policy.setdefault("placement_mode", planning_context.get("placement_mode", ""))
    normalized_tree_policy.setdefault("notes", planning_context.get("notes", ""))

    return {
        "tree_count": max(0, tree_count),
        "tree_points": tree_points,
        "tree_sizes": tree_sizes,
        "tree_policy": normalized_tree_policy,
        "tree_policy_json": json.dumps(normalized_tree_policy, ensure_ascii=True),
    }


def _inject_tree_payload(target: dict[str, Any], tree_payload: dict[str, Any], shape_payload: dict[str, Any]) -> None:
    if shape_payload["shape_type"]:
        target.setdefault("shape_type", shape_payload["shape_type"])
    if shape_payload["locked_shape_type"]:
        target.setdefault("locked_shape_type", shape_payload["locked_shape_type"])

    target.setdefault("tree_count", tree_payload["tree_count"])
    target.setdefault("number_of_trees", tree_payload["tree_count"])
    target.setdefault("tree_points", tree_payload["tree_points"])
    target.setdefault("tree_sizes", tree_payload["tree_sizes"])
    target.setdefault("tree_locations", tree_payload["tree_points"])
    target.setdefault("tree_policy", dict(tree_payload["tree_policy"]))
    target.setdefault("tree_policy_json", tree_payload["tree_policy_json"])

    if isinstance(target.get("tree_policy"), dict):
        target["tree_policy"].setdefault("tree_count", tree_payload["tree_count"])
        target["tree_policy"].setdefault("tree_points", tree_payload["tree_points"])
        target["tree_policy"].setdefault("tree_sizes", tree_payload["tree_sizes"])
        target["tree_policy"].setdefault("inferred_tree_points", tree_payload["tree_policy"].get("inferred_tree_points", tree_payload["tree_points"]))
        target["tree_policy"].setdefault("inferred_tree_sizes", tree_payload["tree_policy"].get("inferred_tree_sizes", tree_payload["tree_sizes"]))
        target["tree_policy"].setdefault("tree_count_source", tree_payload["tree_policy"].get("tree_count_source", "default"))
        target["tree_policy"].setdefault("tree_positions_provided", tree_payload["tree_policy"].get("tree_positions_provided", False))
        target["tree_policy"].setdefault("preferred_edge", tree_payload["tree_policy"].get("preferred_edge", ""))
        target["tree_policy"].setdefault("placement_mode", tree_payload["tree_policy"].get("placement_mode", ""))
        target["tree_policy"].setdefault("notes", tree_payload["tree_policy"].get("notes", ""))


def _extract_gene_defaults(state: dict[str, Any]) -> dict[str, Any]:
    """Extract calculated gene defaults from shape_generation state."""
    shape_generation = state.get("shape_generation", {})
    if not isinstance(shape_generation, dict):
        shape_generation = {}
    
    gene_defaults = shape_generation.get("gene_defaults", {})
    if not isinstance(gene_defaults, dict):
        gene_defaults = {}
    
    # Return only the defaults that have been calculated/specified
    return dict(gene_defaults)


def _inject_gene_defaults(target: dict[str, Any], gene_defaults: dict[str, Any]) -> None:
    """Inject calculated gene defaults into tool arguments if not already specified."""
    if not gene_defaults:
        return
    
    # Only inject defaults for keys not already present in the target
    for key, value in gene_defaults.items():
        if key not in target and value is not None:
            target.setdefault(key, value)
    
    # Also inject into genes_json if present
    if isinstance(target.get("genes_json"), dict):
        for key, value in gene_defaults.items():
            if key not in target["genes_json"] and value is not None:
                target["genes_json"][key] = value
    elif isinstance(target.get("genes"), dict):
        for key, value in gene_defaults.items():
            if key not in target["genes"] and value is not None:
                target["genes"][key] = value


def _extract_shape_payload(state: dict[str, Any]) -> dict[str, Any]:
    design_state = state.get("design_state", {})
    if not isinstance(design_state, dict):
        design_state = {}

    planning_context = design_state.get("planning_json")
    if not isinstance(planning_context, dict):
        planning_context = design_state.get("planning")
    if not isinstance(planning_context, dict):
        planning_context = {}

    shape_generation = state.get("shape_generation", {})
    if not isinstance(shape_generation, dict):
        shape_generation = {}

    selected_shape_type = planning_context.get("selected_shape_type") or shape_generation.get("selected_shape_type")
    locked_shape_type = shape_generation.get("locked_shape_type") or planning_context.get("selected_shape_type")

    if not isinstance(selected_shape_type, str):
        selected_shape_type = ""
    if not isinstance(locked_shape_type, str):
        locked_shape_type = ""

    selected_shape_type = selected_shape_type.strip().lower().replace(" ", "_")
    locked_shape_type = locked_shape_type.strip().lower().replace(" ", "_")

    shape_type = locked_shape_type or selected_shape_type
    if not shape_type:
        shape_request = state.get("shape_request", {})
        if isinstance(shape_request, dict):
            raw_shape_type = shape_request.get("shape_type")
            if isinstance(raw_shape_type, str):
                shape_type = raw_shape_type.strip().lower().replace(" ", "_")

    return {
        "shape_type": shape_type,
        "locked_shape_type": locked_shape_type or shape_type,
    }


def _should_inject_tree_payload(tool_name: str, tool_arguments: dict[str, Any]) -> bool:
    if any(key in tool_arguments for key in ("tree_count", "tree_points", "tree_sizes")):
        return True

    lowered = tool_name.lower()
    return any(
        keyword in lowered
        for keyword in (
            "shape",
            "site",
            "boundary",
            "generator",
            "mesh",
            "grasshopper",
            "tree",
            "manipul",
            "move",
        )
    )


def create_design_tool_node(
    mcp_client: McpClient,
    allowed_tools: list[dict[str, Any]],
    dbg: Callable[[str], None],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """
    Create a tool execution node for design operations.
    Handles all tool calls across different design actions.
    """

    allowed_tool_names = {str(tool.get("name")) for tool in allowed_tools if tool.get("name")}
    tool_aliases = {
        "compute_site_area": "area_of_the_compute_site",
        "calculateSiteArea": "area_of_the_compute_site",
        "siteBoundary": "site_boundary",
        "siteBoundaryReader": "site_boundary_reader_04",
        "move": "manipulation_tools",
    }

    def design_tool_node(state: dict[str, Any], /) -> dict[str, Any]:
        dbg("[workflow][tool] Enter node")

        tree_payload = _extract_tree_payload(state)
        shape_payload = _extract_shape_payload(state)
        gene_defaults = _extract_gene_defaults(state)

        pending_tools = state.get("pending_tool_calls", [])
        if not pending_tools:
            dbg("[workflow][tool] No pending tools")
            state["pending_action"] = "final"
            state["final_response"] = "No valid tools were generated by the model."
            return state

        tool_results: list[str] = []

        for pending_tool in pending_tools:
            state["tool_execution_count"] += 1
            
            if state["tool_execution_count"] > state.get("max_iterations", 10):
                raise RuntimeError("Max tool executions exceeded")

            tool_name = pending_tool.get("name", pending_tool.get("tool_name"))
            if not tool_name:
                raise RuntimeError("Tool call missing name")

            if tool_name in tool_aliases:
                tool_name = tool_aliases[tool_name]

            if tool_name not in allowed_tool_names:
                dbg(f"[workflow][tool] Skipping unsupported tool: {tool_name}")
                continue

            tool_arguments = pending_tool.get("arguments", {})
            if not isinstance(tool_arguments, dict):
                raise RuntimeError("Tool arguments must be an object")

            # Filter out None values
            filtered_args = {
                key: value for key, value in tool_arguments.items() if value is not None
            }

            # Normalize argument keys: strip suffixes like '/Down' or '/Up',
            # lower-case keys so downstream components (and Grasshopper)
            # can read consistent key names such as 'move_back'.
            normalized_args: dict[str, Any] = {}
            for key, value in list(filtered_args.items()):
                try:
                    base = str(key).split("/")[0]
                    norm = base.strip().lower()
                    normalized_args[norm] = value
                except Exception:
                    normalized_args[str(key).lower()] = value

            filtered_args = normalized_args

            # Add string-duplicate keys for numeric/boolean values so callers
            # that expect strings (e.g. GH AsString) will find them.
            for k, v in list(filtered_args.items()):
                try:
                    if str(k).endswith("_str"):
                        continue
                    if isinstance(v, (int, float, bool)):
                        filtered_args.setdefault(f"{k}_str", str(v))
                    elif isinstance(v, (list, dict)):
                        # also provide a JSON string representation for containers
                        try:
                            filtered_args.setdefault(f"{k}_str", json.dumps(v, ensure_ascii=False))
                        except Exception:
                            filtered_args.setdefault(f"{k}_str", str(v))
                    elif isinstance(v, str):
                        filtered_args.setdefault(f"{k}_str", v)
                except Exception:
                    pass

            if _should_inject_tree_payload(tool_name, filtered_args):
                _inject_tree_payload(filtered_args, tree_payload, shape_payload)

                for payload_key in ("genes_json", "genes", "design_request"):
                    payload_value = filtered_args.get(payload_key)
                    if isinstance(payload_value, dict):
                        _inject_tree_payload(payload_value, tree_payload, shape_payload)
                    elif isinstance(payload_value, str):
                        try:
                            payload_data = json.loads(payload_value)
                        except json.JSONDecodeError:
                            payload_data = None
                        if isinstance(payload_data, dict):
                            _inject_tree_payload(payload_data, tree_payload, shape_payload)
                            filtered_args[payload_key] = json.dumps(payload_data)

            # Inject calculated gene defaults (including wing_depth from wing areas)
            if _should_inject_tree_payload(tool_name, filtered_args):
                _inject_gene_defaults(filtered_args, gene_defaults)
                
                for payload_key in ("genes_json", "genes", "design_request"):
                    payload_value = filtered_args.get(payload_key)
                    if isinstance(payload_value, dict):
                        _inject_gene_defaults(payload_value, gene_defaults)
                    elif isinstance(payload_value, str):
                        try:
                            payload_data = json.loads(payload_value)
                        except json.JSONDecodeError:
                            payload_data = None
                        if isinstance(payload_data, dict):
                            _inject_gene_defaults(payload_data, gene_defaults)
                            filtered_args[payload_key] = json.dumps(payload_data)

            dbg(
                f"[workflow][tool] Executing | name={tool_name} | "
                f"args={filtered_args} | count={state['tool_execution_count']}"
            )

            try:
                tool_output = mcp_client.call_tool(tool_name, filtered_args)
            except httpx.ReadTimeout:
                timeout_seconds = getattr(mcp_client, "_timeout_seconds", None)
                timeout_text = (
                    f"{timeout_seconds:.0f}s" if isinstance(timeout_seconds, (int, float)) else "the configured timeout"
                )
                tool_output = f"Tool '{tool_name}' timed out after {timeout_text}."
                state["pending_action"] = "final"
                state["final_response"] = tool_output

            dbg(f"[workflow][tool] Result: {tool_output[:100]}...")
            
            tool_results.append(tool_output)
            state["last_tool_result"] = tool_output
            state["design_state"]["last_tool_result"] = tool_output

        state["pending_tool_calls"] = []
        state["tool_results"] = tool_results
        
        return state

    return design_tool_node
