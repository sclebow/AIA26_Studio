"""Site Context Memory — the single, cached site-intelligence record that BOTH
optimization and manipulation reference, so they share the same understanding of
the site and are never recomputed per run.

Per the spec: the Urban Context captured after boundary confirmation (roads,
transit, metro, schools, retail, healthcare, parks, green space, context edges,
transport corners, public/private edges, noise sources, view corridors) is
stored ONCE here. Every optimization objective then reads from this memory:

    Solar  → sun analysis (geometry + site)
    Noise  → nearest noise_sources
    Access → roads + transit
    View   → view_corridors / attractors
    Context→ edges + corners

Build is idempotent: if the memory already exists for the current context version
(same generatedAt), it's reused unchanged.
"""
from __future__ import annotations

from typing import Any

from . import context_enrichment as ce


# Words that classify an edge's nearest features into the spec's named groups.
_GROUPS: dict[str, tuple[str, ...]] = {
    "transit": ("metro", "subway", "station", "bus", "tram", "transit", "rail"),
    "school": ("school", "college", "university", "education", "kindergarten"),
    "retail": ("shop", "store", "retail", "supermarket", "mall", "grocery", "market"),
    "healthcare": ("hospital", "clinic", "pharmacy", "healthcare", "doctor"),
    "park": ("park", "garden", "green", "playground", "recreation"),
    "water": ("water", "river", "lake", "canal", "sea", "coast", "waterfront"),
    "road": ("road", "street", "avenue", "highway", "motorway", "drive", "lane"),
}


def _classify_edges(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Group edges + their nearest features into the named site-intelligence layers,
    and tag each edge public/private + note transport corners."""
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in _GROUPS}
    public_edges: list[dict[str, Any]] = []
    private_edges: list[dict[str, Any]] = []
    transport_corners: list[dict[str, Any]] = []

    for edge in edges:
        nearest = edge.get("nearest") or {}
        labels = " ".join(str(k).lower() for k in nearest.keys())
        edge_groups = set()
        for group, words in _GROUPS.items():
            if any(w in labels for w in words):
                groups[group].append({"direction": edge.get("direction"), "mid": edge.get("mid"),
                                      "nearest": nearest})
                edge_groups.add(group)
        # Public = fronts a road/transit/retail (active street); private = quiet/residential.
        if edge_groups & {"road", "transit", "retail"}:
            public_edges.append({"direction": edge.get("direction"), "mid": edge.get("mid"),
                                 "reason": "fronts road/transit/retail"})
        else:
            private_edges.append({"direction": edge.get("direction"), "mid": edge.get("mid"),
                                  "reason": "quiet/residential frontage"})
        # Transport corner = an edge near BOTH a road and transit.
        if "road" in edge_groups and "transit" in edge_groups:
            transport_corners.append({"direction": edge.get("direction"), "mid": edge.get("mid")})

    return {
        "layers": {k: v for k, v in groups.items() if v},
        "public_edges": public_edges,
        "private_edges": private_edges,
        "transport_corners": transport_corners,
    }


def build(urban_context: dict[str, Any] | None, *, site_boundary=None,
          obstacles=None, context_scores=None) -> dict[str, Any]:
    """Build the Site Context Memory from the stored urban context. Pure + cheap;
    callers cache the result on the session (see ensure())."""
    uc = urban_context or {}
    edges = uc.get("edges") or []
    classed = _classify_edges(edges)

    # Scorer-ready ctx data (roads / noise_sources / view_attractors) from the edges.
    enriched = ce.enrich_ctx(
        {"site_boundary": site_boundary, "obstacles": obstacles or [],
         "context_scores": context_scores or uc.get("scores") or {}},
        uc,
    )

    return {
        "version": uc.get("generatedAt") or "v1",
        "edges": edges,
        "scores": uc.get("scores") or {},
        # named site-intelligence layers
        "layers": classed["layers"],
        "public_edges": classed["public_edges"],
        "private_edges": classed["private_edges"],
        "transport_corners": classed["transport_corners"],
        # scorer-ready feature data (referenced by objectives, computed ONCE)
        "roads": enriched.get("roads", []),
        "noise_sources": enriched.get("noise_sources", []),
        "view_corridors": enriched.get("view_attractors", []),
        "availability": ce.availability_summary(enriched),
    }


def ensure(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Site Context Memory for this session, building + caching it on the
    state if absent or stale. Returns None if there's no urban context to build from.
    The CALLER is responsible for persisting state if it changed (returns the memory;
    sets state['site_context_memory'] in place)."""
    uc = state.get("urban_context") or {}
    if not uc.get("edges"):
        return None
    cached = state.get("site_context_memory")
    cur_version = uc.get("generatedAt") or "v1"
    if cached and cached.get("version") == cur_version:
        return cached  # reuse — do NOT recompute every run
    mem = build(
        uc,
        site_boundary=state.get("site_boundary"),
        obstacles=None,
        context_scores=uc.get("scores") or state.get("context_scores"),
    )
    state["site_context_memory"] = mem
    return mem
