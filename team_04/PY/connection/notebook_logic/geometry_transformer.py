"""Geometry transformer — canonical move / rotate / scale operations + natural
language command parsing, extracted from the tool_dev geometry workflow into a
proper runtime module.

It does NOT reimplement geometry math: translate/rotate go through the existing
agent.tools.modify_building_boundary (via tool_dev_runtime); scale is a
scale-about-centroid then a revalidation pass through the same tool so the
site-fit check still runs.

Used by the live transform route and the prompt-edit path, so Move/Rotate/Scale
work identically from UI tool buttons and from typed prompts.
"""
from __future__ import annotations

import math
import re
from typing import Any

from . import tool_dev_runtime

# Compass / relative directions → unit (dx, dy) in the site's metric frame
# (north = +y, east = +x).
_DIRECTIONS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "n": (0.0, 1.0), "up": (0.0, 1.0),
    "south": (0.0, -1.0), "s": (0.0, -1.0), "down": (0.0, -1.0),
    "east": (1.0, 0.0), "e": (1.0, 0.0), "right": (1.0, 0.0),
    "west": (-1.0, 0.0), "w": (-1.0, 0.0), "left": (-1.0, 0.0),
    "northeast": (0.707, 0.707), "ne": (0.707, 0.707),
    "northwest": (-0.707, 0.707), "nw": (-0.707, 0.707),
    "southeast": (0.707, -0.707), "se": (0.707, -0.707),
    "southwest": (-0.707, -0.707), "sw": (-0.707, -0.707),
}


# --------------------------------------------------------------------------- #
# Natural-language parsing
# --------------------------------------------------------------------------- #
def parse_move(text: str) -> dict[str, Any] | None:
    """Parse 'move 10m east', 'shift 5 meters to the north', 'move left 8'.
    Returns {dx, dy} in meters, or None if no movement understood."""
    if not text:
        return None
    low = text.lower()
    # distance (meters) — first number in the phrase
    dist_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m\b|meter|metre|meters|metres|units?)?", low)
    dist = float(dist_m.group(1)) if dist_m else None
    direction = None
    for word, vec in _DIRECTIONS.items():
        if re.search(rf"\b{word}\b", low):
            direction = vec
            break
    if direction is None or dist is None:
        return None
    return {"dx": round(direction[0] * dist, 3), "dy": round(direction[1] * dist, 3)}


def parse_rotate(text: str) -> dict[str, Any] | None:
    """Parse 'rotate 30 degrees', 'turn 45° clockwise', 'rotate -15'.
    Clockwise is negative; counter-clockwise / anti-clockwise is positive."""
    if not text:
        return None
    low = text.lower()
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:deg|degree|degrees|°)?", low)
    if not m:
        return None
    angle = float(m.group(1))
    if "clockwise" in low and "counter" not in low and "anti" not in low:
        angle = -abs(angle)
    elif "counter" in low or "anti" in low:
        angle = abs(angle)
    return {"rotation": round(angle, 3)}


def parse_scale(text: str) -> dict[str, Any] | None:
    """Parse 'scale 1.2', 'scale up 20%', 'make it 0.8x', 'shrink by 10%'."""
    if not text:
        return None
    low = text.lower()
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
    if pct:
        frac = float(pct.group(1)) / 100.0
        if any(w in low for w in ("shrink", "reduce", "smaller", "down", "pull")):
            return {"scale": round(1.0 - frac, 3)}
        return {"scale": round(1.0 + frac, 3)}
    mult = re.search(r"(\d+(?:\.\d+)?)\s*x", low) or re.search(r"scale\s*(?:to|by)?\s*(\d+(?:\.\d+)?)", low)
    if mult:
        return {"scale": round(float(mult.group(1)), 3)}
    return None


def parse_command(text: str) -> dict[str, Any] | None:
    """Detect the manipulation kind and parse its parameters from free text.
    Returns {kind, ...params} for move/rotate/scale, or None."""
    if not text:
        return None
    low = text.lower()
    if re.search(r"\b(move|shift|nudge|translate)\b", low):
        p = parse_move(low)
        if p:
            return {"kind": "move", **p}
    if re.search(r"\b(rotate|turn|spin|orient)\b", low):
        p = parse_rotate(low)
        if p:
            return {"kind": "rotate", **p}
    if re.search(r"\b(scale|resize|grow|shrink|enlarge|bigger|smaller)\b", low):
        p = parse_scale(low)
        if p:
            return {"kind": "scale", **p}
    return None


# --------------------------------------------------------------------------- #
# Apply (validation happens inside modify_building_boundary)
# --------------------------------------------------------------------------- #
def scale_about_centroid(boundary: list[list[float]], factor: float) -> list[list[float]]:
    pts = [p for p in boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts or factor == 1.0:
        return boundary
    cx = sum(float(p[0]) for p in pts) / len(pts)
    cy = sum(float(p[1]) for p in pts) / len(pts)
    out = []
    for p in boundary:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            z = [float(p[2])] if len(p) > 2 else []
            out.append([cx + (float(p[0]) - cx) * factor, cy + (float(p[1]) - cy) * factor] + z)
        else:
            out.append(p)
    return out


# --------------------------------------------------------------------------- #
# Pure geometry ops (operate directly on a boundary ring). These are the named
# transforms the manipulation API exposes; apply_transform composes them and adds
# the site-fit validation via modify_building_boundary.
# --------------------------------------------------------------------------- #
def _centroid(boundary: list[list[float]]) -> tuple[float, float]:
    pts = [p for p in boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts:
        return 0.0, 0.0
    return sum(float(p[0]) for p in pts) / len(pts), sum(float(p[1]) for p in pts) / len(pts)


def move_geometry(geometry: list[list[float]], dx: float, dy: float, dz: float = 0.0) -> list[list[float]]:
    """Translate a boundary ring by (dx, dy[, dz])."""
    out = []
    for p in geometry:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            z = (float(p[2]) if len(p) > 2 else 0.0) + float(dz)
            out.append([float(p[0]) + float(dx), float(p[1]) + float(dy), z])
        else:
            out.append(p)
    return out


def rotate_geometry(
    geometry: list[list[float]], angle_degrees: float, pivot: tuple[float, float] | None = None
) -> list[list[float]]:
    """Rotate a boundary ring by angle_degrees about pivot (default: centroid).
    Positive = counter-clockwise, negative = clockwise."""
    cx, cy = pivot if pivot else _centroid(geometry)
    rad = math.radians(float(angle_degrees))
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out = []
    for p in geometry:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = float(p[0]) - cx, float(p[1]) - cy
            rx = cx + x * cos_a - y * sin_a
            ry = cy + x * sin_a + y * cos_a
            z = [float(p[2])] if len(p) > 2 else []
            out.append([rx, ry] + z)
        else:
            out.append(p)
    return out


def scale_geometry(
    geometry: list[list[float]], scale_factor: float, pivot: tuple[float, float] | None = None
) -> list[list[float]]:
    """Scale a boundary ring about pivot (default: centroid)."""
    cx, cy = pivot if pivot else _centroid(geometry)
    out = []
    for p in geometry:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            z = [float(p[2])] if len(p) > 2 else []
            out.append([cx + (float(p[0]) - cx) * float(scale_factor),
                        cy + (float(p[1]) - cy) * float(scale_factor)] + z)
        else:
            out.append(p)
    return out


def push_pull_geometry(
    geometry: list[list[float]], target_part: str | None, distance: float
) -> list[list[float]]:
    """Push/pull the footprint outward (+) or inward (−) by `distance` meters,
    approximated as a uniform offset about the centroid (face-level extrude needs a
    picked face). target_part is accepted for API symmetry."""
    del target_part
    bw_pts = [p for p in geometry if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not bw_pts:
        return geometry
    # Convert an absolute push distance into a scale factor relative to the mean
    # radius so small/large buildings respond proportionally.
    cx, cy = _centroid(geometry)
    import statistics
    radius = statistics.fmean(
        ((float(p[0]) - cx) ** 2 + (float(p[1]) - cy) ** 2) ** 0.5 for p in bw_pts
    ) or 1.0
    factor = max(0.1, 1.0 + float(distance) / radius)
    return scale_geometry(geometry, factor, (cx, cy))


def apply_transform(
    geometry_id: str,
    boundary: list[list[float]],
    *,
    dx: float = 0.0,
    dy: float = 0.0,
    rotation: float = 0.0,
    scale: float = 1.0,
    site_boundary: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Apply move/rotate/scale and return the modify_building_boundary result
    (which includes transformed_boundary + fits_within_site_boundary). Scale is
    applied first about the centroid, then translate/rotate + the site-fit check."""
    working = scale_about_centroid(boundary, float(scale))
    return tool_dev_runtime.modify_geometry(
        geometry_id,
        working,
        site_boundary=site_boundary,
        translate_by_xy=[float(dx), float(dy)],
        rotation_degrees=float(rotation),
    )
