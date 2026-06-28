"""Optimization weights — the multi-objective blend, frontend-adjustable.

The default weights match the project spec. They are kept in one place so the
combiner, the /optimization/weights API, and any frontend slider all read/write
the same source of truth. Weights are normalized before use so they always sum
to 1.0 even after a partial edit.
"""
from __future__ import annotations

from typing import Any

# Canonical objective ids. Each maps to a scoring module in this package.
OBJECTIVES: tuple[str, ...] = (
    "solar", "view", "open_space", "road_access", "density", "setback",
    "walkability", "wind", "privacy", "noise", "structural",
    "construction_efficiency", "context_response", "emergency_access",
    "mixed_use", "public_private",
)

# Spec default weights (the 12 weighted criteria). Objectives not listed here
# default to 0.0 weight — they still produce scores/metrics for the report and can
# be promoted to a strategy, just don't drive the *balanced* total unless weighted.
DEFAULT_WEIGHTS: dict[str, float] = {
    "solar": 0.20,
    "view": 0.15,
    "open_space": 0.10,
    "road_access": 0.10,
    "density": 0.10,
    "setback": 0.07,
    "walkability": 0.07,
    "wind": 0.05,
    "privacy": 0.05,
    "noise": 0.04,
    "structural": 0.04,
    "construction_efficiency": 0.03,
    # Unweighted-by-default (informational / strategy drivers):
    "context_response": 0.0,
    "emergency_access": 0.0,
    "mixed_use": 0.0,
    "public_private": 0.0,
}

# In-process override (set via POST /optimization/weights). None => defaults.
_active_weights: dict[str, float] | None = None


def get_weights() -> dict[str, float]:
    """Return the active weights (normalized so the weighted objectives sum to 1)."""
    raw = dict(_active_weights) if _active_weights is not None else dict(DEFAULT_WEIGHTS)
    return normalize(raw)


def set_weights(weights: dict[str, Any]) -> dict[str, float]:
    """Replace the active weights with a (partial) update, keeping unspecified
    objectives at their default. Returns the normalized result."""
    global _active_weights
    merged = dict(DEFAULT_WEIGHTS)
    for k, v in (weights or {}).items():
        if k in merged:
            try:
                merged[k] = max(0.0, float(v))
            except (TypeError, ValueError):
                continue
    _active_weights = merged
    return normalize(merged)


def reset_weights() -> dict[str, float]:
    global _active_weights
    _active_weights = None
    return get_weights()


def normalize(weights: dict[str, float]) -> dict[str, float]:
    """Scale weights so the non-zero entries sum to 1.0 (avoids drift after edits)."""
    total = sum(v for v in weights.values() if v > 0)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 4) if v > 0 else 0.0 for k, v in weights.items()}
