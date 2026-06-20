"""Phase 2b — OSM Urban Context Fetcher

Fetches real road networks from OpenStreetMap via the Overpass API and
converts them into the road-object schema consumed by road_context.analyze_roads.

Coordinate system: local metres (x = east, y = north) relative to the query
centre, so all downstream tools work unchanged.

Public API
----------
fetch_urban_site(lat, lon, radius_m=200, timeout=15) -> dict
    Download roads + detect intersections for a coordinate.

fetch_or_fallback(lat, lon, ..., fallback_index=0) -> dict
    Same but returns a synthetic fallback on any network failure.

INTERESTING_SITES : list[dict]
    Eight pre-configured locations with rich urban morphology.

pick_site(index=None) -> dict
    Return a preset (index=0 when None).

SYNTHETIC_SITES : list[dict]
    Offline-safe fallback scenarios that exercise the full analysis engine.
    Same output schema as fetch_urban_site().
"""
from __future__ import annotations

import math
import warnings
from typing import Any

try:
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

from shapely.geometry import LineString, Point

# ---------------------------------------------------------------------------
# OSM highway → (hierarchy, default_width_m)
# ---------------------------------------------------------------------------

OSM_HIGHWAY_MAP: dict[str, tuple[str, float]] = {
    # Primary
    "motorway":        ("main",      24.0),
    "motorway_link":   ("main",      10.0),
    "trunk":           ("main",      20.0),
    "trunk_link":      ("main",      10.0),
    "primary":         ("main",      16.0),
    "primary_link":    ("main",       8.0),
    # Secondary
    "secondary":       ("secondary", 12.0),
    "secondary_link":  ("secondary",  6.0),
    "tertiary":        ("secondary", 10.0),
    "tertiary_link":   ("secondary",  5.0),
    "unclassified":    ("secondary",  8.0),
    "residential":     ("secondary",  7.0),
    "living_street":   ("path",       4.5),
    # Service / pedestrian
    "service":         ("path",       4.0),
    "footway":         ("path",       2.0),
    "cycleway":        ("path",       2.5),
    "pedestrian":      ("path",       6.0),
    "path":            ("path",       2.0),
    "steps":           ("path",       1.5),
    "track":           ("path",       3.0),
}

# ---------------------------------------------------------------------------
# Interesting urban presets
# ---------------------------------------------------------------------------

INTERESTING_SITES: list[dict[str, Any]] = [
    {
        "name": "Eixample chamfered crossroads, Barcelona",
        "lat": 41.3936, "lon": 2.1628, "radius_m": 200,
        "site_type_hint": "crossroads",
        "description": (
            "Classic Cerdà grid — octagonal blocks with chamfered corners, "
            "primary arterials (Carrer d'Aragó) crossing secondary streets. "
            "Every corner site is a gateway condition."
        ),
    },
    {
        "name": "Le Marais medieval corner, Paris",
        "lat": 48.8588, "lon": 2.3567, "radius_m": 140,
        "site_type_hint": "corner",
        "description": (
            "Irregular pre-Haussmann block: narrow corner lot, oblique street "
            "angles, mix of main and secondary streets — no 90° corners."
        ),
    },
    {
        "name": "Flatiron triangular block, New York",
        "lat": 40.7412, "lon": -73.9897, "radius_m": 180,
        "site_type_hint": "triangular_corner",
        "description": (
            "Broadway cuts diagonally through the Manhattan grid at 23rd St, "
            "creating the world's most famous acute triangular site."
        ),
    },
    {
        "name": "T-junction terminal, Bloomsbury, London",
        "lat": 51.5228, "lon": -0.1210, "radius_m": 130,
        "site_type_hint": "t_junction_terminal",
        "description": (
            "Georgian residential T-junction: a secondary road terminates at a "
            "through street; the site addresses the visual axis."
        ),
    },
    {
        "name": "Jordaan canal corner, Amsterdam",
        "lat": 52.3745, "lon": 4.8840, "radius_m": 120,
        "site_type_hint": "corner",
        "description": (
            "Canal-side parcel at the intersection of a canal street and a "
            "cross-street — typical Amsterdam water-edge corner condition."
        ),
    },
    {
        "name": "Y-junction, Beyoglu, Istanbul",
        "lat": 41.0330, "lon": 28.9785, "radius_m": 160,
        "site_type_hint": "y_junction",
        "description": (
            "Curved hillside streets converge into a Y-junction; "
            "the site sits at the apex with a strong visual axis toward the Bosphorus."
        ),
    },
    {
        "name": "Laneway corner, Melbourne CBD",
        "lat": -37.8136, "lon": 144.9631, "radius_m": 160,
        "site_type_hint": "corner",
        "description": (
            "Melbourne grid corner with secondary laneway on the rear — "
            "typical inner-city mixed-use condition with two-tier access."
        ),
    },
    {
        "name": "Dense block, Shinjuku, Tokyo",
        "lat": 35.6895, "lon": 139.6917, "radius_m": 150,
        "site_type_hint": "complex_junction",
        "description": (
            "High-density Japanese urban block: narrow secondary and service "
            "streets, complex multi-way intersections, no dominant frontage."
        ),
    },
]

# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

_EARTH_R = 6_371_000.0


def _ll_to_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Convert (lat, lon) → (x, y) metres relative to (ref_lat, ref_lon).

    x = east, y = north.  Accurate to ~0.01 % within 2 km.
    """
    dlat = math.radians(lat - ref_lat)
    dlon = math.radians(lon - ref_lon)
    x = dlon * math.cos(math.radians(ref_lat)) * _EARTH_R
    y = dlat * _EARTH_R
    return x, y


def _deg_bbox(lat: float, lon: float, r: float) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for a square of side 2r around (lat, lon)."""
    dlat = math.degrees(r / _EARTH_R)
    dlon = math.degrees(r / (_EARTH_R * math.cos(math.radians(lat)) + 1e-12))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


# ---------------------------------------------------------------------------
# Overpass fetcher
# ---------------------------------------------------------------------------

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def fetch_urban_site(
    lat: float,
    lon: float,
    radius_m: float = 200,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fetch road network from OpenStreetMap for a circle of ``radius_m`` metres.

    Returns::

        {
          "source":           "osm",
          "lat": ..., "lon": ..., "radius_m": ...,
          "site_boundary":    [[x, y], ...],  # plausible parcel polygon
          "roads":            [...],           # road-object list → analyze_roads
          "intersections":    [...],           # junction dicts
          "road_count":       int,
          "intersection_count": int,
        }

    Raises ``RuntimeError`` on network failure.  Use ``fetch_or_fallback``
    for offline-safe operation.
    """
    if not _REQUESTS_OK:
        raise RuntimeError("requests library not installed; cannot fetch OSM data.")

    s, w, n, e = _deg_bbox(lat, lon, radius_m)
    bbox = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = (
        "[out:json][timeout:25];\n"
        f'(way["highway"]({bbox}););\n'
        "out body;\n>;\nout skel qt;\n"
    )

    try:
        resp = _req.post(_OVERPASS_URL, data={"data": query}, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Overpass API request failed: {exc}") from exc

    data = resp.json()

    # Node lookup: id → (lat, lon)
    node_ll: dict[int, tuple[float, float]] = {}
    for el in data.get("elements", []):
        if el["type"] == "node":
            node_ll[el["id"]] = (el["lat"], el["lon"])

    # Node-usage counter for intersection detection
    node_usage: dict[int, list[int]] = {}  # node_id → [way_id, ...]

    roads: list[dict[str, Any]] = []
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        hw = tags.get("highway", "")
        mapping = OSM_HIGHWAY_MAP.get(hw)
        if mapping is None:
            continue
        hierarchy, default_w = mapping
        width_m = _parse_width(tags, default_w)
        name = tags.get("name") or tags.get("ref")

        cl: list[list[float]] = []
        for nid in el.get("nodes", []):
            if nid in node_ll:
                nlat, nlon = node_ll[nid]
                x, y = _ll_to_m(nlat, nlon, lat, lon)
                cl.append([round(x, 2), round(y, 2)])
            node_usage.setdefault(nid, []).append(el["id"])

        if len(cl) < 2:
            continue

        roads.append({
            "type": "road",
            "centerline": cl,
            "width_m": width_m,
            "hierarchy": hierarchy,
            "osm_highway": hw,
            "osm_way_id": el["id"],
            "name": name,
        })

    intersections = _detect_from_nodes(node_usage, node_ll, lat, lon)
    site_boundary = _infer_site(roads, radius_m)

    return {
        "source": "osm",
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "site_boundary": site_boundary,
        "roads": roads,
        "intersections": intersections,
        "road_count": len(roads),
        "intersection_count": len(intersections),
    }


def _parse_width(tags: dict, default: float) -> float:
    raw = tags.get("width") or tags.get("est_width")
    if raw:
        try:
            return float(str(raw).split()[0])
        except (ValueError, AttributeError):
            pass
    lanes = tags.get("lanes")
    if lanes:
        try:
            return float(lanes) * 3.5
        except (ValueError, TypeError):
            pass
    return default


def _detect_from_nodes(
    node_usage: dict[int, list[int]],
    node_ll: dict[int, tuple[float, float]],
    ref_lat: float,
    ref_lon: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for nid, way_ids in node_usage.items():
        deg = len(way_ids)
        if deg < 3 or nid not in node_ll:
            continue
        nlat, nlon = node_ll[nid]
        x, y = _ll_to_m(nlat, nlon, ref_lat, ref_lon)
        itype = "crossroads" if deg == 4 else ("complex_junction" if deg > 4 else "t_junction")
        result.append({"point": [round(x, 2), round(y, 2)], "degree": deg, "type": itype})
    return result


def _infer_site(roads: list[dict], radius_m: float) -> list[list[float]]:
    """Generate a plausible site polygon aligned to the nearest road."""
    if roads:
        best = min(roads, key=lambda r: LineString(r["centerline"]).distance(Point(0, 0)))
        cl = best["centerline"]
        if len(cl) >= 2:
            dx, dy = cl[1][0] - cl[0][0], cl[1][1] - cl[0][1]
            L = math.hypot(dx, dy)
            if L > 1e-6:
                ux, uy = dx / L, dy / L
                vx, vy = -uy, ux
                w = min(35.0, radius_m * 0.35)
                d = min(22.0, radius_m * 0.22)
                pts = [
                    [w * ux + d * vx, w * uy + d * vy],
                    [-w * ux + d * vx, -w * uy + d * vy],
                    [-w * ux - d * vx, -w * uy - d * vy],
                    [w * ux - d * vx, w * uy - d * vy],
                ]
                pts.append(pts[0])
                return pts
    s, d = min(radius_m * 0.35, 35.0), min(radius_m * 0.22, 22.0)
    return [[-s, -d], [s, -d], [s, d], [-s, d], [-s, -d]]


# ---------------------------------------------------------------------------
# Synthetic fallback sites
# ---------------------------------------------------------------------------

def _barcelona_style() -> dict[str, Any]:
    """Corner site (Barcelona-style): two streets meeting — main to south, secondary to west.

    Back roads are >25 m away so only 2 sides get tagged → site_type = "corner".
    The crossroads intersection at (-12, -12) is 12 m from the SW site corner.
    """
    return {
        "source": "synthetic",
        "site_name": "Synthetic corner site (Eixample-style)",
        "site_type_hint": "corner",
        # Octagonal site with chamfered SW corner sitting at the junction of two streets
        "site_boundary": [
            [0, 0], [40, 0], [47, 7], [47, 30], [0, 30], [0, 0]
        ],
        "roads": [
            # Main road runs east-west, 12 m south of the site bottom (y=0)
            {"type": "road", "centerline": [[-30, -12], [90, -12]],
             "width_m": 20.0, "hierarchy": "main", "name": "Carrer Gran"},
            # Secondary road runs north-south, 12 m west of the site left edge (x=0)
            {"type": "road", "centerline": [[-12, -30], [-12, 70]],
             "width_m": 10.0, "hierarchy": "secondary", "name": "Avinguda Nord"},
            # Back path: 25 m north of site top (30+25=55) → distance=25 > threshold=22 → NOT tagged
            {"type": "road", "centerline": [[-30, 55], [90, 55]],
             "width_m": 4.0, "hierarchy": "path", "name": "Passatge Posterior"},
        ],
        "intersections": [
            # Crossroads 12 m from the SW corner of the site
            {"point": [-12, -12], "degree": 4, "type": "crossroads"},
        ],
        "road_count": 3,
        "intersection_count": 1,
    }


def _london_t_junction() -> dict[str, Any]:
    """T-junction terminal (Bloomsbury-style): site sits at the terminus of a road.

    One frontage (south = High Street).  The Terminus Lane terminates at High
    Street just 12 m below the site, creating a T-junction that makes the site
    a focal visual terminus → site_type = "t_junction_terminal".
    """
    return {
        "source": "synthetic",
        "site_name": "Synthetic T-junction terminal (Bloomsbury-style)",
        "site_type_hint": "t_junction_terminal",
        "site_boundary": [[-22, 12], [22, 12], [22, 48], [-22, 48], [-22, 12]],
        "roads": [
            # Cross street runs east-west at y=0 (12 m below site bottom at y=12)
            {"type": "road", "centerline": [[-90, 0], [90, 0]],
             "width_m": 10.0, "hierarchy": "secondary", "name": "High Street"},
            # Terminus lane ends at the cross street, pointing away from site
            {"type": "road", "centerline": [[0, 0], [0, -60]],
             "width_m": 7.0, "hierarchy": "secondary", "name": "Terminus Lane"},
            # Back lane: 73-48=25 m north of site → distance=25 > threshold=22 → NOT tagged
            {"type": "road", "centerline": [[-90, 73], [90, 73]],
             "width_m": 4.0, "hierarchy": "path", "name": "Back Lane"},
            # Side mews: 50-22=28 m west of site → distance=28 > threshold=23 → NOT tagged
            {"type": "road", "centerline": [[-50, -30], [-50, 80]],
             "width_m": 6.0, "hierarchy": "path", "name": "Side Mews"},
        ],
        "intersections": [
            # T-junction 12 m below site bottom (y=0), site addresses this visual axis
            {"point": [0, 0], "degree": 3, "type": "t_junction"},
        ],
        "road_count": 4,
        "intersection_count": 1,
    }


def _flatiron_style() -> dict[str, Any]:
    """Triangular corner (Flatiron-style): two main roads meet at an acute angle.

    The site is a true triangle.  Two main roads — one horizontal (Broadway) and
    one diagonal (5th Avenue at ≈ 38° from horizontal) — create two frontages with
    an interior angle of ≈ 38° < 45° → site_type = "triangular_corner".
    """
    return {
        "source": "synthetic",
        "site_name": "Synthetic triangular corner (Flatiron-style)",
        "site_type_hint": "triangular_corner",
        # True triangle: acute tip at origin, wide base at top
        "site_boundary": [[0, 0], [55, 0], [10, 35], [0, 0]],
        "roads": [
            # Broadway — horizontal main road, 12 m south of site bottom (y=0)
            {"type": "road", "centerline": [[-20, -12], [95, -12]],
             "width_m": 18.0, "hierarchy": "main", "name": "Broadway"},
            # 5th Avenue — diagonal road running parallel to the NE hypotenuse,
            # approximately 10 m outside that face.  centerline (-1,56)→(78,-5).
            {"type": "road", "centerline": [[-1, 56], [78, -5]],
             "width_m": 14.0, "hierarchy": "main", "name": "5th Avenue"},
            # 23rd Street — secondary cross street north of site,
            # y=65: 65-35=30 m from site top → distance=30 > threshold=25 → NOT tagged
            {"type": "road", "centerline": [[-20, 65], [80, 65]],
             "width_m": 10.0, "hierarchy": "secondary", "name": "23rd Street"},
        ],
        "intersections": [
            # Broadway × 5th Avenue intersection south-east of the triangle apex
            {"point": [57, -12], "degree": 4, "type": "crossroads"},
        ],
        "road_count": 3,
        "intersection_count": 1,
    }


SYNTHETIC_SITES: list[dict[str, Any]] = [
    _barcelona_style(),
    _london_t_junction(),
    _flatiron_style(),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def pick_site(index: int | None = None) -> dict[str, Any]:
    """Return a preset from ``INTERESTING_SITES``.  ``index=None`` → first entry."""
    presets = INTERESTING_SITES
    if index is None:
        return presets[0]
    return presets[index % len(presets)]


def fetch_or_fallback(
    lat: float,
    lon: float,
    radius_m: float = 200,
    timeout: int = 12,
    fallback_index: int = 0,
) -> dict[str, Any]:
    """Fetch from OSM; return a synthetic fallback on any network failure."""
    try:
        return fetch_urban_site(lat, lon, radius_m, timeout)
    except Exception as exc:
        warnings.warn(f"OSM fetch failed ({exc}); using synthetic fallback.")
        return SYNTHETIC_SITES[fallback_index % len(SYNTHETIC_SITES)]


# ---------------------------------------------------------------------------
# GIS upgrade — rich context fetch (roads + buildings + greenery + parking)
# ---------------------------------------------------------------------------

BUILDING_TYPE_MAP: dict[str, str] = {
    # Residential
    "residential": "residential", "apartments": "residential",
    "house": "residential", "detached": "residential",
    "semidetached_house": "residential", "terrace": "residential",
    "bungalow": "residential", "dormitory": "residential",
    "flat": "residential",
    # Commercial
    "commercial": "commercial", "office": "commercial",
    "retail": "commercial", "supermarket": "commercial",
    "shop": "commercial", "hotel": "commercial", "bank": "commercial",
    "mall": "commercial",
    # Civic / institutional
    "civic": "civic", "public": "civic", "school": "civic",
    "hospital": "civic", "library": "civic", "university": "civic",
    "church": "civic", "cathedral": "civic", "mosque": "civic",
    "government": "civic", "museum": "civic",
    # Industrial
    "industrial": "industrial", "warehouse": "industrial",
    "storage": "industrial", "factory": "industrial",
    # Mixed / other
    "mixed": "mixed", "yes": "unknown",
}


def _classify_building(tags: dict) -> str:
    btype = tags.get("building", "yes")
    return BUILDING_TYPE_MAP.get(btype, "unknown")


def fetch_urban_context_rich(
    lat: float,
    lon: float,
    radius_m: float = 200,
    timeout: int = 25,
) -> dict[str, Any]:
    """Fetch roads, buildings, parking, green areas, and trees from OSM.

    Returns the same road schema as ``fetch_urban_site`` plus:

    ``buildings``      list of ``{building_type, polygon_pts, name, levels}``
    ``parking_areas``  list of ``{polygon_pts}``
    ``green_areas``    list of ``{polygon_pts, green_type}``
    ``trees``          list of ``[x, y]`` (from OSM ``natural=tree`` nodes)

    Raises ``RuntimeError`` on any network failure — use
    ``fetch_context_or_fallback`` for offline-safe operation.
    """
    if not _REQUESTS_OK:
        raise RuntimeError("requests library not installed.")

    s, w, n, e = _deg_bbox(lat, lon, radius_m)
    bbox = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"

    query = (
        "[out:json][timeout:30];\n"
        "(\n"
        f'  way["highway"]({bbox});\n'
        f'  way["building"]({bbox});\n'
        f'  way["landuse"="parking"]({bbox});\n'
        f'  way["amenity"="parking"]({bbox});\n'
        f'  way["landuse"~"grass|park|recreation_ground|garden|meadow"]({bbox});\n'
        f'  way["leisure"~"park|garden|pitch|playground"]({bbox});\n'
        f'  way["natural"~"wood|scrub|heath"]({bbox});\n'
        f'  node["natural"="tree"]({bbox});\n'
        ");\n"
        "out body;\n>;\nout skel qt;\n"
    )

    try:
        resp = _req.post(_OVERPASS_URL, data={"data": query}, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Overpass API request failed: {exc}") from exc

    data = resp.json()

    node_ll: dict[int, tuple[float, float]] = {}
    for el in data.get("elements", []):
        if el["type"] == "node":
            node_ll[el["id"]] = (el["lat"], el["lon"])

    node_usage: dict[int, list[int]] = {}
    roads: list[dict[str, Any]] = []
    buildings: list[dict[str, Any]] = []
    parking_areas: list[dict[str, Any]] = []
    green_areas: list[dict[str, Any]] = []
    trees: list[list[float]] = []

    for el in data.get("elements", []):
        # Tree nodes
        if el["type"] == "node":
            tags = el.get("tags", {})
            if tags.get("natural") == "tree" and el["id"] in node_ll:
                nlat, nlon = node_ll[el["id"]]
                x, y = _ll_to_m(nlat, nlon, lat, lon)
                trees.append([round(x, 2), round(y, 2)])
            continue

        if el["type"] != "way":
            continue

        tags = el.get("tags", {})
        node_ids = el.get("nodes", [])

        pts: list[list[float]] = []
        for nid in node_ids:
            if nid in node_ll:
                nlat, nlon = node_ll[nid]
                x, y = _ll_to_m(nlat, nlon, lat, lon)
                pts.append([round(x, 2), round(y, 2)])

        if len(pts) < 2:
            continue

        # ── Road ──────────────────────────────────────────────────────────
        hw = tags.get("highway", "")
        if hw and hw in OSM_HIGHWAY_MAP:
            hierarchy, default_w = OSM_HIGHWAY_MAP[hw]
            width_m = _parse_width(tags, default_w)
            name = tags.get("name") or tags.get("ref")
            for nid in node_ids:
                node_usage.setdefault(nid, []).append(el["id"])
            roads.append({
                "type": "road",
                "centerline": pts,
                "width_m": width_m,
                "hierarchy": hierarchy,
                "osm_highway": hw,
                "osm_way_id": el["id"],
                "name": name,
                "is_roundabout": tags.get("junction") == "roundabout",
                "is_oneway": tags.get("oneway") in ("yes", "1", "true"),
                "lanes": tags.get("lanes"),
            })
            continue

        # ── Building ──────────────────────────────────────────────────────
        if tags.get("building") and len(pts) >= 3:
            btype = _classify_building(tags)
            name = tags.get("name") or tags.get("addr:housename")
            levels = 1
            try:
                levels = int(tags.get("building:levels", 1))
            except (ValueError, TypeError):
                pass
            buildings.append({
                "type": "building",
                "building_type": btype,
                "polygon_pts": pts,
                "name": name,
                "osm_way_id": el["id"],
                "levels": levels,
            })
            continue

        # ── Parking ───────────────────────────────────────────────────────
        if (tags.get("landuse") == "parking" or tags.get("amenity") == "parking") and len(pts) >= 3:
            parking_areas.append({"polygon_pts": pts})
            continue

        # ── Green space ───────────────────────────────────────────────────
        landuse = tags.get("landuse", "")
        leisure = tags.get("leisure", "")
        natural = tags.get("natural", "")
        if (
            landuse in ("grass", "park", "recreation_ground", "garden", "meadow")
            or leisure in ("park", "garden", "pitch", "playground")
            or natural in ("wood", "scrub", "heath")
        ) and len(pts) >= 3:
            green_areas.append({
                "polygon_pts": pts,
                "green_type": landuse or leisure or natural,
            })

    intersections = _detect_from_nodes(node_usage, node_ll, lat, lon)
    site_boundary = _infer_site(roads, radius_m)

    return {
        "source": "osm",
        "lat": lat, "lon": lon, "radius_m": radius_m,
        "site_boundary": site_boundary,
        "roads": roads,
        "buildings": buildings,
        "parking_areas": parking_areas,
        "green_areas": green_areas,
        "trees": trees,
        "intersections": intersections,
        "road_count": len(roads),
        "building_count": len(buildings),
        "intersection_count": len(intersections),
    }


def fetch_context_or_fallback(
    lat: float,
    lon: float,
    radius_m: float = 200,
    timeout: int = 20,
    fallback_index: int = 0,
) -> dict[str, Any]:
    """Rich context fetch with graceful offline fallback.

    On success returns the full ``fetch_urban_context_rich`` result.
    On failure returns a synthetic site (same structure, with empty
    ``buildings``/``green_areas``/``parking_areas``/``trees`` lists so
    callers can generate synthetic context from the road geometry).
    """
    try:
        return fetch_urban_context_rich(lat, lon, radius_m, timeout)
    except Exception as exc:
        warnings.warn(f"OSM rich fetch failed ({exc}); using synthetic fallback.")
        base = SYNTHETIC_SITES[fallback_index % len(SYNTHETIC_SITES)].copy()
        # Ensure the extended keys exist for callers that expect them
        base.setdefault("buildings", [])
        base.setdefault("parking_areas", [])
        base.setdefault("green_areas", [])
        base.setdefault("trees", [])
        return base


# ---------------------------------------------------------------------------
# NetworkX street graph builder (optional dependency)
# ---------------------------------------------------------------------------

def build_street_graph(roads: list[dict[str, Any]]) -> "Any | None":
    """Build a NetworkX undirected graph from road centerlines.

    Nodes are snapped road endpoints / vertices; edges carry ``length``,
    ``hierarchy``, ``width_m``, ``name``, and ``travel_time`` (seconds at a
    hierarchy-appropriate speed).

    Returns ``None`` when NetworkX is not installed.
    """
    try:
        import networkx as _nx
    except ImportError:
        return None

    G = _nx.Graph()
    _SNAP = 4.0  # metres — endpoints within this distance are merged
    nodes: dict[tuple[int, int], int] = {}
    nid_ctr = [0]

    def _snap_key(x: float, y: float) -> tuple[int, int]:
        return (round(x / _SNAP), round(y / _SNAP))

    def _get_node(x: float, y: float) -> int:
        key = _snap_key(x, y)
        if key not in nodes:
            nid = nid_ctr[0]; nid_ctr[0] += 1
            nodes[key] = nid
            G.add_node(nid, x=round(key[0] * _SNAP, 1), y=round(key[1] * _SNAP, 1))
        return nodes[key]

    _SPEED = {"main": 50, "secondary": 30, "path": 10}

    for road in roads:
        cl = road.get("centerline", [])
        h  = road.get("hierarchy", "path")
        w  = road.get("width_m", 6.0)
        nm = road.get("name") or ""
        sp = _SPEED.get(h, 10)

        for i in range(len(cl) - 1):
            n1 = _get_node(cl[i][0], cl[i][1])
            n2 = _get_node(cl[i + 1][0], cl[i + 1][1])
            if n1 == n2:
                continue
            seg_len = math.hypot(cl[i+1][0] - cl[i][0], cl[i+1][1] - cl[i][1])
            tt = seg_len / (sp / 3.6) if sp > 0 else seg_len

            if G.has_edge(n1, n2):
                if G[n1][n2].get("length", 9e9) > seg_len:
                    G[n1][n2].update(length=seg_len, hierarchy=h, width_m=w,
                                     name=nm, travel_time=tt)
            else:
                G.add_edge(n1, n2, length=seg_len, hierarchy=h,
                           width_m=w, name=nm, travel_time=tt)

    return G
