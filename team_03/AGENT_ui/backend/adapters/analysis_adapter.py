"""
Adapter to wrap the five analysis nodes for the web app.

Each public function imports the standalone analysis function directly from the
pipeline code (not the LangGraph node wrapper — those require an mcp_client and
mutate AgentState). All return values are JSON-serializable dicts.

Import failures are handled gracefully: every function returns an error dict
rather than raising so the web app can degrade cleanly when optional deps
(shapely, networkx …) are absent.

Pipeline functions called here (all accept a plain layout dict):
  check_collision(layout, profile_config, wall_thickness, compare_layout)
    -> dict  (nodes/collision.py)
  check_visibility(layout)
    -> list  (nodes/visibility.py)
  check_paths(layout)
    -> dict  (nodes/path_analysis.py)
  check_reachability(layout, profile)
    -> dict  (nodes/reachability.py)
  check_orientation(layout, config)
    -> dict  (nodes/orientation.py)
  compute_scores(visibility, path, reachability, orientation, collision, space_config)
    -> dict  (nodes/scoring.py)
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------

PYTHON_DIR = Path(__file__).resolve().parents[3] / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# ---------------------------------------------------------------------------
# Lazy imports — each node's module is imported separately so a missing dep
# in one module does not break the others.
# ---------------------------------------------------------------------------

def _try_import(module_path: str, symbol: str):
    """
    Attempt to import `symbol` from `module_path`.
    Returns (callable, None) on success or (None, error_str) on failure.
    """
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, symbol), None
    except Exception as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# Public wrappers
# ---------------------------------------------------------------------------

def run_collision(
    layout: dict,
    profile_config: dict | None = None,
    wall_thickness: float = 0.20,
    compare_layout: dict | None = None,
) -> dict:
    """
    Run grid-based collision and accessibility analysis.

    Args:
        layout:         parsed layout JSON
        profile_config: user/profile settings (body_width, min_path_width, etc.)
        wall_thickness: wall thickness in metres (default 0.20)
        compare_layout: optional previous layout for before/after diff

    Returns:
        dict with keys: pass, violations, objects, doors, summary, grid_meta
        On import failure: {"error": "...", "pass": False, "violations": [], ...}
    """
    fn, err = _try_import("nodes.collision", "check_collision")
    if fn is None:
        return {
            "error": f"collision import failed: {err}",
            "pass": False,
            "violations": [],
            "objects": [],
            "doors": [],
            "summary": {"total_violations": 0, "hard_violations": 0},
        }
    try:
        result = fn(
            layout,
            profile_config=profile_config,
            wall_thickness=wall_thickness,
            compare_layout=compare_layout,
        )
        # Strip the internal _grid_meta key — large lists of cell indices that
        # are not JSON-friendly and not needed by the web app.
        result.pop("_grid_meta", None)
        return result
    except Exception as exc:
        return {
            "error": str(exc),
            "pass": False,
            "violations": [],
            "objects": [],
            "doors": [],
            "summary": {"total_violations": 0, "hard_violations": 0},
        }


def run_visibility(layout: dict) -> dict:
    """
    Run line-of-sight analysis between objects in the layout.

    Args:
        layout: parsed layout JSON

    Returns:
        dict with keys: sightlines (list), isovists (list)
        On import failure: {"error": "...", "sightlines": [], "isovists": []}
    """
    check_fn, err1 = _try_import("nodes.visibility", "check_visibility")
    isovist_fn, err2 = _try_import("nodes.visibility", "compute_isovists_for_layout")

    if check_fn is None:
        return {
            "error": f"visibility import failed: {err1 or err2}",
            "sightlines": [],
            "isovists": [],
        }
    try:
        sightlines = check_fn(layout)
        isovists = isovist_fn(layout) if isovist_fn else []
        return {
            "sightlines": sightlines,
            "isovists": isovists,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "sightlines": [],
            "isovists": [],
        }


def run_path_analysis(layout: dict) -> dict:
    """
    Run pathfinding analysis.

    Mode 1 (no furniture): BFS through door graph between room pairs.
    Mode 2 (furniture present): A* on per-room grid between object centroids.

    Args:
        layout: parsed layout JSON

    Returns:
        dict with keys: pairs (list), worst_case (dict)
        On import failure: {"error": "...", "pairs": [], "worst_case": {...}}
    """
    fn, err = _try_import("nodes.path_analysis", "check_paths")
    if fn is None:
        return {
            "error": f"path_analysis import failed: {err}",
            "pairs": [],
            "worst_case": {"from": None, "to": None, "distance": 0.0},
        }
    try:
        return fn(layout)
    except Exception as exc:
        return {
            "error": str(exc),
            "pairs": [],
            "worst_case": {"from": None, "to": None, "distance": 0.0},
        }


def run_reachability(
    layout: dict,
    profile_config: dict | None = None,
) -> dict:
    """
    Run ergonomic reachability analysis for every object in the layout.

    Args:
        layout:         parsed layout JSON
        profile_config: profile settings; relevant keys:
                          reach_height_min (float, default 0.4)
                          reach_height_max (float, default 1.8)
                          reach_radius     (float, default 0.7)
                          seated_height    (float, default 0.9)

    Returns:
        dict with keys: results (list), summary (dict)
        On import failure: {"error": "...", "results": [], "summary": {...}}
    """
    fn, err = _try_import("nodes.reachability", "check_reachability")
    if fn is None:
        return {
            "error": f"reachability import failed: {err}",
            "results": [],
            "summary": {
                "total": 0, "reachable": 0,
                "unreachable": 0, "unreachable_objects": [],
            },
        }
    try:
        return fn(layout, profile=profile_config)
    except Exception as exc:
        return {
            "error": str(exc),
            "results": [],
            "summary": {
                "total": 0, "reachable": 0,
                "unreachable": 0, "unreachable_objects": [],
            },
        }


def run_orientation(
    layout: dict,
    config: dict | None = None,
) -> dict:
    """
    Run facing-direction analysis for objects that declare an 'orientation' field.

    Args:
        layout: parsed layout JSON
        config: optional config dict; relevant key:
                  tolerance_degrees (float, default 45)

    Returns:
        dict with keys: results (list), summary (dict)
        On import failure: {"error": "...", "results": [], "summary": {...}}
    """
    fn, err = _try_import("nodes.orientation", "check_orientation")
    if fn is None:
        return {
            "error": f"orientation import failed: {err}",
            "results": [],
            "summary": {
                "total": 0, "facing_ok": 0,
                "facing_wrong": 0, "skipped": 0, "wrong_objects": [],
            },
        }
    try:
        return fn(layout, config=config)
    except Exception as exc:
        return {
            "error": str(exc),
            "results": [],
            "summary": {
                "total": 0, "facing_ok": 0,
                "facing_wrong": 0, "skipped": 0, "wrong_objects": [],
            },
        }


def run_scoring(
    analysis_results: dict,
    space_config: dict | None = None,
) -> dict:
    """
    Compute the weighted layout quality score from all tool results.

    Args:
        analysis_results: dict that may contain any combination of:
            collision_results    (dict)  — from run_collision()
            visibility_results   (dict)  — from run_visibility(); uses "sightlines" key
            path_results         (dict)  — from run_path_analysis()
            reachability_results (dict)  — from run_reachability()
            orientation_results  (dict)  — from run_orientation()
        space_config: optional space config with "tool_weights" override dict

    Returns:
        dict with keys: total_score, grade, breakdown, recommendation
        On import failure: {"error": "...", "total_score": 0, "grade": "F", ...}
    """
    fn, err = _try_import("nodes.scoring", "compute_scores")
    if fn is None:
        return {
            "error": f"scoring import failed: {err}",
            "total_score": 0,
            "grade": "F",
            "breakdown": {},
            "recommendation": "Scoring unavailable — import failed",
        }
    try:
        # visibility results from run_visibility() are nested under "sightlines"
        vis = analysis_results.get("visibility_results")
        if isinstance(vis, dict) and "sightlines" in vis:
            vis = vis["sightlines"]

        return fn(
            visibility_results=vis,
            path_results=analysis_results.get("path_results"),
            reachability_results=analysis_results.get("reachability_results"),
            orientation_results=analysis_results.get("orientation_results"),
            collision_results=analysis_results.get("collision_results"),
            space_config=space_config,
        )
    except Exception as exc:
        return {
            "error": str(exc),
            "total_score": 0,
            "grade": "F",
            "breakdown": {},
            "recommendation": "Scoring failed",
        }


def run_all(
    layout: dict,
    profile_config: dict | None = None,
    space_config: dict | None = None,
) -> dict:
    """
    Convenience function: run all five analysis tools and scoring in sequence.

    Args:
        layout:         parsed layout JSON
        profile_config: passed to collision and reachability
        space_config:   passed to scoring for weight overrides

    Returns:
        dict with keys:
            collision_results, visibility_results, path_results,
            reachability_results, orientation_results, scoring_results
    """
    collision    = run_collision(layout, profile_config=profile_config)
    visibility   = run_visibility(layout)
    paths        = run_path_analysis(layout)
    reachability = run_reachability(layout, profile_config=profile_config)
    orientation  = run_orientation(layout)

    scoring = run_scoring(
        analysis_results={
            "collision_results":    collision,
            "visibility_results":   visibility,
            "path_results":         paths,
            "reachability_results": reachability,
            "orientation_results":  orientation,
        },
        space_config=space_config,
    )

    return {
        "collision_results":    collision,
        "visibility_results":   visibility,
        "path_results":         paths,
        "reachability_results": reachability,
        "orientation_results":  orientation,
        "scoring_results":      scoring,
    }
