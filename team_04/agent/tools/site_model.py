"""Canonical site model for Team 04 (Phase 0 of BACKEND_PLAN.md).

`build_site_model` bundles the structured site facts that already exist in the
codebase — the boundary graph (corners + sides) and the setback/buildable zone —
into one object so downstream tools read a single source of truth instead of raw
coordinate lists. Phases 1-3 fill the `roads`, `grid`, and `sun` placeholders.

Phase 2 update: ``layout_payload["site_objects"]`` entries of ``type == "road"``
are extracted, analysed by ``road_context.analyze_roads``, and stored in
``model["roads"]``. The resulting ``edge_road_widths`` are fed into the setback
computation so road-adjacent sides get a proportionally larger setback
automatically, and ``model["sides"]`` is updated with per-side ``adjacent_road``
tags so prompts and tools can say "the side along the main road".

The function is deterministic and pure (no LLM, no MCP). It degrades gracefully:
an unusable boundary yields ``{"available": False, ...}`` rather than raising, so
the read_site node can always store *something*.
"""
from __future__ import annotations

from typing import Any

from .site_boundary_graph import analyze_site_boundary
from .site_setback import setback_summary


def build_site_model(
    site_boundary: list[list[float]] | None,
    layout_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a structured site model from a site boundary.

    Parameters
    ----------
    site_boundary:
        Closed polygon as ``[[x, y, z?], ...]``.
    layout_payload:
        Optional original input payload. Consumed keys:

        ``default_setback``, ``edge_setbacks``, ``edge_road_widths``
            Explicit setback overrides (see ``site_setback.py``).
        ``site_objects``
            List of site-context objects.  Entries with ``type == "road"``
            are forwarded to ``road_context.analyze_roads``, which tags
            each site side with its nearest road and derives
            ``edge_road_widths`` for the setback computation.
    """
    layout_payload = layout_payload or {}

    if not isinstance(site_boundary, list) or len(site_boundary) < 3:
        return {"available": False, "reason": "site_boundary missing or has fewer than 3 points"}

    model: dict[str, Any] = {
        "available": True,
        "boundary": site_boundary,
        # Placeholders filled by later phases:
        "roads": None,   # Phase 2 — road_context
        "grid": None,    # Phase 3 — site_grid
        "sun": None,     # Phase 1 — sun_analysis
    }

    try:
        graph_payload = analyze_site_boundary(site_boundary)
        graph = graph_payload.get("data", {}).get("site_boundary_graph", {})
        model["boundary_graph"] = graph
        model["corners"] = graph.get("nodes", [])
        # Each side gets an explicit slot for the road Phase 2 will tag onto it.
        model["sides"] = [
            {**edge, "adjacent_road": None}
            for edge in graph.get("edges", [])
        ]
    except Exception as exc:  # boundary too degenerate for a graph
        model["boundary_graph"] = {}
        model["corners"] = []
        model["sides"] = []
        model["boundary_graph_error"] = str(exc)

    # --- Phase 2: road context -----------------------------------------------
    # Extract road objects from site_objects, analyse them, and tag sides.
    road_erw: dict[int, float] = {}   # edge_road_widths derived from real roads
    site_objects = layout_payload.get("site_objects") or []
    raw_roads = [o for o in site_objects if isinstance(o, dict) and o.get("type") == "road"]

    try:
        from .road_context import analyze_roads  # local import keeps Phase 0 imports clean
        road_result = analyze_roads(model, raw_roads if raw_roads else None)
        model["roads"] = road_result
        # Propagate side tags back into model["sides"]
        if road_result.get("updated_sides"):
            model["sides"] = road_result["updated_sides"]
        # Collect road-derived edge widths for the setback step below
        road_erw = road_result.get("edge_road_widths") or {}
    except Exception as exc:
        model["roads"] = {"available": False, "error": str(exc)}

    # --- Setbacks (Phase 0 + Phase 2 inputs) ---------------------------------
    try:
        setback_kwargs: dict[str, Any] = {}
        if isinstance(layout_payload.get("default_setback"), (int, float)):
            setback_kwargs["default_setback"] = float(layout_payload["default_setback"])
        if isinstance(layout_payload.get("edge_setbacks"), dict):
            setback_kwargs["edge_setbacks"] = {
                int(k): float(v) for k, v in layout_payload["edge_setbacks"].items()
            }
        # Merge: explicit edge_road_widths in payload override road-derived ones
        merged_erw: dict[int, float] = dict(road_erw)
        if isinstance(layout_payload.get("edge_road_widths"), dict):
            merged_erw.update(
                {int(k): float(v) for k, v in layout_payload["edge_road_widths"].items()}
            )
        if merged_erw:
            setback_kwargs["edge_road_widths"] = merged_erw
        model["setbacks"] = setback_summary(site_boundary, **setback_kwargs)
    except Exception as exc:
        model["setbacks"] = None
        model["setbacks_error"] = str(exc)

    return model
