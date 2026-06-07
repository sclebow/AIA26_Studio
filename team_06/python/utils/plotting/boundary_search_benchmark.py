"""Render boundary-search benchmarks as query + top-3 candidate image grids.

Two-stage pipeline (mirrors search_boundary_node.py + boundary_analyzer.py):
  Stage 1 — fast cosine screen via turning-function embeddings (match_boundaries)
  Stage 2 — geometric re-ranking: blended IoU + area + topology score
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = SCRIPT_DIR.parents[1]
PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from tools.boundary_embedding_matcher import match_boundaries
from tools.boundary_analyzer import (
    compute_boundary_stats,
    calculate_area_score,
    calculate_iou_with_rotation,
    calculate_topology_score,
    calculate_composite_score,
)

# Scoring weights — must match search_boundary_node.py
COSINE_WEIGHT = 0.4
GEO_WEIGHT = 0.6
SCREEN_MULTIPLIER = 5
MAX_SCREEN_CANDIDATES = 20

COLORS = {
    "Living": "#FF9999",
    "Bed": "#99CCFF",
    "Kitchen": "#FFFF99",
    "Bath": "#E0E0E0",
    "Dining": "#FFCC99",
    "Extra": "#CCFFCC",
    "Balcony": "#99FF99",
    "Foyer": "#CC99FF",
    "Storage": "#C0C0C0",
    "Unknown": "#FFFFFF",
}


def _area(room: dict[str, Any]) -> float:
    attrs = room.get("attributes", {})
    area = attrs.get("area")
    if area is None:
        geom = room.get("geometry", [])
        if len(geom) >= 3:
            pts = np.array(geom)
            xs, ys = pts[:, 0], pts[:, 1]
            area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
        else:
            area = 0.0
    return round(float(area), 2)


def _load_json(json_path: Path) -> dict[str, Any]:
    with open(json_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _build_dataset_index(
    sample_layouts_path: Path | None,
    pf_jsons_path: Path | None,
) -> dict[str, dict[str, Any]]:
    """Build a combined {layoutId: layout} lookup from both dataset sources."""
    index: dict[str, dict[str, Any]] = {}

    if sample_layouts_path and sample_layouts_path.exists():
        for item in _load_json(sample_layouts_path):
            lid = item.get("layoutId", item.get("id", ""))
            if lid:
                index[lid] = item

    if pf_jsons_path and pf_jsons_path.exists():
        for json_file in pf_jsons_path.glob("*.json"):
            try:
                item = _load_json(json_file)
                lid = item.get("layoutId", json_file.stem)
                if lid:
                    index[lid] = item
            except Exception:
                continue

    return index


def _set_axes_from_outline(ax, layout: dict[str, Any]) -> None:
    outline = layout.get("outline", [])
    if outline:
        xs = [pt[0] for pt in outline]
        ys = [pt[1] for pt in outline]
        margin = 0.5
        ax.set_xlim(min(xs) - margin, max(xs) + margin)
        ax.set_ylim(min(ys) - margin, max(ys) + margin)
    else:
        ax.set_xlim(0, 12.8)
        ax.set_ylim(0, 12.8)
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.axis("off")


def draw_layout(
    ax,
    layout: dict[str, Any],
    title: str | None = None,
    subtitle: str | None = None,
) -> None:
    _set_axes_from_outline(ax, layout)

    for room in layout.get("rooms", []):
        geom = room.get("geometry", [])
        if not geom or len(geom) < 3:
            continue
        poly_points = np.array(geom)
        name = room.get("name", room.get("attributes", {}).get("program", "Unknown"))
        color = COLORS.get(name, COLORS.get(room.get("attributes", {}).get("program", ""), COLORS["Unknown"]))
        area = _area(room)
        ax.add_patch(patches.Polygon(
            poly_points, closed=True, linewidth=1,
            edgecolor="black", facecolor=color, alpha=0.8,
        ))
        min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
        min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
        ax.text(
            min_x + (max_x - min_x) / 2,
            min_y + (max_y - min_y) / 2,
            f"{name}\n{area:.2f} m²",
            color="black", fontsize=7, ha="center", va="center",
        )

    for facade in layout.get("facades", []):
        geom = facade.get("geometry", [])
        if len(geom) >= 2:
            ax.plot([geom[0][0], geom[1][0]], [geom[0][1], geom[1][1]],
                    color="blue", linewidth=4, zorder=5)

    for circ in layout.get("circulation", []):
        geom = circ.get("geometry", [])
        if len(geom) >= 2:
            cx = [geom[0][0], geom[1][0]]
            cy = [geom[0][1], geom[1][1]]
            ax.plot(cx, cy, color="green", linewidth=4, zorder=6)
            ax.text(
                np.mean(cx), np.mean(cy), "ENTRANCE",
                color="white", fontsize=6, ha="center", va="center",
                bbox=dict(facecolor="green", edgecolor="none", pad=0.3, boxstyle="round,pad=0.3"),
                zorder=7,
            )

    for door in layout.get("doors", []):
        geom = door.get("geometry", [])
        if len(geom) >= 1:
            ax.plot(geom[0][0], geom[0][1],
                    marker="o", markersize=6, markerfacecolor="yellow",
                    markeredgecolor="black", markeredgewidth=1.5, zorder=8)

    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    if subtitle:
        ax.text(0.5, 0.98, subtitle, transform=ax.transAxes,
                ha="center", va="top", fontsize=9, color="#333333")


def _cosine_screen(
    input_layout: dict[str, Any],
    sample_layouts_path: Path | None,
    pf_jsons_path: Path | None,
    screen_k: int,
) -> list[dict]:
    """Stage 1: collect cosine candidates from all available dataset sources."""
    pool: list[dict] = []

    if sample_layouts_path and sample_layouts_path.exists():
        res = match_boundaries(
            input_graph=input_layout,
            dataset_path=str(sample_layouts_path),
            top_k=screen_k,
            min_score=0.0,
        )
        pool.extend(res.get("matches", []))

    if pf_jsons_path and pf_jsons_path.exists():
        res = match_boundaries(
            input_graph=input_layout,
            dataset_path=str(pf_jsons_path),
            top_k=screen_k,
            min_score=0.0,
        )
        pool.extend(res.get("matches", []))

    # Deduplicate by layoutId, keep higher cosine score
    seen: dict[str, dict] = {}
    for m in pool:
        lid = m["layoutId"]
        if lid not in seen or m["score"] > seen[lid]["score"]:
            seen[lid] = m

    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:screen_k]


def _geo_rerank(
    cosine_pool: list[dict],
    input_outline: list[list[float]],
) -> list[dict]:
    """Stage 2: blend cosine score with IoU + area + topology."""
    input_stats = compute_boundary_stats(input_outline)
    scored = []
    for match in cosine_pool:
        coords = match["boundary_graph"]["coordinates"]
        cosine_score = match["score"]

        candidate_stats = compute_boundary_stats(coords)
        area_score = calculate_area_score(input_stats["area"], candidate_stats["area"])
        iou_score = calculate_iou_with_rotation(input_outline, coords)
        topo_score = calculate_topology_score(input_stats, candidate_stats)
        geo_score = calculate_composite_score(area_score, iou_score, topo_score)

        final_score = COSINE_WEIGHT * cosine_score + GEO_WEIGHT * geo_score
        scored.append({
            "layoutId": match["layoutId"],
            "score": round(float(final_score), 3),
            "cosine_score": round(float(cosine_score), 3),
            "geo_score": round(float(geo_score), 3),
            "iou_score": round(float(iou_score), 3),
            "area_score": round(float(area_score), 3),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def benchmark_folder(
    query_dir: Path,
    output_dir: Path,
    sample_layouts_path: Path | None = None,
    pf_jsons_path: Path | None = None,
    top_k: int = 3,
    min_score: float = 0.0,
) -> None:
    query_dir = query_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    query_files = sorted(query_dir.glob("*.json"))
    dataset_index = _build_dataset_index(sample_layouts_path, pf_jsons_path)
    screen_k = min(top_k * SCREEN_MULTIPLIER, MAX_SCREEN_CANDIDATES)

    print(f"Dataset index: {len(dataset_index)} layouts")
    print(f"Found {len(query_files)} query layouts in {query_dir}")

    for query_path in query_files:
        query_layout = _load_json(query_path)
        outline = query_layout.get("outline", [])
        input_layout = {
            "outline": outline,
            "circulation": query_layout.get("circulation", []),
        }

        # Stage 1 — cosine screen
        cosine_pool = _cosine_screen(input_layout, sample_layouts_path, pf_jsons_path, screen_k)
        if not cosine_pool:
            print(f"Warning: no cosine candidates for {query_path.name}")

        # Stage 2 — geometric re-rank
        if cosine_pool and outline:
            matches = _geo_rerank(cosine_pool, outline)
            matches = [m for m in matches if m["score"] >= min_score][:top_k]
        else:
            matches = []

        fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=120)
        flat_axes = axes.flatten()

        draw_layout(
            flat_axes[0],
            query_layout,
            title=f"Query: {query_layout.get('layoutId', query_path.stem)}",
            subtitle=query_layout.get("apartment", {}).get("name", ""),
        )

        for idx in range(1, 4):
            ax = flat_axes[idx]
            if idx - 1 < len(matches):
                match = matches[idx - 1]
                match_id = match["layoutId"]
                candidate_layout = dataset_index.get(match_id)
                if candidate_layout is None:
                    ax.axis("off")
                    ax.text(0.5, 0.5, f"Missing: {match_id}", ha="center", va="center")
                    continue
                subtitle = (
                    f"score {match['score']:.3f}"
                    f"  |  cos {match['cosine_score']:.3f}"
                    f"  |  geo {match['geo_score']:.3f}"
                    f"  |  iou {match['iou_score']:.3f}"
                )
                draw_layout(ax, candidate_layout,
                            title=f"Candidate {idx}: {match_id}",
                            subtitle=subtitle)
            else:
                ax.axis("off")
                ax.text(0.5, 0.5, "No candidate", ha="center", va="center")

        fig.suptitle(
            f"Boundary search  —  {query_layout.get('layoutId', query_path.stem)}",
            fontsize=16, fontweight="bold",
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        out_path = output_dir / f"{query_path.stem}_benchmark.png"
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render boundary search benchmarks for query layouts.")
    parser.add_argument(
        "--query_dir",
        type=str,
        default=str(PROJECT_ROOT / "layout_inputs" / "to_be_tested"),
    )
    parser.add_argument(
        "--sample_layouts",
        type=str,
        default=str(PROJECT_ROOT / "layout_inputs" / "sample_layouts.json"),
        help="Path to sample_layouts.json (pass empty string to skip)",
    )
    parser.add_argument(
        "--pf_jsons",
        type=str,
        default=str(PROJECT_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons"),
        help="Path to pf_jsons directory",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(SCRIPT_DIR / "boundary_benchmark_images"),
    )
    parser.add_argument("--top_k", type=int, default=3)
    parser.add_argument("--min_score", type=float, default=0.0)
    args = parser.parse_args()

    benchmark_folder(
        query_dir=Path(args.query_dir),
        output_dir=Path(args.output_dir),
        sample_layouts_path=Path(args.sample_layouts) if args.sample_layouts else None,
        pf_jsons_path=Path(args.pf_jsons) if args.pf_jsons else None,
        top_k=args.top_k,
        min_score=args.min_score,
    )
