"""
Quick smoke test for bootstrap + visibility.
Run: python test_bootstrap.py --layout industrial_03
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from _runtime.bootstrap import bootstrap
from nodes.visibility import check_visibility, build_visibility_node
from nodes.path_analysis import check_paths, build_path_node
from nodes.reachability import check_reachability
from nodes.orientation import check_orientation
from nodes.collision import check_collision, build_collision_node
from nodes.scoring import compute_scores


def main():
    # Test that graph.py imports without errors
    from graph import build_graph, run_agent
    print("graph.py imports OK")

    ctx = bootstrap()
    data = ctx.layout_data

    # Build the graph and print its structure to verify all nodes and edges are
    # wired correctly before running the full test. This makes it easy to catch
    # missing nodes or broken edge definitions without executing the whole workflow.
    app = build_graph(ctx)
    print("\nGraph structure:")
    app.get_graph().print_ascii()
    print()

    layout_name = data.get("layoutId") or data.get("name") or data.get("id") or "(unnamed)"
    rooms = data.get("rooms", [])
    room_names = [r.get("name") or r.get("id") or "(unknown)" for r in rooms]

    print(f"\nLayout:      {layout_name}")
    print(f"Rooms found: {len(rooms)}")
    print("Room names:")
    for name in room_names:
        print(f"  - {name}")

    print(f"\nMCP tools discovered: {len(ctx.tools)}")
    for t in ctx.tools:
        print(f"  - {t.get('name')}")
    print("\nMCP connection: OK")

    # --- Visibility check ---
    print("\n--- Visibility Analysis ---")
    pairs = check_visibility(data)
    print(f"Pairs checked: {len(pairs)}\n")
    for p in pairs:
        seated   = "YES" if p["visible_seated"]   else "NO"
        standing = "YES" if p["visible_standing"]  else "NO"
        blocker  = p["blocked_by"] or "-"
        print(
            f"  {p['source']:20s} ->{p['target']:20s} | "
            f"seated={seated:3s}  standing={standing:3s}  blocked_by={blocker}"
        )

    # --- Visibility node (MCP push) ---
    print("\n--- Visibility Node (push to GH) ---")
    state = {
        "iteration": 0,
        "max_iterations": ctx.max_iterations,
        "layout_json_string": json.dumps(data),
        "messages": [],
        "visibility_results": None,
    }
    visibility_node = build_visibility_node(ctx.mcp_client)
    state = visibility_node(state)
    print(f"Results stored in state: {len(state['visibility_results'])} pairs")

    # --- Path Analysis ---
    print("\n--- Path Analysis ---")
    path_results = check_paths(data)
    has_furniture = bool(data.get("objects") or data.get("furniture"))
    mode = "object level" if has_furniture else "room level"
    pairs = path_results.get("pairs", [])
    worst = path_results.get("worst_case", {})

    print(f"Mode:         {mode}")
    print(f"Pairs checked: {len(pairs)}")
    if worst.get("from"):
        print(f"Worst case:   {worst['from']} ->{worst['to']}, {worst['distance']}m")
    else:
        print("Worst case:   n/a")

    print("First 5 pairs:")
    for p in pairs[:5]:
        print(
            f"  {p['source']:20s} ->{p['target']:20s} | "
            f"steps: {p['steps']:3d} | distance: {p['distance']}m | {p['status']}"
        )

    # --- Path Node (MCP push) ---
    print("\n--- Path Node (push to GH) ---")
    state["iteration"] = 0
    state["path_results"] = None
    path_node = build_path_node(ctx.mcp_client)
    state = path_node(state)
    print(f"Results stored in state: {len(state['path_results'].get('pairs', []))} pairs")

    # --- Reachability Analysis ---
    print("\n--- Reachability Analysis ---")
    reach_output = check_reachability(data)
    summary = reach_output["summary"]
    reach_results = reach_output["results"]

    print(f"Total objects checked: {summary['total']}")
    print(f"Reachable:             {summary['reachable']}")
    print(f"Unreachable:           {summary['unreachable']}")
    if summary["unreachable_objects"]:
        print("Unreachable objects:")
        for name in summary["unreachable_objects"]:
            print(f"  - {name}")
    else:
        print("Unreachable objects:   none")

    print("\nFirst 5 results:")
    for r in reach_results[:5]:
        reach   = "YES" if r["reachable"] else "NO"
        h_ok    = "YES" if r["height_ok"] else "NO"
        rad_ok  = "YES" if r["radius_ok"] else "NO"
        height  = f"{r['functional_point_height']}m" if r["functional_point_height"] is not None else "n/a"
        dist    = f"{r['distance_to_functional']}m"  if r["distance_to_functional"]  is not None else "n/a"
        print(
            f"  {r['name']:25s} | reachable={reach:3s} | "
            f"height_ok={h_ok:3s} | radius_ok={rad_ok:3s} | "
            f"height={height:8s} | dist={dist}"
        )

    # --- Orientation Analysis ---
    # Note: industrial_005 has no orientation fields — total=0 is expected
    print("\n--- Orientation Analysis ---")
    orient_output = check_orientation(data)
    orient_summary = orient_output["summary"]

    print(f"Total checked:  {orient_summary['total']}")
    print(f"Facing ok:      {orient_summary['facing_ok']}")
    print(f"Facing wrong:   {orient_summary['facing_wrong']}")
    print(f"Skipped:        {orient_summary['skipped']}")
    if orient_summary["wrong_objects"]:
        print("Wrong objects:")
        for name in orient_summary["wrong_objects"]:
            print(f"  - {name}")

    # --- Collision Analysis ---
    # Tests the collision tool directly against the loaded layout before the
    # full LangGraph is wired. No profile_config → defaults to wheelchair profile.
    print("\n--- Collision Analysis ---")
    collision_result = check_collision(data)
    coll_summary = collision_result["summary"]

    status = "PASS" if collision_result["pass"] else "FAIL"
    print(f"Status:           {status}")
    print(f"Hard violations:  {coll_summary['hard_violations']}")
    print(f"Total violations: {coll_summary['total_violations']}")
    print(f"Blocked area:     {coll_summary['blocked_area_m2']} m²")
    print(f"Warning area:     {coll_summary['warning_area_m2']} m²")

    violations = collision_result.get("violations", [])
    if violations:
        print("First 3 violations:")
        for v in violations[:3]:
            print(f"  - {v}")

    objects_with_violations = collision_result.get("objects", [])
    if objects_with_violations:
        print("First 3 objects with violations:")
        for obj in objects_with_violations[:3]:
            cv = obj.get("clearance_violation") or {}
            blocked = cv.get("blocked_cells", 0)
            min_cl  = cv.get("min_clearance_m", "n/a")
            print(
                f"  {obj['name']:25s} | type={obj['type']:12s} | "
                f"blocked_cells={blocked:4d} | min_clearance={min_cl}m"
            )

    # --- Collision Node (push to GH) ---
    # Pushes collision results to Grasshopper for visualization via MCP.
    # Mirrors how the graph node runs — GH must be open and Swiftlet running.
    print("\n--- Collision Node (push to GH) ---")
    state["iteration"] = 0
    state["collision_results"] = None
    collision_node = build_collision_node(ctx.mcp_client, ctx.workspace_path)
    state = collision_node(state)
    print(f"Results stored in state: pass={state['collision_results']['pass']}, "
          f"hard_violations={state['collision_results']['summary']['hard_violations']}")

    # --- Scoring ---
    # Aggregates all tool results into a single weighted score and letter grade.
    # Runs after every analysis node has populated state so the breakdown
    # reflects the full picture — no MCP call needed, pure Python.
    print("\n--- Scoring ---")
    score_result = compute_scores(
        visibility_results   = state.get("visibility_results"),
        path_results         = state.get("path_results"),
        reachability_results = state.get("reachability_results"),
        orientation_results  = state.get("orientation_results"),
        collision_results    = state.get("collision_results"),
        space_config         = None,
    )
    print(f"Total score:     {score_result['total_score']} / 100")
    print(f"Grade:           {score_result['grade']}")
    print(f"Recommendation:  {score_result['recommendation']}")
    print("Breakdown:")
    for tool, bd in score_result["breakdown"].items():
        print(
            f"  {tool:13s}  score={bd['score']:5.1f}  "
            f"weight={bd['weight']:.2f}  weighted={bd['weighted']:.2f}"
        )

    # --- Place Objects Test ---
    # Manual smoke test: sends a real place_objects call to Grasshopper via MCP
    # and verifies the tool is reachable before the full graph is wired.
    # GH must be open and Swiftlet running — this draws a box in Rhino if it works.
    print("\n--- Place Objects Test ---")
    # Test 1 — place one object using the JSON array format the new GH script expects.
    # objects_list is now a JSON string containing a list of dicts, not a colon-separated string.
    # A box should appear in Rhino at [5.0, 3.0] inside Clean Room if GH is listening.
    try:
        place_result = ctx.mcp_client.call_tool("place_objects", {
            "layout_json": json.dumps(ctx.layout_data),
            "room_name": "Clean Room",
            "objects_list": json.dumps([
                {
                    "name": "assembly_station",
                    "position": [5.0, 3.0],
                    "size": [2.0, 1.5, 1.0]
                }
            ]),
            "user_profile": "standard",
            "clear_room": False,
        })
        print(f"Raw result: {place_result}")
        print("place_objects: OK")
    except Exception as e:
        print(f"place_objects: FAILED — {e}")

    # Test 2 — clear all objects from Clean Room by sending an empty list with clear_room=True.
    # Verifies that GH correctly removes previously placed geometry when asked to start fresh.
    try:
        clear_result = ctx.mcp_client.call_tool("place_objects", {
            "layout_json": json.dumps(ctx.layout_data),
            "room_name": "Clean Room",
            "objects_list": json.dumps([]),
            "user_profile": "standard",
            "clear_room": True,
        })
        print(f"Raw result: {clear_result}")
        print("clear test: OK")
    except Exception as e:
        print(f"clear test: FAILED — {e}")

    # --- Session Test ---
    # Verify that bootstrap correctly wired up the session paths and that
    # create_session() wrote session_active.json to workspace/.
    print("\n--- Session Test ---")

    # Confirm the paths bootstrap resolved and stored in Context
    print(f"workspace_path:  {ctx.workspace_path}")
    print(f"output_path:     {ctx.output_path}")
    print(f"layout_name:     {ctx.layout_name}")

    # session_active.json must exist after bootstrap — if it doesn't,
    # create_session() failed silently or workspace_path is wrong
    session_file = ctx.workspace_path / "session_active.json"
    print(f"session_active.json exists: {session_file.exists()}")

    # Confirm the loaded layout_data actually matches the requested layout file —
    # a mismatch here means the wrong JSON was copied into the session
    loaded_layout_id = ctx.layout_data.get("layoutId") or ctx.layout_data.get("id") or "(no layoutId field)"
    print(f"layoutId in session:  {loaded_layout_id}")

    ctx.mcp_client.close()


if __name__ == "__main__":
    main()
