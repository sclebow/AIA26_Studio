"""Edge-based optimization — position buildings relative to selected site edges.

Provides functions to:
- Score candidate positions based on proximity to selected edge
- Generate candidates attracted to selected edge
- Align building orientation to edge direction
- Validate edge-based placement against constraints
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

from shapely.geometry import Point, Polygon


# ============================================================================
# Edge Data Structure
# ============================================================================

class EdgeMetadata(NamedTuple):
    """Edge metadata from context analysis."""
    edge_id: str
    label: str  # "North Edge", "Southeast Edge", etc.
    direction: str  # "North", "Southeast", etc.
    angle: float  # Compass angle (0-360°, 0=north)
    sector: str  # Compass sector
    start_point: tuple[float, float]
    end_point: tuple[float, float]
    midpoint: tuple[float, float]
    vx: float  # East component of edge vector
    vy: float  # North component of edge vector


# ============================================================================
# Edge-Based Scoring
# ============================================================================

def calculate_distance_to_edge(
    point: tuple[float, float],
    edge_start: tuple[float, float],
    edge_end: tuple[float, float],
) -> float:
    """Calculate shortest distance from point to line segment.

    Args:
        point: (x, y) coordinates
        edge_start: Edge start point
        edge_end: Edge end point

    Returns:
        Distance in same units as coordinates
    """
    x, y = point
    x1, y1 = edge_start
    x2, y2 = edge_end

    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy

    if len_sq == 0:
        return math.sqrt((x - x1) ** 2 + (y - y1) ** 2)

    # Project point onto line segment
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / len_sq))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return math.sqrt((x - closest_x) ** 2 + (y - closest_y) ** 2)


def calculate_edge_attraction_score(
    building_footprint: list[list[float]],
    selected_edge: EdgeMetadata,
    max_attraction_distance: float = 50.0,  # meters
) -> float:
    """Score how well a building is positioned relative to a selected edge.

    Args:
        building_footprint: Building coordinates
        selected_edge: EdgeMetadata for the edge to attract towards
        max_attraction_distance: Distance beyond which attraction = 0

    Returns:
        Score 0-100, where 100 is closest to edge
    """
    if not building_footprint or len(building_footprint) < 3:
        return 0.0

    # Calculate building centroid
    centroid_x = sum(p[0] for p in building_footprint) / len(building_footprint)
    centroid_y = sum(p[1] for p in building_footprint) / len(building_footprint)
    centroid = (centroid_x, centroid_y)

    # Distance from building centroid to edge
    distance = calculate_distance_to_edge(
        centroid,
        selected_edge.start_point,
        selected_edge.end_point,
    )

    # Score: closer = higher
    if distance > max_attraction_distance:
        return 0.0

    # Linear falloff from distance=0 (score=100) to max_distance (score=0)
    score = (1 - distance / max_attraction_distance) * 100
    return max(0, min(100, score))


def get_edge_normal(edge: EdgeMetadata) -> tuple[float, float]:
    """Get the outward normal direction of an edge (perpendicular, pointing outward).

    Args:
        edge: EdgeMetadata

    Returns:
        (normal_x, normal_y) unit vector
    """
    # Edge vector
    edge_vx = edge.vx
    edge_vy = edge.vy

    # Normal perpendicular to edge (rotate 90° counter-clockwise)
    # If edge points in direction (vx, vy), normal points in (-vy, vx)
    normal_vx = -edge_vy
    normal_vy = edge_vx

    # Normalize
    length = math.sqrt(normal_vx**2 + normal_vy**2)
    if length > 0:
        normal_vx /= length
        normal_vy /= length

    return normal_vx, normal_vy


def move_candidate_towards_edge(
    building_footprint: list[list[float]],
    selected_edge: EdgeMetadata,
    distance_from_edge: float,
) -> list[list[float]] | None:
    """Move a building closer to a selected edge.

    Args:
        building_footprint: Original building coordinates
        selected_edge: Edge to move towards
        distance_from_edge: Target distance from edge to building centroid

    Returns:
        Moved building footprint, or None if invalid
    """
    if not building_footprint or len(building_footprint) < 3:
        return None

    # Calculate building centroid
    centroid_x = sum(p[0] for p in building_footprint) / len(building_footprint)
    centroid_y = sum(p[1] for p in building_footprint) / len(building_footprint)

    # Get outward normal
    normal_x, normal_y = get_edge_normal(selected_edge)

    # Project centroid onto edge segment
    edge_start = selected_edge.start_point
    edge_end = selected_edge.end_point

    # Vector from edge start to centroid
    dx_to_c = centroid_x - edge_start[0]
    dy_to_c = centroid_y - edge_start[1]

    # Edge vector
    edge_dx = edge_end[0] - edge_start[0]
    edge_dy = edge_end[1] - edge_start[1]

    len_sq = edge_dx**2 + edge_dy**2
    if len_sq == 0:
        return None

    # Parameter along edge (clamped to segment)
    t = max(0, min(1, (dx_to_c * edge_dx + dy_to_c * edge_dy) / len_sq))

    # Closest point on edge
    closest_x = edge_start[0] + t * edge_dx
    closest_y = edge_start[1] + t * edge_dy

    # New centroid position: distance_from_edge along the normal
    new_centroid_x = closest_x + normal_x * distance_from_edge
    new_centroid_y = closest_y + normal_y * distance_from_edge

    # Displacement to apply
    delta_x = new_centroid_x - centroid_x
    delta_y = new_centroid_y - centroid_y

    # Move all vertices
    moved_footprint = [[p[0] + delta_x, p[1] + delta_y] for p in building_footprint]

    return moved_footprint


def get_edge_direction_angle(edge: EdgeMetadata) -> float:
    """Get the direction angle of an edge (for alignment).

    Args:
        edge: EdgeMetadata

    Returns:
        Angle in degrees from north, clockwise
    """
    # Edge angle (from centroid to midpoint)
    return edge.angle


def align_building_to_edge(
    building_footprint: list[list[float]],
    selected_edge: EdgeMetadata,
    rotation_degrees: float | None = None,
) -> list[list[float]] | None:
    """Rotate a building to align with a selected edge.

    Args:
        building_footprint: Building coordinates
        selected_edge: Edge to align to
        rotation_degrees: Rotation to apply (if None, uses edge direction)

    Returns:
        Rotated building footprint, or None if invalid
    """
    if not building_footprint or len(building_footprint) < 3:
        return None

    # Calculate building centroid
    centroid_x = sum(p[0] for p in building_footprint) / len(building_footprint)
    centroid_y = sum(p[1] for p in building_footprint) / len(building_footprint)

    # Determine rotation angle
    if rotation_degrees is None:
        rotation_degrees = selected_edge.angle

    rotation_rad = math.radians(rotation_degrees)
    cos_a = math.cos(rotation_rad)
    sin_a = math.sin(rotation_rad)

    # Rotate each vertex around centroid
    rotated = []
    for x, y in building_footprint:
        # Translate to origin
        dx = x - centroid_x
        dy = y - centroid_y

        # Rotate
        rotated_x = dx * cos_a - dy * sin_a
        rotated_y = dx * sin_a + dy * cos_a

        # Translate back
        rotated.append([rotated_x + centroid_x, rotated_y + centroid_y])

    return rotated


def generate_candidates_near_edge(
    site_boundary: list[list[float]],
    selected_edge: EdgeMetadata,
    buildable_area: Polygon | None = None,
    base_footprint: list[list[float]] | None = None,
    num_candidates: int = 5,
) -> list[dict[str, Any]]:
    """Generate candidate building positions near a selected edge.

    Args:
        site_boundary: Site perimeter
        selected_edge: Edge to position near
        buildable_area: Polygon of allowed area (if None, uses site_boundary)
        base_footprint: Base building shape (for positioning)
        num_candidates: Number of candidates to generate

    Returns:
        List of candidate position dicts
    """
    candidates = []

    if base_footprint is None:
        base_footprint = site_boundary  # Use site boundary as fallback

    if buildable_area is None:
        buildable_area = Polygon(site_boundary)

    # Generate positions at varying distances from edge
    distances = [10.0, 15.0, 20.0, 25.0, 30.0][:num_candidates]

    for dist in distances:
        # Move towards edge
        moved = move_candidate_towards_edge(base_footprint, selected_edge, dist)

        if moved is None:
            continue

        # Check if within buildable area
        try:
            moved_poly = Polygon(moved)
            if not buildable_area.contains(moved_poly):
                continue
        except Exception:
            continue

        # Calculate attraction score
        attraction_score = calculate_edge_attraction_score(moved, selected_edge)

        candidates.append({
            "position": moved,
            "distance_from_edge": dist,
            "edge_attraction_score": attraction_score,
            "selected_edge_id": selected_edge.edge_id,
            "selected_edge_label": selected_edge.label,
        })

    return candidates


def validate_edge_alignment(
    building_footprint: list[list[float]],
    selected_edge: EdgeMetadata,
    tolerance_degrees: float = 10.0,
) -> tuple[bool, str]:
    """Check if a building is well-aligned with a selected edge.

    Args:
        building_footprint: Building coordinates
        selected_edge: Edge to check alignment with
        tolerance_degrees: Allowed angle deviation

    Returns:
        (is_aligned, message)
    """
    if not building_footprint or len(building_footprint) < 3:
        return False, "Invalid building footprint"

    # Find longest edge of building
    longest_edge_length = 0
    longest_edge_angle = 0

    for i in range(len(building_footprint)):
        p1 = building_footprint[i]
        p2 = building_footprint[(i + 1) % len(building_footprint)]

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        edge_length = math.sqrt(dx**2 + dy**2)

        if edge_length > longest_edge_length:
            longest_edge_length = edge_length
            # Calculate angle of this edge
            angle = math.degrees(math.atan2(dx, dy)) % 360

            longest_edge_angle = angle

    # Compare with selected edge angle
    selected_edge_angle = selected_edge.angle

    # Find smallest angular difference (accounting for 360° wrap)
    diff = abs(longest_edge_angle - selected_edge_angle)
    if diff > 180:
        diff = 360 - diff

    is_aligned = diff <= tolerance_degrees

    message = (
        f"Building aligned within {diff:.1f}° (target: {tolerance_degrees}°)"
        if is_aligned
        else f"Building not aligned: {diff:.1f}° off (target: {tolerance_degrees}°)"
    )

    return is_aligned, message


def create_edge_metadata_from_context(edge_data: dict[str, Any]) -> EdgeMetadata | None:
    """Create EdgeMetadata from context analysis edge dict.

    Args:
        edge_data: Edge dict from context analysis

    Returns:
        EdgeMetadata or None if invalid
    """
    required_fields = ["id", "label", "direction", "compassAngle", "compassSector", "a", "b", "mid"]

    if not all(field in edge_data for field in required_fields):
        return None

    mid = edge_data.get("mid") or edge_data.get("midpoint", [0, 0])
    a = edge_data["a"]
    b = edge_data["b"]

    vx = mid[0] - (sum(p[0] for p in edge_data.get("polygon", [a, b])) / max(1, len(
        edge_data.get("polygon", [a, b])
    )))
    vy = mid[1] - (sum(p[1] for p in edge_data.get("polygon", [a, b])) / max(1, len(
        edge_data.get("polygon", [a, b])
    )))

    return EdgeMetadata(
        edge_id=edge_data.get("id") or edge_data.get("edge_id"),
        label=edge_data.get("display_name") or edge_data.get("label"),
        direction=edge_data.get("direction"),
        angle=edge_data.get("compassAngle") or edge_data.get("angle", 0),
        sector=edge_data.get("compassSector") or edge_data.get("direction"),
        start_point=(a[0], a[1]),
        end_point=(b[0], b[1]),
        midpoint=(mid[0], mid[1]),
        vx=vx,
        vy=vy,
    )
