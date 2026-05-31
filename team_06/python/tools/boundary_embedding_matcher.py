# ============================================================================
# boundary_embedding_matcher.py
#
# Create dense, fixed-size embeddings directly from floorplan boundary
# geometry and use cosine similarity for retrieval.
#
# Design goals:
# - Keep the tool fully self-contained and deterministic.
# - Avoid dependency on external geometry engines and heavy ML frameworks.
# - Produce vectors that can be indexed later in FAISS (or similar ANN indexes).
#
# High-level pipeline:
# 1) Read boundary coordinates (`outline`) and optional circulation polyline.
# 2) Extract an anchor point from `circulation` (prefer "Front Door" semantics).
# 3) Re-order the polygon so the boundary starts at the anchor projection.
# 4) Build an ordered cycle graph with normalized edge lengths and signed turning angles.
# 5) Resample graph signature and turning function to fixed lengths.
# 6) Concatenate features and L2-normalize to obtain one embedding vector.
# 7) Compare vectors with cosine similarity for retrieval.
#
# Lightweight: numpy-only implementation intended for quick indexing/prototyping.
# ============================================================================

from __future__ import annotations
import json
from typing import Any, List, Dict
import numpy as np
from pathlib import Path
import math

# Embedding sizes (should match boundary_analyzer defaults)
GRAPH_SIGNATURE_SAMPLES = 64
TURNING_SAMPLES = 64


def _is_closed_polygon(coords: List[List[float]]) -> bool:
    # Return True when the polygon explicitly repeats the first point as last point.
    return len(coords) > 1 and coords[0] == coords[-1]


def _open_polygon(coords: List[List[float]]) -> List[List[float]]:
    # Return polygon without duplicated closing vertex for easier cyclic processing.
    return coords[:-1] if _is_closed_polygon(coords) else coords[:]


def _points_close(point_a: List[float], point_b: List[float], tolerance: float = 1e-6) -> bool:
    # Numerical safety check to compare 2D points with tolerance.
    return abs(point_a[0] - point_b[0]) <= tolerance and abs(point_a[1] - point_b[1]) <= tolerance


def _normalize_coords(coords: List[List[float]]) -> List[tuple[float, float]]:
    # Canonicalize a polygon for exact outline comparison.
    # The result ignores repeated closing vertices and rounds coordinates to
    # avoid tiny floating-point differences from breaking exact matches.
    open_coords = _open_polygon(coords)
    return [(round(point[0], 6), round(point[1], 6)) for point in open_coords]


def _polygon_variants(coords: List[List[float]]) -> List[List[tuple[float, float]]]:
    # Generate cyclic and reversed variants so exact-outline checks are robust
    # to vertex start position and winding direction.
    open_coords = _normalize_coords(coords)
    if not open_coords:
        return [[]]

    variants: List[List[tuple[float, float]]] = []
    for source in (open_coords, list(reversed(open_coords))):
        for shift in range(len(source)):
            variants.append(source[shift:] + source[:shift])
    return variants


def _exact_outline_match(query_coords: List[List[float]], candidate_coords: List[List[float]]) -> bool:
    # Return True when two outlines are the same up to cyclic rotation and
    # winding direction.
    query_variants = _polygon_variants(query_coords)
    candidate_norm = _normalize_coords(candidate_coords)
    return candidate_norm in query_variants


def _project_point_to_segment(point: List[float], start: List[float], end: List[float]) -> tuple[List[float], float]:
    # Project a point onto a segment and return (projected_point, euclidean_distance).
    # Used to find where the circulation anchor falls on the polygon boundary.
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
    # Compute perimeter of an open polygon vertex sequence.
    # Notes:
    # - `coords` is expected to be open (no duplicated last vertex).
    # - We still use cyclic roll so last vertex connects back to first.
    coords_array = np.array(coords)
    shifted = np.roll(coords_array, -1, axis=0)
    distances = np.sqrt(np.sum((coords_array - shifted) ** 2, axis=1))
    return float(np.sum(distances))


def extract_circulation_anchor_point(layout: Dict[str, Any]) -> List[float] | None:
    # Extract the geometric anchor that defines boundary start orientation.
    # Strategy:
    # - Use `layout['circulation']` directly as the door-edge indicator.
    # - Take the first circulation item with valid geometry.
    # - Use the midpoint of the first segment (`geometry[0]` to `geometry[1]`) to
    #   reduce sensitivity to arbitrary polyline direction/order in exports.
    # - If only one point exists, use that point directly.
    # Returns: [x, y] anchor point, or None when circulation is unavailable.
    circulation_items = layout.get("circulation", [])
    if not circulation_items:
        return None

    item = next((entry for entry in circulation_items if entry.get("geometry")), circulation_items[0])
    geometry = item.get("geometry", [])
    if not geometry:
        return None

    if len(geometry) >= 2:
        x0, y0 = geometry[0]
        x1, y1 = geometry[1]
        return [(x0 + x1) / 2.0, (y0 + y1) / 2.0]

    return list(geometry[0])


def _align_outline_to_anchor(coords: List[List[float]], anchor_point: List[float] | None) -> Dict[str, Any]:
        # Cyclically rotate the boundary so traversal starts at the anchor location.
        # This removes cyclic-shift ambiguity: the same polygon can be encoded with
        # different start vertices. By anchoring to circulation, shape descriptors
        # and embeddings become consistent across layouts.
        # Behavior:
        # - If anchor is None: return polygon closed from its current first vertex.
        # - If anchor exists: project it to closest polygon segment and insert that
        #   projected point as start when needed.
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
    # Return signed turn angle (radians) at `current_point`.
    # Positive/negative sign is determined by 2D cross product orientation.
    incoming = np.array(prev_point, dtype=float) - np.array(current_point, dtype=float)
    outgoing = np.array(next_point, dtype=float) - np.array(current_point, dtype=float)
    cross = float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0])
    dot = float(np.dot(incoming, outgoing))
    return float(np.arctan2(cross, dot))


def build_boundary_graph(coords: List[List[float]], anchor_point: List[float] | None = None) -> Dict[str, Any]:
    # Encode polygon boundary into an ordered cycle graph signature.
    # Output fields:
    # - nodes: per-vertex coordinates and turn angles
    # - edges: per-edge lengths and normalized lengths
    # - signature: compact ordered list [[edge_len_norm, turn_over_pi], ...]
    # The signature is the core signal used later to build fixed-size embeddings.
    aligned = _align_outline_to_anchor(coords, anchor_point)
    graph_coords = aligned["coordinates"]
    open_coords = _open_polygon(graph_coords)
    perimeter = _polygon_perimeter(open_coords)

    if not open_coords:
        return {
            "anchor_point": anchor_point,
            "start_vertex_index": 0,
            "perimeter": 0.0,
            "vertex_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
            "signature": [],
        }

    vertex_count = len(open_coords)
    nodes = []
    edges = []
    signature = []

    for index in range(vertex_count):
        current_point = open_coords[index]
        next_point = open_coords[(index + 1) % vertex_count]
        previous_point = open_coords[(index - 1) % vertex_count]

        edge_length = float(np.linalg.norm(np.array(next_point, dtype=float) - np.array(current_point, dtype=float)))
        turn_angle = _signed_turn_angle(previous_point, current_point, next_point)

        nodes.append({
            "index": index,
            "point": [round(current_point[0], 6), round(current_point[1], 6)],
            "turn_angle_radians": round(turn_angle, 6),
            "turn_angle_normalized": round(turn_angle / math.pi, 6),
        })
        edges.append({
            "index": index,
            "from": index,
            "to": (index + 1) % vertex_count,
            "length": round(edge_length, 6),
            "normalized_length": round(edge_length / perimeter, 6) if perimeter else 0.0,
        })
        signature.append([
            edge_length / perimeter if perimeter else 0.0,
            turn_angle / math.pi,
        ])

    return {
        "anchor_point": anchor_point,
        "start_vertex_index": aligned["start_vertex_index"],
        "perimeter": round(perimeter, 6),
        "vertex_count": vertex_count,
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "signature": signature,
    }


def _resample_cyclic_signature(signature: List[List[float]], sample_count: int = GRAPH_SIGNATURE_SAMPLES) -> np.ndarray:
    # Resample variable-length cyclic signature to fixed shape (sample_count, 2).
    # Why this matters:
    # - Different floorplans have different vertex counts.
    # - Retrieval/indexing requires fixed-size vectors.
    # - Interpolation over normalized cycle position keeps descriptors comparable.
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


def _compute_turning_samples_from_graph(graph: Dict[str, Any], sample_count: int = TURNING_SAMPLES) -> np.ndarray:
    # Compute uniformly sampled turning-function from graph signature.
    # Steps:
    # 1) Read normalized edge lengths and turn angles from `signature`.
    # 2) Convert turning to cumulative turning along normalized perimeter.
    # 3) Normalize by 2*pi and interpolate to `sample_count` points.
    # Result is a compact 1D curve describing global boundary turning behavior.
    sig = graph.get("signature", [])
    if not sig:
        return np.zeros(sample_count, dtype=float)

    samples = np.array(sig, dtype=float)
    normalized_edge_lengths = samples[:, 0]
    turn_angle_over_pi = samples[:, 1]
    turn_radians = turn_angle_over_pi * math.pi

    positions = np.concatenate(([0.0], np.cumsum(normalized_edge_lengths)))[:-1]
    cumulative_turn = np.cumsum(turn_radians)
    cumulative_turn_norm = cumulative_turn / (2.0 * math.pi)

    target_positions = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)
    pos_ext = np.append(positions, 1.0)
    turn_ext = np.append(cumulative_turn_norm, cumulative_turn_norm[0] if len(cumulative_turn_norm) else 0.0)

    return np.interp(target_positions, pos_ext, turn_ext)


def _vector_from_graph(graph: Dict[str, Any], sig_samples: int = GRAPH_SIGNATURE_SAMPLES, turning_samples: int = TURNING_SAMPLES) -> np.ndarray:
    # Produce final embedding vector from boundary graph.
    # Feature layout:
    # - Signature branch: (sig_samples, 2) -> flattened size 2*sig_samples
    # - Turning branch: size turning_samples
    # - Final vector size: 2*sig_samples + turning_samples
    # The vector is L2-normalized so cosine similarity equals dot product.
    sig_resampled = _resample_cyclic_signature(graph.get("signature", []), sample_count=sig_samples)
    # sig_resampled: (sig_samples, 2)
    sig_flat = sig_resampled.flatten()

    turning = _compute_turning_samples_from_graph(graph, sample_count=turning_samples)

    v = np.concatenate([sig_flat, turning])
    norm = np.linalg.norm(v)
    if norm == 0:
        return v.astype(float)
    return (v / norm).astype(float)


def match_boundaries(
    input_coords: List[List[float]] | None = None,
    input_graph: Dict[str, Any] | None = None,
    dataset_path: str | Path | None = None,
    top_k: int = 3,
    min_score: float = 0.5
) -> Dict[str, Any]:
    # Retrieve similar layouts using cosine similarity in boundary-embedding space.
    # Query modes:
    # - `input_graph`: use a precomputed graph directly.
    # - `input_coords`: build the graph from raw coordinates.
    # Dataset expectations:
    # - JSON array where each item has at least `outline`.
    # - `circulation` is optional but recommended for anchor consistency.
    # Returns a dict with matches, query label, count, and optional error.
    if input_graph is None:
        if input_coords is None:
            return {"error": "Either input_graph or input_coords must be provided", "matches": [], "count": 0}
        # No anchor point info available here; build_graph will handle None
        input_graph = build_boundary_graph(input_coords, None)

    input_vec = _vector_from_graph(input_graph)
    input_coords_norm = _normalize_coords(input_coords or input_graph.get("coordinates", [])) if input_coords or input_graph.get("coordinates") else None

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

    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        dataset = json.load(f)

    results = []

    for layout in dataset:
        layout_id = layout.get('layoutId', 'unknown')
        coords = layout.get('outline', [])
        if not coords:
            continue

        # Candidate embeddings are anchor-aware when circulation is available.
        anchor = extract_circulation_anchor_point(layout)
        cand_graph = build_boundary_graph(coords, anchor)
        cand_vec = _vector_from_graph(cand_graph)

        # cosine similarity between normalized vectors is dot product
        if input_vec.size == 0 or cand_vec.size == 0:
            sim = 0.0
        else:
            sim = float(np.dot(input_vec, cand_vec))

        # If the outlines are identical up to rotation/winding, force the score
        # near the top so exact shape matches cannot be buried by anchor noise.
        if input_coords_norm is not None and _exact_outline_match(input_coords_norm, coords):
            sim = max(sim, 0.999)

        if sim >= min_score:
            results.append({
                "layoutId": layout_id,
                "score": round(sim, 3),
                "name": layout.get('apartment', {}).get('name'),
                "boundary_graph": cand_graph
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    results = results[:top_k]

    return {"matches": results, "query": "boundary_embedding", "count": len(results)}


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
