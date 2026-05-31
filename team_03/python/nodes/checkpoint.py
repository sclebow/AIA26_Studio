from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any
from _runtime.session import save_session

if TYPE_CHECKING:
    from graph import AgentState


def build_user_checkpoint_node(mcp_client):
    """Return a checkpoint node with access to MCP for viewport toggles.

    The toggle loop uses the lightweight `set_viewport` MCP tool when
    available (draws geometry only, no analysis). Falls back to
    `collision-detector-grid` if `set_viewport` is not registered in GH.
    """

    # Check once at build time whether set_viewport is available.
    # Use a mutable list so the closure can disable it on repeated failures.
    _viewport_state = {"use_set_viewport": False}
    try:
        tools = mcp_client.list_tools()
        if any(t.get("name") == "set_viewport" for t in tools):
            _viewport_state["use_set_viewport"] = True
            print("[checkpoint] set_viewport MCP tool detected — using fast viewport toggle")
    except Exception:
        pass

    def _send_layout_to_viewport(layout_data: dict, profile_config: dict | None,
                                  label: str, mode: str = "all"):
        """Push a layout to the GH viewport.

        Prefers set_viewport (instant, no analysis) over collision-detector-grid
        (runs full collision analysis — slow). Disables set_viewport after a
        timeout so subsequent calls fall back immediately.
        """
        layout_json = json.dumps(layout_data)

        if _viewport_state["use_set_viewport"]:
            try:
                mcp_client.call_tool("set_viewport", {
                    "layout_json": layout_json,
                    "mode": mode,
                }, timeout=10.0)
                print(f"  -> {label} sent to viewport (set_viewport, mode={mode})")
                return
            except Exception as exc:
                _viewport_state["use_set_viewport"] = False
                print(f"  -> set_viewport timed out/failed ({exc})")
                print("  -> Disabled set_viewport for this session — using collision-detector-grid")

        # Fallback: use collision-detector-grid (slower — runs analysis)
        profile = profile_config or {}
        gh_user_type = profile.get("profile_type", "wheelchair_user").replace("_user", "")
        gh_profile = {
            "user_type": gh_user_type,
            "body_width_m": profile.get("body_width", 0.70),
            "min_corridor_width_m": profile.get("min_path_width", 0.90),
            "min_door_width_m": profile.get("min_door_width", 0.85),
            "turning_radius_m": profile.get("turning_radius", 1.50),
        }
        try:
            mcp_client.call_tool("collision-detector-grid", {
                "layout_json": layout_json,
                "user_profile": json.dumps(gh_profile),
                "wall_thickness": 0.20,
            })
            print(f"  -> {label} sent to viewport (collision-detector-grid fallback)")
        except Exception as exc:
            print(f"  -> Failed to send {label}: {exc}")

    def _send_visibility_to_viewport(layout_json_string: str, visibility_results: list | None):
        """Push visibility lines to the GH viewport."""
        if not visibility_results:
            print("  -> No visibility data to display")
            return
        try:
            # Handle both old format (list) and new format (dict)
            if isinstance(visibility_results, list):
                vis_json = json.dumps({
                    "sightlines": visibility_results,
                    "isovists": []
                })
            else:
                vis_json = json.dumps(visibility_results)
            mcp_client.call_tool("visualize_visibility", {
                "layout_json": layout_json_string,
                "visibility_json": vis_json,
            })
            print("  -> Visibility analysis sent to viewport")
        except Exception as exc:
            print(f"  -> Failed to send visibility: {exc}")

    def _send_paths_to_viewport(layout_json_string: str, path_results: dict | None):
        """Push path lines to the GH viewport."""
        if not path_results:
            print("  -> No path data to display")
            return
        try:
            mcp_client.call_tool("visualize_paths", {
                "layout_json": layout_json_string,
                "paths_json": json.dumps(path_results),
            })
            print("  -> Path analysis sent to viewport")
        except Exception as exc:
            print(f"  -> Failed to send paths: {exc}")

    def user_checkpoint_node(state: AgentState) -> dict:
        # Present the current score to the user and let them decide whether to
        # approve the layout or describe further changes.
        # This is the only node that blocks on user input — all other nodes are
        # fully automated.

        # ── Structural integrity check ──────────────────────────────────
        # Verify that doors, windows, structure, and outline haven't been
        # lost during the pipeline. If any are missing, restore from original.
        original = state.get("original_layout") or {}
        current_layout = json.loads(state["layout_json_string"])
        integrity_warnings = []
        restored = False

        for layer in ("doors", "windows", "mep", "structure", "outline"):
            orig_data = original.get(layer)
            curr_data = current_layout.get(layer)
            if orig_data and not curr_data:
                current_layout[layer] = orig_data
                restored = True
                if layer == "outline":
                    integrity_warnings.append(f"  {layer}: RESTORED (was missing)")
                else:
                    integrity_warnings.append(f"  {layer}: RESTORED — {len(orig_data)} items recovered")
            elif isinstance(orig_data, list) and isinstance(curr_data, list):
                if len(curr_data) < len(orig_data):
                    current_layout[layer] = orig_data
                    restored = True
                    integrity_warnings.append(
                        f"  {layer}: RESTORED — had {len(curr_data)}, restored to {len(orig_data)}"
                    )

        if restored:
            save_session(current_layout, state["workspace_path"])
            print("\n[checkpoint] Structural integrity issues detected and fixed:")
            for w in integrity_warnings:
                print(w)

        # ── Door change detection ───────────────────────────────────────
        orig_doors = {d.get("id"): d for d in original.get("doors", [])}
        curr_doors = {d.get("id"): d for d in current_layout.get("doors", [])}
        door_changes = []
        for door_id, orig_door in orig_doors.items():
            curr_door = curr_doors.get(door_id)
            if not curr_door:
                door_changes.append(f"  REMOVED: {orig_door.get('name', door_id)}")
            elif orig_door.get("geometry") != curr_door.get("geometry"):
                door_changes.append(f"  MODIFIED: {orig_door.get('name', door_id)}")
        for door_id in curr_doors:
            if door_id not in orig_doors:
                door_changes.append(f"  ADDED: {curr_doors[door_id].get('name', door_id)}")

        # ── Auto-send current layout to viewport on arrival ───────────
        profile_config = state.get("profile_config")
        try:
            print("\n[checkpoint] Sending current layout to viewport...")
            _send_layout_to_viewport(current_layout, profile_config, "Current layout")
        except Exception as exc:
            print(f"[checkpoint] Viewport auto-send failed ({exc}) — continuing without viewport")

        scoring = state.get("scoring_results") or {}
        score = scoring.get("total_score", 0)
        grade = scoring.get("grade", "?")
        rec   = scoring.get("recommendation", "")
        breakdown = scoring.get("breakdown", {})

        prev_scoring = state.get("previous_scoring") or {}
        prev_score = prev_scoring.get("total_score")
        prev_breakdown = prev_scoring.get("breakdown", {})
        has_previous = prev_score is not None

        # ── ANSI color helpers ──────────────────────────────────────────
        GREEN  = "\033[92m"
        RED    = "\033[91m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        BOLD   = "\033[1m"
        DIM    = "\033[2m"
        RESET  = "\033[0m"

        def _delta_str(current: float, previous: float | None) -> str:
            """Return colored delta string like '▲ +5.2' or '▼ -3.1'."""
            if previous is None:
                return ""
            diff = current - previous
            if abs(diff) < 0.05:
                return f"  {DIM}= no change{RESET}"
            if diff > 0:
                return f"  {GREEN}▲ +{diff:.1f}{RESET}"
            return f"  {RED}▼ {diff:.1f}{RESET}"

        def _score_color(s: float) -> str:
            """Color a score value based on its range."""
            if s >= 80:
                return f"{GREEN}{s:5.1f}{RESET}"
            if s >= 50:
                return f"{YELLOW}{s:5.1f}{RESET}"
            return f"{RED}{s:5.1f}{RESET}"

        # ── Display report ──────────────────────────────────────────────
        print(f"\n{BOLD}{'=' * 60}{RESET}")

        score_display = _score_color(score)
        delta = _delta_str(score, prev_score)
        print(f"{BOLD}LAYOUT SCORE: {score_display}/100  Grade: {grade}{delta}{RESET}")

        if has_previous:
            prev_display = _score_color(prev_score)
            print(f"{DIM}Previous:     {prev_display}/100{RESET}")

        rec_color = GREEN if "approved" in rec.lower() or "pass" in rec.lower() else YELLOW
        print(f"Recommendation: {rec_color}{rec}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        print(f"\n{BOLD}Score breakdown:{RESET}")
        for tool_name, details in breakdown.items():
            s = details.get("score", 0)
            w = details.get("weight", 0)
            ws = details.get("weighted", 0)
            prev_detail = prev_breakdown.get(tool_name, {})
            prev_s = prev_detail.get("score") if has_previous else None
            s_color = _score_color(s)
            delta = _delta_str(s, prev_s)
            print(f"  {tool_name:15s}  {s_color}/100  {DIM}(weight {w:.2f}, +{ws:.2f}){RESET}{delta}")

        collision = state.get("collision_results") or {}
        violations = collision.get("violations", [])
        if violations:
            print(f"\n{RED}{BOLD}Collision violations ({len(violations)}):{RESET}")
            for v in violations[:5]:
                if isinstance(v, str):
                    print(f"  {RED}- {v}{RESET}")
                elif isinstance(v, dict):
                    print(f"  {RED}- {v.get('type', '?')}: {v.get('description', str(v))}{RESET}")

        # ── Zone placement summary ──────────────────────────────────────
        zone_queue   = state.get("zone_queue") or []
        current_zone = state.get("current_zone")
        placement_history = state.get("placement_history") or []
        if placement_history and current_zone:
            zone_items = [p for p in placement_history if p.get("room") == current_zone]
            if zone_items:
                print(f"\n{CYAN}{BOLD}Placed in {current_zone}:{RESET}")
                for item in zone_items:
                    action = "ADDED" if not item.get("from") else "MOVED"
                    color  = GREEN if action == "ADDED" else YELLOW
                    print(f"  {color}{action}{RESET}  {item.get('name')}  "
                          f"at {item.get('to', [0, 0])}")

        history = state.get("placement_history")
        if history:
            print(f"\n{CYAN}{BOLD}Furniture changes made ({len(history)} items):{RESET}")
            for c in history:
                name = c.get("name", "?")
                action = c.get("action", "?")
                room = c.get("room", "?")
                if action == "moved":
                    fr = c.get("from", [0, 0])
                    to = c.get("to", [0, 0])
                    print(f"  {YELLOW}MOVED{RESET}  {name:30s}  ({fr[0]:6.1f}, {fr[1]:6.1f}) -> ({to[0]:6.1f}, {to[1]:6.1f})  {DIM}[{room}]{RESET}")
                else:
                    to = c.get("to", [0, 0])
                    print(f"  {GREEN}ADDED{RESET}  {name:30s}  at ({to[0]:6.1f}, {to[1]:6.1f})  {DIM}[{room}]{RESET}")

        if integrity_warnings:
            print(f"\n{YELLOW}Structural integrity fixes applied:{RESET}")
            for w in integrity_warnings:
                print(f"{YELLOW}{w}{RESET}")

        if door_changes:
            print(f"\n{RED}Door changes detected:{RESET}")
            for dc in door_changes:
                print(f"{RED}{dc}{RESET}")
            print(f"  {DIM}(Review carefully — door modifications may affect accessibility){RESET}")

        # ── Interactive toggle loop ─────────────────────────────────────
        # The user can switch viewport views before approving or requesting
        # changes. Each number sends data to GH via MCP; the viewport
        # updates in real time. Non-numeric input exits the loop.
        has_changes = bool(state.get("placement_history"))

        # ── Generate smart suggestions based on lowest scores ─────────
        suggestions = []
        # Build a simple score map even if breakdown is missing
        score_map = {}
        if breakdown:
            score_map = {k: v.get("score", 100) for k, v in breakdown.items()}
        else:
            # Fallback: infer from raw results if scoring didn't run properly
            if collision.get("pass") is False:
                score_map["collision"] = 40.0
            if state.get("visibility_results"):
                vis = state["visibility_results"]
                if isinstance(vis, list) and vis:
                    avg = sum(1 for v in vis if v.get("visible", True)) / len(vis) * 100
                    score_map["visibility"] = avg

        if score_map:
            sorted_tools = sorted(score_map.items(), key=lambda x: x[1])
            for tool_name, s in sorted_tools:
                if s >= 80:
                    continue  # Only suggest for weak scores
                if tool_name == "collision" and s < 80:
                    # Check what's causing the collision issues
                    objs = collision.get("objects", [])
                    furniture_objs = [o for o in objs if o.get("object_type") == "furniture" and o.get("clearance_violation")]
                    if furniture_objs:
                        worst = sorted(furniture_objs, key=lambda o: o["clearance_violation"].get("blocked_area_m2", 0), reverse=True)
                        names = [o.get("name", "?") for o in worst[:3]]
                        suggestions.append({
                            "key": "s1",
                            "prompt": f"Move {', '.join(names)} away from walls and other furniture to increase clearance to at least {profile_config.get('min_path_width', 0.90) if profile_config else 0.90}m",
                            "label": f"Fix collisions ({', '.join(names[:2])}...)",
                        })
                    else:
                        suggestions.append({
                            "key": "s1",
                            "prompt": "Rearrange furniture to increase corridor clearance and reduce blocked areas",
                            "label": "Fix collision clearance",
                        })
                elif tool_name == "visibility" and s < 80:
                    suggestions.append({
                        "key": "s2",
                        "prompt": "Reposition furniture that blocks line-of-sight between the entrance and key areas. Prioritize clear sightlines from doors to workstations",
                        "label": "Improve visibility / sightlines",
                    })
                elif tool_name == "path" and s < 80:
                    suggestions.append({
                        "key": "s3",
                        "prompt": "Reorganize furniture to create wider, more direct paths between doors and all workstations. Ensure minimum corridor width is maintained throughout",
                        "label": "Improve path accessibility",
                    })
                elif tool_name == "reachability" and s < 80:
                    suggestions.append({
                        "key": "s4",
                        "prompt": "Move furniture blocking access to use points. Ensure every workstation's use_point is reachable from the nearest door without obstruction",
                        "label": "Fix unreachable furniture",
                    })
                elif tool_name == "orientation" and s < 80:
                    suggestions.append({
                        "key": "s5",
                        "prompt": "Rotate or reposition furniture so use points face toward open space and away from walls",
                        "label": "Fix furniture orientation",
                    })

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}Viewport:{RESET}")
        print("  1 = BEFORE layout (original)")
        if has_changes:
            print("  2 = AFTER layout (current)")
        else:
            print(f"  2 = AFTER layout {DIM}(disabled — no changes yet){RESET}")
        print("  3 = + Collision overlay")
        print("  4 = + Visibility overlay")
        print("  5 = + Path overlay")
        print("  0 = Clear overlays (layout only)")

        if not suggestions and score < 80:
            # Generic fallback suggestion when no specific tool analysis matched
            suggestions.append({
                "key": "s1",
                "prompt": "Rearrange furniture to improve overall accessibility. Increase clearance between objects, ensure paths to all use points are unobstructed, and maintain minimum corridor widths",
                "label": "Improve overall accessibility",
            })

        if suggestions:
            print(f"\n{BOLD}Suggestions:{RESET}")
            for sug in suggestions:
                print(f"  {CYAN}{sug['key']}{RESET} = {sug['label']}")

        populate_done = state.get("populate_done")
        if populate_done and zone_queue:
            next_zone_name = zone_queue[0].get("zone_name", "next zone")
            next_count     = len(zone_queue[0].get("objects", []))
            print(f"\n{BOLD}Zone '{current_zone}' complete.{RESET}")
            print(f"Next zone: '{next_zone_name}' ({next_count} objects)")
            print(f"  {GREEN}'yes'{RESET}     -> proceed to next zone")
            print(f"  {GREEN}'end'{RESET}     -> save layout and get final analysis")
            print(f"  anything else -> describe changes to make to this zone")
        elif populate_done and not zone_queue:
            print(f"\n{BOLD}All zones complete — full layout ready.{RESET}")
            print(f"  {GREEN}'end'{RESET}     -> save layout and get final analysis")
            print(f"  anything else -> describe any final changes")
        else:
            print(f"\n{BOLD}Actions:{RESET}")
            print("  'yes'     -> proceed to next zone")
            print("  'end'     -> save layout and get final analysis")
            print("  anything else -> describe changes to make to this zone")
        print(f"{'=' * 60}")
        print()

        # Track which layout is active in the viewport (default: current)
        active_layout = current_layout
        active_label = "AFTER" if has_changes else "CURRENT"

        def _send_collision(layout_data, label):
            """Send layout to collision-detector-grid (always works, shows layout context via clearance mesh)."""
            layout_json = json.dumps(layout_data)
            profile = profile_config or {}
            gh_user_type = profile.get("profile_type", "wheelchair_user").replace("_user", "")
            gh_profile = {
                "user_type": gh_user_type,
                "body_width_m": profile.get("body_width", 0.70),
                "min_corridor_width_m": profile.get("min_path_width", 0.90),
                "min_door_width_m": profile.get("min_door_width", 0.85),
                "turning_radius_m": profile.get("turning_radius", 1.50),
            }
            args = {
                "layout_json": layout_json,
                "user_profile": json.dumps(gh_profile),
                "wall_thickness": 0.20,
            }
            mcp_client.call_tool("collision-detector-grid", args, timeout=30.0)
            print(f"  -> {label} sent to collision-detector-grid")

        while True:
            user_input = input("Your decision: ").strip()

            try:
                if user_input == "1":
                    active_layout = original
                    active_label = "BEFORE"
                    print(f"  Layout: {active_label} (original)")
                    # Try set_viewport first, fall back to collision-detector-grid
                    _send_layout_to_viewport(active_layout, profile_config, active_label)
                    continue
                elif user_input == "2":
                    if not has_changes:
                        print("  -> No changes yet — AFTER not available.")
                        continue
                    active_layout = current_layout
                    active_label = "AFTER"
                    print(f"  Layout: {active_label} (current)")
                    _send_layout_to_viewport(active_layout, profile_config, active_label)
                    continue
                elif user_input == "3":
                    print(f"  {active_label} + Collision overlay")
                    _send_collision(active_layout, active_label)
                    continue
                elif user_input == "4":
                    print(f"  {active_label} + Visibility overlay")
                    # Send collision first as layout base (it always works)
                    _send_collision(active_layout, active_label)
                    _send_visibility_to_viewport(
                        json.dumps(active_layout),
                        state.get("visibility_results"),
                    )
                    continue
                elif user_input == "5":
                    print(f"  {active_label} + Path overlay")
                    _send_collision(active_layout, active_label)
                    _send_paths_to_viewport(
                        json.dumps(active_layout),
                        state.get("path_results"),
                    )
                    continue
                elif user_input == "0":
                    print(f"  Layout only: {active_label}")
                    _send_layout_to_viewport(active_layout, profile_config, active_label)
                    continue
                else:
                    # Check if it's a suggestion key (s1, s2, etc.)
                    matched_sug = next((s for s in suggestions if s["key"] == user_input.lower()), None)
                    if matched_sug:
                        print(f"\n  {CYAN}Applying suggestion: {matched_sug['label']}{RESET}")
                        print(f"  {DIM}> {matched_sug['prompt']}{RESET}\n")
                        user_input = matched_sug["prompt"]
                        break
                    # Not a toggle or suggestion — exit loop as user instruction
                    break
            except Exception as exc:
                print(f"  -> Viewport toggle failed: {exc}")
                continue

        # Build base updates — include restored layout if integrity was fixed.
        # Always snapshot current scoring as previous_scoring so the next
        # checkpoint visit can show the delta.
        updates: dict = {"previous_scoring": scoring}
        if restored:
            updates["layout_json_string"] = json.dumps(current_layout)


        if user_input.lower() in ("approve", "approved", "yes", "ok", "done", "y"):
            if state.get("_query_mode") or not state.get("placement_history"):
                updates["user_approved"] = False
                updates["final_response"] = state.get("final_response", "Analysis complete.")
                return updates
            updates["user_approved"] = True
            updates["messages"] = [{"role": "user", "content": user_input.lower()}]
            return updates

        else:
            updates["user_approved"] = False
            updates["messages"] = [{"role": "user", "content": user_input}]
            updates["iteration"] = 0
            return updates

    return user_checkpoint_node
