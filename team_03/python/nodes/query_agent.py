from __future__ import annotations
import json
from typing import Any
from nodes.collision import check_collision
from nodes.path_analysis import check_paths
from nodes.reachability import check_reachability


# Keywords that map to specific tools
_COLLISION_KEYS  = ["collision", "clearance", "blocked", "wall", "equipment", "safety"]
_PATH_KEYS       = ["path", "circulation", "route", "corridor", "navigation", "flow"]
_REACH_KEYS      = ["reach", "reachab", "access", "connect"]
_VISIBILITY_KEYS = ["visib", "sightline", "sight line", "line of sight"]


def _detect_tools(prompt: str) -> dict[str, bool]:
    """Detect which tools to run based on user prompt keywords."""
    p = prompt.lower()
    # "all" only triggers run_all when combined with
    # analysis intent — not when used as a quantifier
    # e.g. "all stations" should NOT trigger run_all
    run_all = any(w in p for w in [
        "full analysis", "full layout", "complete analysis",
        "entire layout", "everything", "analyze the layout",
        "analyse the layout", "analyze the full", "analyse the full",
        "run a full", "full check",
    ])
    has_collision    = any(k in p for k in _COLLISION_KEYS)
    has_path         = any(k in p for k in _PATH_KEYS)
    has_reachability = any(k in p for k in _REACH_KEYS)
    has_visibility   = any(k in p for k in _VISIBILITY_KEYS)

    # "only" modifier — if user says "X only", suppress everything else
    only = "only" in p
    if only:
        return {
            "collision":    has_collision,
            "path":         has_path,
            "reachability": has_reachability,
            "visibility":   has_visibility,
        }

    return {
        "collision":    run_all or has_collision,
        "path":         run_all or has_path,
        "reachability": run_all or has_reachability,
        "visibility":   run_all or has_visibility,
    }


def build_query_agent_node(mcp_client):
    """Satellite node — analyze layout without placing objects."""

    def query_agent_node(state: dict) -> dict:
        print("\nQuery agent — analyzing layout without placement...")

        # Extract user prompt
        user_prompt = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, dict):
                role    = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role    = getattr(msg, "type", "")
                content = getattr(msg, "content", "")
            if role in ("user", "human"):
                user_prompt = content
                break

        tools_to_run = _detect_tools(user_prompt)

        # If no specific tool detected, run all
        if not any(tools_to_run.values()):
            tools_to_run = {k: True for k in tools_to_run}

        print(f"  Tools: { {k for k,v in tools_to_run.items() if v} }")

        try:
            layout         = json.loads(state["layout_json_string"])
            profile_config = state.get("profile_config") or {}
            original       = state.get("original_layout")

            lines = ["## Layout Analysis Report", ""]

            # -- Collision -----------------------------------------------
            if tools_to_run["collision"]:
                result  = check_collision(layout, profile_config,
                                          compare_layout=original)
                summary = result.get("summary", {})
                blocked = summary.get("blocked_area_m2", 0)
                w_bl    = summary.get("walls_blocked_m2", 0)
                e_bl    = summary.get("equipment_blocked_m2", 0)
                n_hard  = summary.get("hard_violations", 0)
                new_v   = (result.get("comparison") or {}).get("new_violations", [])

                lines += [
                    "### Collision & Clearance",
                    f"  Hard violations: {n_hard}",
                    f"  Blocked area: {blocked:.2f}m2  [walls: {w_bl:.2f}m2 | equipment: {e_bl:.2f}m2]",
                ]
                if new_v:
                    lines.append(f"  New violations from placed objects: {len(new_v)}")
                    for v in new_v[:3]:
                        lines.append(f"    - {v}")
                lines.append("")

            # -- Path ----------------------------------------------------
            if tools_to_run["path"]:
                result      = check_paths(layout)
                pairs       = result.get("pairs", [])
                total_pairs = len(pairs)
                conn_ok     = result.get("connectivity_ok", True)
                worst       = result.get("worst_case", {})
                avg_dist    = 0
                if pairs:
                    dists    = [p.get("distance", 0) for p in pairs if p.get("distance")]
                    avg_dist = sum(dists) / len(dists) if dists else 0

                lines += [
                    "### Path Efficiency",
                    f"  Pairs checked: {total_pairs}",
                    f"  Connectivity: {'OK' if conn_ok else 'BLOCKED -- some areas unreachable'}",
                ]
                if avg_dist:
                    lines.append(f"  Avg path length: {avg_dist:.2f}m")
                if worst.get("from"):
                    lines.append(
                        f"  Longest path: {worst['from']} -> {worst['to']} "
                        f"({worst.get('distance', '?')}m)"
                    )
                lines.append("")

            # -- Reachability --------------------------------------------
            if tools_to_run["reachability"]:
                result      = check_reachability(layout, profile_config)
                r_sum       = result.get("summary", {})
                reachable   = r_sum.get("reachable", 0)
                total_obj   = r_sum.get("total", 0)
                unreachable = r_sum.get("unreachable_objects", [])

                lines += [
                    "### Reachability",
                    f"  {reachable}/{total_obj} objects reachable",
                ]
                if unreachable:
                    lines.append("  Unreachable:")
                    for obj in unreachable[:5]:
                        name = obj if isinstance(obj, str) else obj.get("name", str(obj))
                        lines.append(f"    - {name}")
                lines.append("")

            # -- Visibility (MCP call -- GH handles this) ----------------
            if tools_to_run["visibility"]:
                try:
                    from nodes.visibility import check_visibility, compute_isovists_for_layout
                    import json as _json
                    _layout = _json.loads(state["layout_json_string"])
                    _sightlines = check_visibility(_layout)
                    _isovists = compute_isovists_for_layout(_layout)
                    _vis_json = _json.dumps({"sightlines": _sightlines, "isovists": _isovists})
                    viz_result = mcp_client.call_tool(
                        "visualize_visibility",
                        {
                            "layout_json": state["layout_json_string"],
                            "visibility_json": _vis_json,
                        }
                    )
                    lines += [
                        "### Visibility",
                        "  Visibility lines drawn in GH viewport",
                        f"  Result: {str(viz_result)[:100]}",
                        "",
                    ]
                except Exception as exc:
                    lines += ["### Visibility",
                              f"  Could not run visibility: {exc}", ""]

            report = "\n".join(lines)
            print(report)

        except Exception as exc:
            print(f"[query_agent] Analysis failed: {exc}")
            report = f"Analysis could not complete: {exc}"

        return_dict = {"final_response": report}
        if tools_to_run.get("collision") and "collision_result" in locals():
            return_dict["collision_results"] = collision_result
        if tools_to_run.get("path") and "path_result" in locals():
            return_dict["path_results"] = path_result
        if tools_to_run.get("reachability") and "reachability_result" in locals():
            return_dict["reachability_results"] = reachability_result
        if tools_to_run.get("visibility") and "_sightlines" in locals():
            return_dict["visibility_results"] = {
                "sightlines": _sightlines,
                "isovists":   _isovists if "_isovists" in locals() else [],
            }
        return return_dict

    return query_agent_node
