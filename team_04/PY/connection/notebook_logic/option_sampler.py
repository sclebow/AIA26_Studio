"""Option sampler — generate diverse, valid candidate placements (position +
rotation) inside the confirmed site, so optimization options are spread across the
site rather than stacked at the centre.

Wraps the existing agent.tools.view_optimizer.sample_valid_placements (grid +
rotation sampling with site-fit validation) — no sampling math is reimplemented.
The view optimizer already consumes these candidates; this module also exposes
them directly for diagnostics / non-NSGA fallback.
"""
from __future__ import annotations

from typing import Any

from . import site_state
from agent.tools.view_optimizer import sample_valid_placements, rank_placements_by_view


def _center_boundary(boundary: list[list[float]]) -> list[list[float]]:
    """Translate a footprint so its centroid is at the origin — the sampler grids
    placements relative to the footprint, so a pre-positioned/rotated ring (large
    axis-aligned bbox) samples poorly."""
    pts = [p for p in boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts:
        return boundary
    cx = sum(float(p[0]) for p in pts) / len(pts)
    cy = sum(float(p[1]) for p in pts) / len(pts)
    return [[float(p[0]) - cx, float(p[1]) - cy] + ([float(p[2])] if len(p) > 2 else []) for p in boundary]


def sample_candidates(
    boundary: list[list[float]],
    *,
    site_boundary: list[list[float]] | None = None,
    grid_step: float = 8.0,
    rotation_step_degrees: int = 30,
    site_setbacks: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Valid candidate placements (each has centroid_xy, rotation, boundary) inside
    the site, across a grid of positions × rotation angles. Falls back to the
    confirmed site when no site_boundary is given."""
    site = site_boundary or site_state.load_confirmed_boundary()
    if not site:
        return []
    centered = _center_boundary(boundary)
    return sample_valid_placements(
        centered,
        site,
        grid_step=grid_step,
        rotation_step_degrees=rotation_step_degrees,
        site_setbacks=site_setbacks,
    )


def ranked_candidates(
    boundary: list[list[float]],
    *,
    obstacles: list[list[list[float]]] | None = None,
    site_boundary: list[list[float]] | None = None,
    grid_step: float = 8.0,
    rotation_step_degrees: int = 30,
    top_n: int = 4,
) -> list[dict[str, Any]]:
    """Sample candidates then rank them by view quality — a fast, deterministic
    alternative to NSGA-II that still yields position/rotation-diverse options."""
    candidates = sample_candidates(
        boundary,
        site_boundary=site_boundary,
        grid_step=grid_step,
        rotation_step_degrees=rotation_step_degrees,
    )
    if not candidates:
        return []
    ranked = rank_placements_by_view(candidates, obstacles or [])
    return ranked[:top_n]
