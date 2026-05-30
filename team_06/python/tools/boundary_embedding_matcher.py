"""
boundary_embedding_matcher.py

Create dense, fixed-size embeddings from the boundary-graph + turning-function
produced by `boundary_analyzer.build_boundary_graph` and provide a simple
cosine-similarity matcher API similar to `embedding_matcher.match_layouts`.

This tool is lightweight (numpy-only) and intended for quick indexing/prototyping
before moving to FAISS or a learned fusion model.
"""

from __future__ import annotations
import json
from typing import Any, List, Dict
import numpy as np
from pathlib import Path

# Reuse helpers from boundary_analyzer
from tools.boundary_analyzer import (
    build_boundary_graph,
    _resample_cyclic_signature,
    _compute_turning_samples_from_graph,
    extract_circulation_anchor_point,
)


# Embedding sizes (should match boundary_analyzer defaults)
GRAPH_SIGNATURE_SAMPLES = 64
TURNING_SAMPLES = 64


def _vector_from_graph(graph: Dict[str, Any], sig_samples: int = GRAPH_SIGNATURE_SAMPLES, turning_samples: int = TURNING_SAMPLES) -> np.ndarray:
    """Produce a fixed-size 1D numpy vector from a boundary graph.

    - Resample the signature (edge_length, turn/pi) to `sig_samples` and flatten.
    - Resample the turning-function to `turning_samples`.
    - Concatenate and L2-normalize the result.
    """
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
    """Match an input boundary against a dataset using cosine similarity on
    boundary embeddings (signature + turning-function).

    Args:
        input_coords: raw polygon coordinates (if provided, used to build graph)
        input_graph: precomputed boundary_graph (preferred)
        dataset_path: path to dataset JSON (array of layouts with 'outline')
        top_k: number of top matches to return
        min_score: minimum cosine similarity to include

    Returns:
        {"matches": [...], "query": ..., "count": N}
    """
    if input_graph is None:
        if input_coords is None:
            return {"error": "Either input_graph or input_coords must be provided", "matches": [], "count": 0}
        # No anchor point info available here; build_graph will handle None
        input_graph = build_boundary_graph(input_coords, None)

    input_vec = _vector_from_graph(input_graph)

    # Load dataset
    if dataset_path is None:
        return {"error": "dataset_path must be provided", "matches": [], "count": 0}

    dataset_path = Path(dataset_path)
    if not dataset_path.is_absolute():
        dataset_path = Path(__file__).parent.parent.parent / dataset_path

    if not dataset_path.exists():
        return {"error": f"Dataset not found at {dataset_path}", "matches": [], "count": 0}

    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    results = []

    for layout in dataset:
        layout_id = layout.get('layoutId', 'unknown')
        coords = layout.get('outline', [])
        if not coords:
            continue

        anchor = extract_circulation_anchor_point(layout)
        cand_graph = build_boundary_graph(coords, anchor)
        cand_vec = _vector_from_graph(cand_graph)

        # cosine similarity between normalized vectors is dot product
        if input_vec.size == 0 or cand_vec.size == 0:
            sim = 0.0
        else:
            sim = float(np.dot(input_vec, cand_vec))

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
