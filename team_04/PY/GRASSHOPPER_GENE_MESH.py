"""
Grasshopper Python component - generative design optimizer.

Inputs to create in Grasshopper:
- genes_json or genes: JSON string or dictionary with the user request / seed genes
- iterations: number of candidates to evaluate
- seed: optional integer random seed
- locked_shape_type: optional override for typology lock
- site_boundary: optional site boundary polygon or boundary payload
- tree_points: optional list of tree positions for overlap penalties
- tree_sizes: optional list of tree size values aligned with tree_points
- tree_count: optional tree count used when points/sizes are provided as strings or omitted

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


def _is_null_like_text(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return text in {"", "null", "none", "undefined", "nan"}


def _coerce_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        payload = dict(value)
        raw_shape_type = payload.get("shape_type")
        if raw_shape_type is None or _is_null_like_text(raw_shape_type):
            payload.pop("shape_type", None)
        if not payload or (len(payload) == 1 and payload.get("shape_type") is None):
            return {}
        return payload
    if hasattr(value, "ToString"):
        value = value.ToString()
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if _is_null_like_text(value):
        return {}
    if value.startswith("{") or value.startswith("["):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            raw_shape_type = parsed.get("shape_type")
            if raw_shape_type is None or _is_null_like_text(raw_shape_type):
                parsed.pop("shape_type", None)
            if not parsed:
                return {}
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
    if _is_null_like_text(value):
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []


def _coerce_int_payload(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if hasattr(value, "ToString"):
        value = value.ToString()
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text:
        return default
    try:
        return int(float(text))
    except Exception:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (int, float)):
                return int(parsed)
        except Exception:
            pass
    return default


def _coerce_float_payload(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "ToString"):
        value = value.ToString()
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (int, float)):
                return float(parsed)
        except Exception:
            pass
    return default


def _has_meaningful_input(
    raw_payload: Any,
    shape_lock: Any,
    site_boundary: Any,
    tree_count: int,
    tree_points: Any,
    tree_sizes: Any,
) -> bool:
    if isinstance(raw_payload, dict):
        if raw_payload:
            if any(key in raw_payload for key in ("shape_type", "length", "width", "height", "rotation", "vertices", "arm_a_length", "arm_b_length", "wing_depth", "courtyard_size")):
                if any(not _is_null_like_text(raw_payload.get(key)) for key in raw_payload.keys() if key != "shape_type"):
                    return True
                if not _is_null_like_text(raw_payload.get("shape_type")) and str(raw_payload.get("shape_type")).strip().lower() != "rectangle":
                    return True
        else:
            raw_payload = None
    elif isinstance(raw_payload, str):
        if not _is_null_like_text(raw_payload):
            return True
    elif raw_payload not in (None, [], {}):
        return True
    if isinstance(shape_lock, str) and shape_lock.strip():
        return True
    if site_boundary:
        return True
    if tree_count > 0:
        return True
    if tree_points:
        return True
    if tree_sizes:
        return True
    return False


def _point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    x = float(point[0])
    y = float(point[1])
    inside = False
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
    if isinstance(trees, str):
        parsed = _coerce_list_payload(trees)
        trees = parsed if parsed else trees
    if isinstance(trees, list):
        points: list[list[float]] = []
        for item in trees:
            if hasattr(item, "ToString"):
                item = item.ToString()
            if isinstance(item, str):
                item_text = item.strip()
                if not item_text:
                    continue
                try:
                    parsed_item = json.loads(item_text)
                    item = parsed_item
                except Exception:
                    continue
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append([float(item[0]), float(item[1])])
        return points
    return []


def _extract_tree_sizes(raw_sizes: Any, tree_count: int) -> list[float]:
    if raw_sizes is None:
        return []
    sizes = raw_sizes
    if isinstance(sizes, dict):
        for key in ("sizes", "tree_sizes", "radii", "canopy_sizes"):
            if key in sizes:
                sizes = sizes[key]
                break
    if isinstance(sizes, str):
        parsed = _coerce_list_payload(sizes)
        sizes = parsed if parsed else sizes
    if isinstance(sizes, list):
        result: list[float] = []
        for item in sizes:
            if hasattr(item, "ToString"):
                item = item.ToString()
            try:
                result.append(float(item))
            except Exception:
                continue
        return result[:tree_count] if tree_count else result
    if isinstance(sizes, (int, float)):
        return [float(sizes)] * max(0, tree_count)
    return []


def _infer_tree_sizes_from_points(tree_points: list[list[float]]) -> list[float]:
    if not tree_points:
        return []

    y_values = [point[1] for point in tree_points if len(point) >= 2]
    if not y_values:
        return [5.0 for _ in tree_points]

    min_y = min(y_values)
    max_y = max(y_values)
    y_span = max(max_y - min_y, 1e-9)

    inferred_sizes: list[float] = []
    for point in tree_points:
        y_value = point[1] if len(point) >= 2 else min_y
        normalized = (y_value - min_y) / y_span
        inferred_sizes.append(round(4.5 + (normalized * 2.0), 2))
    return inferred_sizes


def _infer_tree_points_from_count(tree_count: int) -> list[list[float]]:
    if tree_count <= 0:
        return []
    if tree_count == 1:
        return [[0.5, 0.92]]
    if tree_count == 2:
        return [[0.333, 0.92], [0.667, 0.92]]
    return [[round((index + 1) / (tree_count + 1), 3), 0.92] for index in range(tree_count)]


def _evaluate_candidate(
    shape: Any,
    site_boundary: list[list[float]],
    tree_points: list[list[float]],
    tree_sizes: list[float],
) -> tuple[float, dict[str, float]]:
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
        for index, (tree_x, tree_y) in enumerate(tree_points):
            if min_pt[0] <= tree_x <= max_pt[0] and min_pt[1] <= tree_y <= max_pt[1]:
                size_factor = 1.0
                if index < len(tree_sizes):
                    try:
                        size_factor = max(0.5, float(tree_sizes[index]) / 5.0)
                    except Exception:
                        size_factor = 1.0
                overlap_penalty += 200.0 * size_factor
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
    tree_sizes: list[float],
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
        score, metrics = _evaluate_candidate(shape, site_boundary, tree_points, tree_sizes)

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
    py_folder = r"C:\PROJECTS\1\AIA26_Studio\team_04\PY"
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
    tree_count = _coerce_int_payload(globals().get("tree_count"), 0)
    if tree_count <= 0:
        tree_count = _coerce_int_payload(globals().get("number_of_trees"), 0)

    tree_points = _extract_tree_points(globals().get("tree_points"))
    if not tree_points:
        tree_points = _extract_tree_points(globals().get("tree_locations"))
    if not tree_points and tree_count > 0:
        tree_points = _infer_tree_points_from_count(tree_count)
    tree_sizes = _extract_tree_sizes(globals().get("tree_sizes"), len(tree_points))
    if not tree_sizes and tree_points:
        tree_sizes = _infer_tree_sizes_from_points(tree_points)
    if tree_sizes and len(tree_sizes) < len(tree_points):
        tree_sizes.extend([tree_sizes[-1]] * (len(tree_points) - len(tree_sizes)))
    elif len(tree_sizes) > len(tree_points):
        tree_sizes = tree_sizes[:len(tree_points)]

    if not _has_meaningful_input(raw_payload, shape_lock, site_boundary, tree_count, tree_points, tree_sizes):
        mesh = None
        vertices = None
        faces = None
        metadata = "No input provided."
        genes_payload = None
        error = "No generative input was provided to GRASSHOPPER_GENE_MESH.py."
    else:
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
            tree_sizes=tree_sizes,
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
