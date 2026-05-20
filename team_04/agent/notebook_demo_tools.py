from __future__ import annotations

from typing import Any

from .mcp_client import LocalToolClient


def build_notebook_demo_tool_client(
    site_boundary: list[list[float]],
    *,
    site_summary: str = "Notebook local site context for end-to-end placement test.",
    setback_m: float = 5.0,
    spatial_intention_score: float = 0.91,
    performance_score: float = 0.88,
    shape_integrity_score: float = 0.94,
) -> LocalToolClient:
    normalized_site_boundary = _normalize_boundary(site_boundary)
    site_area_sqm = _polygon_area_xy(normalized_site_boundary)

    def site_boundary_reader(layout_json: str = "") -> dict[str, Any]:
        del layout_json
        return {
            "success": True,
            "data": {
                "site_boundary": normalized_site_boundary,
                "site_area_sqm": site_area_sqm,
            },
        }

    def context_reader(layout_json: str = "") -> dict[str, Any]:
        del layout_json
        return {
            "success": True,
            "data": {
                "summary": site_summary,
                "site_area_sqm": site_area_sqm,
            },
        }

    def legal_constraints_reader(layout_json: str = "") -> dict[str, Any]:
        del layout_json
        return {
            "success": True,
            "data": {
                "setback_m": setback_m,
            },
        }

    def site_fit_checker(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"fits": True}}

    def setback_checker(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"compliant": True}}

    def area_requirement_checker(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"gfa_compliant": True}}

    def adjacency_access_checker(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"road_access_ok": True}}

    def tree_constraint_checker(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"no_conflicts": True}}

    def spatial_intention_evaluator(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"score": spatial_intention_score}}

    def performance_evaluator(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"score": performance_score}}

    def shape_integrity_evaluator(layout_json: str = "", geometry_id: str = "") -> dict[str, Any]:
        del layout_json
        del geometry_id
        return {"success": True, "data": {"score": shape_integrity_score}}

    tool_definitions = {
        "site_boundary_reader": (
            {
                "name": "site_boundary_reader",
                "description": "Read the notebook site boundary.",
            },
            site_boundary_reader,
        ),
        "context_reader": (
            {
                "name": "context_reader",
                "description": "Read notebook site context.",
            },
            context_reader,
        ),
        "legal_constraints_reader": (
            {
                "name": "legal_constraints_reader",
                "description": "Read notebook legal constraints.",
            },
            legal_constraints_reader,
        ),
        "site_fit_checker": (
            {
                "name": "site_fit_checker",
                "description": "Deterministic notebook site fit check.",
            },
            site_fit_checker,
        ),
        "setback_checker": (
            {
                "name": "setback_checker",
                "description": "Deterministic notebook setback check.",
            },
            setback_checker,
        ),
        "area_requirement_checker": (
            {
                "name": "area_requirement_checker",
                "description": "Deterministic notebook area requirement check.",
            },
            area_requirement_checker,
        ),
        "adjacency_access_checker": (
            {
                "name": "adjacency_access_checker",
                "description": "Deterministic notebook adjacency and access check.",
            },
            adjacency_access_checker,
        ),
        "tree_constraint_checker": (
            {
                "name": "tree_constraint_checker",
                "description": "Deterministic notebook tree conflict check.",
            },
            tree_constraint_checker,
        ),
        "spatial_intention_evaluator": (
            {
                "name": "spatial_intention_evaluator",
                "description": "Deterministic notebook spatial intention evaluation.",
            },
            spatial_intention_evaluator,
        ),
        "performance_evaluator": (
            {
                "name": "performance_evaluator",
                "description": "Deterministic notebook performance evaluation.",
            },
            performance_evaluator,
        ),
        "shape_integrity_evaluator": (
            {
                "name": "shape_integrity_evaluator",
                "description": "Deterministic notebook shape integrity evaluation.",
            },
            shape_integrity_evaluator,
        ),
    }
    return LocalToolClient(tool_definitions)


def _normalize_boundary(site_boundary: list[list[float]]) -> list[list[float]]:
    normalized = [
        [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
        for point in site_boundary
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    if normalized and normalized[0] != normalized[-1]:
        normalized.append(list(normalized[0]))
    return normalized


def _polygon_area_xy(boundary: list[list[float]]) -> float:
    if len(boundary) < 4:
        return 0.0
    area = 0.0
    for index in range(len(boundary) - 1):
        x1, y1 = boundary[index][0], boundary[index][1]
        x2, y2 = boundary[index + 1][0], boundary[index + 1][1]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) * 0.5