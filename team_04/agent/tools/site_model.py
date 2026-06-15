"""Canonical site model for Team 04 (Phase 0 of BACKEND_PLAN.md).

`build_site_model` bundles the structured site facts that already exist in the
codebase — the boundary graph (corners + sides) and the setback/buildable zone —
into one object so downstream tools read a single source of truth instead of raw
coordinate lists. Phases 1-3 fill the `roads`, `grid`, and `sun` placeholders.

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
        Optional original input payload. Used to pull explicit setback overrides
        (``default_setback``, ``edge_setbacks``, ``edge_road_widths``) when present.
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

    try:
        setback_kwargs: dict[str, Any] = {}
        if isinstance(layout_payload.get("default_setback"), (int, float)):
            setback_kwargs["default_setback"] = float(layout_payload["default_setback"])
        if isinstance(layout_payload.get("edge_setbacks"), dict):
            setback_kwargs["edge_setbacks"] = {
                int(k): float(v) for k, v in layout_payload["edge_setbacks"].items()
            }
        if isinstance(layout_payload.get("edge_road_widths"), dict):
            setback_kwargs["edge_road_widths"] = {
                int(k): float(v) for k, v in layout_payload["edge_road_widths"].items()
            }
        model["setbacks"] = setback_summary(site_boundary, **setback_kwargs)
    except Exception as exc:
        model["setbacks"] = None
        model["setbacks_error"] = str(exc)

    return model
