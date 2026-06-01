"""
graph.py — Phase 3 agent graph: state, nodes, edges, and routing.

This is the main file to edit when changing how the agent works.
- AgentState        : all data flowing between nodes
- build_graph       : wires every node and edge together
- run_agent         : called from main.py; builds and runs the graph once
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Annotated, Any, TypedDict
from langgraph.graph.message import add_messages

from langgraph.graph import END, START, StateGraph

from nodes.reason import build_reason_node
from nodes.tools import build_tool_node
from nodes.add_objects import build_add_objects_node
from nodes.visibility import build_visibility_node
from nodes.path_analysis import build_path_node
from nodes.reachability import build_reachability_node
from nodes.orientation import build_orientation_node
from nodes.collision import build_collision_node
from nodes.scoring import build_scoring_node
from nodes.profile_agent import build_profile_agent_node
from nodes.space_type_agent import build_space_type_agent_node
from nodes.query_agent import build_query_agent_node
from nodes.populate_agent import build_populate_agent_node
from nodes.checkpoint import build_user_checkpoint_node
from nodes.explain import explain_node
from nodes.output import output_node
from nodes.fan_out import analysis_fan_out_node, group1_join_node
from _runtime.utils import _slim_layout, _format_tool_catalog


# ---------------------------------------------------------------------------
# Reducer for parallel node writes.
# When Group 1 nodes (collision, visibility, orientation) run in parallel they
# all return state updates simultaneously. LangGraph requires a reducer for any
# field that more than one parallel branch writes; without one it raises
# InvalidUpdateError. _keep_last takes the last non-None value so a node that
# doesn't touch a field (returns None) never clobbers a sibling's result.
# ---------------------------------------------------------------------------

def _keep_last(a, b):
    return b if b is not None else a


# ---------------------------------------------------------------------------
# State — the data every node can read and write.
# Keys are grouped by concern so it is easy to trace which nodes own each field.
# Fields written by parallel branches are Annotated with _keep_last.
# Fields written only by a single node stay as plain TypedDict fields.
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # Core conversation — add_messages merges appended entries rather than
    # replacing the whole list; required because parallel nodes all append.
    messages:            Annotated[list[dict[str, Any]], add_messages]

    # Every node increments iteration and may write pending_tool_calls or
    # final_response — _keep_last prevents InvalidUpdateError from parallel writes.
    pending_tool_calls:  Annotated[list[dict[str, Any]] | None, _keep_last]
    iteration:           Annotated[int,                         _keep_last]
    final_response:      Annotated[str | None,                  _keep_last]

    # Plain fields — written only once at startup, never by parallel branches.
    max_iterations:      int
    tool_catalog:        str

    # Layout and session paths — layout_json_string is updated by add_objects
    # and tools nodes after placements; needs _keep_last so updates propagate.
    layout_json_string:  Annotated[str, _keep_last]
    workspace_path:      str
    layout_name:         str
    _llm:                Any

    # Pre-agent outputs — written by sequential pre-agents; _keep_last guards
    # against the unlikely case a retry or graph change writes them in parallel.
    space_config:        Annotated[dict[str, Any] | None, _keep_last]
    profile_config:      Annotated[dict[str, Any] | None, _keep_last]

    # Object placement — reason sets these, add_objects clears them.
    object_to_place:       Annotated[dict[str, Any] | None, _keep_last]
    object_queue:          Annotated[list[dict] | None,     _keep_last]
    last_placement_result: Annotated[dict[str, Any] | None, _keep_last]

    # Analysis results — collision/visibility/orientation run in parallel;
    # path/reachability are sequential but annotated for future-safety.
    collision_results:    Annotated[dict[str, Any] | None, _keep_last]
    visibility_results:   Annotated[list | None,           _keep_last]
    orientation_results:  Annotated[dict[str, Any] | None, _keep_last]
    path_results:         Annotated[dict[str, Any] | None, _keep_last]
    reachability_results: Annotated[dict[str, Any] | None, _keep_last]

    # Scoring and control — each written by a single node but annotated
    # defensively so any future parallelisation doesn't silently corrupt state.
    scoring_results:     Annotated[dict[str, Any] | None, _keep_last]
    evaluation_passed:   Annotated[bool | None,           _keep_last]
    user_approved:       Annotated[bool | None,           _keep_last]

    # Adjustment loop counter — prevents infinite loops when collision/reachability
    # violations persist despite object placement attempts. After max adjustments
    # the graph continues to scoring regardless.
    adjustment_count:    Annotated[int, _keep_last]

    # Placement history — list of dicts describing each furniture move.
    # Populated by add_objects, displayed by user_checkpoint before approval.
    placement_history:   Annotated[list[dict] | None, _keep_last]

    # Previous scoring — snapshot of scoring_results from the last checkpoint
    # visit, used to show before/after score comparison with deltas.
    previous_scoring:    Annotated[dict[str, Any] | None, _keep_last]

    # Original layout snapshot — used to detect if doors/windows/structure
    # were modified or lost during the pipeline.
    original_layout:     dict | None

    # Query mode flag — set by reason node when user asks to analyze without placing.
    # Routes to query_agent instead of analysis_fan_out.
    _query_mode:         Annotated[bool | None, _keep_last]

    # Spatial relationship graph — NetworkX MultiGraph stored as node-link dict
    # for JSON serialization, plus a compact text version for LLM context.
    # Rebuilt from layout JSON after each placement (base edges only).
    # Enriched by enrich_graph_node after all analysis tools complete.
    spatial_graph:       Annotated[dict | None, _keep_last]
    spatial_graph_text:  Annotated[str | None,  _keep_last]

    # Node IDs to highlight in the visualizer. Set by add_objects after placement,
    # carried into enrich_graph_node so highlights persist through both update steps.
    # Reset to [] by _build_initial_state at the start of each new user request.
    viz_highlight_ids:   Annotated[list[str] | None, _keep_last]

    # Set to True by populate_agent after it fills the queue so the keyword
    # check in _route_after_reason never fires a second time for the same request.
    populate_done:       Annotated[bool | None, _keep_last]

    # Sanitized placement profile — vehicle profiles (forklift, crane, pallet_jack)
    # are stripped out here so populate_agent always places with standard_worker.
    # Separate from profile_config, which is used for circulation analysis.
    placement_profile:   Annotated[dict | None, _keep_last]

    # Zone-by-zone populate flow — zone_queue holds remaining zones after the
    # first one is loaded into object_queue; current_zone tracks the active zone.
    zone_queue:    Annotated[list[dict] | None, _keep_last]
    current_zone:  Annotated[str | None,        _keep_last]


# ---------------------------------------------------------------------------
# Routing functions — pure state reads, no side effects.
# Each returns a string that matches a key in the conditional_edges map.
# ---------------------------------------------------------------------------

def _route_after_reason(state: AgentState) -> str:
    # If populate_agent filled the queue but reason hasn't set object_to_place yet,
    # drain the queue directly without calling the LLM again.
    queue = state.get("object_queue") or []
    if queue and not state.get("object_to_place"):
        return "add_objects"

    # Reason node sets exactly one of these fields to signal what should happen next.
    # object_to_place takes priority: place the object before running any analysis.
    if state.get("object_to_place"):
        return "add_objects"
    if state.get("_query_mode"):
        return "query_agent"
    # final_response means the LLM is done reasoning — move to analysis pipeline.
    # Empty string "" is treated as "cleared" (not finished); only a real
    # non-empty string triggers the finish route.
    fr = state.get("final_response")
    if fr is not None and fr != "":
        return "finish"
    # Default: a tool call was queued; execute it then return to reason.
    return "run_tool"


MAX_ADJUSTMENTS = 3  # Max times the graph loops back to reason for collision/reachability fixes


def _route_after_group1(state: AgentState) -> str:
    if state.get("object_queue"):
        return "drain"
    # Group 1 = collision + visibility + orientation.
    # Hard violations mean the layout is physically impassable — route back
    # to reason immediately rather than wasting time on path checks.
    # BUT: only loop back if (a) the agent placed objects, and (b) we haven't
    # exceeded the max adjustment attempts. Otherwise continue to scoring.
    adj = state.get("adjustment_count", 0)
    collision = state.get("collision_results")
    if collision and not collision.get("pass", True):
        hard = collision.get("summary", {}).get("hard_violations", 0)
        if hard > 0 and state.get("last_placement_result") is not None and adj < MAX_ADJUSTMENTS:
            print(f"[router] Hard collision violations — adjustment {adj + 1}/{MAX_ADJUSTMENTS}")
            return "adjust"
    return "continue"


def _route_after_group2(state: AgentState) -> str:
    if state.get("object_queue"):
        return "adjust"
    # Group 2 = path + reachability.
    # Same logic with max adjustment limit.
    has_placed = state.get("last_placement_result") is not None
    adj = state.get("adjustment_count", 0)

    if has_placed and adj < MAX_ADJUSTMENTS:
        path = state.get("path_results")
        if path:
            pairs = path.get("pairs", [])
            unreachable = [p for p in pairs if p.get("status") == "unreachable"]
            if pairs and len(unreachable) > len(pairs) * 0.3:
                print(f"[router] Path violations — adjustment {adj + 1}/{MAX_ADJUSTMENTS}")
                return "adjust"

        reach = state.get("reachability_results")
        if reach:
            summary = reach.get("summary", {})
            total    = summary.get("total", 0)
            reachable = summary.get("reachable", 0)
            if total > 0 and reachable / total < 0.7:
                print(f"[router] Reachability violations — adjustment {adj + 1}/{MAX_ADJUSTMENTS}")
                return "adjust"

    return "continue"


def _route_after_checkpoint(state: AgentState) -> str:
    user_input = ""
    messages = state.get("messages") or []
    # Find the last human/user message — not assistant or tool messages
    SYSTEM_PREFIXES = (
        "tool result:", "scoring complete", "layout score",
        "collision", "visibility", "path analysis",
        "reachability", "analysis complete", "placed ",
        "moved ", "spatial graph", "current layout"
    )
    for msg in reversed(messages):
        role = (msg.type if hasattr(msg, "type") 
                else msg.get("role", ""))
        if role not in ("human", "user"):
            continue
        content = (
            msg.content if hasattr(msg, "content")
            else msg.get("content", "")
        ).strip()
        if any(content.lower().startswith(p) for p in SYSTEM_PREFIXES):
            continue
        if len(content) > 200:
            continue
        user_input = content.lower()
        break

    zone_queue = state.get("zone_queue") or []

    print(f"[checkpoint_debug] user_input='{user_input}' "
          f"zone_queue_len={len(state.get('zone_queue') or [])} "
          f"user_approved={state.get('user_approved')}")

    # "yes" → proceed to next zone
    if user_input == "yes" and zone_queue:
        return "next_zone"

    # "end" or "approve" → save and trigger final analysis
    if user_input in ("end", "approve"):
        return "approved"

    # Legacy flag fallback for non-populate flows
    if state.get("user_approved") and not zone_queue:
        return "approved"

    # Empty input with no zones left → done
    if (state.get("_query_mode") is False
            and not state.get("placement_history")
            and not zone_queue):
        return "query_done"

    # Anything else → loop back to reason with user instructions
    return "continue"


# ---------------------------------------------------------------------------
# analysis_fan_out_node, group1_join_node → nodes/fan_out.py
# build_user_checkpoint_node             → nodes/checkpoint.py
# explain_node                           → nodes/explain.py
# output_node                            → nodes/output.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Spatial graph helpers
# ---------------------------------------------------------------------------

def _build_correction_message(state: dict, G=None) -> str:
    """Build an explicit correction message from spatial graph findings.

    Injected into conversation history when the router sends the LLM back for
    adjustments, so the LLM knows exactly what to fix (move vectors, positions,
    clearance details) instead of guessing.

    Pass G directly from enrich_graph_node to avoid deserializing stale state.
    """
    if G is None:
        graph_data = state.get("spatial_graph")
        if not graph_data:
            return ""
        try:
            from spatial_graph import dict_to_graph
            G = dict_to_graph(graph_data)
        except Exception:
            return ""

    issues = []

    for nid, nd in G.nodes(data=True):
        if nd.get("ntype") not in ("furniture", "mep"):
            continue
        name = nd.get("name", nid)

        if nd.get("clearance_ok") is False:
            md = nd.get("move_direction")
            mdist = nd.get("move_distance_m")
            deficit = nd.get("deficit_m", "?")
            has_m = nd.get("min_clearance_m")
            req_m = nd.get("required_clearance_m")
            detail = f"has {has_m}m clearance, needs {req_m}m" if has_m and req_m else f"deficit {deficit}m"
            center = nd.get("center")
            pos_str = f" (currently at x={center[0]:.1f}, y={center[1]:.1f})" if center else ""
            if md and mdist:
                issues.append(
                    f"- {name}{pos_str}: CLEARANCE VIOLATION ({detail}). "
                    f"Fix: move [{md[0]:+.2f}, {md[1]:+.2f}] by {mdist}m")
            else:
                issues.append(
                    f"- {name}{pos_str}: CLEARANCE VIOLATION ({detail}). "
                    f"Reposition away from walls and obstacles.")

        if nd.get("reachable") is False:
            reasons = []
            if not nd.get("height_ok", True):
                reasons.append("height out of reach range")
            if not nd.get("radius_ok", True):
                reasons.append("too far from use point")
            issues.append(
                f"- {name}: UNREACHABLE ({', '.join(reasons) if reasons else 'blocked'})")

        if nd.get("facing_ok") is False:
            issues.append(
                f"- {name}: WRONG FACING (off by {nd.get('angle_diff', '?')}deg)")

    blocks = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "blocks"]
    for u, v in blocks:
        un = G.nodes[u].get("name", u)
        vn = G.nodes[v].get("name", v)
        issues.append(f"- {un} BLOCKS the functional line of {vn}. Move {un} out of the way.")

    unreachable_paths = [(u, v) for u, v, d in G.edges(data=True)
                         if d.get("etype") == "path" and not d.get("reachable")]
    for u, v in unreachable_paths:
        un = G.nodes[u].get("name", u)
        vn = G.nodes[v].get("name", v)
        issues.append(f"- Path from {un} to {vn} is BLOCKED.")

    if not issues:
        return ""

    adj = state.get("adjustment_count", 0) + 1
    return (
        f"SPATIAL GRAPH CORRECTION (attempt {adj}/{MAX_ADJUSTMENTS})\n"
        f"The analysis found {len(issues)} issue(s) that need fixing:\n\n"
        + "\n".join(issues) + "\n\n"
        "Use move_object with the vectors above. "
        "Do NOT call analysis tools -- they run automatically after placement."
    )


def enrich_graph_node(state: AgentState) -> dict:
    """Enrich the spatial graph with analysis tool results.

    Runs after all 5 analysis tools complete (after reachability) and before
    the group2 routing decision. Adds analysis-derived node attributes and
    edges, prints ANSI-colored FINDINGS, and injects a correction message
    into the conversation when violations are found after placement.
    """
    graph_data = state.get("spatial_graph")
    if not graph_data:
        return {}
    try:
        from spatial_graph import (
            dict_to_graph, enrich_graph_from_analysis,
            graph_to_dict, serialize_for_llm,
        )
        G = dict_to_graph(graph_data)
        G = enrich_graph_from_analysis(
            G,
            state.get("collision_results"),
            state.get("visibility_results"),
            state.get("path_results"),
            state.get("reachability_results"),
            state.get("orientation_results"),
        )
        text = serialize_for_llm(G)
        print(f"\n[enrich_graph] Spatial graph: {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges")
        if not state.get("object_queue") and not state.get("zone_queue"):
            print(text)

        # Collect actionable findings for ANSI display
        # Skip walls (structural, not movable) — their "clearance" is
        # just wall thickness, not an actionable issue.
        _skip_ntypes = {"wall"}
        _findings = []
        for nid, nd in G.nodes(data=True):
            if nd.get("ntype") in _skip_ntypes:
                continue
            name = nd.get("name", nid)
            if nd.get("clearance_ok") is False:
                deficit = nd.get("deficit_m", "?")
                has_m = nd.get("min_clearance_m")
                req_m = nd.get("required_clearance_m")
                detail = f"has {has_m}m, needs {req_m}m" if has_m and req_m else f"deficit {deficit}m"
                md = nd.get("move_direction")
                mdist = nd.get("move_distance_m")
                if md and mdist:
                    _findings.append(
                        f"  \033[91mCLEARANCE\033[0m  {name}: {detail} "
                        f"-> move [{md[0]:+.1f},{md[1]:+.1f}] {mdist}m")
                else:
                    _findings.append(f"  \033[91mCLEARANCE\033[0m  {name}: {detail}")
            if nd.get("reachable") is False:
                reasons = []
                if not nd.get("height_ok", True):
                    reasons.append("height")
                if not nd.get("radius_ok", True):
                    reasons.append("radius")
                _findings.append(
                    f"  \033[93mUNREACH \033[0m  {name}: "
                    f"{', '.join(reasons) if reasons else 'blocked'}")
            if nd.get("facing_ok") is False:
                _findings.append(
                    f"  \033[93mFACING  \033[0m  {name}: off by {nd.get('angle_diff', '?')}deg")

        for u, v in [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "blocks"]:
            un = G.nodes[u].get("name", u)
            vn = G.nodes[v].get("name", v)
            _findings.append(f"  \033[91mBLOCKS  \033[0m  {un} blocks {vn}")

        for u, v, d in [(u, v, d) for u, v, d in G.edges(data=True)
                        if d.get("etype") == "path" and not d.get("reachable")]:
            un = G.nodes[u].get("name", u)
            vn = G.nodes[v].get("name", v)
            _findings.append(f"  \033[91mNO PATH \033[0m  {un} -> {vn}: unreachable")

        if _findings:
            print(f"\n\033[1m[enrich_graph] === FINDINGS ({len(_findings)}) ===\033[0m")
            for f in _findings:
                print(f)
            print()
        else:
            print(f"\n\033[92m[enrich_graph] No issues found - all clear\033[0m\n")

        try:
            from visualize_interactive import update_from_enriched_graph as _update_viz
            _viz_path = Path(__file__).parent / "view_graph" / "spatial_graph_interactive.html"
            _carry = set(state.get("viz_highlight_ids") or [])
            _update_viz(G, output_path=_viz_path, extra_new_ids=_carry)
            print(f"\033[36m[viz] Interactive graph updated: {_viz_path}\033[0m")
        except Exception as _e:
            print(f"[viz] Warning: {_e}")

        updates = {
            "spatial_graph": graph_to_dict(G),
            "spatial_graph_text": text,
        }

        # Inject correction message if findings exist and objects were placed this round.
        # The router may send the LLM back to reason — this message tells it what to fix.
        if _findings and state.get("last_placement_result") is not None:
            correction = _build_correction_message(state, G=G)
            if correction:
                updates["messages"] = [{"role": "user", "content": correction}]

        return updates
    except Exception as exc:
        print(f"[enrich_graph] Warning: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Graph wiring — build all nodes, then wire edges and conditional routes.
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    # Build every node from its factory function.
    # Factories receive the dependencies they need (LLM, MCP client, paths)
    # and return a plain callable that accepts and returns AgentState.
    profile_agent    = build_profile_agent_node(ctx.llm, ctx.knowledge_dir)
    space_type_agent = build_space_type_agent_node(ctx.llm, ctx.knowledge_dir)
    query_agent      = build_query_agent_node(ctx.mcp_client)

    def query_end_node(state):
        print("\n[query_agent] Analysis complete — no changes saved.")
        return {}

    def increment_adjustment_node(state):
        return {"adjustment_count": state.get("adjustment_count", 0) + 1}

    populate_agent   = build_populate_agent_node(ctx.llm, ctx.knowledge_dir)
    reason           = build_reason_node(ctx.llm)
    tool             = build_tool_node(ctx.mcp_client, ctx.tools, ctx.workspace_path)
    add_objects      = build_add_objects_node(ctx.mcp_client, ctx.workspace_path)
    visibility       = build_visibility_node(ctx.mcp_client)
    path             = build_path_node(ctx.mcp_client)
    reachability     = build_reachability_node(ctx.mcp_client)
    orientation      = build_orientation_node(ctx.mcp_client)
    collision        = build_collision_node(ctx.mcp_client, ctx.workspace_path)
    scoring          = build_scoring_node()
    user_checkpoint  = build_user_checkpoint_node(ctx.mcp_client)

    graph = StateGraph(AgentState)

    # Register every node so it can be referenced by name in edge wiring.
    graph.add_node("profile_agent",    profile_agent)
    graph.add_node("space_type_agent", space_type_agent)
    graph.add_node("query_agent",      query_agent)
    graph.add_node("query_end",        query_end_node)
    graph.add_node("reason",           reason)
    graph.add_node("increment_adjustment", increment_adjustment_node)
    graph.add_node("populate_agent",   populate_agent)
    graph.add_node("tool",             tool)
    graph.add_node("add_objects",      add_objects)
    graph.add_node("analysis_fan_out", analysis_fan_out_node)
    graph.add_node("visibility",       visibility)
    graph.add_node("path",             path)
    graph.add_node("reachability",     reachability)
    graph.add_node("orientation",      orientation)
    graph.add_node("collision",        collision)
    graph.add_node("group1_join",      group1_join_node)
    graph.add_node("enrich_graph",     enrich_graph_node)
    graph.add_node("scoring",          scoring)
    graph.add_node("user_checkpoint",  user_checkpoint)
    from prompts import POPULATE_COORDS_PROMPT as _COORDS_PROMPT
    from _runtime.llm import call_llm_simple as _call_llm_simple
    import json as _json_z

    _SUPPORT_KW = {"office","meeting","restroom","toilet","utility",
                   "corridor","hallway","stair","server","break",
                   "canteen","lobby","reception"}

    def next_zone_node(state: dict) -> dict:
        zone_queue = list(state.get("zone_queue") or [])
        while zone_queue and any(
            kw in zone_queue[0].get("zone_name","").lower()
            for kw in _SUPPORT_KW
        ):
            print(f"[zone] Skipping support room: {zone_queue[0]['zone_name']}")
            zone_queue = zone_queue[1:]
        if not zone_queue:
            print("[zone] No more functional zones.")
            return {"zone_queue": [], "object_queue": []}
        next_plan = zone_queue[0]
        remaining = zone_queue[1:]
        zone_name = next_plan.get("zone_name", "")
        try:
            layout = _json_z.loads(state.get("layout_json_string", "{}"))
        except Exception:
            layout = {}
        rooms = layout.get("rooms", [])
        room  = next((r for r in rooms if r.get("name") == zone_name), None)
        if not room:
            print(f"[zone] Room '{zone_name}' not found — skipping")
            return next_zone_node({**state, "zone_queue": zone_queue[1:]})
        geom = room.get("geometry", [])
        xs = [p[0] for p in geom]
        ys = [p[1] for p in geom]
        space_config      = state.get("space_config") or {}
        placement_profile = state.get("placement_profile") or {}
        actual_profile    = placement_profile.get("profile_type","standard_worker")
        objects    = next_plan.get("objects", [])
        has_coords = bool(objects) and "objects_list" in objects[0]
        if has_coords:
            zone_placements = objects
        else:
            print(f"[zone] Calculating coordinates for: {zone_name} ({len(objects)} objects)")
            from nodes.populate_agent import calculate_zone_coordinates

            room_summary = {
                "bounds": {
                    "min_x": round(min(xs),2), "max_x": round(max(xs),2),
                    "min_y": round(min(ys),2), "max_y": round(max(ys),2),
                },
                "width": round(max(xs)-min(xs),2),
                "depth": round(max(ys)-min(ys),2),
            }

            doors   = layout.get("doors", [])
            windows = layout.get("windows", [])
            mep     = layout.get("mep", [])

            def _door_mid(d):
                g = d.get("geometry", [])
                if len(g) >= 2: return [(g[0][0]+g[1][0])/2, (g[0][1]+g[1][1])/2]
                return d.get("position", [0, 0])

            def _is_load(d):
                l = (d.get("name","") + d.get("type","")).lower()
                return any(k in l for k in ("load","dock","freight","cargo"))

            door_info = {
                "loading_doors":   [{"name": d.get("name",""), "midpoint": _door_mid(d)} for d in doors if _is_load(d)],
                "personnel_doors": [{"name": d.get("name",""), "midpoint": _door_mid(d)} for d in doors if not _is_load(d)],
            }
            window_midpoints = [
                [(w["geometry"][0][0]+w["geometry"][1][0])/2,
                 (w["geometry"][0][1]+w["geometry"][1][1])/2]
                for w in windows if len(w.get("geometry",[]))>=2
            ]
            mep_info = []
            for m in mep:
                g = m.get("geometry", [])
                if g:
                    mxs = [p[0] for p in g]; mys = [p[1] for p in g]
                    mep_info.append({
                        "name": m.get("name",""),
                        "system": m.get("system",""),
                        "center": [sum(mxs)/len(mxs), sum(mys)/len(mys)],
                    })

            zone_placements = calculate_zone_coordinates(
                ctx.llm,
                zone_name,
                next_plan.get("zone_function", "production"),
                room_summary,
                objects,
                space_config.get("clearance", 1.2),
                actual_profile,
                door_info,
                window_midpoints,
                mep_info,
            )
        if not zone_placements:
            print(f"[zone] No placements for '{zone_name}' — skipping")
            if remaining:
                return next_zone_node({**state, "zone_queue": remaining})
            return {"zone_queue": [], "object_queue": []}
        print(f"[zone_debug] Final zone_placements count: {len(zone_placements)}")
        print(f"[zone_debug] Returning object_queue with {len(zone_placements)} items")
        print(f"[zone] Advancing to: {zone_name} ({len(zone_placements)} objects)")
        return {
            "object_to_place":   {},
            "object_queue":      zone_placements,
            "zone_queue":        remaining,
            "current_zone":      zone_name,
            "user_approved":     None,
            "adjustment_count":  0,
            "placement_history": [],
        }

    graph.add_node("next_zone", next_zone_node)
    graph.add_node("explain",          explain_node)
    graph.add_node("output",           output_node)

    # Pre-agents run sequentially once at startup to classify the layout type
    # and resolve the user accessibility profile before the LLM sees anything.
    graph.add_edge(START, "profile_agent")
    graph.add_edge("profile_agent", "space_type_agent")
    def populate_check_node(state):
        return {}

    graph.add_node("populate_check", populate_check_node)
    graph.add_edge("space_type_agent", "populate_check")

    def _route_after_populate_check(state):
        if state.get("populate_done"):
            return "reason"
        msg = state.get("messages", [])
        if msg:
            last = msg[-1]
            last_msg = last.content if hasattr(last, "content") else last.get("content", "")
        else:
            last_msg = ""
        keywords = ["populate", "fill", "set up", "setup", "generate layout"]
        if any(k in last_msg.lower() for k in keywords):
            return "populate_agent"
        return "reason"

    graph.add_conditional_edges(
        "populate_check", _route_after_populate_check,
        {"populate_agent": "populate_agent", "reason": "reason"},
    )
    graph.add_edge("populate_agent", "reason")

    # Reason routes to: place an object, execute a tool, or move to analysis.
    # "finish" goes to analysis_fan_out which triggers all Group 1 nodes in parallel.
    graph.add_conditional_edges(
        "reason", _route_after_reason,
        {
            "add_objects":    "add_objects",
            "query_agent":    "query_agent",
            "run_tool":       "tool",
            "finish":         "analysis_fan_out",
        },
    )

    # Tool result is fed back to reason so the LLM can interpret it.
    graph.add_edge("tool", "reason")

    # Query agent bypasses placement pipeline — goes to a no-save terminal.
    graph.add_edge("query_agent", "user_checkpoint")
    graph.add_edge("query_end",   END)

    # After a placement, go through the same analysis fan-out node
    # so both paths (placement and direct finish) trigger the same parallel group.
    def _route_after_add_objects(state):
        if state.get("object_queue"):
            return "reason"
        return "analysis_fan_out"

    graph.add_conditional_edges(
        "add_objects", _route_after_add_objects,
        {"reason": "reason", "analysis_fan_out": "analysis_fan_out"}
    )

    # analysis_fan_out fans out to all three Group 1 nodes in parallel.
    graph.add_edge("analysis_fan_out", "collision")
    graph.add_edge("analysis_fan_out", "visibility")
    graph.add_edge("analysis_fan_out", "orientation")

    # Group 1 convergence: all three feed into group1_join so LangGraph
    # waits for all of them before evaluating collision results.
    graph.add_edge("collision",   "group1_join")
    graph.add_edge("visibility",  "group1_join")
    graph.add_edge("orientation", "group1_join")

    # group1_join checks collision results — hard violations route back to reason
    # via increment_adjustment so adjustment_count stays accurate.
    graph.add_conditional_edges(
        "group1_join", _route_after_group1,
        {"adjust": "increment_adjustment", "drain": "reason", "continue": "path"},
    )
    graph.add_edge("increment_adjustment", "reason")

    # Group 2: path → reachability → enrich_graph → routing decision.
    # enrich_graph runs BEFORE _route_after_group2 so the spatial graph has
    # all analysis data when the router (and _build_correction_message) reads it.
    graph.add_edge("path", "reachability")
    graph.add_edge("reachability", "enrich_graph")
    graph.add_conditional_edges(
        "enrich_graph", _route_after_group2,
        {"adjust": "reason", "continue": "scoring"},
    )

    # Scoring aggregates all results and triggers the human approval step.
    graph.add_edge("scoring", "user_checkpoint")

    # Zone advance: after checkpoint approves a zone, load the next one into reason.
    graph.add_edge("next_zone", "reason")

    # User checkpoint: approve → explain → output; otherwise loop back for changes.
    graph.add_conditional_edges(
        "user_checkpoint", _route_after_checkpoint,
        {"approved": "explain", "continue": "reason",
         "query_done": "query_end", "next_zone": "next_zone"},
    )

    # Explain runs once after approval; output writes the file and ends the session.
    graph.add_edge("explain", "output")
    graph.add_edge("output", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point — called from main.py.
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)
    initial_state = _build_initial_state(prompt, ctx)

    # Print the graph topology before running so the wiring is visible
    # in the terminal output before any node executes.
    print("\nWorkflow graph:")
    app.get_graph().print_ascii()
    print()

    final_state = app.invoke(initial_state)

    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError("Agent finished without final response")
    return final_response


# ---------------------------------------------------------------------------
# Helpers — _slim_layout and _format_tool_catalog live in _runtime/utils.py
# ---------------------------------------------------------------------------

def _build_initial_state(prompt: str, ctx: Any) -> AgentState:
    # The user message embeds a slim version of the layout JSON to keep the
    # LLM context lean. But layout_json_string stores the FULL layout because
    # MCP tools (collision-detector-grid, visualize_visibility) need all fields
    # (outline, structure, mep) that _slim_layout strips.

    # Build the initial spatial graph from the base layout (geometry only,
    # no furniture placed yet). Gives the LLM room topology from the first turn.
    from spatial_graph import build_graph_from_layout, graph_to_dict, serialize_for_llm
    _sg = build_graph_from_layout(ctx.layout_data)
    _sg_dict = graph_to_dict(_sg)
    _sg_text = serialize_for_llm(_sg)
    print(f"\n[spatial_graph] Initial graph: {_sg.number_of_nodes()} nodes, "
          f"{_sg.number_of_edges()} edges")
    print(_sg_text)
    try:
        from visualize_interactive import build_interactive_graph as _viz, http_url as _http_url
        _viz_path = Path(__file__).parent / "view_graph" / "spatial_graph_interactive.html"
        _viz(_sg, title=f"Spatial Graph — {ctx.layout_name}", output_path=_viz_path)
        print(f"\033[36m[viz] Interactive graph: {_http_url(_viz_path)}\033[0m")
    except Exception as _e:
        print(f"[viz] Warning: {_e}")

    slim = _slim_layout(ctx.layout_data)
    layout_text = json.dumps(slim, indent=2)
    user_message = (
        f"Space config will be determined by Space Type Agent.\n"
        f"Profile config will be determined by Profile Agent.\n\n"
        f"User request:\n{prompt}\n\n"
        f"Current layout JSON:\n{layout_text}"
    )
    return {
        "messages":              [{"role": "user", "content": user_message}],
        "pending_tool_calls":    None,
        "final_response":        None,
        "iteration":             0,
        "max_iterations":        ctx.max_iterations,
        "tool_catalog":          _format_tool_catalog(ctx.tools),
        "layout_json_string":    json.dumps(ctx.layout_data),
        "workspace_path":        str(ctx.workspace_path),
        "layout_name":           ctx.layout_name,
        "space_config":          None,
        "profile_config":        None,
        "object_to_place":       None,
        "object_queue":          [],
        "last_placement_result": None,
        "visibility_results":    None,
        "path_results":          None,
        "reachability_results":  None,
        "orientation_results":   None,
        "collision_results":     None,
        "scoring_results":       None,
        "evaluation_passed":     None,
        "user_approved":         None,
        "adjustment_count":      0,
        "placement_history":     None,
        "previous_scoring":      None,
        "original_layout":       ctx.layout_data,
        "_llm":                  ctx.llm,
        "_query_mode":           None,
        "spatial_graph":         _sg_dict,
        "spatial_graph_text":    _sg_text,
        "viz_highlight_ids":     [],   # clear highlights on each new request
        "populate_done":         None,
        "placement_profile":     None,
        "zone_queue":            [],
        "current_zone":          None,
    }


