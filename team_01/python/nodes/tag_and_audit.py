# =============================================================================
# TAG AND AUDIT
# =============================================================================
# Reads a floor plan JSON, generates structural column/beam layout options.
#
# Standalone : python tag_and_audit.py
# As module  : from nodes.tag_and_audit import generate_structure
#              result = generate_structure(layout_dict)
# =============================================================================

TOLERANCE            = 0.01
MIN_GAP              = 2.5
MIN_GAP_GRID         = 1.49
MAX_GAP              = 5.0
TOO_CLOSE            = 1.5
MID_PROXIMITY        = 1.0
MIN_CHAIN_LEN        = 4.0
MAX_BEAM_FOR_COL     = 2.2
MIN_DIST_PROTECTED   = 1.5
protected_room_names = ["bedroom", "living"]

import json
import os
import math
import string
import itertools
from pathlib import Path
from itertools import product as iproduct

import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from shapely.geometry import LineString, Point, MultiLineString
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import linemerge, unary_union

# =============================================================================
# PURE HELPERS (no dependency on layout data)
# =============================================================================
room_colors = {
    "bedroom": "#C8D8E8", "living": "#E8D8C8", "kitchen": "#D8E8C8",
    "washroom": "#C8E8E0", "utility": "#E0E0D8", "circulation": "#E8E8C8",
    "foyer": "#E8C8D8", "default": "#F0F0F0",
}


def get_color(room_name):
    for k in room_colors:
        if k in room_name.lower():
            return room_colors[k]
    return room_colors["default"]


def key(pt):
    return (round(pt[0], 3), round(pt[1], 3))


def is_corner(p_prev, p_curr, p_next):
    d1 = (p_curr[0]-p_prev[0], p_curr[1]-p_prev[1])
    d2 = (p_next[0]-p_curr[0], p_next[1]-p_curr[1])
    return abs(d1[0]*d2[1] - d1[1]*d2[0]) > TOLERANCE


def edge_direction(u, v):
    return 'h' if abs(u[1] - v[1]) < TOLERANCE else 'v'


def edge_midpoint(u, v):
    return ((u[0]+v[0])/2, (u[1]+v[1])/2)


def get_axis_val(u, v, direction):
    return round(u[1], 3) if direction == 'h' else round(u[0], 3)


def mid_group_val(u, v, direction):
    mid = edge_midpoint(u, v)
    return mid[0] if direction == 'h' else mid[1]


def ray_cast_distance(edge, direction, ref_edges, sign):
    u, v = edge
    mid = edge_midpoint(u, v)
    mid_x, mid_y = mid
    axis_val = get_axis_val(u, v, direction)
    hits = []
    for fu, fv in ref_edges:
        fd = edge_direction(fu, fv)
        if fd != direction:
            continue
        fval = get_axis_val(fu, fv, direction)
        if sign > 0 and fval <= axis_val:
            continue
        if sign < 0 and fval >= axis_val:
            continue
        if direction == 'h':
            if min(fu[0], fv[0]) <= mid_x <= max(fu[0], fv[0]):
                hits.append(abs(fval - axis_val))
        else:
            if min(fu[1], fv[1]) <= mid_y <= max(fu[1], fv[1]):
                hits.append(abs(fval - axis_val))
    return min(hits) if hits else float('inf')


def is_collinear_to_perimeter(edge, perimeter_edges):
    u, v = edge
    d = edge_direction(u, v)
    val = get_axis_val(u, v, d)
    for pu, pv in perimeter_edges:
        if edge_direction(pu, pv) == d and abs(get_axis_val(pu, pv, d) - val) < TOLERANCE:
            return True
    return False


def chain_length(edge, all_wall_edges):
    u, v = edge
    d = edge_direction(u, v)
    val = get_axis_val(u, v, d)
    same = [LineString([eu, ev]) for eu, ev in all_wall_edges
            if edge_direction(eu, ev) == d and abs(get_axis_val(eu, ev, d) - val) < TOLERANCE]
    if not same:
        return LineString([u, v]).length
    if len(same) == 1:
        return same[0].length
    merged = linemerge(unary_union(MultiLineString(same)))
    if merged.geom_type == 'LineString':
        return merged.length
    mid = Point(edge_midpoint(u, v))
    for geom in merged.geoms:
        if geom.distance(mid) < TOLERANCE:
            return geom.length
    return LineString([u, v]).length


def build_graph(edges):
    G = nx.Graph()
    for u, v in edges:
        G.add_edge(u, v)
    return G


def find_open_ends(edges):
    G = build_graph(edges)
    return [n for n in G.nodes() if G.degree(n) == 1]


def node_touches_edge(node, edge):
    u, v = edge
    return (round(u[0], 3), round(u[1], 3)) == node or (round(v[0], 3), round(v[1], 3)) == node


def group_by_mid_proximity(edge_ids, edges_by_id, direction, tolerance):
    sorted_ids = sorted(edge_ids, key=lambda eid: mid_group_val(*edges_by_id[eid], direction))
    clusters = []
    for eid in sorted_ids:
        u, v = edges_by_id[eid]
        mv = mid_group_val(u, v, direction)
        placed = False
        for cluster in clusters:
            for cid in cluster:
                if abs(mv - mid_group_val(*edges_by_id[cid], direction)) <= tolerance:
                    cluster.append(eid)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([eid])
    return clusters


def has_collinear_fixed(edge, direction, fixed_edges):
    u, v = edge
    val = get_axis_val(u, v, direction)
    for fu, fv in fixed_edges:
        if edge_direction(fu, fv) == direction and abs(get_axis_val(fu, fv, direction) - val) < TOLERANCE:
            return True
    return False


def cull_dangling(grid, all_edges):
    culled = set()
    changed = True
    while changed:
        changed = False
        active = [e for e in grid if tuple(sorted(e)) not in culled]
        G = nx.Graph()
        for u, v in all_edges:
            G.add_edge(u, v)
        for u, v in active:
            if tuple(sorted([u, v])) in culled:
                continue
            if G.degree(u) == 1 or G.degree(v) == 1:
                culled.add(tuple(sorted([u, v])))
                changed = True
    return [e for e in grid if tuple(sorted(e)) not in culled]


def cull_grid_direction(edge_ids, edge_id_map, direction, fixed_edges):
    if not edge_ids:
        return set(), []
    cull_ids, opt_groups = set(), []
    clusters = group_by_mid_proximity(edge_ids, edge_id_map, direction, MID_PROXIMITY)
    for cluster in clusters:
        ray_results = {}
        for eid in cluster:
            e = edge_id_map[eid]
            dn = ray_cast_distance(e, direction, fixed_edges, -1)
            dp = ray_cast_distance(e, direction, fixed_edges, +1)
            ray_results[eid] = (dn, dp, dn > MIN_GAP_GRID and dp > MIN_GAP_GRID)
        ray_candidates = [eid for eid in cluster if ray_results[eid][2]]
        for eid in cluster:
            if not ray_results[eid][2]:
                cull_ids.add(eid)
        col_candidates = [eid for eid in ray_candidates
                          if has_collinear_fixed(edge_id_map[eid], direction, fixed_edges)]
        for eid in ray_candidates:
            if eid not in col_candidates:
                cull_ids.add(eid)
        if not col_candidates:
            continue
        col_sorted = sorted(col_candidates, key=lambda eid: get_axis_val(*edge_id_map[eid], direction))
        cand_clusters = []
        for eid in col_sorted:
            val = get_axis_val(*edge_id_map[eid], direction)
            placed = False
            for cc in cand_clusters:
                for ceid in cc:
                    if abs(val - get_axis_val(*edge_id_map[ceid], direction)) < TOO_CLOSE:
                        cc.append(eid)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                cand_clusters.append([eid])
        for cc in cand_clusters:
            if len(cc) == 1:
                continue
            vals = [get_axis_val(*edge_id_map[eid], direction) for eid in cc]
            span = max(vals) - min(vals)
            if span < MAX_GAP:
                opt_groups.append(cc)
            else:
                for eid in cc:
                    if eid not in [col_sorted[0], col_sorted[1]]:
                        cull_ids.add(eid)
                opt_groups.append([col_sorted[0], col_sorted[1]])
    return cull_ids, opt_groups


def find_open_corners(edges, peri_node_set):
    G = build_graph(edges)
    corners = []
    for node in G.nodes():
        if node in peri_node_set:
            continue
        if G.degree(node) != 2:
            continue
        nbrs = list(G.neighbors(node))
        if edge_direction(node, nbrs[0]) != edge_direction(node, nbrs[1]):
            corners.append(node)
    return corners


def is_collinear_deg2(node, G):
    if G.degree(node) != 2:
        return False
    nbrs = list(G.neighbors(node))
    n1, n2 = nbrs[0], nbrs[1]
    same_x = abs(n1[0]-node[0]) < TOLERANCE and abs(n2[0]-node[0]) < TOLERANCE
    same_y = abs(n1[1]-node[1]) < TOLERANCE and abs(n2[1]-node[1]) < TOLERANCE
    return same_x or same_y


def merge_through_node(node, G):
    nbrs = list(G.neighbors(node))
    return (nbrs[0], nbrs[1])


def get_label(idx):
    letters = string.ascii_uppercase
    if idx < 26:
        return letters[idx]
    return letters[idx // 26 - 1] + letters[idx % 26]


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def generate_structure(layout: dict, save_outputs: bool = False, output_dir: str = None) -> dict:
    """
    Generate structural column/beam grid for a layout.
    Returns the layout dict with structure (first option) applied.
    If save_outputs=True, saves all options as PNG+JSON to output_dir.
    """
    if not layout.get("rooms") or not layout.get("outline"):
        print("[tag_and_audit] Layout missing rooms or outline — returning unchanged")
        return layout

    input_stem = layout.get("layoutId", "layout").replace("/", "_").replace(" ", "_")
    print(f"\nAnalysing floor plan: {input_stem}")

    if save_outputs and output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # ── BUILD OUTLINE + GRID ──────────────────────────────────────────────────
    outline_poly = ShapelyPolygon(layout["outline"])

    all_points = set()
    for room in layout["rooms"]:
        for pt in room["geometry"][:-1]:
            all_points.add(key(pt))

    unique_x = sorted(set(pt[0] for pt in all_points))
    unique_y = sorted(set(pt[1] for pt in all_points))

    candidate_columns = []
    for x in unique_x:
        for y in unique_y:
            pt = Point(x, y)
            if outline_poly.contains(pt) or outline_poly.boundary.distance(pt) < TOLERANCE:
                candidate_columns.append((x, y))

    # print(f"  Unique X: {len(unique_x)}  Unique Y: {len(unique_y)}  Candidates: {len(candidate_columns)}")

    # ── COLUMN CLASSIFICATION ─────────────────────────────────────────────────
    room_corners = set(key(pt) for room in layout["rooms"] for pt in room["geometry"][:-1])

    wall_segments = []
    for room in layout["rooms"]:
        pts = room["geometry"][:-1]
        for i in range(len(pts)):
            wall_segments.append(LineString([pts[i], pts[(i+1) % len(pts)]]))

    outline_pts = layout["outline"][:-1]

    perimeter_corner_cols    = []
    collinear_perimeter_cols = []
    wall_corner_cols         = []
    wall_floating_cols       = []

    for pt in candidate_columns:
        p           = Point(pt)
        on_boundary = outline_poly.boundary.distance(p) < TOLERANCE
        is_rc       = pt in room_corners
        on_wall     = any(seg.distance(p) < TOLERANCE for seg in wall_segments)

        if on_boundary:
            matches = [i for i, op in enumerate(outline_pts)
                       if abs(op[0]-pt[0]) < TOLERANCE and abs(op[1]-pt[1]) < TOLERANCE]
            classified = False
            for i in matches:
                p_prev = outline_pts[(i-1) % len(outline_pts)]
                p_curr = outline_pts[i]
                p_next = outline_pts[(i+1) % len(outline_pts)]
                if key(p_prev) == key(p_curr) or key(p_next) == key(p_curr):
                    continue
                if is_corner(p_prev, p_curr, p_next):
                    perimeter_corner_cols.append(pt)
                    classified = True
                    break
            if not classified and is_rc:
                collinear_perimeter_cols.append(pt)
        else:
            if is_rc:
                wall_corner_cols.append(pt)
            elif on_wall:
                wall_floating_cols.append(pt)

    # ── BUILD PRIMAL GRAPH ────────────────────────────────────────────────────
    all_pts = list(set(perimeter_corner_cols) | set(collinear_perimeter_cols) |
                   set(wall_corner_cols)       | set(wall_floating_cols))

    def safe_add_edge(G, a, b):
        mid = LineString([a, b]).interpolate(0.5, normalized=True)
        if outline_poly.contains(mid) or outline_poly.boundary.distance(mid) < TOLERANCE:
            G.add_edge(a, b)

    G_primal = nx.Graph()
    for pt in all_pts:
        G_primal.add_node(pt)

    for pt in all_pts:
        same_x = sorted([n for n in all_pts if abs(n[0]-pt[0]) < TOLERANCE and n != pt],
                        key=lambda n: n[1])
        idx = next((i for i, n in enumerate(same_x) if n[1] > pt[1]), None)
        if idx is not None:
            safe_add_edge(G_primal, pt, same_x[idx])
        if idx is not None and idx > 0:
            safe_add_edge(G_primal, pt, same_x[idx-1])
        elif idx is None and same_x:
            safe_add_edge(G_primal, pt, same_x[-1])

        same_y = sorted([n for n in all_pts if abs(n[1]-pt[1]) < TOLERANCE and n != pt],
                        key=lambda n: n[0])
        idx = next((i for i, n in enumerate(same_y) if n[0] > pt[0]), None)
        if idx is not None:
            safe_add_edge(G_primal, pt, same_y[idx])
        if idx is not None and idx > 0:
            safe_add_edge(G_primal, pt, same_y[idx-1])
        elif idx is None and same_y:
            safe_add_edge(G_primal, pt, same_y[-1])

    # ── EDGE CLASSIFICATION ───────────────────────────────────────────────────
    room_wall_segs_ls = []
    for room in layout["rooms"]:
        pts = room["geometry"][:-1]
        for i in range(len(pts)):
            room_wall_segs_ls.append(LineString([pts[i], pts[(i+1) % len(pts)]]))

    def is_on_perimeter(a, b):
        mid = LineString([a, b]).interpolate(0.5, normalized=True)
        return outline_poly.boundary.distance(mid) < TOLERANCE

    def is_on_room_wall(a, b):
        mid = LineString([a, b]).interpolate(0.5, normalized=True)
        return any(w.distance(mid) < TOLERANCE for w in room_wall_segs_ls)

    perimeter_nodes = set(perimeter_corner_cols) | set(collinear_perimeter_cols)

    base_perimeter_edges = [(u, v) for u, v in G_primal.edges()
                            if u in perimeter_nodes and v in perimeter_nodes]
    base_wall_edges = [(u, v) for u, v in G_primal.edges() if is_on_room_wall(u, v)]

    edge_types = {}
    for u, v in G_primal.edges():
        ek = tuple(sorted([u, v]))
        if is_on_perimeter(u, v):
            edge_types[ek] = 'perimeter'
        elif is_on_room_wall(u, v):
            edge_types[ek] = 'wall'
        else:
            edge_types[ek] = 'grid'

    grid_edge_dict = {ek: ek for ek, t in edge_types.items() if t == 'grid'}

    # ── WALL CULLING ──────────────────────────────────────────────────────────
    perimeter_edges_list = list(base_perimeter_edges)
    wall_edges_list      = list(base_wall_edges)

    fixed_wall, candidate_wall = [], []
    for edge in wall_edges_list:
        if is_collinear_to_perimeter(edge, perimeter_edges_list):
            fixed_wall.append(edge)
        elif chain_length(edge, wall_edges_list) >= MIN_CHAIN_LEN:
            fixed_wall.append(edge)
        else:
            candidate_wall.append(edge)

    ref_edges = perimeter_edges_list + wall_edges_list
    ray_res = {}
    for i, edge in enumerate(candidate_wall):
        d = edge_direction(*edge)
        dn = ray_cast_distance(edge, d, ref_edges, -1)
        dp = ray_cast_distance(edge, d, ref_edges, +1)
        ray_res[i] = (dn, dp, dn > MIN_GAP and dp > MIN_GAP)

    initial_culled = {i for i, r in ray_res.items() if not r[2]}
    recheck_ref    = perimeter_edges_list + fixed_wall + \
                     [e for i, e in enumerate(candidate_wall) if i not in initial_culled]

    final_wall_keep = {}
    for i, edge in enumerate(candidate_wall):
        if i in initial_culled:
            final_wall_keep[i] = False
            continue
        d  = edge_direction(*edge)
        dn = ray_cast_distance(edge, d, recheck_ref, -1)
        dp = ray_cast_distance(edge, d, recheck_ref, +1)
        final_wall_keep[i] = dn > MIN_GAP and dp > MIN_GAP

    kept_candidates = [e for i, e in enumerate(candidate_wall) if final_wall_keep.get(i, False)]
    culled_wall     = [e for i, e in enumerate(candidate_wall) if not final_wall_keep.get(i, False)]
    base_wall       = fixed_wall + kept_candidates

    open_ends = find_open_ends(perimeter_edges_list + base_wall)
    open_end_fixes = {}
    for node in open_ends:
        fixers = [e for e in culled_wall if node_touches_edge(node, e)]
        if fixers:
            open_end_fixes[node] = fixers

    all_opt_groups_wall, all_forced_wall = [], []
    for node, fixers in open_end_fixes.items():
        if len(fixers) == 1:
            all_forced_wall.append(fixers[0])
        else:
            all_opt_groups_wall.append(fixers)

    def build_wall_layout(choices={}):
        extra = list(all_forced_wall)
        for gi, group in enumerate(all_opt_groups_wall):
            extra.append(choices.get(gi, group[0]))
        return base_wall + extra

    if all_opt_groups_wall:
        combos       = list(itertools.islice(iproduct(*all_opt_groups_wall), 5))
        wall_options = [build_wall_layout({i: c[i] for i in range(len(all_opt_groups_wall))})
                        for c in combos]
    else:
        wall_options = [build_wall_layout()]

    final_perimeter_edges = {tuple(sorted(e)): e for e in perimeter_edges_list}
    final_grid_edges      = dict(grid_edge_dict)

    # ── OPEN CORNER FIX ───────────────────────────────────────────────────────
    perimeter_node_set = set()
    for u, v in base_perimeter_edges:
        perimeter_node_set.add((round(u[0], 3), round(u[1], 3)))
        perimeter_node_set.add((round(v[0], 3), round(v[1], 3)))

    final_wall_options = []
    for wall_opt in wall_options:
        all_edges_opt = base_perimeter_edges + wall_opt
        corners       = find_open_corners(all_edges_opt, perimeter_node_set)
        in_use        = set(tuple(sorted(e)) for e in all_edges_opt)

        corner_opt_groups, corner_forced = [], []
        for node in corners:
            touching = []
            for edge in base_wall_edges:
                u, v = edge
                un = (round(u[0], 3), round(u[1], 3))
                vn = (round(v[0], 3), round(v[1], 3))
                if un == node or vn == node:
                    touching.append((un, vn))
            not_in_use = [e for e in touching if tuple(sorted(e)) not in in_use]
            if not not_in_use:
                continue
            if len(not_in_use) == 1:
                corner_forced.append(not_in_use[0])
            else:
                corner_opt_groups.append(not_in_use)

        def build_fixed(base, forced, choices={}):
            extra = list(forced)
            for gi, group in enumerate(corner_opt_groups):
                extra.append(choices.get(gi, group[0]))
            return base + extra

        if corner_opt_groups:
            combos   = list(itertools.islice(iproduct(*corner_opt_groups), 5))
            expanded = [build_fixed(wall_opt, corner_forced,
                                    {i: c[i] for i in range(len(corner_opt_groups))})
                        for c in combos]
        else:
            expanded = [build_fixed(wall_opt, corner_forced)]
        final_wall_options.extend(expanded)

    seen_keys, unique_opts = [], []
    for opt in final_wall_options:
        k = frozenset(tuple(sorted(e)) for e in opt)
        if k not in seen_keys:
            seen_keys.append(k)
            unique_opts.append(opt)
    wall_options = unique_opts

    # ── GRID CULLING ──────────────────────────────────────────────────────────
    def run_grid_culling(wall_opt):
        fixed_w = list(final_perimeter_edges.values()) + wall_opt
        all_w   = fixed_w + list(final_grid_edges.values())
        active  = cull_dangling(list(final_grid_edges.values()), all_w)
        id_map  = {i: e for i, e in enumerate(active)}
        h_ids   = [i for i, e in id_map.items() if edge_direction(*e) == 'h']
        v_ids   = [i for i, e in id_map.items() if edge_direction(*e) == 'v']

        h_cull, h_opts = cull_grid_direction(h_ids, id_map, 'h', fixed_w)
        v_cull, v_opts = cull_grid_direction(v_ids, id_map, 'v', fixed_w)

        all_cull = h_cull | v_cull
        all_opts = h_opts + v_opts

        def build_grid(choices={}):
            kept = []
            for eid, e in id_map.items():
                if eid in all_cull:
                    continue
                in_group = False
                for gi, group in enumerate(all_opts):
                    if eid in group:
                        in_group = True
                        if eid == choices.get(gi, group[0]):
                            kept.append(e)
                        break
                if not in_group:
                    kept.append(e)
            return kept

        if all_opts:
            combos = list(itertools.islice(iproduct(*[g for g in all_opts]), 5))
            return [build_grid({i: c[i] for i in range(len(all_opts))}) for c in combos]
        return [build_grid({})]

    all_layout_options = []
    for wall_idx, wall_opt in enumerate(wall_options):
        for grid_idx, grid_opt in enumerate(run_grid_culling(wall_opt)):
            all_layout_options.append((wall_idx, grid_idx, wall_opt, grid_opt))

    # print(f"  Layout combinations: {len(all_layout_options)}")

    # ── COLUMN CULLING + FINALISATION ─────────────────────────────────────────
    perimeter_node_set = set()
    for u, v in final_perimeter_edges.values():
        perimeter_node_set.add((round(u[0], 3), round(u[1], 3)))
        perimeter_node_set.add((round(v[0], 3), round(v[1], 3)))

    protected_nodes = set()
    for room in layout["rooms"]:
        if any(pn in room["name"].lower() for pn in protected_room_names):
            for pt in room["geometry"][:-1]:
                protected_nodes.add((round(pt[0], 3), round(pt[1], 3)))

    anchor_nodes = perimeter_node_set | protected_nodes
    final_layouts = []

    for wall_idx, grid_idx, wall_opt, grid_opt in all_layout_options:
        final_kept = list(final_perimeter_edges.values()) + wall_opt + grid_opt

        G_final = nx.Graph()
        for u, v in final_kept:
            G_final.add_edge((round(u[0], 3), round(u[1], 3)),
                             (round(v[0], 3), round(v[1], 3)))

        cull_nodes = set()
        for node in G_final.nodes():
            if node in set(perimeter_corner_cols):
                continue
            if is_collinear_deg2(node, G_final):
                cull_nodes.add(node)

        cleaned_edges = set()
        for u, v in G_final.edges():
            if u in cull_nodes or v in cull_nodes:
                continue
            cleaned_edges.add(tuple(sorted([u, v])))

        for node in cull_nodes:
            u, v = merge_through_node(node, G_final)
            while u in cull_nodes:
                nbrs = list(G_final.neighbors(u))
                u = nbrs[0] if nbrs[1] == node else nbrs[1]
            while v in cull_nodes:
                nbrs = list(G_final.neighbors(v))
                v = nbrs[0] if nbrs[1] == node else nbrs[1]
            if u != v:
                cleaned_edges.add(tuple(sorted([u, v])))

        G_clean = nx.Graph()
        for u, v in cleaned_edges:
            G_clean.add_edge(u, v)

        col_cull = set()
        for node in G_clean.nodes():
            if node in perimeter_node_set or node in protected_nodes:
                continue
            if G_clean.degree(node) >= 4:
                continue
            nbrs = list(G_clean.neighbors(node))
            if max(math.dist(node, nb) for nb in nbrs) >= MAX_BEAM_FOR_COL:
                continue
            if min(math.dist(node, a) for a in anchor_nodes) >= MIN_DIST_PROTECTED:
                continue
            col_cull.add(node)

        final_layouts.append({
            'wall_idx'   : wall_idx,
            'grid_idx'   : grid_idx,
            'beam_edges' : list(cleaned_edges),
            'columns'    : set(G_clean.nodes()) - col_cull,
            'culled_cols': col_cull,
        })

    # print(f"  Final layouts: {len(final_layouts)}")

    if not final_layouts:
        print("[tag_and_audit] No layouts generated — returning unchanged")
        return layout

    # ── NAMING ────────────────────────────────────────────────────────────────
    all_col_nodes = set()
    for ld in final_layouts:
        all_col_nodes |= ld['columns']

    all_x_vals = sorted(set(round(pt[0], 3) for pt in all_col_nodes))
    all_y_vals = sorted(set(round(pt[1], 3) for pt in all_col_nodes))
    x_label = {x: get_label(i) for i, x in enumerate(all_x_vals)}
    y_label = {y: str(i+1)     for i, y in enumerate(all_y_vals)}

    def get_col_name(pt):
        return f"{x_label.get(round(pt[0], 3), '?')}{y_label.get(round(pt[1], 3), '?')}"

    # ── BUILD STRUCTURE + OPTIONAL SAVE ──────────────────────────────────────
    all_outputs = []

    for opt_idx, ld in enumerate(final_layouts):
        columns    = ld['columns']
        beam_edges = ld['beam_edges']

        structure = []
        for pt in sorted(columns):
            col_name = get_col_name(pt)
            col_type = 'perimeter' if pt in perimeter_node_set else 'internal'
            structure.append({
                "id"        : col_name,
                "name"      : f"Col_{col_name}",
                "geometry"  : [[pt[0], pt[1]]],
                "attributes": {"type": col_type, "material": None, "conflict": None},
            })

        for u, v in sorted(beam_edges):
            beam_name = f"{get_col_name(u)}-{get_col_name(v)}"
            beam_type = 'perimeter' if (u in perimeter_node_set and v in perimeter_node_set) else 'internal'
            structure.append({
                "id"        : beam_name,
                "name"      : f"Beam_{beam_name}",
                "geometry"  : [[u[0], u[1]], [v[0], v[1]]],
                "attributes": {
                    "type": beam_type, "length": round(math.dist(u, v), 3),
                    "isWallAligned": None, "structuralRole": None,
                    "material": None, "conflict": None,
                    "depth": None, "width": None, "section": None,
                },
            })

        output_json = {**layout, "structure": structure}
        all_outputs.append(output_json)
        n_cols  = sum(1 for s in structure if len(s['geometry']) == 1)
        n_beams = sum(1 for s in structure if len(s['geometry']) == 2)
        max_span = max((s["attributes"]["length"] for s in structure
                        if len(s["geometry"]) == 2 and s["attributes"].get("length")), default=0)
        print(f"  Option {opt_idx+1}: {n_cols} columns · {n_beams} beams · max span {round(max_span, 2)}m")

        if save_outputs and output_dir:
            n_cols  = sum(1 for s in structure if len(s['geometry']) == 1)
            n_beams = sum(1 for s in structure if len(s['geometry']) == 2)

            fig, ax = plt.subplots(figsize=(16, 12))
            for room in layout["rooms"]:
                poly = ShapelyPolygon(room["geometry"])
                x, y = poly.exterior.xy
                ax.fill(x, y, color=get_color(room["name"]), alpha=0.3)
                cx, cy = poly.centroid.x, poly.centroid.y
                ax.text(cx, cy, room["name"], fontsize=7, ha="center", va="center", color="#444")
            for x in unique_x:
                ax.axvline(x=x, color="#cccccc", linewidth=0.6, linestyle="--")
            for y in unique_y:
                ax.axhline(y=y, color="#cccccc", linewidth=0.6, linestyle="--")
            for s in structure:
                if len(s['geometry']) == 2:
                    u, v = s['geometry'][0], s['geometry'][1]
                    ax.plot([u[0], v[0]], [u[1], v[1]], color="#444444", linewidth=1.5, zorder=3)
                    mx, my = (u[0]+v[0])/2, (u[1]+v[1])/2
                    ax.text(mx, my, s['id'], fontsize=8, ha="center", va="center",
                            color="#666666", zorder=4,
                            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6))
            for s in structure:
                if len(s['geometry']) == 1:
                    pt    = tuple(s['geometry'][0])
                    color = "#E74C3C" if s['attributes']['type'] == 'perimeter' else "#3A7FD5"
                    ax.scatter(pt[0], pt[1], color=color, s=100, zorder=6)
                    ax.text(pt[0], pt[1]-0.15, s['id'], fontsize=9, ha="center", va="top",
                            color=color, zorder=7, fontweight='bold')
            for pt in ld['culled_cols']:
                ax.scatter(pt[0], pt[1], color="#cccccc", s=40, zorder=5)
            ax.scatter([], [], color="#E74C3C", s=100, label="Perimeter columns")
            ax.scatter([], [], color="#3A7FD5", s=100, label="Internal columns")
            ax.scatter([], [], color="#cccccc", s=40,  label=f"No column ({len(ld['culled_cols'])})")
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.invert_yaxis()
            ax.legend(loc="lower right", fontsize=8)
            ax.set_title(f"Option {opt_idx+1} — {n_cols} columns · {n_beams} beams")
            plt.tight_layout(pad=3.0)
            ax.set_xlim(min(unique_x)-1, max(unique_x)+1)
            ax.set_ylim(min(unique_y)-1, max(unique_y)+1)
            png_path = os.path.join(output_dir, f"{input_stem}_op{opt_idx+1}.png")
            plt.savefig(png_path, dpi=150, bbox_inches='tight')
            plt.close()
            json_path = os.path.join(output_dir, f"{input_stem}_op{opt_idx+1}.json")
            with open(json_path, 'w') as f:
                json.dump(output_json, f, indent=2)
            print(f"  Saved: {png_path}  ({n_cols}c · {n_beams}b)")

    print(f"  {len(all_outputs)} structural option(s) ready for {input_stem}")
    return all_outputs


# =============================================================================
# STANDALONE ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    _this_dir  = Path(__file__).parent
    input_path = str(_this_dir / "../../gh/other layouts/layout_2bhk.json")
    output_dir = str(_this_dir / "../../output")

    with open(input_path, "r") as f:
        layout_data = json.load(f)

    options = generate_structure(layout_data, save_outputs=True, output_dir=output_dir)
    print(f"\nDone — {len(options)} options, {len(options[0].get('structure', []))} structural elements in option 1")
