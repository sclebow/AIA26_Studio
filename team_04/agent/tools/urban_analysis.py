"""Phase 2b — Urban Analysis Engine

Classifies intersection types, corner conditions, access opportunities, and
generates architectural response recommendations for any site.

Works with OSM-fetched data (osm_context.py) and the synthetic road objects
used throughout the existing test suite.  Builds on top of the Phase 2
``road_context.analyze_roads`` result already stored in ``site_model["roads"]``.

Public API
----------
full_urban_analysis(site_model, roads=None, intersections=None) -> dict
    Master function: complete urban analysis in one call.

detect_intersections_from_roads(roads, snap_dist_m=3.0) -> list
    Geometrically find where road centrelines cross or nearly meet.

classify_site_type(frontages, near_intersections, site_model) -> str
    One of: corner | crossroads_corner | t_junction_terminal | y_junction |
    triangular_corner | linear | back_parcel | cul_de_sac | complex.

generate_urban_response(site_type, frontages, near_intersections, corner_conditions) -> dict
    Structured architectural guidance keyed to the site type.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon

# ---------------------------------------------------------------------------
# Site type taxonomy
# ---------------------------------------------------------------------------

SITE_TYPE_LABELS: dict[str, str] = {
    "corner":               "Corner Site",
    "crossroads_corner":    "Crossroads Corner",
    "t_junction_terminal":  "T-Junction Terminal (Focal Terminus)",
    "y_junction":           "Y-Junction",
    "triangular_corner":    "Triangular Corner",
    "linear":               "Linear Street Frontage",
    "back_parcel":          "Back Parcel (No Direct Frontage)",
    "cul_de_sac":           "Cul-de-Sac",
    "complex":              "Complex Multi-Road Site",
}

_HIER_RANK: dict[str, int] = {"main": 3, "secondary": 2, "path": 1}


# ---------------------------------------------------------------------------
# Intersection detection from road geometry
# ---------------------------------------------------------------------------

def detect_intersections_from_roads(
    roads: list[dict[str, Any]],
    snap_dist_m: float = 3.0,
) -> list[dict[str, Any]]:
    """Return intersection dicts for all points where 2+ road centrelines meet.

    Uses pairwise Shapely intersection + endpoint snap.  Deduplicates results
    within ``snap_dist_m * 4`` of each other.
    """
    lines: list[tuple[int, LineString]] = []
    for i, r in enumerate(roads):
        try:
            ls = LineString(r["centerline"])
            if ls.length > 0:
                lines.append((i, ls))
        except Exception:
            continue

    raw: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, int]] = set()

    def _snap_key(x: float, y: float) -> tuple[int, int]:
        k = snap_dist_m or 1.0
        return (round(x / k), round(y / k))

    def _add(x: float, y: float, ri: int, rj: int) -> None:
        key = _snap_key(x, y)
        if key not in seen_keys:
            seen_keys.add(key)
            raw.append({"point": [round(x, 2), round(y, 2)], "_ri": ri, "_rj": rj})

    for i, (ri, li) in enumerate(lines):
        for j, (rj, lj) in enumerate(lines[i + 1:], i + 1):
            geom = None
            try:
                if li.intersects(lj):
                    geom = li.intersection(lj)
            except Exception:
                pass

            if geom is not None:
                if geom.geom_type == "Point":
                    _add(geom.x, geom.y, ri, rj)
                elif geom.geom_type == "MultiPoint":
                    for pt in geom.geoms:
                        _add(pt.x, pt.y, ri, rj)
                elif "Line" in geom.geom_type:
                    c = geom.centroid
                    _add(c.x, c.y, ri, rj)
            else:
                # Check if endpoints are within snap distance
                for ep in (lj.coords[0], lj.coords[-1]):
                    if li.distance(Point(ep)) < snap_dist_m:
                        _add(ep[0], ep[1], ri, rj)

    # Group raw points into clusters and compute the arm count for each cluster.
    result: list[dict[str, Any]] = []
    used: set[int] = set()
    for i, pt_dict in enumerate(raw):
        if i in used:
            continue
        cluster = [i]
        for j, other in enumerate(raw[i + 1:], i + 1):
            dist = math.hypot(
                pt_dict["point"][0] - other["point"][0],
                pt_dict["point"][1] - other["point"][1],
            )
            if dist < snap_dist_m * 4:
                cluster.append(j)
                used.add(j)

        cx = sum(raw[k]["point"][0] for k in cluster) / len(cluster)
        cy = sum(raw[k]["point"][1] for k in cluster) / len(cluster)
        pt = Point(cx, cy)

        # Count arms (road-graph degree):
        # A road that passes THROUGH the intersection contributes 2 arms.
        # A road that ENDS at the intersection contributes 1 arm.
        arms = 0
        tol = snap_dist_m * 2
        for _, ls in lines:
            if ls.distance(pt) > tol:
                continue
            at_start = Point(ls.coords[0]).distance(pt) < tol
            at_end = Point(ls.coords[-1]).distance(pt) < tol
            arms += 1 if (at_start or at_end) else 2

        degree = max(arms, 2)

        result.append({
            "point": [round(cx, 2), round(cy, 2)],
            "degree": degree,
            "type": _classify_degree(degree),
        })

    return result


def _classify_degree(degree: int) -> str:
    if degree <= 1:
        return "dead_end"
    if degree == 2:
        return "bend"
    if degree == 3:
        return "t_junction"
    if degree == 4:
        return "crossroads"
    return "complex_junction"


def classify_intersection_advanced(
    degree: int,
    roads_at_node: list[dict],
    is_roundabout: bool = False,
) -> str:
    """Refined classification including roundabouts and Y vs T distinction.

    A Y-junction has three arms at roughly equal angles (~120°);
    a T-junction has one arm nearly perpendicular to the through-road.
    """
    if is_roundabout:
        return "roundabout"
    if degree <= 1:
        return "dead_end"
    if degree == 2:
        return "bend"
    if degree == 4:
        return "crossroads"
    if degree > 4:
        return "complex_junction"

    # Degree-3: distinguish T from Y by road angles
    if len(roads_at_node) < 2:
        return "t_junction"
    dirs = []
    for road in roads_at_node[:3]:
        cl = road.get("centerline", [])
        if len(cl) >= 2:
            dx, dy = cl[-1][0] - cl[0][0], cl[-1][1] - cl[0][1]
            L = math.hypot(dx, dy)
            if L > 1e-6:
                dirs.append((dx / L, dy / L))
    if len(dirs) >= 3:
        # Compute the three pairwise angles
        angles = []
        for i in range(len(dirs)):
            for j in range(i + 1, len(dirs)):
                dot = max(-1.0, min(1.0, dirs[i][0]*dirs[j][0] + dirs[i][1]*dirs[j][1]))
                angles.append(math.degrees(math.acos(abs(dot))))
        max_diff = max(angles) - min(angles) if angles else 0
        # Y-junction: angles are roughly equal (all near 60° for a perfect Y)
        if max_diff < 30:
            return "y_junction"
    return "t_junction"


# ---------------------------------------------------------------------------
# Frontage extraction
# ---------------------------------------------------------------------------

def find_frontages(
    site_model: dict[str, Any],
    roads_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return per-side frontage info for all sides that adjoin a road.

    Enriches each side with a ``visibility_score`` (0..1) and
    ``recommended_access`` string.
    """
    if roads_result is None:
        roads_result = site_model.get("roads") or {}

    if not roads_result.get("available"):
        return []

    all_frontages = roads_result.get("frontage_m") or 0.0
    max_frontage = max(
        (r.get("frontage_m", 0.0) for r in roads_result.get("roads") or []),
        default=1.0,
    ) or 1.0

    corners = site_model.get("corners") or []
    sides_data = site_model.get("sides") or []

    frontages: list[dict[str, Any]] = []
    for side in roads_result.get("updated_sides") or sides_data:
        adj = side.get("adjacent_road")
        if adj is None:
            continue

        si = side.get("edge_index", 0)
        length_m = _side_length_m(corners, sides_data, si)
        vis = _visibility_score(adj, max_frontage)

        frontages.append({
            "side_index": si,
            "road_name": adj.get("name"),
            "road_hierarchy": adj.get("hierarchy", "path"),
            "road_width_m": adj.get("width_m", 6.0),
            "frontage_length_m": round(length_m, 2),
            "distance_m": round(adj.get("distance_m", 0.0), 2),
            "frontage_m": round(adj.get("frontage_m", 0.0), 2),
            "visibility_score": round(vis, 3),
            "recommended_access": _recommend_access(adj),
        })

    # Sort highest visibility first
    frontages.sort(key=lambda f: f["visibility_score"], reverse=True)
    return frontages


def _side_length_m(corners: list, sides_data: list, si: int) -> float:
    for side in sides_data:
        if side.get("edge_index") == si:
            fi = side.get("from_node_index")
            ti = side.get("to_node_index")
            if fi is not None and ti is not None and fi < len(corners) and ti < len(corners):
                p1 = corners[fi]["point"]
                p2 = corners[ti]["point"]
                return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    return 0.0


def _visibility_score(adj: dict[str, Any], max_frontage: float) -> float:
    rank = _HIER_RANK.get(adj.get("hierarchy", "path"), 1)
    width = min(adj.get("width_m", 6.0), 24.0)
    frontage = adj.get("frontage_m", 0.0) / (max_frontage or 1.0)
    return min(1.0, rank / 3.0 * 0.4 + width / 24.0 * 0.3 + frontage * 0.3)


def _recommend_access(adj: dict[str, Any]) -> str:
    h = adj.get("hierarchy", "path")
    w = adj.get("width_m", 6.0)
    if h == "main" and w >= 14.0:
        return "pedestrian"        # too busy for vehicle entry; pedestrians only
    if h in ("main", "secondary") and w >= 8.0:
        return "primary_vehicle"
    if h == "secondary":
        return "secondary_vehicle"
    return "service"


# ---------------------------------------------------------------------------
# Nearby intersection enrichment
# ---------------------------------------------------------------------------

def nearby_intersections(
    site_model: dict[str, Any],
    intersections: list[dict[str, Any]],
    radius_m: float = 100.0,
) -> list[dict[str, Any]]:
    """Filter intersections within ``radius_m`` of the site and add distance."""
    boundary = site_model.get("boundary") or []
    if len(boundary) < 3:
        return []
    poly = Polygon([(p[0], p[1]) for p in boundary])
    edge = poly.boundary

    result: list[dict[str, Any]] = []
    for ix in intersections:
        pt = Point(ix["point"])
        dist = 0.0 if poly.contains(pt) else float(edge.distance(pt))
        if dist > radius_m:
            continue
        clean = {k: v for k, v in ix.items() if not k.startswith("_")}
        result.append({**clean, "distance_to_site_m": round(dist, 2)})

    result.sort(key=lambda x: x["distance_to_site_m"])
    return result


# ---------------------------------------------------------------------------
# Site type classification
# ---------------------------------------------------------------------------

def classify_site_type(
    frontages: list[dict[str, Any]],
    near_ix: list[dict[str, Any]],
    site_model: dict[str, Any],
) -> str:
    """Classify the dominant urban condition.

    Priority chain:
    0 frontages → cul_de_sac | back_parcel
    1 frontage  → t_junction_terminal | linear
    2 frontages → triangular_corner | crossroads_corner | y_junction | corner
    3+ frontages → complex
    """
    n = len(frontages)

    if n == 0:
        if any(ix.get("type") == "dead_end" for ix in near_ix):
            return "cul_de_sac"
        return "back_parcel"

    if n >= 3:
        return "complex"

    if n == 1:
        # T-junction terminal: a junction is very close and the site faces the axis
        close_junction = next(
            (ix for ix in near_ix
             if ix.get("type") == "t_junction" and ix.get("distance_to_site_m", 999) < 35),
            None,
        )
        if close_junction:
            return "t_junction_terminal"
        return "linear"

    # n == 2: some kind of corner
    angle = _inter_frontage_angle(site_model, frontages)

    # Very acute corner (< 45°) → triangular
    if angle is not None and angle < 45.0:
        return "triangular_corner"

    # Y-junction: close junction + similar-hierarchy roads
    hierarchies = {f["road_hierarchy"] for f in frontages}
    close_y = next(
        (ix for ix in near_ix
         if ix.get("type") in ("t_junction", "complex_junction")
         and ix.get("distance_to_site_m", 999) < 25),
        None,
    )
    if close_y and len(hierarchies) == 1:
        return "y_junction"

    # Crossroads corner: 4-way nearby
    close_cross = next(
        (ix for ix in near_ix
         if ix.get("type") == "crossroads"
         and ix.get("distance_to_site_m", 999) < 30),
        None,
    )
    if close_cross:
        return "crossroads_corner"

    return "corner"


def _inter_frontage_angle(
    site_model: dict[str, Any],
    frontages: list[dict[str, Any]],
) -> float | None:
    """Angle in degrees between the two frontage side vectors (smaller of 2 supplementary angles)."""
    corners = site_model.get("corners") or []
    sides_data = site_model.get("sides") or []
    if len(frontages) < 2:
        return None
    try:
        dirs = []
        for f in frontages[:2]:
            side = next((s for s in sides_data if s.get("edge_index") == f["side_index"]), None)
            if side is None:
                return None
            fi, ti = side.get("from_node_index"), side.get("to_node_index")
            if fi is None or ti is None:
                return None
            p1, p2 = corners[fi]["point"], corners[ti]["point"]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            L = math.hypot(dx, dy)
            if L < 1e-9:
                return None
            dirs.append((dx / L, dy / L))
        dot = abs(dirs[0][0] * dirs[1][0] + dirs[0][1] * dirs[1][1])
        dot = max(0.0, min(1.0, dot))
        return math.degrees(math.acos(dot))
    except (IndexError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Corner condition analysis
# ---------------------------------------------------------------------------

def analyze_corner_conditions(
    site_model: dict[str, Any],
    frontages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For each site corner shared by two frontage sides, return visibility + gateway info."""
    corners = site_model.get("corners") or []
    sides_data = site_model.get("sides") or []
    frontage_by_side = {f["side_index"]: f for f in frontages}
    frontage_sides = set(frontage_by_side)

    result: list[dict[str, Any]] = []
    for ci, corner_data in enumerate(corners):
        # Find the frontage sides that start or end at this corner
        adj = []
        for sd in sides_data:
            si = sd.get("edge_index", -1)
            if si not in frontage_sides:
                continue
            if sd.get("from_node_index") == ci or sd.get("to_node_index") == ci:
                adj.append(frontage_by_side[si])

        if len(adj) < 2:
            continue

        f1, f2 = adj[0], adj[1]
        vis = math.sqrt(f1["visibility_score"] * f2["visibility_score"])
        is_gateway = f1["road_hierarchy"] == "main" or f2["road_hierarchy"] == "main"
        pt = corner_data["point"]

        result.append({
            "corner_index": ci,
            "point": [float(pt[0]), float(pt[1])],
            "sides": [f1["side_index"], f2["side_index"]],
            "road_hierarchies": [f1["road_hierarchy"], f2["road_hierarchy"]],
            "visibility_score": round(vis, 3),
            "is_gateway": is_gateway,
            "recommended_treatment": (
                "Gateway landmark — high architectural expression, chamfered or curved corner, corner entrance."
                if is_gateway else
                "Active corner — dual facade treatment, angled or setback corner, secondary entrance."
            ),
        })

    result.sort(key=lambda x: x["visibility_score"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Access analysis
# ---------------------------------------------------------------------------

def analyze_access(
    site_model: dict[str, Any],
    frontages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recommend vehicle, pedestrian, and service access points per frontage side."""
    corners = site_model.get("corners") or []
    sides_data = site_model.get("sides") or []

    vehicle: list[dict[str, Any]] = []
    pedestrian: list[dict[str, Any]] = []
    service: list[dict[str, Any]] = []

    def _midpoint(si: int) -> list[float] | None:
        for sd in sides_data:
            if sd.get("edge_index") == si:
                fi, ti = sd.get("from_node_index"), sd.get("to_node_index")
                if fi is not None and ti is not None and fi < len(corners) and ti < len(corners):
                    p1, p2 = corners[fi]["point"], corners[ti]["point"]
                    return [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]
        return None

    for f in frontages:
        mid = _midpoint(f["side_index"])
        if mid is None:
            continue
        rec = f["recommended_access"]
        base = {
            "point": mid,
            "side_index": f["side_index"],
            "road": f["road_name"],
            "hierarchy": f["road_hierarchy"],
            "road_width_m": f["road_width_m"],
        }

        if rec == "pedestrian":
            pedestrian.append({**base, "notes": "Main-road pedestrian entry — vehicle access via side street."})
        elif rec == "primary_vehicle":
            vehicle.append({**base, "notes": f"Primary vehicle + pedestrian entry ({f['road_width_m']:.0f} m wide)."})
            pedestrian.append({**base, "notes": "Shared pedestrian / vehicle frontage."})
        elif rec == "secondary_vehicle":
            vehicle.append({**base, "notes": f"Secondary vehicle access ({f['road_width_m']:.0f} m wide)."})
            pedestrian.append({**base, "notes": "Secondary pedestrian approach."})
        else:
            service.append({**base, "notes": f"Service / delivery access ({f['road_hierarchy']} street)."})

    # Guarantee at least one service point if nothing else identified
    if not vehicle and not service and frontages:
        lowest = min(frontages, key=lambda f: _HIER_RANK.get(f["road_hierarchy"], 1))
        mid = _midpoint(lowest["side_index"])
        if mid:
            service.append({
                "point": mid, "side_index": lowest["side_index"],
                "road": lowest["road_name"], "hierarchy": lowest["road_hierarchy"],
                "road_width_m": lowest["road_width_m"],
                "notes": "Only available frontage — combined access.",
            })

    return {
        "vehicle": vehicle,
        "pedestrian": pedestrian,
        "service": service,
        "vehicle_count": len(vehicle),
        "pedestrian_count": len(pedestrian),
        "service_count": len(service),
    }


# ---------------------------------------------------------------------------
# Urban response templates
# ---------------------------------------------------------------------------

_RESPONSES: dict[str, dict[str, str | None]] = {
    "corner": {
        "building_response": (
            "Activate both street frontages. This corner belongs to both streets "
            "simultaneously — the architecture must claim both."
        ),
        "massing_strategy": (
            "Articulate the mass to address both streets. Consider a step or setback "
            "at the corner to create a plaza reveal or corner entrance feature."
        ),
        "entry_strategy": (
            "Primary entrance at or near the corner point. A splayed or angled entry "
            "reinforces the dual address and is visible from both roads."
        ),
        "facade_strategy": (
            "Continuous street-wall on both frontages. Ground floor activation (retail, lobby). "
            "Higher parapet expression or bay window at the corner."
        ),
        "corner_treatment": (
            "Chamfered corner, curved corner tower, or recessed corner plaza. "
            "Avoid a blank or closed corner — it is the most-seen point."
        ),
    },
    "crossroads_corner": {
        "building_response": (
            "Maximise four-way visibility. This site is a landmark anchor for the entire "
            "crossroads — it will be read from four approaching directions."
        ),
        "massing_strategy": (
            "Vertical emphasis at the corner. Step massing down along both street walls "
            "to frame the intersection rather than block it."
        ),
        "entry_strategy": (
            "Diagonal or corner entry facing the intersection. "
            "A canopied or raised threshold signals importance from all four quadrants."
        ),
        "facade_strategy": (
            "All four elevations are public and active. Glazed ground floor on both main roads. "
            "No blank rear walls — the crossroads has no 'back'."
        ),
        "corner_treatment": (
            "Bold sculptural corner — transparent glass blade, angled cut, or expressed structural "
            "corner. This is the highest-visibility node in the block."
        ),
    },
    "t_junction_terminal": {
        "building_response": (
            "The building terminates a street and is seen head-on from a distance. "
            "Every element of the terminus facade will be scrutinised by approaching users."
        ),
        "massing_strategy": (
            "Symmetrical or centred massing facing the road axis. "
            "Wings extending along the cross street complete the T-junction enclosure."
        ),
        "entry_strategy": (
            "Central entrance on the terminus facade, framed and directly readable from the road. "
            "A portico, canopy, or recess marks the centrepoint of the visual axis."
        ),
        "facade_strategy": (
            "Landmark terminus elevation — consider symmetry, bay articulation, or a strong "
            "vertical centrepiece. The cross-street sides are secondary but must also be active."
        ),
        "corner_treatment": (
            "Corner wings anchor the visual closure of the junction. "
            "Matching cornice or parapet lines tie the two flanks to the terminus facade."
        ),
    },
    "y_junction": {
        "building_response": (
            "Respond to two diverging visual axes. "
            "The building is read simultaneously from both approaching roads."
        ),
        "massing_strategy": (
            "Wedge or triangular plan resolving the Y. "
            "The apex points toward the junction and is the building's primary address."
        ),
        "entry_strategy": (
            "Entry at the apex or along the wider of the two flanking streets. "
            "An acute corner entry makes the split geometry a feature, not a problem."
        ),
        "facade_strategy": (
            "Dynamic angled facades track the street geometry rather than fighting it. "
            "Emphasise the apex with height, material change, or signage."
        ),
        "corner_treatment": (
            "Acute corner — round or chamfer to avoid a knife-edge. "
            "The curved or sliced apex reads as a deliberate gesture from both approach roads."
        ),
    },
    "triangular_corner": {
        "building_response": (
            "A triangular site is a gift for bold massing. "
            "The acute apex corner is the signature address of the city block."
        ),
        "massing_strategy": (
            "The acute corner rises tallest; the wider base anchors the mass. "
            "A wedge or prow form occupies the full triangle efficiently."
        ),
        "entry_strategy": (
            "Entry at the acute corner — the most prominent and visible point from both roads. "
            "A raised lobby or entrance canopy amplifies the corner's landmark quality."
        ),
        "facade_strategy": (
            "The narrow apex is the building's logo. "
            "Glazed or sculptural tip; the wider flanks carry more conventional fenestration."
        ),
        "corner_treatment": (
            "Curved or chamfered apex — a knife-edge corner is structurally and perceptually risky. "
            "The curvature tracks the diverging road angle."
        ),
    },
    "linear": {
        "building_response": (
            "Define and reinforce the street wall. Build to the building line. "
            "The urban value here is consistency and enclosure, not singularity."
        ),
        "massing_strategy": (
            "Continuous slab or terrace along the frontage. "
            "Vertical bays break the horizontal mass and give rhythm."
        ),
        "entry_strategy": (
            "Entry at the centre or at a bay break. Clear signage from the street. "
            "Avoid entries at the very ends of the frontage — they weaken the street wall."
        ),
        "facade_strategy": (
            "Consistent primary facade. Active ground floor (retail / lobby). "
            "Match the cornice height of neighbours to maintain the street datum."
        ),
        "corner_treatment": None,
    },
    "cul_de_sac": {
        "building_response": (
            "Inward-facing and private. The building addresses the shared turning head "
            "as a common threshold, not a public street."
        ),
        "massing_strategy": (
            "Curved plan following the cul-de-sac arc. "
            "Low scale appropriate; no reason to tower over a private court."
        ),
        "entry_strategy": (
            "Entry directly off the turning head. Integrated parking or cycle storage. "
            "A shared threshold with adjacent properties is possible."
        ),
        "facade_strategy": (
            "Softer, more residential character. "
            "Active ground edges facing the court; private garden edges to the rear."
        ),
        "corner_treatment": None,
    },
    "back_parcel": {
        "building_response": (
            "No direct road frontage — the building relies on pedestrian or shared access. "
            "Justify the back-land condition with high internal amenity."
        ),
        "massing_strategy": (
            "Internal courtyard or atrium plan. "
            "Turn absence of frontage into an advantage: a private, quiet character."
        ),
        "entry_strategy": (
            "Entry via shared lane or easement. Pedestrian priority. "
            "A clear threshold marker distinguishes the private entry."
        ),
        "facade_strategy": (
            "Private elevations; active internal courtyard faces. "
            "The 'back' is also the 'front' — treat all internal edges with care."
        ),
        "corner_treatment": None,
    },
    "complex": {
        "building_response": (
            "Multiple road frontages: establish a clear hierarchy of addresses. "
            "The main road is the primary face; others are secondary."
        ),
        "massing_strategy": (
            "Step the massing to address each road at its appropriate scale. "
            "The dominant mass faces the most important road."
        ),
        "entry_strategy": (
            "Primary entry from the main road. Secondary pedestrian entries on side roads. "
            "Service from the lowest-hierarchy street."
        ),
        "facade_strategy": (
            "Each frontage is treated to its road's character and scale. "
            "Differentiate primary (main road) vs secondary (side streets) clearly."
        ),
        "corner_treatment": (
            "All corners are active. Resolve each with an expression appropriate to "
            "the two streets it mediates."
        ),
    },
}


def generate_urban_response(
    site_type: str,
    frontages: list[dict[str, Any]],
    near_ix: list[dict[str, Any]],
    corner_conditions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return structured architectural response recommendations."""
    template = _RESPONSES.get(site_type, _RESPONSES["linear"])
    return {
        "site_type": site_type,
        "site_type_label": SITE_TYPE_LABELS.get(site_type, site_type),
        **{k: v for k, v in template.items()},
        "priority_frontage_side": frontages[0]["side_index"] if frontages else None,
        "secondary_frontage_side": frontages[1]["side_index"] if len(frontages) > 1 else None,
        "gateway_corners": [c for c in corner_conditions if c.get("is_gateway")],
        "nearby_junction_type": near_ix[0]["type"] if near_ix else None,
    }


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def full_urban_analysis(
    site_model: dict[str, Any],
    roads: list[dict[str, Any]] | None = None,
    intersections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Complete urban analysis for a site.

    Parameters
    ----------
    site_model:
        From ``build_site_model``.  Must contain ``roads`` (Phase 2 result).
    roads:
        Supplementary road list (used for intersection detection when
        ``intersections`` is not provided and ``site_model["roads"]`` is
        already populated but doesn't carry raw geometry for detection).
    intersections:
        Pre-detected junctions (e.g. from ``osm_context.fetch_urban_site``).
        When ``None``, detected geometrically from road centrelines.

    Returns
    -------
    dict with keys: available, source, site_type, frontage_count, frontages,
    nearby_intersections, corner_conditions, access, urban_response,
    ambiguity, ambiguity_message.
    """
    roads_result = site_model.get("roads") or {}

    if not roads_result.get("available"):
        return {
            "available": False,
            "source": "none",
            "site_type": "back_parcel",
            "frontage_count": 0,
            "frontages": [],
            "nearby_intersections": [],
            "corner_conditions": [],
            "access": {"vehicle": [], "pedestrian": [], "service": [],
                       "vehicle_count": 0, "pedestrian_count": 0, "service_count": 0},
            "urban_response": generate_urban_response("back_parcel", [], [], []),
            "ambiguity": "no_road_data",
            "ambiguity_message": "No road data in site model — urban analysis unavailable.",
        }

    # 1. Frontages (built from Phase 2 side tagging)
    frontages = find_frontages(site_model, roads_result)

    # 2. Intersections (use provided list or detect geometrically)
    road_list = roads or roads_result.get("roads") or []
    if intersections is None:
        intersections = detect_intersections_from_roads(road_list)

    near = nearby_intersections(site_model, intersections)

    # 3. Site type
    site_type = classify_site_type(frontages, near, site_model)

    # 4. Corner conditions
    corners = analyze_corner_conditions(site_model, frontages)

    # 5. Access
    access = analyze_access(site_model, frontages)

    # 6. Urban response
    response = generate_urban_response(site_type, frontages, near, corners)

    return {
        "available": True,
        "source": roads_result.get("source", "synthetic"),
        "site_type": site_type,
        "frontage_count": len(frontages),
        "frontages": frontages,
        "nearby_intersections": near,
        "corner_conditions": corners,
        "access": access,
        "urban_response": response,
        "ambiguity": None,
        "ambiguity_message": None,
    }


# ---------------------------------------------------------------------------
# GIS upgrade — NetworkX street graph analysis
# ---------------------------------------------------------------------------

def build_street_network(roads: list[dict]) -> "Any | None":
    """Build a NetworkX graph from road centerlines (requires networkx).

    Delegates to ``osm_context.build_street_graph`` so there is one
    canonical implementation.  Returns ``None`` when NetworkX is absent.
    """
    try:
        from team_04.agent.tools.osm_context import build_street_graph
        return build_street_graph(roads)
    except Exception:
        # Fallback: try importing without the package prefix (notebooks)
        try:
            import importlib, sys as _sys
            spec = importlib.util.find_spec("osm_context")
            if spec:
                mod = importlib.import_module("osm_context")
                return mod.build_street_graph(roads)
        except Exception:
            pass
        return None


def compute_centrality(graph: "Any") -> dict:
    """Return betweenness + closeness centrality dicts from a NetworkX graph.

    Both are normalised to [0, 1].  Returns ``{}`` when NetworkX is absent
    or the graph is too small.
    """
    if graph is None:
        return {}
    try:
        import networkx as nx
        if graph.number_of_nodes() < 2:
            return {}
        bc = nx.betweenness_centrality(graph, weight="length", normalized=True)
        cc = nx.closeness_centrality(graph, distance="length")
        max_cc = max(cc.values(), default=1.0) or 1.0
        cc_norm = {k: v / max_cc for k, v in cc.items()}
        return {"betweenness": bc, "closeness": cc_norm}
    except Exception:
        return {}


def compute_urban_importance(
    site_model: dict,
    graph: "Any",
    centrality: dict,
    radius_m: float = 60.0,
) -> dict:
    """Score the site's urban importance from network centrality of nearby nodes.

    Returns ``{score, grade, factors}`` where ``score`` ∈ [0, 1] and
    ``grade`` ∈ {A+, A, B, C, D}.
    """
    if graph is None or not centrality:
        return {"score": 0.5, "grade": "B", "factors": {}}

    boundary = site_model.get("boundary", [])
    if len(boundary) < 3:
        return {"score": 0.5, "grade": "B", "factors": {}}

    poly = Polygon([(p[0], p[1]) for p in boundary])
    bc   = centrality.get("betweenness", {})
    cc   = centrality.get("closeness",   {})

    near_bc: list[float] = []
    near_cc: list[float] = []
    for nid, data in graph.nodes(data=True):
        pt   = Point(data.get("x", 0), data.get("y", 0))
        dist = 0.0 if poly.contains(pt) else float(poly.boundary.distance(pt))
        if dist <= radius_m:
            near_bc.append(bc.get(nid, 0.0))
            near_cc.append(cc.get(nid, 0.0))

    if not near_bc:
        return {"score": 0.5, "grade": "B", "factors": {"betweenness": 0.0, "closeness": 0.0}}

    avg_bc = sum(near_bc) / len(near_bc)
    avg_cc = sum(near_cc) / len(near_cc)
    score  = min(1.0, avg_bc * 0.6 + avg_cc * 0.4)
    grade  = (
        "A+" if score > 0.80 else
        "A"  if score > 0.60 else
        "B"  if score > 0.40 else
        "C"  if score > 0.20 else
        "D"
    )
    return {
        "score": round(score, 3),
        "grade": grade,
        "factors": {
            "betweenness": round(avg_bc, 3),
            "closeness":   round(avg_cc, 3),
            "sample_nodes": len(near_bc),
        },
    }


def road_to_polygon(road: dict) -> "Any | None":
    """Return a Shapely Polygon representing the road surface (for GIS visualisation)."""
    cl = road.get("centerline", [])
    w  = road.get("width_m", 6.0)
    if len(cl) < 2:
        return None
    try:
        from shapely.geometry import LineString
        return LineString(cl).buffer(w / 2, cap_style=2, join_style=2)
    except Exception:
        return None
