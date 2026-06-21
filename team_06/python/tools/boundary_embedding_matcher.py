# ============================================================================
# boundary_embedding_matcher.py
#
# Turning-function-only boundary search.
#
# Pipeline:
# 1) Read outline and circulation.
# 2) Pick the bottom-left point of the circulation edge as the anchor.
# 3) Rotate the outline so the anchor is the first point.
# 4) Force clockwise traversal.
# 5) Sample the signed turning function into a 64-D vector.
# 6) Compare vectors with cosine similarity.
# ============================================================================

from __future__ import annotations
import json
from typing import Any, List, Dict
import numpy as np
from pathlib import Path
import math

# Turning-function embedding size.
TURNING_SAMPLES = 64


def _is_closed_polygon(coords: List[List[float]]) -> bool:
    return len(coords) > 1 and coords[0] == coords[-1]


def _open_polygon(coords: List[List[float]]) -> List[List[float]]:
    return coords[:-1] if _is_closed_polygon(coords) else coords[:]


def _points_close(point_a: List[float], point_b: List[float], tolerance: float = 1e-6) -> bool:
    return abs(point_a[0] - point_b[0]) <= tolerance and abs(point_a[1] - point_b[1]) <= tolerance


def _polygon_area(coords: List[List[float]]) -> float:
    open_coords = _open_polygon(coords)
    if len(open_coords) < 3:
        return 0.0
    area = 0.0
    for index in range(len(open_coords)):
        x1, y1 = open_coords[index]
        x2, y2 = open_coords[(index + 1) % len(open_coords)]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _force_clockwise(coords: List[List[float]]) -> List[List[float]]:
    open_coords = _open_polygon(coords)
    if len(open_coords) < 2:
        return coords[:]

    if _polygon_area(open_coords) > 0:
        rotated = [open_coords[0]] + list(reversed(open_coords[1:]))
    else:
        rotated = open_coords[:]

    if not _points_close(rotated[0], rotated[-1]):
        rotated.append(rotated[0])
    return rotated


def _project_point_to_segment(point: List[float], start: List[float], end: List[float]) -> tuple[List[float], float]:
    point_vec = np.array(point, dtype=float)
    start_vec = np.array(start, dtype=float)
    end_vec = np.array(end, dtype=float)
    segment_vec = end_vec - start_vec
    segment_length_sq = float(np.dot(segment_vec, segment_vec))

    if segment_length_sq == 0.0:
        projected = start_vec
    else:
        t = float(np.dot(point_vec - start_vec, segment_vec) / segment_length_sq)
        t = max(0.0, min(1.0, t))
        projected = start_vec + t * segment_vec

    distance = float(np.linalg.norm(point_vec - projected))
    return projected.tolist(), distance


def _polygon_perimeter(coords: List[List[float]]) -> float:
    coords_array = np.array(coords)
    shifted = np.roll(coords_array, -1, axis=0)
    distances = np.sqrt(np.sum((coords_array - shifted) ** 2, axis=1))
    return float(np.sum(distances))


def extract_circulation_anchor_point(layout: Dict[str, Any]) -> List[float] | None:
    circulation_items = layout.get("circulation", [])
    if not circulation_items:
        return None

    item = next((entry for entry in circulation_items if entry.get("geometry")), circulation_items[0])
    geometry = item.get("geometry", [])
    if not geometry:
        return None

    if len(geometry) >= 2:
        # Use the most bottom-left point of the circulation edge.
        return min([list(geometry[0]), list(geometry[1])], key=lambda point: (point[1], point[0]))

    return list(geometry[0])


def _align_outline_to_anchor(coords: List[List[float]], anchor_point: List[float] | None) -> Dict[str, Any]:
    open_coords = _open_polygon(coords)
    if not open_coords:
        return {
            "coordinates": coords[:],
            "start_vertex_index": 0,
            "anchor_point": anchor_point,
        }

    if anchor_point is None:
        return {
            "coordinates": open_coords + [open_coords[0]],
            "start_vertex_index": 0,
            "anchor_point": None,
        }

    best_index = 0
    best_projection = open_coords[0]
    best_distance = float("inf")
    vertex_count = len(open_coords)

    for index in range(vertex_count):
        segment_start = open_coords[index]
        segment_end = open_coords[(index + 1) % vertex_count]
        projected_point, distance = _project_point_to_segment(anchor_point, segment_start, segment_end)
        if distance < best_distance:
            best_distance = distance
            best_index = index
            best_projection = projected_point

    next_vertex = open_coords[(best_index + 1) % vertex_count]
    if _points_close(best_projection, next_vertex):
        rotated_open = open_coords[(best_index + 1) % vertex_count:] + open_coords[:best_index + 1]
    else:
        rotated_open = [best_projection] + open_coords[(best_index + 1) % vertex_count:] + open_coords[:best_index + 1]

    if not _points_close(rotated_open[0], rotated_open[-1]):
        rotated_open = rotated_open + [rotated_open[0]]

    return {
        "coordinates": rotated_open,
        "start_vertex_index": 0,
        "anchor_point": anchor_point,
    }


def _signed_turn_angle(prev_point: List[float], current_point: List[float], next_point: List[float]) -> float:
    incoming = np.array(prev_point, dtype=float) - np.array(current_point, dtype=float)
    outgoing = np.array(next_point, dtype=float) - np.array(current_point, dtype=float)
    cross = float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0])
    dot = float(np.dot(incoming, outgoing))
    return float(np.arctan2(cross, dot))


def _compute_turning_samples_from_coords(coords: List[List[float]], sample_count: int = TURNING_SAMPLES) -> np.ndarray:
    """Compute a 64-sample turning function for a clockwise polygon."""
    open_coords = _open_polygon(coords)
    if len(open_coords) < 3:
        return np.zeros(sample_count, dtype=float)

    perimeter = _polygon_perimeter(open_coords)
    if perimeter == 0:
        return np.zeros(sample_count, dtype=float)

    samples = []
    vertex_count = len(open_coords)
    for index in range(vertex_count):
        current_point = open_coords[index]
        next_point = open_coords[(index + 1) % vertex_count]
        previous_point = open_coords[(index - 1) % vertex_count]

        edge_length = float(np.linalg.norm(np.array(next_point, dtype=float) - np.array(current_point, dtype=float)))
        turn_angle = _signed_turn_angle(previous_point, current_point, next_point)
        samples.append([edge_length / perimeter, turn_angle / math.pi])

    samples_array = np.array(samples, dtype=float)
    normalized_edge_lengths = samples_array[:, 0]
    turn_angle_over_pi = samples_array[:, 1]
    turn_radians = turn_angle_over_pi * math.pi

    positions = np.concatenate(([0.0], np.cumsum(normalized_edge_lengths)))[:-1]
    cumulative_turn = np.cumsum(turn_radians)
    cumulative_turn_norm = cumulative_turn / (2.0 * math.pi)

    target_positions = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)
    pos_ext = np.append(positions, 1.0)
    turn_ext = np.append(cumulative_turn_norm, cumulative_turn_norm[0] if len(cumulative_turn_norm) else 0.0)

    return np.interp(target_positions, pos_ext, turn_ext)


def _vector_from_coords(coords: List[List[float]]) -> np.ndarray:
    turning = _compute_turning_samples_from_coords(coords, sample_count=TURNING_SAMPLES)
    norm = np.linalg.norm(turning)
    if norm == 0:
        return turning.astype(float)
    return (turning / norm).astype(float)


def _normalize_layout_outline(layout: Dict[str, Any]) -> List[List[float]]:
    coords = layout.get("outline", [])
    anchor = extract_circulation_anchor_point(layout)
    aligned = _align_outline_to_anchor(coords, anchor)["coordinates"]
    clockwise = _force_clockwise(aligned)
    return clockwise


def _resample_cyclic_signature(signature: List[List[float]], sample_count: int = TURNING_SAMPLES) -> np.ndarray:
    if not signature:
        return np.zeros((sample_count, 2), dtype=float)

    samples = np.array(signature, dtype=float)
    if len(samples) == 1:
        return np.repeat(samples, sample_count, axis=0)

    positions = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    positions_extended = np.append(positions, 1.0)
    samples_extended = np.vstack([samples, samples[0]])
    target_positions = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)

    return np.column_stack([
        np.interp(target_positions, positions_extended, samples_extended[:, 0]),
        np.interp(target_positions, positions_extended, samples_extended[:, 1]),
    ])


def _vector_from_graph(graph: Dict[str, Any], sample_count: int = TURNING_SAMPLES) -> np.ndarray:
    coords = graph.get("coordinates")
    if coords is None:
        coords = graph.get("outline", [])
    turning = _compute_turning_samples_from_coords(coords, sample_count=sample_count)
    norm = np.linalg.norm(turning)
    if norm == 0:
        return turning.astype(float)
    return (turning / norm).astype(float)


def match_boundaries(
    input_coords: List[List[float]] | None = None,
    input_graph: Dict[str, Any] | None = None,
    dataset_path: str | Path | None = None,
    tf_sampled_path: str | Path | None = None,
    top_k: int = 3,
    min_score: float = 0.5
) -> Dict[str, Any]:
    if input_graph is None:
        if input_coords is None:
            return {"error": "Either input_graph or input_coords must be provided", "matches": [], "count": 0}
        input_graph = {"coordinates": input_coords}

    if input_coords is None:
        input_coords = input_graph.get("coordinates", []) or input_graph.get("outline", [])

    input_layout_like = {"outline": input_coords, "circulation": input_graph.get("circulation", [])}
    input_coords_clockwise = _normalize_layout_outline(input_layout_like)
    input_vec = _vector_from_coords(input_coords_clockwise)

    # Load dataset
    if dataset_path is None:
        return {"error": "dataset_path must be provided", "matches": [], "count": 0}

    dataset_path = Path(dataset_path)
    if not dataset_path.is_absolute():
        # Support both repo-root relative paths (`team_06/...`) and
        # module-relative paths (`layout_inputs/...`).
        if str(dataset_path).startswith("team_06"):
            dataset_path = Path(__file__).parent.parent.parent.parent / dataset_path
        else:
            dataset_path = Path(__file__).parent.parent.parent / dataset_path

    if not dataset_path.exists():
        return {"error": f"Dataset not found at {dataset_path}", "matches": [], "count": 0}

    if dataset_path.is_dir():
        dataset = []
        for json_file in sorted(dataset_path.glob('*.json')):
            with open(json_file, 'r', encoding='utf-8-sig') as f:
                item = json.load(f)
            if isinstance(item, list):
                dataset.extend(item)
            else:
                dataset.append(item)
    else:
        with open(dataset_path, 'r', encoding='utf-8-sig') as f:
            dataset = json.load(f)

    results = []

    # Fast path: if precomputed sampled turning functions exist, use them.
    tf_default_dir = dataset_path.parent / 'pf_embeddings' if dataset_path.is_dir() else dataset_path.parent
    tf_file = Path(tf_sampled_path) if tf_sampled_path is not None else tf_default_dir / 'tf_sampled.npy'
    if not tf_file.is_absolute():
        if str(tf_file).startswith("team_06"):
            tf_file = Path(__file__).parent.parent.parent.parent / tf_file
        else:
            tf_file = dataset_path.parent / tf_file
    if tf_file.exists():
        try:
            sampled_array = np.load(str(tf_file))  # shape (N, dim)
            # L2-normalize rows for cosine similarity
            norms = np.linalg.norm(sampled_array, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            sampled_normed = sampled_array / norms

            # Ensure input vector has same dimension as sampled vectors
            if input_vec.size != sampled_normed.shape[1]:
                # If dims mismatch, resample/trim/pad: simplest is to resample input
                # by linear interpolation over its original samples to match target dim.
                target_dim = sampled_normed.shape[1]
                src = np.linspace(0.0, 1.0, num=input_vec.size, endpoint=False)
                dst = np.linspace(0.0, 1.0, num=target_dim, endpoint=False)
                input_vec = np.interp(dst, src, input_vec)
                vnorm = np.linalg.norm(input_vec)
                if vnorm != 0:
                    input_vec = input_vec / vnorm

            sims = float(np.nan) if input_vec.size == 0 else (sampled_normed @ input_vec)
            # top_k indices
            top_k = min(top_k, sampled_normed.shape[0])
            idxs = np.argsort(-sims)[:top_k]

            for idx in idxs:
                layout = dataset[idx]
                layout_id = layout.get('layoutId', layout.get('id', f'idx_{idx}'))
                results.append({
                    'layoutId': layout_id,
                    'score': round(float(sims[idx]), 3),
                    'name': layout.get('apartment', {}).get('name'),
                    'boundary_graph': {
                        'coordinates': _normalize_layout_outline(layout),
                        'vector_size': sampled_normed.shape[1],
                    }
                })
            return {'matches': results, 'query': 'turning_function_precomputed', 'count': len(results)}
        except Exception:
            # Fall back to on-the-fly computation below
            pass

    for layout in dataset:
        layout_id = layout.get('layoutId', 'unknown')
        coords = layout.get('outline', [])
        if not coords:
            continue

        candidate_coords = _normalize_layout_outline(layout)
        cand_vec = _vector_from_coords(candidate_coords)

        if input_vec.size == 0 or cand_vec.size == 0:
            sim = 0.0
        else:
            sim = float(np.dot(input_vec, cand_vec))

        if sim >= min_score:
            results.append({
                "layoutId": layout_id,
                "score": round(sim, 3),
                "name": layout.get('apartment', {}).get('name'),
                "boundary_graph": {
                    "coordinates": candidate_coords,
                    "vector_size": TURNING_SAMPLES,
                },
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    results = results[:top_k]

    return {"matches": results, "query": "turning_function", "count": len(results)}


# Simple command-line test helper
if __name__ == '__main__':
    import sys
    from pathlib import Path

    if len(sys.argv) < 3:
        print('Usage: python boundary_embedding_matcher.py <input_layout.json> <dataset.json>')
        sys.exit(1)

    input_path = Path(sys.argv[1])
    dataset_path = Path(sys.argv[2])

    with open(input_path, 'r', encoding='utf-8') as f:
        input_layout = json.load(f)

    input_coords = input_layout.get('outline', [])
    res = match_boundaries(input_coords=input_coords, dataset_path=dataset_path, top_k=5, min_score=0.0)
    print('Found', res['count'], 'matches')
    for m in res['matches']:
        print(m['layoutId'], m['score'])
