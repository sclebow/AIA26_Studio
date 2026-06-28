"""Urban Context Analysis — STAGE between Boundary and Shape Generation.

Given a confirmed site (a metric-frame boundary + the lat/lng its metric frame is
centered on), fetch the surrounding city from OpenStreetMap via Overpass within a
2 km radius, classify it into road/amenity layers, project everything into the
SAME metric frame the building geometry uses, compute per-edge nearest-feature
distances, derive ten 0-100 context scores, and produce an AI-style context report.

Pure data + math here; the route (routes/context_routes.py) handles HTTP + caching,
and the frontend (views/contextView.js + explorer) renders the digital twin.

Nothing is mocked: roads/amenities are real OSM features for the user's actual site.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any

# Multiple mirrors — public Overpass servers 504 under load, so we try in order.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
CONTEXT_RADIUS_M = 2000.0
# Buildings are far heavier than roads/amenities; fetch them within a tighter radius
# so the digital-twin query stays under the public servers' time budget.
BUILDING_RADIUS_M = 700.0
_R = 6378137.0  # WGS84 equatorial radius (m) — matches the frontend's projection.


# --------------------------------------------------------------------------- #
# Projection — lat/lng -> the site's local metric frame (equirectangular about
# the projection origin). This is the inverse of projectRingToMeters in the
# frontend, so OSM features land in the same coordinate space as the building.
# --------------------------------------------------------------------------- #
def _project(lat: float, lng: float, lat0: float, lng0: float) -> list[float]:
    cos_lat = math.cos(math.radians(lat0))
    x = math.radians(lng - lng0) * _R * cos_lat
    y = math.radians(lat - lat0) * _R
    return [round(x, 2), round(y, 2)]


# --------------------------------------------------------------------------- #
# Layer taxonomy — how OSM tags map onto the Context Explorer tree.
# Each entry: (category, layer, color, optional dash for roads).
# --------------------------------------------------------------------------- #
ROAD_STYLES = {
    "primary": {"label": "Primary", "color": "#ff5d5d", "width": 4, "dash": None},
    "secondary": {"label": "Secondary", "color": "#ffae42", "width": 3, "dash": None},
    "tertiary": {"label": "Tertiary", "color": "#ffe04a", "width": 2, "dash": [6, 4]},
    "residential": {"label": "Local", "color": "#7fd1ff", "width": 1.5, "dash": [3, 4]},
}

# amenity layer -> (category, label, color, Overpass selector fragments)
AMENITY_LAYERS: dict[str, dict[str, Any]] = {
    "school": {"category": "Education", "label": "Schools", "color": "#5ad17f",
               "match": [("amenity", "school")]},
    "university": {"category": "Education", "label": "Universities", "color": "#37b86a",
                   "match": [("amenity", "university"), ("amenity", "college")]},
    "hospital": {"category": "Healthcare", "label": "Hospitals", "color": "#ff6f91",
                 "match": [("amenity", "hospital"), ("amenity", "clinic")]},
    "grocery": {"category": "Retail", "label": "Grocery", "color": "#c08cff",
                "match": [("shop", "supermarket"), ("shop", "convenience"), ("shop", "grocery")]},
    "shopping": {"category": "Retail", "label": "Shopping", "color": "#9a6cff",
                 "match": [("shop", "mall"), ("shop", "department_store")]},
    "park": {"category": "Parks", "label": "Parks", "color": "#3fd6a4",
             "match": [("leisure", "park"), ("leisure", "garden")]},
    "bus_stop": {"category": "Transportation", "label": "Bus Stops", "color": "#4ad0ff",
                 "match": [("highway", "bus_stop")]},
    "metro": {"category": "Transportation", "label": "Metro Stations", "color": "#2bb6ff",
              "match": [("railway", "station"), ("station", "subway")]},
    "train": {"category": "Transportation", "label": "Train Stations", "color": "#1f8fff",
              "match": [("railway", "halt")]},
    "restaurant": {"category": "Retail", "label": "Restaurants", "color": "#ff9d5c",
                   "match": [("amenity", "restaurant"), ("amenity", "cafe")]},
    "public": {"category": "Public", "label": "Public Facilities", "color": "#b8c4d6",
               "match": [("amenity", "library"), ("amenity", "townhall"), ("amenity", "community_centre")]},
}


# --------------------------------------------------------------------------- #
# Overpass query + fetch
# --------------------------------------------------------------------------- #
def _roads_amenities_query(lat: float, lng: float, radius: float) -> str:
    """Roads + amenities — the lighter query that must always succeed. Each group
    gets its own `out` so dense amenity nodes can't starve road geometry."""
    a = f"around:{int(radius)},{lat},{lng}"
    return (
        "[out:json][timeout:60];"
        f'(way[highway~"^(primary|secondary|tertiary|residential)$"]({a}););out geom 1500;'
        f'(node[amenity]({a});way[amenity]({a});'
        f'node[shop]({a});way[shop]({a});'
        f'node[leisure~"^(park|garden)$"]({a});way[leisure~"^(park|garden)$"]({a});'
        f'node[railway~"^(station|halt)$"]({a});'
        f'node[highway=bus_stop]({a}););out center 2500;'
    )


def _buildings_query(lat: float, lng: float, radius: float) -> str:
    a = f"around:{int(radius)},{lat},{lng}"
    return f'[out:json][timeout:50];(way[building]({a}););out geom 900;'


def _overpass(query: str, timeout: int = 70) -> dict[str, Any]:
    """POST a query, trying each mirror until one succeeds. Raises if all fail."""
    data = urllib.parse.urlencode({"data": query}).encode()
    last_exc: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "AIA26-Studio-Team04/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last_exc = exc
            continue
    raise last_exc or RuntimeError("All Overpass mirrors failed")


def fetch_overpass(lat: float, lng: float, radius: float = CONTEXT_RADIUS_M) -> dict[str, Any]:
    """Fetch the 2 km context. Roads + amenities are required (raises if they fail).
    Buildings are best-effort with a tighter radius — if that heavy query times out,
    we still return the rest so the stage works without the 3D building twin."""
    raw = _overpass(_roads_amenities_query(lat, lng, radius), timeout=75)
    try:
        b = _overpass(_buildings_query(lat, lng, min(radius, BUILDING_RADIUS_M)), timeout=60)
        raw.setdefault("elements", []).extend(b.get("elements", []))
    except Exception:  # noqa: BLE001 — twin buildings are optional, never fatal
        pass
    return raw


# --------------------------------------------------------------------------- #
# Classification — raw OSM -> layered, projected context
# --------------------------------------------------------------------------- #
def _way_centroid_latlng(el: dict[str, Any]) -> tuple[float, float] | None:
    geom = el.get("geometry")
    if geom:
        lats = [g["lat"] for g in geom]
        lngs = [g["lon"] for g in geom]
        return sum(lats) / len(lats), sum(lngs) / len(lngs)
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    if "lat" in el:
        return el["lat"], el["lon"]
    return None


def _road_class(tags: dict[str, str]) -> str | None:
    hw = tags.get("highway")
    return hw if hw in ROAD_STYLES else None


def _amenity_layer(tags: dict[str, str]) -> str | None:
    for layer, spec in AMENITY_LAYERS.items():
        for k, v in spec["match"]:
            if tags.get(k) == v:
                return layer
    return None


def classify(raw: dict[str, Any], lat0: float, lng0: float) -> dict[str, Any]:
    """Turn the Overpass dump into projected, layered context geometry."""
    roads: dict[str, list[dict[str, Any]]] = {k: [] for k in ROAD_STYLES}
    amenities: dict[str, list[dict[str, Any]]] = {k: [] for k in AMENITY_LAYERS}
    buildings: list[list[list[float]]] = []

    for el in raw.get("elements", []):
        tags = el.get("tags") or {}

        # Roads — keep the full projected polyline.
        rc = _road_class(tags)
        if rc and el.get("type") == "way" and el.get("geometry"):
            poly = [_project(g["lat"], g["lon"], lat0, lng0) for g in el["geometry"]]
            roads[rc].append({"name": tags.get("name"), "path": poly})
            continue

        # OSM building footprints (for the 3D twin). Keep a reasonable count.
        if tags.get("building") and el.get("type") == "way" and el.get("geometry") and len(buildings) < 1200:
            ring = [_project(g["lat"], g["lon"], lat0, lng0) for g in el["geometry"]]
            if len(ring) >= 3:
                # crude per-building height from levels if present, else default.
                lvls = tags.get("building:levels")
                h = float(lvls) * 3.0 if lvls and str(lvls).replace(".", "").isdigit() else 9.0
                buildings.append({"ring": ring, "height": round(h, 1)})
            continue

        # Amenities (points or area centroids).
        layer = _amenity_layer(tags)
        if layer:
            ll = _way_centroid_latlng(el)
            if ll:
                xy = _project(ll[0], ll[1], lat0, lng0)
                amenities[layer].append({"name": tags.get("name"), "xy": xy})

    return {"roads": roads, "amenities": amenities, "buildings": buildings}


# --------------------------------------------------------------------------- #
# Distances — site edges -> nearest feature per layer
# --------------------------------------------------------------------------- #
def _dist_point_to_seg(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _min_dist_to_polyline(pt, path) -> float:
    best = float("inf")
    for i in range(len(path) - 1):
        d = _dist_point_to_seg(pt[0], pt[1], path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
        if d < best:
            best = d
    return best


def _edge_label(i: int) -> str:
    return f"Edge {chr(ord('A') + i)}"


def _site_edges(boundary: list[list[float]]) -> list[dict[str, Any]]:
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    edges = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        # compass label from the midpoint relative to the centroid
        edges.append({"index": i, "label": _edge_label(i), "a": list(a), "b": list(b), "mid": list(mid)})
    return edges


def _compass(mid, centroid) -> str:
    dx, dy = mid[0] - centroid[0], mid[1] - centroid[1]
    ang = math.degrees(math.atan2(dy, dx))  # 0=E, 90=N
    dirs = [("East", -22.5, 22.5), ("North", 67.5, 112.5), ("West", 157.5, 180.0),
            ("West", -180.0, -157.5), ("South", -112.5, -67.5)]
    if 22.5 <= ang < 67.5:
        return "Northeast"
    if 112.5 <= ang < 157.5:
        return "Northwest"
    if -157.5 <= ang < -112.5:
        return "Southwest"
    if -67.5 <= ang < -22.5:
        return "Southeast"
    if -22.5 <= ang < 22.5:
        return "East"
    if 67.5 <= ang < 112.5:
        return "North"
    if -112.5 <= ang < -67.5:
        return "South"
    return "West"


def edge_intelligence(boundary: list[list[float]], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Per site edge, the nearest feature of each layer (distance in m + name)."""
    centroid = (
        sum(p[0] for p in boundary) / len(boundary),
        sum(p[1] for p in boundary) / len(boundary),
    )
    edges = _site_edges(boundary)
    roads, amenities = context["roads"], context["amenities"]
    out = []
    for e in edges:
        mid = e["mid"]
        nearest: dict[str, dict[str, Any]] = {}
        # roads
        for rc, items in roads.items():
            best = None
            for r in items:
                d = _min_dist_to_polyline(mid, r["path"]) if len(r["path"]) >= 2 else float("inf")
                if best is None or d < best["distance_m"]:
                    best = {"distance_m": round(d), "name": r.get("name")}
            if best and best["distance_m"] < float("inf"):
                nearest[f"road_{rc}"] = {**best, "label": ROAD_STYLES[rc]["label"] + " Road"}
        # amenities
        for layer, items in amenities.items():
            best = None
            for it in items:
                d = math.hypot(mid[0] - it["xy"][0], mid[1] - it["xy"][1])
                if best is None or d < best["distance_m"]:
                    best = {"distance_m": round(d), "name": it.get("name")}
            if best:
                nearest[layer] = {**best, "label": AMENITY_LAYERS[layer]["label"]}
        out.append({
            "index": e["index"], "label": e["label"],
            "direction": _compass(mid, centroid),
            "a": e["a"], "b": e["b"], "mid": mid,
            "nearest": nearest,
        })
    return out


# --------------------------------------------------------------------------- #
# Layer summary — counts + nearest distance (for the Context Explorer)
# --------------------------------------------------------------------------- #
def layer_summary(boundary: list[list[float]], context: dict[str, Any]) -> dict[str, Any]:
    centroid = (
        sum(p[0] for p in boundary) / len(boundary),
        sum(p[1] for p in boundary) / len(boundary),
    )
    roads = {}
    for rc, items in context["roads"].items():
        nearest = min(
            (_min_dist_to_polyline(centroid, r["path"]) for r in items if len(r["path"]) >= 2),
            default=None,
        )
        roads[rc] = {"label": ROAD_STYLES[rc]["label"], "color": ROAD_STYLES[rc]["color"],
                     "count": len(items), "nearest_m": round(nearest) if nearest is not None else None}
    amen = {}
    for layer, items in context["amenities"].items():
        nearest = min(
            (math.hypot(centroid[0] - it["xy"][0], centroid[1] - it["xy"][1]) for it in items),
            default=None,
        )
        spec = AMENITY_LAYERS[layer]
        amen[layer] = {"category": spec["category"], "label": spec["label"], "color": spec["color"],
                       "count": len(items), "nearest_m": round(nearest) if nearest is not None else None}
    return {"roads": roads, "amenities": amen, "buildings": len(context.get("buildings", []))}


# --------------------------------------------------------------------------- #
# Context scores — ten 0-100 indices derived from counts + proximity.
# --------------------------------------------------------------------------- #
def _proximity_score(nearest_m: float | None, count: int, *, ideal_m: float, max_count: int) -> float:
    """Blend of 'how close is the nearest' and 'how many are around'. 0-100."""
    if not count:
        return 0.0
    # proximity: full marks within ideal_m, decaying to ~0 by 4x ideal.
    prox = max(0.0, 1.0 - (max(0.0, (nearest_m or ideal_m) - ideal_m) / (3 * ideal_m)))
    density = min(1.0, count / max_count)
    return round(100 * (0.65 * prox + 0.35 * density), 0)


def context_scores(summary: dict[str, Any]) -> dict[str, float]:
    a = summary["amenities"]
    r = summary["roads"]

    def amen(layer):
        return a.get(layer, {"count": 0, "nearest_m": None})

    transit = max(
        _proximity_score(amen("metro")["nearest_m"], amen("metro")["count"], ideal_m=400, max_count=4),
        _proximity_score(amen("train")["nearest_m"], amen("train")["count"], ideal_m=800, max_count=3),
        _proximity_score(amen("bus_stop")["nearest_m"], amen("bus_stop")["count"], ideal_m=200, max_count=20),
    )
    walk = _proximity_score(amen("restaurant")["nearest_m"], amen("restaurant")["count"], ideal_m=200, max_count=30)
    education = max(
        _proximity_score(amen("school")["nearest_m"], amen("school")["count"], ideal_m=400, max_count=8),
        _proximity_score(amen("university")["nearest_m"], amen("university")["count"], ideal_m=1000, max_count=3),
    )
    green = _proximity_score(amen("park")["nearest_m"], amen("park")["count"], ideal_m=300, max_count=6)
    retail = max(
        _proximity_score(amen("grocery")["nearest_m"], amen("grocery")["count"], ideal_m=250, max_count=10),
        _proximity_score(amen("shopping")["nearest_m"], amen("shopping")["count"], ideal_m=600, max_count=4),
    )
    healthcare = _proximity_score(amen("hospital")["nearest_m"], amen("hospital")["count"], ideal_m=800, max_count=4)
    # road hierarchy access — closeness to primary/secondary roads.
    road_access = max(
        _proximity_score(r.get("primary", {}).get("nearest_m"), r.get("primary", {}).get("count", 0), ideal_m=150, max_count=4),
        _proximity_score(r.get("secondary", {}).get("nearest_m"), r.get("secondary", {}).get("count", 0), ideal_m=250, max_count=6),
    )
    accessibility = round((transit + road_access) / 2, 0)
    connectivity = round((road_access + 0.5 * transit + 0.5 * walk) / 2, 0)
    amenity = round((retail + education + healthcare + green) / 4, 0)
    vitality = round((transit + walk + retail + green) / 4, 0)

    return {
        "transit": transit, "walkability": walk, "education": education,
        "green_space": green, "retail": retail, "healthcare": healthcare,
        "accessibility": accessibility, "connectivity": connectivity,
        "amenity": amenity, "urban_vitality": vitality,
    }


SCORE_LABELS = {
    "transit": "Transit", "walkability": "Walkability", "education": "Education",
    "green_space": "Green Space", "retail": "Retail", "healthcare": "Healthcare",
    "accessibility": "Accessibility", "connectivity": "Connectivity",
    "amenity": "Amenity", "urban_vitality": "Urban Vitality",
}


# --------------------------------------------------------------------------- #
# Context report — AI-style summary + design opportunities.
# --------------------------------------------------------------------------- #
def build_report(edges: list[dict[str, Any]], scores: dict[str, float], summary: dict[str, Any]) -> dict[str, Any]:
    """A structured + prose context report. Tries the LLM for the narrative; falls
    back to a deterministic template so the report always renders."""
    edge_lines = []
    for e in edges:
        n = e["nearest"]
        bits = []
        for key in ("metro", "train", "bus_stop", "park", "school", "grocery", "shopping", "hospital"):
            if key in n and n[key]["distance_m"] is not None:
                bits.append(f"{n[key]['distance_m']}m from {n[key]['label']}")
        # adjacency to a primary road
        if "road_primary" in n and n["road_primary"]["distance_m"] <= 30:
            bits.insert(0, "adjacent to a Primary Road")
        edge_lines.append({"edge": f"{e['direction']} Edge ({e['label']})", "notes": bits[:3]})

    opportunities = _opportunities(scores)

    narrative = _llm_narrative(edge_lines, scores, opportunities)
    return {
        "edges": edge_lines,
        "opportunities": opportunities,
        "scores": scores,
        "narrative": narrative,
    }


def _opportunities(scores: dict[str, float]) -> list[str]:
    out = []
    if scores["transit"] >= 70:
        out.append("Strong transit-oriented development potential")
    if scores["walkability"] >= 70:
        out.append("High walkability — activate ground-floor frontage")
    if scores["accessibility"] >= 70:
        out.append("Excellent accessibility favours mixed-use programming")
    if scores["green_space"] >= 70:
        out.append("Preserve view corridors toward nearby green space")
    if scores["retail"] >= 70:
        out.append("Active retail context — engage street-facing edges")
    if scores["education"] >= 70:
        out.append("Education-rich area suits residential / student housing")
    if scores["healthcare"] >= 70:
        out.append("Good healthcare proximity supports senior / care living")
    if not out:
        out.append("Moderate context — a flexible, self-sufficient program fits best")
    return out


def design_directives(scores: dict[str, float]) -> dict[str, Any]:
    """Turn scores into concrete hints the shape-generation + optimization stages
    can act on (context-aware design)."""
    d: dict[str, Any] = {"density_bias": 0.0, "preserve_views": False,
                         "mixed_use": False, "activate_street_edges": False, "notes": []}
    if scores["transit"] >= 70:
        d["density_bias"] += 0.25
        d["notes"].append("High transit → higher density")
    if scores["green_space"] >= 70:
        d["preserve_views"] = True
        d["notes"].append("High green space → preserve view corridors, maximise landscape integration")
    if scores["accessibility"] >= 70:
        d["mixed_use"] = True
        d["notes"].append("High accessibility → favour mixed-use")
    if scores["retail"] >= 70:
        d["activate_street_edges"] = True
        d["notes"].append("High retail → activate street-facing edges")
    d["density_bias"] = round(min(0.5, d["density_bias"]), 2)
    return d


def _llm_narrative(edge_lines, scores, opportunities) -> str:
    """Optional LLM-written summary; deterministic fallback otherwise."""
    try:
        from langchain_openai import ChatOpenAI

        from agent.config import load_settings

        s = load_settings()
        llm = ChatOpenAI(api_key=s.api_key, base_url=s.base_url, model=s.llm_model,
                         timeout=s.request_timeout_seconds, temperature=0.3)
        payload = {"edges": edge_lines, "scores": scores, "opportunities": opportunities}
        prompt = (
            "You are an urban planner. Write a concise (max 120 words) urban-context "
            "summary for a development site, using ONLY the data given. Mention the "
            "standout edges and the strongest scores. No markdown headers, plain prose.\n\n"
            + json.dumps(payload)
        )
        resp = llm.invoke([{"role": "user", "content": prompt}])
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        text = str(content).strip()
        if text:
            return text
    except Exception:  # noqa: BLE001
        pass
    # Deterministic fallback.
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_txt = ", ".join(f"{SCORE_LABELS[k]} {int(v)}" for k, v in top)
    return (
        f"The site sits in a context scoring strongest on {top_txt}. "
        + " ".join(o + "." for o in opportunities[:3])
    )


# --------------------------------------------------------------------------- #
# Top-level orchestration — used by the route.
# --------------------------------------------------------------------------- #
def analyze_context(
    boundary: list[list[float]], center: dict[str, float], *, radius: float = CONTEXT_RADIUS_M
) -> dict[str, Any]:
    """Full pipeline: fetch -> classify -> summary -> edges -> scores -> report.
    `center` is {lat, lng} (the projection origin); `boundary` is in the metric frame."""
    lat0, lng0 = float(center["lat"]), float(center["lng"])
    raw = fetch_overpass(lat0, lng0, radius)
    context = classify(raw, lat0, lng0)
    summary = layer_summary(boundary, context)
    edges = edge_intelligence(boundary, context)
    scores = context_scores(summary)
    report = build_report(edges, scores, summary)
    directives = design_directives(scores)
    return {
        "radius_m": radius,
        "center": {"lat": lat0, "lng": lng0},
        "geometry": context,        # roads / amenities / buildings (projected)
        "summary": summary,         # counts + nearest per layer
        "edges": edges,             # per-edge nearest features
        "scores": scores,           # ten 0-100 indices
        "score_labels": SCORE_LABELS,
        "report": report,           # narrative + opportunities
        "directives": directives,   # context-aware design hints
    }
