"""
Adapter to wrap spatial_graph.py for the web app.

Adds team_03/python to sys.path so the existing pipeline code can be imported
without modification. All return values are JSON-serializable (no NetworkX
objects escape this module).
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup — add team_03/python so pipeline imports resolve
# ---------------------------------------------------------------------------

PYTHON_DIR = Path(__file__).resolve().parents[3] / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# ---------------------------------------------------------------------------
# Import pipeline code — fail gracefully so the web app can still start
# even when optional dependencies (networkx, shapely …) are missing.
# ---------------------------------------------------------------------------

try:
    from spatial_graph import (  # type: ignore
        build_graph_from_layout,
        enrich_graph_from_analysis,
        graph_to_dict,
        serialize_for_llm,
    )
    _IMPORT_OK = True
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    _IMPORT_OK = False
    _IMPORT_ERROR = str(exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_graph(layout: dict) -> dict:
    """
    Build the spatial graph from a layout dict and return it as a
    JSON-serializable node-link dict suitable for the frontend.

    Args:
        layout: parsed layout JSON (dict with rooms, doors, furniture …)

    Returns:
        node-link dict (networkx.node_link_data format) or an error dict.
    """
    if not _IMPORT_OK:
        return {"error": f"spatial_graph import failed: {_IMPORT_ERROR}"}
    try:
        G = build_graph_from_layout(layout)
        return graph_to_dict(G)
    except Exception as exc:
        return {"error": str(exc)}


def build_enriched_graph(
    layout: dict,
    collision_results: dict | None = None,
    visibility_results: list | None = None,
    path_results: dict | None = None,
    reachability_results: dict | None = None,
    orientation_results: dict | None = None,
) -> dict:
    """
    Build the spatial graph and enrich it with analysis results.

    Args:
        layout:               parsed layout JSON
        collision_results:    output of run_collision(), or None
        visibility_results:   output of run_visibility(), or None
        path_results:         output of run_path_analysis(), or None
        reachability_results: output of run_reachability(), or None
        orientation_results:  output of run_orientation(), or None

    Returns:
        Enriched node-link dict or an error dict.
    """
    if not _IMPORT_OK:
        return {"error": f"spatial_graph import failed: {_IMPORT_ERROR}"}
    try:
        G = build_graph_from_layout(layout)
        G = enrich_graph_from_analysis(
            G,
            collision_results=collision_results,
            visibility_results=visibility_results,
            path_results=path_results,
            reachability_results=reachability_results,
            orientation_results=orientation_results,
        )
        return graph_to_dict(G)
    except Exception as exc:
        return {"error": str(exc)}


def get_graph_text(layout: dict) -> str:
    """
    Return an LLM-friendly compact text representation of the spatial graph.

    Args:
        layout: parsed layout JSON

    Returns:
        Multi-line string description of the graph, or an error string.
    """
    if not _IMPORT_OK:
        return f"ERROR: spatial_graph import failed: {_IMPORT_ERROR}"
    try:
        G = build_graph_from_layout(layout)
        return serialize_for_llm(G)
    except Exception as exc:
        return f"ERROR: {exc}"


def get_enriched_graph_text(
    layout: dict,
    collision_results: dict | None = None,
    visibility_results: list | None = None,
    path_results: dict | None = None,
    reachability_results: dict | None = None,
    orientation_results: dict | None = None,
) -> str:
    """
    Build, enrich, and serialize the graph as LLM-friendly text.

    Args:
        layout:               parsed layout JSON
        collision_results:    output of run_collision(), or None
        visibility_results:   output of run_visibility(), or None
        path_results:         output of run_path_analysis(), or None
        reachability_results: output of run_reachability(), or None
        orientation_results:  output of run_orientation(), or None

    Returns:
        Multi-line string description of the enriched graph, or an error string.
    """
    if not _IMPORT_OK:
        return f"ERROR: spatial_graph import failed: {_IMPORT_ERROR}"
    try:
        G = build_graph_from_layout(layout)
        G = enrich_graph_from_analysis(
            G,
            collision_results=collision_results,
            visibility_results=visibility_results,
            path_results=path_results,
            reachability_results=reachability_results,
            orientation_results=orientation_results,
        )
        return serialize_for_llm(G)
    except Exception as exc:
        return f"ERROR: {exc}"
