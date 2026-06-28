"""Setback rules and buildable area validation.

Defines setback requirements by building typology and provides functions to:
- Calculate buildable areas after applying setbacks
- Validate building compliance with setback rules
- Calculate setback violations
"""

from __future__ import annotations

from typing import Any, NamedTuple

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union


# ============================================================================
# Setback Rule Definitions
# ============================================================================

class SetbackRules(NamedTuple):
    """Setback requirements for a building type."""
    front_setback: float  # meters from front edge
    rear_setback: float   # meters from rear edge
    side_setback: float   # meters from side edges
    min_open_space: float  # percentage (0-100)
    description: str


# Standard setback rules by building type
SETBACK_RULES_BY_TYPE: dict[str, SetbackRules] = {
    "residential": SetbackRules(
        front_setback=5.0,
        rear_setback=3.0,
        side_setback=3.0,
        min_open_space=30.0,
        description="Residential: 5m front, 3m rear, 3m sides, 30% open space"
    ),
    "commercial": SetbackRules(
        front_setback=6.0,
        rear_setback=4.0,
        side_setback=4.0,
        min_open_space=20.0,
        description="Commercial: 6m front, 4m rear, 4m sides, 20% open space"
    ),
    "mixed-use": SetbackRules(
        front_setback=6.0,
        rear_setback=4.0,
        side_setback=4.0,
        min_open_space=25.0,
        description="Mixed-use: 6m front, 4m rear, 4m sides, 25% open space"
    ),
    "industrial": SetbackRules(
        front_setback=10.0,
        rear_setback=5.0,
        side_setback=5.0,
        min_open_space=15.0,
        description="Industrial: 10m front, 5m rear, 5m sides, 15% open space"
    ),
    "default": SetbackRules(
        front_setback=5.0,
        rear_setback=3.0,
        side_setback=3.0,
        min_open_space=25.0,
        description="Default: 5m front, 3m rear, 3m sides, 25% open space"
    ),
}


# ============================================================================
# Setback Functions
# ============================================================================

def get_setback_rules(building_type: str | None = None) -> SetbackRules:
    """Get setback rules for a building type.

    Args:
        building_type: Building type (residential, commercial, mixed-use, industrial)

    Returns:
        SetbackRules for the type, or default if type not recognized
    """
    if not building_type:
        return SETBACK_RULES_BY_TYPE["default"]

    building_type_lower = building_type.lower().replace(" ", "-")
    return SETBACK_RULES_BY_TYPE.get(building_type_lower, SETBACK_RULES_BY_TYPE["default"])


def create_buildable_area(
    site_boundary: list[list[float]],
    setback_rules: SetbackRules | None = None,
    building_type: str | None = None,
) -> Polygon | None:
    """Create the buildable area by applying setbacks to the site boundary.

    Args:
        site_boundary: List of [x, y] coordinates defining site perimeter
        setback_rules: SetbackRules instance (if None, uses building_type)
        building_type: Building type for default rules

    Returns:
        Polygon representing buildable area, or None if invalid
    """
    if not site_boundary or len(site_boundary) < 3:
        return None

    rules = setback_rules or get_setback_rules(building_type)

    try:
        # Create site polygon
        site_polygon = Polygon(site_boundary)
        if not site_polygon.is_valid:
            site_polygon = site_polygon.buffer(0)  # Fix self-intersections

        # Apply uniform inset (setback) to all sides
        # Use the maximum setback value for conservative approach
        max_setback = max(rules.front_setback, rules.rear_setback, rules.side_setback)

        # Buffer negative to shrink inward
        buildable = site_polygon.buffer(-max_setback)

        if buildable.is_empty or buildable.area <= 0:
            return None

        return buildable
    except Exception as e:
        print(f"[setback_rules] Error creating buildable area: {e}")
        return None


def point_inside_polygon(point: tuple[float, float], polygon: Polygon) -> bool:
    """Check if a point is inside a polygon.

    Args:
        point: (x, y) coordinates
        polygon: Shapely Polygon

    Returns:
        True if point is strictly inside polygon
    """
    p = Point(point)
    return polygon.contains(p)


def check_setback_compliance(
    building_footprint: list[list[float]],
    buildable_area: Polygon,
    tolerance: float = 0.1,
) -> tuple[bool, str]:
    """Check if a building footprint complies with setback rules.

    Args:
        building_footprint: List of [x, y] coordinates
        buildable_area: Polygon of allowable building area
        tolerance: Small tolerance for floating-point errors (meters)

    Returns:
        (is_compliant, message)
    """
    if not building_footprint or len(building_footprint) < 3:
        return False, "Invalid building footprint"

    if buildable_area is None or buildable_area.is_empty:
        return False, "Invalid buildable area"

    try:
        building_polygon = Polygon(building_footprint)
        if not building_polygon.is_valid:
            building_polygon = building_polygon.buffer(0)

        # Check if entire building is within buildable area
        if not buildable_area.contains(building_polygon):
            # Check if there's ANY overlap (not just containment)
            if not building_polygon.intersects(buildable_area):
                return False, "Building completely outside buildable area"

            # Calculate how much is outside
            difference = building_polygon.difference(buildable_area)
            outside_area = difference.area
            total_area = building_polygon.area
            outside_pct = (outside_area / total_area * 100) if total_area > 0 else 0

            return False, f"Building extends {outside_pct:.1f}% outside buildable area (setback violation)"

        return True, "Passed setback compliance"

    except Exception as e:
        return False, f"Error checking setback compliance: {e}"


def calculate_setback_violation(
    building_footprint: list[list[float]],
    buildable_area: Polygon,
) -> dict[str, Any]:
    """Calculate detailed setback violation metrics.

    Args:
        building_footprint: List of [x, y] coordinates
        buildable_area: Polygon of allowable building area

    Returns:
        Dict with violation metrics
    """
    if not building_footprint or not buildable_area:
        return {
            "violated": True,
            "violation_type": "invalid_input",
            "violation_area": 0,
            "violation_percentage": 0,
            "closest_point_distance": 0,
            "message": "Invalid input",
        }

    try:
        building_polygon = Polygon(building_footprint)
        if not building_polygon.is_valid:
            building_polygon = building_polygon.buffer(0)

        # Check if building is completely inside buildable area
        if buildable_area.contains(building_polygon):
            return {
                "violated": False,
                "violation_type": "none",
                "violation_area": 0,
                "violation_percentage": 0,
                "closest_point_distance": 0,
                "message": "No setback violation",
            }

        # Calculate overlapping areas
        intersection = building_polygon.intersection(buildable_area)
        difference = building_polygon.difference(buildable_area)

        violation_area = difference.area
        total_area = building_polygon.area
        violation_pct = (violation_area / total_area * 100) if total_area > 0 else 0

        # Calculate distance to buildable area boundary
        exterior_ring = buildable_area.exterior
        building_boundary = building_polygon.exterior

        min_distance = float('inf')
        for x, y in building_footprint:
            point = Point(x, y)
            distance = exterior_ring.distance(point)
            min_distance = min(min_distance, distance)

        violation_type = "outside" if violation_pct > 50 else "partial"

        return {
            "violated": True,
            "violation_type": violation_type,
            "violation_area": violation_area,
            "violation_percentage": violation_pct,
            "closest_point_distance": -min_distance,  # Negative = outside
            "message": f"Setback violation: {violation_pct:.1f}% outside buildable area",
        }

    except Exception as e:
        return {
            "violated": True,
            "violation_type": "calculation_error",
            "violation_area": 0,
            "violation_percentage": 0,
            "closest_point_distance": 0,
            "message": f"Error calculating violation: {e}",
        }


def calculate_open_space_percentage(
    site_boundary: list[list[float]],
    building_footprint: list[list[float]],
) -> float:
    """Calculate percentage of open space on site.

    Args:
        site_boundary: Site perimeter coordinates
        building_footprint: Building footprint coordinates

    Returns:
        Open space percentage (0-100)
    """
    try:
        site_polygon = Polygon(site_boundary)
        building_polygon = Polygon(building_footprint)

        if not site_polygon.is_valid or not building_polygon.is_valid:
            return 0.0

        site_area = site_polygon.area
        building_area = building_polygon.area
        open_area = site_area - building_area

        if site_area <= 0:
            return 0.0

        return max(0.0, (open_area / site_area) * 100)

    except Exception:
        return 0.0


def validate_option_boundary(
    candidate_boundary: list[list[float]],
    site_boundary: list[list[float]],
    buildable_area: Polygon | None = None,
    building_type: str | None = None,
) -> dict[str, Any]:
    """Comprehensive validation of a candidate building against site and setback constraints.

    Args:
        candidate_boundary: Candidate building footprint
        site_boundary: Confirmed site boundary
        buildable_area: Pre-computed buildable area (if None, will be calculated)
        building_type: Building type for setback rules

    Returns:
        Validation result dict with status and messages
    """
    validation = {
        "valid": False,
        "inside_site": False,
        "inside_buildable_area": False,
        "setback_compliant": False,
        "open_space_compliant": False,
        "messages": [],
    }

    # Check if inside site boundary
    try:
        site_polygon = Polygon(site_boundary)
        candidate_polygon = Polygon(candidate_boundary)

        if not site_polygon.is_valid:
            site_polygon = site_polygon.buffer(0)
        if not candidate_polygon.is_valid:
            candidate_polygon = candidate_polygon.buffer(0)

        if not site_polygon.contains(candidate_polygon):
            validation["messages"].append("Building footprint crosses the confirmed site boundary.")
            return validation

        validation["inside_site"] = True

    except Exception as e:
        validation["messages"].append(f"Error checking site boundary: {e}")
        return validation

    # Calculate or use provided buildable area
    if buildable_area is None:
        buildable_area = create_buildable_area(site_boundary, building_type=building_type)

    # Check setback compliance
    if buildable_area is not None:
        compliant, message = check_setback_compliance(candidate_boundary, buildable_area)
        if compliant:
            validation["setback_compliant"] = True
            validation["inside_buildable_area"] = True
        else:
            validation["messages"].append(f"Rejected: {message}")
            return validation
    else:
        # No buildable area constraint, just ensure inside site
        validation["inside_buildable_area"] = True
        validation["setback_compliant"] = True

    # Check open space requirement
    rules = get_setback_rules(building_type)
    open_space_pct = calculate_open_space_percentage(site_boundary, candidate_boundary)

    if open_space_pct >= rules.min_open_space:
        validation["open_space_compliant"] = True
    else:
        validation["messages"].append(
            f"Warning: Open space {open_space_pct:.1f}% below target {rules.min_open_space}%"
        )

    validation["valid"] = True
    validation["messages"].append("Passed all constraints")

    return validation
