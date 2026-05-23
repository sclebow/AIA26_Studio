"""
Grasshopper Python component - generative design optimizer.

Inputs to create in Grasshopper:
- genes_json or genes: JSON string or dictionary with the user request / seed genes
- iterations: number of candidates to evaluate
- seed: optional integer random seed
- locked_shape_type: optional override for typology lock
- site_boundary: optional site boundary polygon or boundary payload
- tree_points: optional list of tree positions for overlap penalties

Example genes:
{
  "shape_type": "u_shape",
  "length": 40,
  "width": 30,
  "height": 15,
  "rotation": 45
}

Outputs:
- mesh: Rhino mesh for the best candidate
- vertices: text summary of vertices
- faces: text summary of faces
- metadata: fitness summary text
- genes_payload: normalized best genes JSON
- error: error message if any
"""

from __future__ import annotations

import importlib
import json
import math
import random
import sys
from typing import Any

mesh = None
vertices = None
faces = None
metadata = None
genes_payload = None
error = None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "ToString"):
        value = value.ToString()
    return str(value)


def _coerce_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "ToString"):
        value = value.ToString()
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return {}
    if value.startswith("{") or value.startswith("["):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        return {"genes_list": parsed}
    return {"shape_type": value}


def _coerce_list_payload(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "ToString"):
        value = value.ToString()
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        # Helper: coerce possible GUIDs or Grasshopper references to Rhino geometry
    def _coerce_geom(obj):
        try:
            if obj is None:
                return None
            g = rs.coercegeometry(obj)
            if g is not None:
                return g
        except Exception:
            pass
        try:
            c = rs.coercecurve(obj)
            if c is not None:
                return c
        except Exception:
            pass
        try:
            b = rs.coercebrep(obj)
            if b is not None:
                return b
        except Exception:
            pass
        try:
            s = rs.coercesurface(obj)
            if s is not None:
                return s
        except Exception:
            pass
        return obj
        return parsed if isinstance(parsed, list) else []
    return []


def _point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
        geo = _coerce_geom(site_crv)
        # If geometry supports Contains (brep/surface), use it
        try:
            if hasattr(geo, "Contains"):
                r = geo.Contains(test, rg.Plane.WorldXY, tol)
                return r != rg.PointContainment.Outside
        except Exception:
            pass

        # If it's a closed planar curve, use rhinoscriptsyntax helper
        try:
            inside = rs.PointInPlanarClosedCurve([test.X, test.Y, test.Z], geo)
            # rs.PointInPlanarClosedCurve returns 1 for inside, 0 on curve, -1 outside
            return inside == 1 or inside == 0
        except Exception:
            pass

        return False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index][0], polygon[index][1]
        x2, y2 = polygon[(index + 1) % count][0], polygon[(index + 1) % count][1]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1):
            inside = not inside
    return inside


def _extract_site_boundary(raw_boundary: Any) -> list[list[float]]:
    if raw_boundary is None:
        return []
    boundary = raw_boundary
    if isinstance(boundary, dict):
        for key in ("boundary", "points", "vertices", "polyline"):
            if key in boundary:
                boundary = boundary[key]
                break
    if isinstance(boundary, list):
        points: list[list[float]] = []
        for item in boundary:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append([float(item[0]), float(item[1])])
        return points
    return []


def _extract_tree_points(raw_trees: Any) -> list[list[float]]:
    if raw_trees is None:
        return []
    trees = raw_trees
    if isinstance(trees, dict):
        for key in ("trees", "points", "tree_points", "locations"):
            if key in trees:
                trees = trees[key]
                break
    if isinstance(trees, list):
        points: list[list[float]] = []
        for item in trees:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append([float(item[0]), float(item[1])])
        return points
    return []


def _evaluate_candidate(shape: Any, site_boundary: list[list[float]], tree_points: list[list[float]]) -> tuple[float, dict[str, float]]:
    area = float(shape.metadata.get("area", 0.0) or 0.0)
    volume = float(shape.metadata.get("volume", 0.0) or 0.0)
    perimeter = float(shape.metadata.get("perimeter", 0.0) or 0.0)
    bbox = shape.metadata.get("bounding_box", {})
    min_pt = bbox.get("min", [0.0, 0.0, 0.0])
    max_pt = bbox.get("max", [0.0, 0.0, 0.0])

    score = area + volume * 0.05 - perimeter * 0.1
    penalties = 0.0

    if site_boundary:
        outside_count = 0
        for vertex in shape.vertices_2d:
            if not _point_in_polygon(vertex, site_boundary):
                outside_count += 1
        boundary_penalty = outside_count * 500.0
        penalties += boundary_penalty

    if tree_points:
        overlap_penalty = 0.0
        for tree_x, tree_y in tree_points:
            if min_pt[0] <= tree_x <= max_pt[0] and min_pt[1] <= tree_y <= max_pt[1]:
                overlap_penalty += 200.0
        penalties += overlap_penalty

    score -= penalties
    return score, {
        "area": area,
        "volume": volume,
        "perimeter": perimeter,
        "penalties": penalties,
        "score": score,
    }


def _build_mesh(rg_module: Any, vertices_3d: list[list[float]], face_indices: list[list[int]]) -> tuple[Any, int]:
    gh_mesh = rg_module.Mesh()
    for vertex in vertices_3d:
        gh_mesh.Vertices.Add(float(vertex[0]), float(vertex[1]), float(vertex[2]))

    face_count = 0
    for face in face_indices:
        if len(face) == 3:
            gh_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]))
            face_count += 1
        elif len(face) == 4:
            gh_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]), int(face[3]))
            face_count += 1
        elif len(face) > 4:
            for index in range(1, len(face) - 1):
                gh_mesh.Faces.AddFace(int(face[0]), int(face[index]), int(face[index + 1]))
                face_count += 1

    gh_mesh.Normals.ComputeNormals()
    gh_mesh.Compact()
    return gh_mesh, face_count


def load_shape_generator_module() -> Any:
    """Import or reload the VSCode shape generator module."""
    shape_module = importlib.import_module("shape_generator_node")
    return importlib.reload(shape_module)


def generate_shape_from_genes(generator: Any, genes: dict[str, Any], locked_shape_type: str | None, rng: random.Random) -> dict[str, Any]:
    """Create one candidate genes payload, respecting any typology lock."""
    return generator.generate_random_genes(
        shape_type=genes.get("shape_type"),
        locked_shape_type=locked_shape_type,
        overrides=genes,
        rng=rng,
    )


def apply_site_transform(shape: Any, genes: dict[str, Any]) -> Any:
    """Placeholder for site placement logic.

    The current generator already applies base_point and rotation inside the
    shape generator, so this function remains the hook for future site-specific
    transforms if you decide to add them later.
    """
    return shape


def convert_to_rhino_mesh(rg_module: Any, shape: Any) -> tuple[Any, int]:
    """Convert a generated shape into a Rhino mesh."""
    return _build_mesh(rg_module, shape.vertices_3d, shape.faces)


def run_generative_loop(
    rg_module: Any,
    generator: Any,
    seed_genes: dict[str, Any],
    seed_genes_obj: Any,
    iterations: int,
    locked_shape_type: str | None,
    site_boundary: list[list[float]],
    tree_points: list[list[float]],
    rng: random.Random,
) -> tuple[Any, Any, int, dict[str, Any], Any, dict[str, float]]:
    """Run the optimization loop and return the best mesh and metadata."""
    best_candidate = None
    best_mesh = None
    best_face_count = 0
    best_score = -1.0e18
    best_metrics: dict[str, float] = {}
    best_shape = None

    for _ in range(iterations):
        candidate_genes = generate_shape_from_genes(
            generator=generator,
            genes=seed_genes,
            locked_shape_type=locked_shape_type,
            rng=rng,
        )

        shape = generator.generate_from_genes(candidate_genes)
        shape = apply_site_transform(shape, candidate_genes)
        score, metrics = _evaluate_candidate(shape, site_boundary, tree_points)

        if best_candidate is None or score > best_score:
            best_candidate = candidate_genes
            best_score = score
            best_metrics = metrics
            best_mesh, best_face_count = convert_to_rhino_mesh(rg_module, shape)
            best_shape = shape

    if best_candidate is None or best_shape is None:
        raise RuntimeError("No valid candidates were generated")

    return best_mesh, best_shape, best_face_count, best_candidate, best_metrics, {"score": best_score}


try:
    py_folder = r"D:\3rd sem\STUDIO\AIA26_Studio - Copy (2)\team_04\PY"
    if py_folder not in sys.path:
        sys.path.insert(0, py_folder)

    rg = importlib.import_module("Rhino.Geometry")
    shape_module = load_shape_generator_module()
    ShapeGenerator = shape_module.ShapeGenerator
    ShapeGenes = shape_module.ShapeGenes

    rng = random.Random()
    seed_value = globals().get("seed")
    if seed_value is not None:
        try:
            rng.seed(int(seed_value))
        except Exception:
            rng.seed(str(seed_value))

    iterations_value = globals().get("iterations", 24)
    try:
        iterations = max(1, int(iterations_value))
    except Exception:
        iterations = 24

    raw_payload = globals().get("genes_json")
    if raw_payload is None:
        raw_payload = globals().get("genes")
    if raw_payload is None:
        raw_payload = globals().get("design_request")

    seed_genes = _coerce_payload(raw_payload)
    seed_genes_obj = ShapeGenes.from_dict(seed_genes)

    shape_lock = globals().get("locked_shape_type")
    if not shape_lock:
        shape_generation = _coerce_payload(globals().get("shape_generation"))
        shape_lock = shape_generation.get("locked_shape_type")
    if not shape_lock:
        shape_lock = seed_genes.get("shape_type")

    site_boundary = _extract_site_boundary(globals().get("site_boundary"))
    tree_points = _extract_tree_points(globals().get("tree_points"))

    generator = ShapeGenerator(shape_id_prefix="GH")
    best_mesh, best_shape, best_face_count, best_candidate, best_metrics, fitness_info = run_generative_loop(
        rg_module=rg,
        generator=generator,
        seed_genes=seed_genes,
        seed_genes_obj=seed_genes_obj,
        iterations=iterations,
        locked_shape_type=shape_lock,
        site_boundary=site_boundary,
        tree_points=tree_points,
        rng=rng,
    )

    mesh = best_mesh
    vertices = "%d vertices" % len(best_shape.vertices_3d)
    faces = "%d faces" % best_face_count
    genes_payload = json.dumps(best_candidate, indent=2)
    metadata = (
        "Shape: {shape_type}\n"
        "Iterations: {iterations}\n"
        "Locked shape: {locked_shape}\n"
        "Area: {area:.2f}\n"
        "Volume: {volume:.2f}\n"
        "Perimeter: {perimeter:.2f}\n"
        "Penalties: {penalties:.2f}\n"
        "Fitness: {score:.2f}"
    ).format(
        shape_type=best_shape.shape_type,
        iterations=iterations,
        locked_shape=shape_lock or "none",
        area=best_metrics.get("area", 0.0),
        volume=best_metrics.get("volume", 0.0),
        perimeter=best_metrics.get("perimeter", 0.0),
        penalties=best_metrics.get("penalties", 0.0),
        score=fitness_info.get("score", 0.0),
    )

except Exception as exc:
    import traceback

    error = "ERROR: %s\n\n%s" % (exc, traceback.format_exc())
    mesh = None
    vertices = None
    faces = None
    metadata = None
    genes_payload = None
