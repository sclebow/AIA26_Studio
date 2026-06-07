"""Render boundary-search benchmarks as query + top-3 candidate image grids."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Make project imports work when running this file directly.
SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = SCRIPT_DIR.parents[1]
PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from tools.boundary_embedding_matcher import match_boundaries

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


def format_area(room: dict[str, Any]) -> float:
    attrs = room.get("attributes", {})
    area = attrs.get("area")
    if area is None:
        geom = room.get("geometry", [])
        if len(geom) >= 4:
            points = np.array(geom)
            xs = points[:, 0]
            ys = points[:, 1]
            area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
        else:
            area = 0.0
    return round(float(area), 2)


def _load_json(json_path: Path) -> dict[str, Any]:
    with open(json_path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _resolve_path(path: Path, base: Path = PROJECT_ROOT) -> Path:
    if path.is_absolute():
        return path
    return path.expanduser().resolve()


def _load_dataset_index(dataset_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    dataset = _load_json(dataset_path)
    by_id = {item.get("layoutId", item.get("id", "")): item for item in dataset}
    return dataset, by_id


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


def draw_layout(ax, layout: dict[str, Any], title: str | None = None, subtitle: str | None = None) -> None:
    _set_axes_from_outline(ax, layout)

    rooms = layout.get("rooms", [])
    for room in rooms:
        geom = room.get("geometry", [])
        if not geom or len(geom) < 3:
            continue

        poly_points = np.array(geom)
        name = room.get("name", room.get("attributes", {}).get("program", "Unknown"))
        color = COLORS.get(name, COLORS.get(room.get("attributes", {}).get("program", ""), COLORS["Unknown"]))
        area = format_area(room)

        poly = patches.Polygon(
            poly_points,
            closed=True,
            linewidth=1,
            edgecolor="black",
            facecolor=color,
            alpha=0.8,
        )
        ax.add_patch(poly)

        min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
        min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
        label = f"{name}\n{area:.2f} m²"
        ax.text(
            min_x + (max_x - min_x) / 2,
            min_y + (max_y - min_y) / 2,
            label,
            color="black",
            fontsize=7,
            ha="center",
            va="center",
        )

    for facade in layout.get("facades", []):
        geom = facade.get("geometry", [])
        if len(geom) >= 2:
            fx = [geom[0][0], geom[1][0]]
            fy = [geom[0][1], geom[1][1]]
            ax.plot(fx, fy, color="blue", linewidth=4, zorder=5)

    for circ in layout.get("circulation", []):
        geom = circ.get("geometry", [])
        if len(geom) >= 2:
            cx = [geom[0][0], geom[1][0]]
            cy = [geom[0][1], geom[1][1]]
            ax.plot(cx, cy, color="green", linewidth=4, zorder=6)
            ax.text(
                np.mean(cx),
                np.mean(cy),
                "ENTRANCE",
                color="white",
                fontsize=6,
                ha="center",
                va="center",
                bbox=dict(facecolor="green", edgecolor="none", pad=0.3, boxstyle="round,pad=0.3"),
                zorder=7,
            )

    for door in layout.get("doors", []):
        geom = door.get("geometry", [])
        if len(geom) >= 1:
            dx, dy = geom[0][0], geom[0][1]
            ax.plot(dx, dy, marker="o", markersize=6, color="yellow", markeredgecolor="black", zorder=8)

    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    if subtitle:
        ax.text(
            0.5,
            0.98,
            subtitle,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=10,
            color="#333333",
        )


def benchmark_folder(
    query_dir: Path,
    dataset_path: Path,
    output_dir: Path,
    tf_sampled_path: Path | None = None,
    top_k: int = 3,
    min_score: float = 0.0,
) -> None:
    query_dir = _resolve_path(query_dir)
    dataset_path = _resolve_path(dataset_path)
    output_dir = _resolve_path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    query_files = sorted(query_dir.glob("*.json"))
    dataset, dataset_by_id = _load_dataset_index(dataset_path)

    print(f"Found {len(query_files)} query layouts in {query_dir}")
    for query_path in query_files:
        query_layout = _load_json(query_path)
        result = match_boundaries(
            input_coords=query_layout.get("outline", []),
            dataset_path=str(dataset_path),
            tf_sampled_path=str(tf_sampled_path) if tf_sampled_path is not None else None,
            top_k=top_k,
            min_score=min_score,
        )
        matches = result.get("matches", [])
        if not matches and result.get("error"):
            print(f"Warning: search failed for {query_path.name}: {result['error']}")

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
                match_id = match.get("layoutId", "unknown")
                score = float(match.get("score", 0.0))
                candidate_layout = dataset_by_id.get(match_id)
                if candidate_layout is None:
                    ax.axis("off")
                    ax.text(0.5, 0.5, f"Missing: {match_id}", ha="center", va="center")
                    continue

                draw_layout(
                    ax,
                    candidate_layout,
                    title=f"Candidate {idx}: {match_id}",
                    subtitle=f"score {score:.3f}",
                )
            else:
                ax.axis("off")
                ax.text(0.5, 0.5, "No candidate", ha="center", va="center")

        fig.suptitle(f"Boundary search test - {query_layout.get('layoutId', query_path.stem)}", fontsize=16, fontweight="bold")
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
        "--dataset",
        type=str,
        default=str(PROJECT_ROOT / "layout_inputs" / "sample_layouts.json"),
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(SCRIPT_DIR / "boundary_benchmark_images"),
    )
    parser.add_argument(
        "--tf_sampled",
        type=str,
        default=None,
        help="Optional precomputed tf_sampled.npy to use for matching.",
    )
    parser.add_argument("--top_k", type=int, default=3)
    parser.add_argument("--min_score", type=float, default=0.0)
    args = parser.parse_args()

    benchmark_folder(
        query_dir=Path(args.query_dir),
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output_dir),
        tf_sampled_path=Path(args.tf_sampled) if args.tf_sampled else None,
        top_k=args.top_k,
        min_score=args.min_score,
    )
