from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import call_llm_simple
from prompts import POPULATE_PLAN_PROMPT

_DEFAULT_PLACEMENT_PROFILE = "standard_worker"


def calculate_zone_coordinates(
    llm, zone_name, zone_function, room_summary, objects,
    clearance_m, actual_profile, door_info, window_midpoints, mep_info
):
    """Calculate x,y coordinates for a zone's objects. Returns list of placement dicts."""
    import json
    from prompts import POPULATE_COORDS_PROMPT
    from _runtime.llm import call_llm_simple

    coords_input = json.dumps({
        "zone_name":         zone_name,
        "zone_function":     zone_function,
        "room_bounds":       room_summary["bounds"],
        "room_width":        room_summary["width"],
        "room_depth":        room_summary["depth"],
        "objects":           objects,
        "clearance_m":       clearance_m,
        "placement_profile": actual_profile,
        "doors":             door_info,
        "windows":           window_midpoints,
        "mep":               mep_info,
    }, indent=2)

    result = call_llm_simple(llm, POPULATE_COORDS_PROMPT, coords_input)
    placements = []
    if result and isinstance(result, dict):
        placements = result.get("placements", [])

    normalized = []
    for p in placements:
        objects_list = p.get("objects_list", "")
        if objects_list and objects_list.strip().startswith("["):
            try:
                items = json.loads(objects_list)
                if isinstance(items, list):
                    for item in items:
                        name = item.get("name", "object")
                        pos  = item.get("position", [0, 0])
                        size = item.get("size", [1.0, 1.0, 0.9])
                        w, d, h = size[0], size[1], size[2]
                        normalized.append({
                            "room_name":    zone_name,
                            "objects_list": f"{name}:{w}x{d}x{h}:x={pos[0]},y={pos[1]}",
                            "user_profile": actual_profile,
                            "clear_room":   False,
                        })
                    continue
            except Exception:
                pass
        if objects_list and ":" in objects_list and "x=" in objects_list:
            p["user_profile"] = actual_profile
            if not p.get("room_name"):
                p["room_name"] = zone_name
            normalized.append(p)

    return normalized


def build_populate_agent_node(llm: Any, knowledge_dir: Path):
    """Return a LangGraph node that generates a full placement queue from a workflow pattern."""

    def populate_agent_node(state: dict) -> dict:
        print("\n[populate_agent] Building full placement plan...")

        # Load workflow patterns
        patterns_path = knowledge_dir / "industrial" / "workflow_patterns.json"
        try:
            patterns = json.loads(patterns_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[populate_agent] Could not load workflow_patterns.json: {exc}")
            return {}

        # Match space_config["space_type"] to the closest pattern key
        space_config = state.get("space_config") or {}
        space_type   = space_config.get("space_type", "workshop").lower()

        matched_pattern = None
        matched_key     = None
        for pt_key, pt_variants in patterns.items():
            if pt_key in space_type or space_type in pt_key:
                matched_pattern = next(iter(pt_variants.values()))
                matched_key     = pt_key
                break

        if not matched_pattern:
            matched_pattern = next(iter(patterns.get("workshop", {}).values()), {})
            matched_key     = "workshop"
            print(f"[populate_agent] No pattern for '{space_type}' — defaulting to workshop")

        # Parse layout geometry
        try:
            layout = json.loads(state.get("layout_json_string", "{}"))
        except Exception:
            layout = {}

        rooms     = layout.get("rooms", [])
        doors     = layout.get("doors", [])
        mep_items = layout.get("mep", [])
        windows   = layout.get("windows", [])

        # Compact room bounds
        room_summaries = []
        for room in rooms:
            geom = room.get("geometry", [])
            if not geom:
                continue
            xs = [p[0] for p in geom]
            ys = [p[1] for p in geom]
            room_summaries.append({
                "name":  room.get("name", ""),
                "id":    room.get("id", ""),
                "bounds": {
                    "min_x": round(min(xs), 2), "max_x": round(max(xs), 2),
                    "min_y": round(min(ys), 2), "max_y": round(max(ys), 2),
                },
                "width": round(max(xs) - min(xs), 2),
                "depth": round(max(ys) - min(ys), 2),
            })

        # Categorise doors by type
        def _is_loading(door: dict) -> bool:
            label = (door.get("name", "") + door.get("type", "") + door.get("id", "")).lower()
            return any(kw in label for kw in ("load", "dock", "freight", "cargo"))

        def _door_midpoint(door: dict) -> list[float]:
            geom = door.get("geometry", [])
            if len(geom) >= 2:
                return [round((geom[0][0] + geom[1][0]) / 2, 2),
                        round((geom[0][1] + geom[1][1]) / 2, 2)]
            pos = door.get("position", [0, 0])
            return [round(pos[0], 2), round(pos[1], 2)]

        door_info = {
            "loading_doors":   [{"name": d.get("name", ""), "midpoint": _door_midpoint(d)}
                                 for d in doors if _is_loading(d)],
            "personnel_doors": [{"name": d.get("name", ""), "midpoint": _door_midpoint(d)}
                                 for d in doors if not _is_loading(d)],
        }

        # Window midpoints for tall-rack avoidance
        window_midpoints = []
        for w in windows:
            geom = w.get("geometry", [])
            if len(geom) >= 2:
                window_midpoints.append([round((geom[0][0] + geom[1][0]) / 2, 2),
                                         round((geom[0][1] + geom[1][1]) / 2, 2)])

        # MEP element centres
        mep_info = []
        for m in mep_items:
            geom = m.get("geometry", [])
            if geom:
                xs = [p[0] for p in geom]
                ys = [p[1] for p in geom]
                mep_info.append({
                    "name":   m.get("name", ""),
                    "system": m.get("system", m.get("type", "")),
                    "center": [round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2)],
                })

        # Build readable room list for LLM
        room_list_text = "AVAILABLE ROOMS (use these exact names in your output):\n"
        for r in room_summaries:
            area = round(r["width"] * r["depth"], 1)
            room_list_text += f'  - "{r["name"]}" ({r["width"]}m x {r["depth"]}m, area={area}m²)\n'
        print(room_list_text)

        # Resolve placement profile — use the pre-sanitized placement_profile set
        # by profile_agent (vehicle profiles already stripped to standard_worker).
        placement_profile = state.get("placement_profile") or {}
        actual_profile    = placement_profile.get("profile_type", _DEFAULT_PLACEMENT_PROFILE)

        real_room_names = [r.get("name", "") for r in rooms if r.get("name")]

        # Phase 1 — Plan: what goes where (no coordinates)
        print("[populate_agent] Phase 1: planning zone distribution...")
        plan_input = json.dumps({
            "room_list_readable": room_list_text,
            "rooms":              room_summaries,
            "space_config":       space_config,
            "workflow_pattern":   matched_pattern,
            "matched_type":       matched_key,
        }, indent=2)

        plan_result = call_llm_simple(llm, POPULATE_PLAN_PROMPT, plan_input)
        zone_plan = []
        if plan_result and isinstance(plan_result, dict):
            zone_plan = plan_result.get("plan", [])

        if not zone_plan:
            print("[populate_agent] Warning: no plan generated.")
            return {"populate_done": True}

        print(f"[populate_agent] Phase 1 complete: {len(zone_plan)} zones planned")
        for z in zone_plan:
            print(f"  - {z.get('zone_name')}: {len(z.get('objects', []))} objects "
                  f"({z.get('zone_function')})")

        SUPPORT_KEYWORDS = {"office", "meeting", "restroom", "toilet",
                            "utility", "corridor", "hallway", "stair",
                            "server", "break", "canteen", "lobby", "reception"}

        def _is_support(zone_name: str) -> bool:
            name_lower = zone_name.lower()
            return any(kw in name_lower for kw in SUPPORT_KEYWORDS)

        # Filter support rooms from plan entirely
        zone_plan = [z for z in zone_plan if not _is_support(z.get("zone_name", ""))]

        if not zone_plan:
            print("[populate_agent] No functional zones in plan.")
            return {"populate_done": True}

        # Phase 2 — only calculate coordinates for FIRST zone
        print("[populate_agent] Phase 2: calculating coordinates for first zone...")
        first_zone_plan  = zone_plan[0]
        remaining_plans  = zone_plan[1:]  # stored as plans, no coordinates yet

        zone_name = first_zone_plan.get("zone_name", "")
        room = next((r for r in room_summaries if r["name"] == zone_name), None)

        if not room:
            print(f"[populate_agent] First zone '{zone_name}' not found — aborting")
            return {"populate_done": True}

        zone_placements = calculate_zone_coordinates(
            llm, zone_name, first_zone_plan.get("zone_function"),
            room, first_zone_plan.get("objects", []),
            space_config.get("clearance", 1.2), actual_profile,
            door_info, window_midpoints, mep_info
        )

        if not zone_placements:
            print(f"[populate_agent] No coordinates for '{zone_name}' — aborting")
            return {"populate_done": True}

        for p in zone_placements:
            if p.get("room_name") not in real_room_names:
                p["room_name"] = zone_name

        print(f"  - {zone_name}: {len(zone_placements)} objects with coordinates")
        print(f"  - {len(remaining_plans)} zones queued as plans")

        return {
            "object_to_place": {},
            "object_queue":    zone_placements,
            "zone_queue":      remaining_plans,
            "current_zone":    zone_name,
            "populate_done":   True,
        }

    return populate_agent_node