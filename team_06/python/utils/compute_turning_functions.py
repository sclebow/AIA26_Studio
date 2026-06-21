"""
Compute piecewise turning functions and sampled turning-function vectors
for layouts in sample_layouts.json, following Graph2Plan's strategy.
Outputs:
 - turning_piecewise.pkl : list of dicts {'x': [...], 'y': [...], 'layoutId': id}
 - tf_sampled.npy        : array (n_layouts, sample_count)
 - D.npy                 : distance matrix (n_layouts, n_layouts)
 - topk.npy              : indices of nearest neighbors (n_layouts, top_k)

Usage:
 python compute_turning_functions.py --dataset team_06/layout_inputs/sample_layouts.json --sample_count 64 --top_k 100

"""
from __future__ import annotations
import json
from pathlib import Path
import argparse
import numpy as np
import pickle
import math


def _open_polygon(coords):
    if not coords:
        return []
    if coords[0] == coords[-1]:
        return coords[:-1]
    return coords[:]


def _polygon_perimeter(coords):
    coords_array = np.array(coords, dtype=float)
    if len(coords_array) < 2:
        return 0.0
    shifted = np.roll(coords_array, -1, axis=0)
    distances = np.sqrt(np.sum((coords_array - shifted) ** 2, axis=1))
    return float(np.sum(distances))


def _signed_turn_angle(prev_point, current_point, next_point):
    incoming = np.array(prev_point, dtype=float) - np.array(current_point, dtype=float)
    outgoing = np.array(next_point, dtype=float) - np.array(current_point, dtype=float)
    cross = float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0])
    dot = float(np.dot(incoming, outgoing))
    return float(math.atan2(cross, dot))


def piecewise_turning_function(coords):
    open_coords = _open_polygon(coords)
    n = len(open_coords)
    if n < 3:
        return {"x": [0.0], "y": [0.0]}

    perimeter = _polygon_perimeter(open_coords)
    if perimeter == 0:
        return {"x": [0.0], "y": [0.0]}

    edge_norms = []
    turn_radians = []
    for i in range(n):
        curr = open_coords[i]
        nxt = open_coords[(i + 1) % n]
        prev = open_coords[(i - 1) % n]
        edge_len = float(np.linalg.norm(np.array(nxt, dtype=float) - np.array(curr, dtype=float)))
        edge_norms.append(edge_len / perimeter)
        turn = _signed_turn_angle(prev, curr, nxt)
        turn_radians.append(turn)

    positions = np.concatenate(([0.0], np.cumsum(edge_norms)))[:-1]
    cumulative_turn = np.cumsum(turn_radians)
    return {"x": positions.tolist(), "y": cumulative_turn.tolist()}


def sample_turning_function(piece, sample_count=64):
    # piece: {'x': positions (0..1), 'y': cumulative_turn_radians}
    x = np.array(piece.get("x", []), dtype=float)
    y = np.array(piece.get("y", []), dtype=float)
    if x.size == 0:
        return np.zeros(sample_count, dtype=float)
    # extend to 1.0 to handle wrap
    x_ext = np.append(x, 1.0)
    # wrap cumulative turn: append first value + total_turn to close cycle
    total_turn = y[-1] if y.size else 0.0
    y_ext = np.append(y, y[0] + total_turn if y.size else 0.0)
    target = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)
    sampled = np.interp(target, x_ext, y_ext)
    # normalize by 2*pi (optional) and return
    return (sampled / (2.0 * math.pi)).astype(float)


def _load_dataset(dataset_path: Path) -> list:
    """Load layouts from a single JSON file or a directory of JSON files."""
    if dataset_path.is_dir():
        data = []
        for json_file in sorted(dataset_path.glob('*.json')):
            with open(json_file, 'r', encoding='utf-8-sig') as f:
                item = json.load(f)
            if isinstance(item, list):
                data.extend(item)
            else:
                data.append(item)
        return data
    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def compute(dataset_path: Path, sample_count: int = 64, top_k: int = 100, out_dir: Path | None = None):
    data = _load_dataset(dataset_path)

    pieces = []
    sampled_list = []
    ids = []
    for item in data:
        coords = item.get('outline', [])
        pid = item.get('layoutId', item.get('id', None)) or item.get('name', 'unknown')
        piece = piecewise_turning_function(coords)
        pieces.append({"layoutId": pid, "x": piece['x'], "y": piece['y']})
        sampled = sample_turning_function(piece, sample_count=sample_count)
        sampled_list.append(sampled)
        ids.append(pid)

    sampled_array = np.stack(sampled_list, axis=0)

    # distance matrix (L2)
    diffs = sampled_array[:, None, :] - sampled_array[None, :, :]
    D = np.sqrt(np.sum(diffs * diffs, axis=2))

    # top_k indices (excluding self)
    top_k = min(top_k, sampled_array.shape[0])
    idxs = np.argsort(D, axis=1)[:, :top_k]

    if out_dir is None:
        out_dir = dataset_path.parent / 'pf_embeddings' if dataset_path.is_dir() else dataset_path.parent
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / 'turning_piecewise.pkl', 'wb') as f:
        pickle.dump(pieces, f)
    np.save(out_dir / 'tf_sampled.npy', sampled_array)
    np.save(out_dir / 'D.npy', D)
    np.save(out_dir / 'topk.npy', idxs)

    print('Saved', sampled_array.shape, 'sampled TFs to', out_dir)
    return {
        'n': sampled_array.shape[0],
        'sample_count': sample_count,
        'tf_path': str(out_dir / 'tf_sampled.npy'),
        'D_path': str(out_dir / 'D.npy'),
        'topk_path': str(out_dir / 'topk.npy'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=str, default='team_06/layout_inputs/Planfinder_Dataset/pf_jsons')
    parser.add_argument('--sample_count', type=int, default=64)
    parser.add_argument('--top_k', type=int, default=100)
    parser.add_argument('--out_dir', type=str, default=None)
    args = parser.parse_args()
    res = compute(Path(args.dataset), sample_count=args.sample_count, top_k=args.top_k, out_dir=Path(args.out_dir) if args.out_dir else None)
    print(res)
