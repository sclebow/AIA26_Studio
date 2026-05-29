"""
Spatial relationship graph for the accessibility agent.

Builds a NetworkX MultiGraph from the layout JSON where nodes are actionable
elements (rooms, doors, furniture, mep) and edges encode spatial, functional,
and analysis-derived relationships.  The graph lives inside the LangGraph
AgentState as a JSON-serializable dict and is serialized to compact text for
LLM consumption.

Pure module — no LangGraph, MCP, or LLM dependencies.
"""

import json
import math
from typing import Any

import networkx as nx


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _centroid(geometry: list[list[float]]) -> tuple[float, float] | None:
    """Return the centroid (avg x, avg y) of a polygon or line."""
    if not geometry:
        return None
    xs = [pt[0] for pt in geometry]
    ys = [pt[1] for pt in geometry]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _line_length(geometry: list[list[float]]) -> float:
    """Length of a 2-point line segment (doors, windows)."""
    if not geometry or len(geometry) < 2:
        return 0.0
    return _distance(tuple(geometry[0]), tuple(geometry[1]))


def _bbox_dims(geometry: list[list[float]]) -> tuple[float, float]:
    """Return (width, depth) of bounding box."""
    if not geometry:
        return (0.0, 0.0)
    xs = [pt[0] for pt in geometry]
    ys = [pt[1] for pt in geometry]
    return (max(xs) - min(xs), max(ys) - min(ys))


def _point_to_segment_distance(
    px: float, py: float,
    x1: float, y1: float, x2: float, y2: float,
) -> float:
    """Shortest distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return _distance((px, py), (x1, y1))
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    return _distance((px, py), (x1 + t * dx, y1 + t * dy))


# ---------------------------------------------------------------------------
# Graph construction from layout JSON
# ---------------------------------------------------------------------------

NEAR_THRESHOLD_M = 3.0  # max distance for "near" edges between furniture


def build_graph_from_layout(layout: dict) -> nx.MultiGraph:
    """Build the structural spatial graph from a layout dict.

    Nodes: rooms, doors, walls, windows, furniture, mep.
    Edges: contained_in, door_connects, adjacent, near, near_wall, near_window.
    """
    G = nx.MultiGraph()

    # --- Rooms ---
    for room in layout.get("rooms", []):
        rid = room.get("id")
        if not rid:
            continue
        center = _centroid(room.get("geometry", []))
        G.add_node(rid,
                   ntype="room",
                   name=room.get("name", rid),
                   area=room.get("attributes", {}).get("area", 0),
                   center=center)

    # --- Doors ---
    for door in layout.get("doors", []):
        did = door.get("id")
        if not did:
            continue
        width = round(_line_length(door.get("geometry", [])), 2)
        connects = door.get("attributes", {}).get("connectsRooms", [])
        G.add_node(did,
                   ntype="door",
                   name=door.get("name", did),
                   width=width,
                   connects=connects)

        # door_connects edges
        for room_id in connects:
            if room_id in G and G.nodes[room_id].get("ntype") == "room":
                G.add_edge(did, room_id, etype="door_connects")

        # adjacent edges between rooms connected by this door
        room_ids = [r for r in connects if r in G and G.nodes[r].get("ntype") == "room"]
        if len(room_ids) >= 2:
            G.add_edge(room_ids[0], room_ids[1],
                       etype="adjacent",
                       via_door=did,
                       door_width=width)

    # --- Furniture ---
    for furn in layout.get("furniture", []):
        fid = furn.get("id")
        if not fid:
            continue
        geom = furn.get("geometry", [])
        center = _centroid(geom)
        bbox_w, bbox_d = _bbox_dims(geom)
        room_id = furn.get("attributes", {}).get("roomId", "")

        G.add_node(fid,
                   ntype="furniture",
                   name=furn.get("name", fid),
                   roomId=room_id,
                   center=center,
                   bbox_w=round(bbox_w, 2),
                   bbox_d=round(bbox_d, 2))

        # contained_in edge
        if room_id and room_id in G:
            G.add_edge(fid, room_id, etype="contained_in")

    # --- MEP ---
    for mep in layout.get("mep", []):
        mid = mep.get("id")
        if not mid:
            continue
        center = _centroid(mep.get("geometry", []))
        room_id = mep.get("attributes", {}).get("roomId", "")
        system = mep.get("attributes", {}).get("system", "unknown")

        G.add_node(mid,
                   ntype="mep",
                   name=mep.get("name", mid),
                   system=system,
                   roomId=room_id,
                   center=center)

        if room_id and room_id in G:
            G.add_edge(mid, room_id, etype="contained_in")

    # --- Structure (walls) ---
    for wall in layout.get("structure", []):
        wid = wall.get("id")
        if not wid:
            continue
        geom = wall.get("geometry", [])
        center = _centroid(geom)
        length = round(_line_length(geom), 2)
        attrs = wall.get("attributes", {})
        p1 = geom[0] if len(geom) >= 1 else None
        p2 = geom[1] if len(geom) >= 2 else None
        G.add_node(wid,
                   ntype="wall",
                   name=wall.get("name", wid),
                   wall_type=attrs.get("type", "unknown"),
                   material=attrs.get("material", "unknown"),
                   center=center,
                   length=length,
                   p1=p1, p2=p2)

    # --- Windows ---
    for window in layout.get("windows", []):
        wid = window.get("id")
        if not wid:
            continue
        geom = window.get("geometry", [])
        center = _centroid(geom)
        width = round(_line_length(geom), 2)
        room_id = window.get("attributes", {}).get("roomId", "")
        p1 = geom[0] if len(geom) >= 1 else None
        p2 = geom[1] if len(geom) >= 2 else None
        G.add_node(wid,
                   ntype="window",
                   name=window.get("name", wid),
                   window_type=window.get("type", "unknown"),
                   roomId=room_id,
                   center=center,
                   width=width,
                   p1=p1, p2=p2)
        if room_id and room_id in G:
            G.add_edge(wid, room_id, etype="contained_in")

    # --- Near edges ---
    furn_nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == "furniture"]
    wall_nodes = [(n, G.nodes[n]) for n in G if G.nodes[n].get("ntype") == "wall"]
    win_nodes  = [(n, G.nodes[n]) for n in G if G.nodes[n].get("ntype") == "window"]

    # furniture-to-furniture (same room, centroid distance)
    for i, n1 in enumerate(furn_nodes):
        d1 = G.nodes[n1]
        c1 = d1.get("center")
        r1 = d1.get("roomId")
        if not c1 or not r1:
            continue
        for n2 in furn_nodes[i + 1:]:
            d2 = G.nodes[n2]
            c2 = d2.get("center")
            r2 = d2.get("roomId")
            if not c2 or r1 != r2:
                continue
            dist = round(_distance(c1, c2), 2)
            if dist <= NEAR_THRESHOLD_M:
                G.add_edge(n1, n2, etype="near", distance_m=dist)

    # furniture-to-wall (point-to-segment distance)
    for fid in furn_nodes:
        fc = G.nodes[fid].get("center")
        if not fc:
            continue
        for wid, wd in wall_nodes:
            wp1, wp2 = wd.get("p1"), wd.get("p2")
            if not wp1 or not wp2:
                continue
            dist = round(_point_to_segment_distance(
                fc[0], fc[1], wp1[0], wp1[1], wp2[0], wp2[1]), 2)
            if dist <= NEAR_THRESHOLD_M:
                G.add_edge(fid, wid, etype="near_wall", distance_m=dist)

    # furniture-to-window (point-to-segment, same room only)
    for fid in furn_nodes:
        fd = G.nodes[fid]
        fc = fd.get("center")
        fr = fd.get("roomId")
        if not fc:
            continue
        for wid, wd in win_nodes:
            wr = wd.get("roomId")
            if fr and wr and fr != wr:
                continue
            wp1, wp2 = wd.get("p1"), wd.get("p2")
            if not wp1 or not wp2:
                continue
            dist = round(_point_to_segment_distance(
                fc[0], fc[1], wp1[0], wp1[1], wp2[0], wp2[1]), 2)
            if dist <= NEAR_THRESHOLD_M:
                G.add_edge(fid, wid, etype="near_window", distance_m=dist)

    return G


# ---------------------------------------------------------------------------
# Enrich graph with analysis tool results
# ---------------------------------------------------------------------------

def enrich_graph_from_analysis(
    G: nx.MultiGraph,
    collision_results: dict | None,
    visibility_results: list | None,
    path_results: dict | None,
    reachability_results: dict | None,
    orientation_results: dict | None,
) -> nx.MultiGraph:
    """Add edges and node attributes from the 5 analysis tools."""

    # --- Collision ---
    # Skip walls — they are structural (not movable) and their
    # "clearance" is just wall thickness, not an actionable issue.
    _skip_ntypes = {"wall"}
    if collision_results and isinstance(collision_results, dict):
        for obj in collision_results.get("objects", []):
            oid = obj.get("id")
            if not oid or oid not in G:
                continue
            if G.nodes[oid].get("ntype") in _skip_ntypes:
                continue

            cv = obj.get("clearance_violation")
            if cv:
                deficit = round(cv.get("deficit_m", 0), 2)
                G.nodes[oid]["clearance_ok"] = deficit <= 0
                G.nodes[oid]["deficit_m"] = deficit
                G.nodes[oid]["min_clearance_m"] = round(cv.get("min_clearance_m", 0), 2)
                G.nodes[oid]["required_clearance_m"] = round(cv.get("required_m", 0), 2)
            else:
                G.nodes[oid]["clearance_ok"] = True

            upa = obj.get("use_point_analysis")
            if upa:
                ms = upa.get("move_suggestion")
                if ms:
                    G.nodes[oid]["move_direction"] = ms.get("direction")
                    G.nodes[oid]["move_distance_m"] = round(ms.get("distance_m", 0), 2)

            # Fallback: if no move_suggestion from use_point_analysis,
            # compute a direction toward the room center (away from walls).
            if cv and "move_direction" not in G.nodes[oid]:
                room_id = G.nodes[oid].get("roomId")
                obj_center = G.nodes[oid].get("center")
                if room_id and room_id in G and obj_center:
                    room_center = G.nodes[room_id].get("center")
                    if room_center:
                        dx = room_center[0] - obj_center[0]
                        dy = room_center[1] - obj_center[1]
                        mag = (dx**2 + dy**2) ** 0.5
                        if mag > 0.01:
                            deficit = cv.get("deficit_m", 0.3)
                            G.nodes[oid]["move_direction"] = [round(dx/mag, 3), round(dy/mag, 3)]
                            G.nodes[oid]["move_distance_m"] = round(deficit + 0.1, 2)

            fla = obj.get("functional_line_analysis")
            if fla and fla.get("blocked"):
                blocker = fla.get("blocking_object_id")
                if blocker and blocker in G:
                    G.add_edge(blocker, oid, etype="blocks")

    # --- Visibility ---
    if visibility_results and isinstance(visibility_results, list):
        for vis in visibility_results:
            src = vis.get("source")
            tgt = vis.get("target")
            if not src or not tgt:
                continue
            src_node = _find_node(G, src)
            tgt_node = _find_node(G, tgt)
            if src_node and tgt_node:
                visible = vis.get("visible_seated", False) or vis.get("visible_standing", False)
                G.add_edge(src_node, tgt_node,
                           etype="sightline",
                           visible=visible,
                           blocked_by=vis.get("blocked_by"))

    # --- Path ---
    if path_results and isinstance(path_results, dict):
        for pair in path_results.get("pairs", []):
            src = pair.get("source")
            tgt = pair.get("target")
            if not src or not tgt:
                continue
            src_node = _find_node(G, src)
            tgt_node = _find_node(G, tgt)
            if src_node and tgt_node:
                G.add_edge(src_node, tgt_node,
                           etype="path",
                           distance_m=round(pair.get("distance", 0), 2),
                           reachable=pair.get("status") == "reachable")

    # --- Reachability ---
    if reachability_results and isinstance(reachability_results, dict):
        for res in reachability_results.get("results", []):
            oid = res.get("object_id")
            node = _find_node(G, oid) if oid else None
            if node:
                G.nodes[node]["reachable"] = res.get("reachable", True)
                G.nodes[node]["height_ok"] = res.get("height_ok", True)
                G.nodes[node]["radius_ok"] = res.get("radius_ok", True)

    # --- Orientation ---
    if orientation_results and isinstance(orientation_results, dict):
        for res in orientation_results.get("results", []):
            oid = res.get("object_id")
            node = _find_node(G, oid) if oid else None
            if node:
                G.nodes[node]["facing_ok"] = res.get("facing_ok", True)
                G.nodes[node]["angle_diff"] = round(res.get("angle_diff", 0), 1)

    return G


def _find_node(G: nx.MultiGraph, identifier: str) -> str | None:
    """Find a node by id or by name attribute."""
    if not identifier:
        return None
    if identifier in G:
        return identifier
    # Search by name
    for nid, data in G.nodes(data=True):
        if data.get("name") == identifier:
            return nid
    return None


# ---------------------------------------------------------------------------
# Serialization for LangGraph state transport
# ---------------------------------------------------------------------------

def graph_to_dict(G: nx.MultiGraph) -> dict:
    """Convert nx.MultiGraph to a JSON-serializable dict."""
    return nx.node_link_data(G)


def dict_to_graph(data: dict) -> nx.MultiGraph:
    """Restore nx.MultiGraph from a node-link dict."""
    return nx.node_link_graph(data)


# ---------------------------------------------------------------------------
# Compact text serialization for LLM context
# ---------------------------------------------------------------------------

MAX_SERIALIZE_LINES = 50


def serialize_for_llm(G: nx.MultiGraph) -> str:
    """Produce a compact text representation of the spatial graph for the LLM."""
    lines: list[str] = []
    nodes_data = dict(G.nodes(data=True))

    # Header
    lines.append(f"SPATIAL GRAPH ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)")
    lines.append("")

    # --- Rooms ---
    rooms = [(nid, d) for nid, d in nodes_data.items() if d.get("ntype") == "room"]
    if rooms:
        lines.append("ROOMS:")
        for rid, rd in rooms:
            area = rd.get("area", "?")
            lines.append(f"  {rid} \"{rd.get('name', rid)}\" area={area}m2")

    # --- Connectivity (adjacent room pairs via doors) ---
    adj_edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("etype") == "adjacent"]
    if adj_edges:
        lines.append("CONNECTIVITY:")
        for u, v, d in adj_edges:
            door_id = d.get("via_door", "?")
            dw = d.get("door_width", "?")
            uname = nodes_data.get(u, {}).get("name", u)
            vname = nodes_data.get(v, {}).get("name", v)
            lines.append(f"  {uname} <--{door_id}({dw}m)--> {vname}")

    # --- Structure (walls) ---
    walls = [(nid, d) for nid, d in nodes_data.items() if d.get("ntype") == "wall"]
    if walls:
        lines.append("STRUCTURE:")
        for wid, wd in walls:
            wtype = wd.get("wall_type", "?")
            length = wd.get("length", "?")
            lines.append(f"  {wid} \"{wd.get('name', wid)}\" {wtype} {length}m")

    # --- Windows (compact: grouped by room) ---
    win_nodes_ser = [(nid, d) for nid, d in nodes_data.items() if d.get("ntype") == "window"]
    if win_nodes_ser:
        by_room_w: dict[str, list] = {}
        for wid, wd in win_nodes_ser:
            rm = wd.get("roomId", "unassigned")
            rname = nodes_data.get(rm, {}).get("name", rm) if rm in nodes_data else rm
            by_room_w.setdefault(rname, []).append(wd)
        parts_w = []
        for rn, wins in by_room_w.items():
            types: dict[str, int] = {}
            for w in wins:
                t = w.get("window_type", "?")
                types[t] = types.get(t, 0) + 1
            type_str = ", ".join(f"{c}x {t}" for t, c in types.items())
            parts_w.append(f"{rn}: {len(wins)} ({type_str})")
        lines.append(f"WINDOWS: {'; '.join(parts_w)}")

    # --- Furniture grouped by room ---
    furn_nodes = [(nid, d) for nid, d in nodes_data.items() if d.get("ntype") == "furniture"]
    if furn_nodes:
        by_room: dict[str, list] = {}
        for fid, fd in furn_nodes:
            rm = fd.get("roomId", "unassigned")
            room_name = nodes_data.get(rm, {}).get("name", rm) if rm in nodes_data else rm
            by_room.setdefault(room_name, []).append((fid, fd))

        for room_name, items in by_room.items():
            lines.append(f"FURNITURE in {room_name}:")
            for fid, fd in items:
                center = fd.get("center")
                pos_str = f"at({center[0]:.1f},{center[1]:.1f})" if center else "at(?)"
                parts = [f"  {fid} \"{fd.get('name', fid)}\" {pos_str}"]

                # Analysis attributes (only if present)
                if "clearance_ok" in fd:
                    if fd["clearance_ok"]:
                        parts.append("clearance=OK")
                    else:
                        deficit = fd.get("deficit_m", "?")
                        parts.append(f"clearance=FAIL(-{deficit}m)")
                if "reachable" in fd:
                    parts.append(f"reachable={'YES' if fd['reachable'] else 'NO'}")
                if "facing_ok" in fd:
                    parts.append(f"facing={'OK' if fd['facing_ok'] else 'WRONG'}")

                lines.append(" ".join(parts))

    # --- MEP ---
    mep_nodes = [(nid, d) for nid, d in nodes_data.items() if d.get("ntype") == "mep"]
    if mep_nodes:
        lines.append("MEP:")
        for mid, md in mep_nodes:
            lines.append(f"  {mid} \"{md.get('name', mid)}\" system={md.get('system', '?')}")

    # --- Relations (near/adjacent only — sightline and path omitted for brevity) ---
    relation_types = {"near", "adjacent"}
    rel_edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("etype") in relation_types]
    if rel_edges:
        lines.append("RELATIONS:")
        for u, v, d in rel_edges:
            uname = nodes_data.get(u, {}).get("name", u)
            vname = nodes_data.get(v, {}).get("name", v)
            etype = d.get("etype")

            if etype == "near":
                lines.append(f"  {uname} --near({d.get('distance_m', '?')}m)--> {vname}")
            elif etype == "adjacent":
                door_id = d.get("via_door", "?")
                dw = d.get("door_width", "?")
                lines.append(f"  {uname} --adjacent({door_id},{dw}m)--> {vname}")

    # --- Issues (actionable problems) ---
    issues: list[str] = []
    for nid, nd in nodes_data.items():
        if nd.get("ntype") not in ("furniture", "mep"):
            continue
        name = nd.get("name", nid)

        if nd.get("clearance_ok") is False:
            md = nd.get("move_direction")
            mdist = nd.get("move_distance_m")
            deficit = nd.get("deficit_m", "?")
            has_m = nd.get("min_clearance_m")
            req_m = nd.get("required_clearance_m")
            detail = f"has {has_m}m, needs {req_m}m" if has_m and req_m else f"deficit {deficit}m"
            if md and mdist:
                issues.append(
                    f"  {name}: move [{md[0]:+.1f},{md[1]:+.1f}] {mdist}m "
                    f"to fix clearance ({detail})")
            else:
                issues.append(f"  {name}: clearance violation ({detail}) -- reposition away from walls")

        if nd.get("reachable") is False:
            reasons = []
            if not nd.get("height_ok", True):
                reasons.append("height")
            if not nd.get("radius_ok", True):
                reasons.append("radius")
            issues.append(f"  {name}: unreachable ({', '.join(reasons) if reasons else 'check position'})")

        if nd.get("facing_ok") is False:
            issues.append(f"  {name}: facing wrong (off by {nd.get('angle_diff', '?')}deg)")

    if issues:
        lines.append("ISSUES:")
        lines.extend(issues)

    # Truncate if too long
    if len(lines) > MAX_SERIALIZE_LINES:
        lines = lines[:MAX_SERIALIZE_LINES - 1]
        lines.append("  ... (truncated)")

    return "\n".join(lines)
