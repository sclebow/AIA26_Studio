"""
Boundary Analyzer Tool - Matches input boundaries against reference dataset
Uses area, IoU, and topology scoring with SVG visualization output.
"""

import json
import math
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any
import numpy as np

from utils.svg_utils import generate_boundary_comparison_svg


# ============================================================================
# CONSTANTS
# ============================================================================

# Scoring weights (must sum to 1.0)
WEIGHT_AREA = 0.2
WEIGHT_IOU = 0.5
WEIGHT_TOPOLOGY = 0.3

# Grid-based IoU sampling resolution
GRID_RESOLUTION = 100

# Rotation angles to test (degrees)
ROTATION_ANGLES = [0, 90, 180, 270]

# Default number of top matches to return
DEFAULT_TOP_N = 5


# ============================================================================
# TOOL SCHEMA
# ============================================================================

def get_boundary_analyzer_schema() -> Dict[str, Any]:
    """Return the MCP tool schema for boundary_analyzer."""
    return {
        "name": "boundary_analyzer",
        "description": "Analyzes input boundary against dataset to find best matches using area, IoU, and topology scoring",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_boundary": {
                    "type": "array",
                    "description": "Closed loop coordinates [[x1,y1], [x2,y2], ..., [xn,yn]] (optional if input_layout_path is provided)",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2
                    }
                },
                "input_layout_path": {
                    "type": "string",
                    "description": "Path to input layout JSON file (will use 'outline' field as boundary)",
                    "default": "team_06/team_06_input_layout.json"
                },
                "dataset_path": {
                    "type": "string",
                    "description": "Path to layout dataset JSON file (optional)",
                    "default": "team_06/layout_inputs/sample_layouts.json"
                },
                "top_n_results": {
                    "type": "integer",
                    "description": "Number of top matches to return",
                    "default": DEFAULT_TOP_N
                }
            },
            "required": []
        }
    }


# ============================================================================
# GEOMETRY UTILITIES
# ============================================================================

def polygon_area(coords: List[List[float]]) -> float:
    """Calculate polygon area using Shoelace formula."""
    coords = np.array(coords)
    x = coords[:, 0]
    y = coords[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def polygon_perimeter(coords: List[List[float]]) -> float:
    """Calculate polygon perimeter."""
    coords = np.array(coords)
    shifted = np.roll(coords, -1, axis=0)
    distances = np.sqrt(np.sum((coords - shifted) ** 2, axis=1))
    return np.sum(distances)


def polygon_compactness(area: float, perimeter: float) -> float:
    """Calculate compactness: 4π × area / perimeter²."""
    if perimeter == 0:
        return 0
    return (4 * math.pi * area) / (perimeter ** 2)


def get_bounding_box(coords: List[List[float]]) -> Tuple[float, float, float, float]:
    """Get bounding box (min_x, max_x, min_y, max_y) of polygon."""
    coords_array = np.array(coords)
    min_x = coords_array[:, 0].min()
    max_x = coords_array[:, 0].max()
    min_y = coords_array[:, 1].min()
    max_y = coords_array[:, 1].max()
    return min_x, max_x, min_y, max_y


def normalize_to_origin(coords: List[List[float]]) -> List[List[float]]:
    """Translate polygon so its bounding box starts at (0, 0)."""
    min_x, _, min_y, _ = get_bounding_box(coords)
    return [[x - min_x, y - min_y] for x, y in coords]


def rotate_polygon(coords: List[List[float]], angle_degrees: float) -> List[List[float]]:
    """Rotate polygon around its centroid."""
    coords_array = np.array(coords)
    
    # Calculate centroid
    cx = coords_array[:, 0].mean()
    cy = coords_array[:, 1].mean()
    
    # Translate to origin
    translated = coords_array - [cx, cy]
    
    # Rotate
    angle_rad = np.radians(angle_degrees)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    rotation_matrix = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    rotated = translated @ rotation_matrix.T
    
    # Translate back
    result = rotated + [cx, cy]
    
    return result.tolist()


def point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    """Check if a point is inside a polygon using ray casting algorithm."""
    x, y = point
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside


def calculate_iou_grid(coords1: List[List[float]], coords2: List[List[float]], 
                       grid_resolution: int = GRID_RESOLUTION) -> float:
    """
    Calculate IoU using grid-based sampling (works for concave polygons).
    More accurate for complex shapes than polygon intersection algorithms.
    """
    # Get combined bounding box
    all_coords = coords1 + coords2
    min_x, max_x, min_y, max_y = get_bounding_box(all_coords)
    
    if max_x == min_x or max_y == min_y:
        return 0.0
    
    # Create grid
    dx = (max_x - min_x) / grid_resolution
    dy = (max_y - min_y) / grid_resolution
    
    intersection_count = 0
    union_count = 0
    
    # Sample grid points
    for i in range(grid_resolution):
        for j in range(grid_resolution):
            x = min_x + (i + 0.5) * dx
            y = min_y + (j + 0.5) * dy
            
            in_poly1 = point_in_polygon((x, y), coords1)
            in_poly2 = point_in_polygon((x, y), coords2)
            
            if in_poly1 and in_poly2:
                intersection_count += 1
            if in_poly1 or in_poly2:
                union_count += 1
    
    if union_count == 0:
        return 0.0
    
    return intersection_count / union_count


def calculate_iou_with_rotation(coords1: List[List[float]], coords2: List[List[float]]) -> float:
    """
    Calculate best IoU across 4 rotations (0°, 90°, 180°, 270°).
    Also normalizes both polygons to start at origin.
    Uses grid-based sampling for accurate concave polygon handling.
    """
    # Normalize both polygons to origin
    coords1_norm = normalize_to_origin(coords1)
    coords2_norm = normalize_to_origin(coords2)
    
    best_iou = 0.0
    
    # Try all rotation angles
    for angle in ROTATION_ANGLES:
        coords2_rotated = rotate_polygon(coords2_norm, angle)
        # Re-normalize after rotation to ensure alignment
        coords2_rotated_norm = normalize_to_origin(coords2_rotated)
        iou = calculate_iou_grid(coords1_norm, coords2_rotated_norm)
        best_iou = max(best_iou, iou)
    
    return best_iou


# ============================================================================
# SCORING FUNCTIONS
# ============================================================================

def calculate_area_score(area1: float, area2: float) -> float:
    """Calculate area similarity score (0-1)."""
    if max(area1, area2) == 0:
        return 1.0
    return 1.0 - abs(area1 - area2) / max(area1, area2)


def calculate_topology_score(stats1: Dict, stats2: Dict) -> float:
    """Calculate topology score based on vertex count, perimeter, and compactness."""
    vertex_sim = 1.0 - abs(stats1['vertex_count'] - stats2['vertex_count']) / \
                 max(stats1['vertex_count'], stats2['vertex_count'])
    
    perimeter_sim = 1.0 - abs(stats1['perimeter'] - stats2['perimeter']) / \
                    max(stats1['perimeter'], stats2['perimeter'])
    
    compactness_sim = 1.0 - abs(stats1['compactness'] - stats2['compactness'])
    
    return (vertex_sim + perimeter_sim + compactness_sim) / 3.0


def calculate_composite_score(area_score: float, iou_score: float, topology_score: float) -> float:
    """Calculate weighted composite score using predefined weights."""
    return (WEIGHT_AREA * area_score + 
            WEIGHT_IOU * iou_score + 
            WEIGHT_TOPOLOGY * topology_score)


def compute_boundary_stats(coords: List[List[float]]) -> Dict[str, float]:
    """Compute all statistics for a boundary."""
    area = polygon_area(coords)
    perimeter = polygon_perimeter(coords)
    compactness = polygon_compactness(area, perimeter)
    
    return {
        "area": round(area, 2),
        "perimeter": round(perimeter, 2),
        "vertex_count": len(coords) - 1 if coords[0] == coords[-1] else len(coords),
        "compactness": round(compactness, 3)
    }


# SVG generation delegated to utils.svg_utils.generate_boundary_comparison_svg


# ============================================================================
# MAIN TOOL FUNCTION
# ============================================================================

def boundary_analyzer(input_boundary: List[List[float]] = None,
                     input_layout_path: str = None,
                     dataset_path: str = None,
                     top_n_results: int = 5) -> Dict[str, Any]:
    """
    Analyze input boundary against dataset and return top matches with visualization.
    
    Args:
        input_boundary: Closed loop coordinates [[x1,y1], [x2,y2], ..., [xn,yn]] (optional if input_layout_path provided)
        input_layout_path: Path to input layout JSON file (will use 'outline' field)
        dataset_path: Path to layout dataset JSON (optional)
        top_n_results: Number of top matches to return
    
    Returns:
        Dictionary with analysis results, scores, and SVG visualization
    """
    
    # Load input boundary from file if path provided
    if input_layout_path is not None:
        input_layout_path = Path(input_layout_path)
        if not input_layout_path.is_absolute():
            if str(input_layout_path).startswith("team_06"):
                input_layout_path = Path(__file__).parent.parent.parent.parent / input_layout_path
            else:
                input_layout_path = Path(__file__).parent.parent.parent / input_layout_path
        
        if not input_layout_path.exists():
            return {
                "status": "error",
                "message": f"Input layout file not found at {input_layout_path}"
            }
        
        with open(input_layout_path, 'r') as f:
            input_layout = json.load(f)
        
        input_boundary = input_layout.get('outline', [])
        if not input_boundary:
            return {
                "status": "error",
                "message": "Input layout file does not contain 'outline' field"
            }
    
    # Validate that we have an input boundary
    if input_boundary is None or len(input_boundary) == 0:
        return {
            "status": "error",
            "message": "Either input_boundary or input_layout_path must be provided"
        }
    
    if dataset_path is None:
        dataset_path = Path(__file__).parent.parent.parent / "layout_inputs" / "sample_layouts.json"
    else:
        dataset_path = Path(dataset_path)
        if not dataset_path.is_absolute():
            # If path starts with team_06, it's already relative to repo root
            if str(dataset_path).startswith("team_06"):
                # Go up to repo root (team_06/python/tools -> AIA26_Studio)
                dataset_path = Path(__file__).parent.parent.parent.parent / dataset_path
            else:
                # Otherwise, it's relative to team_06 folder
                dataset_path = Path(__file__).parent.parent.parent / dataset_path
    
    if not dataset_path.exists():
        return {
            "status": "error",
            "message": f"Dataset not found at {dataset_path}"
        }
    
    with open(dataset_path, 'r') as f:
        dataset = json.load(f)
    
    input_stats = compute_boundary_stats(input_boundary)
    
    results = []
    
    # Parse sample_layouts.json structure (array of layouts with 'outline' field)
    for layout in dataset:
        # Use 'outline' field for boundary coordinates
        candidate_coords = layout.get('outline', [])
        
        if not candidate_coords:
            continue
            
        candidate_stats = compute_boundary_stats(candidate_coords)
        
        area_score = calculate_area_score(input_stats['area'], candidate_stats['area'])
        iou_score = calculate_iou_with_rotation(input_boundary, candidate_coords)
        topology_score = calculate_topology_score(input_stats, candidate_stats)
        composite_score = calculate_composite_score(area_score, iou_score, topology_score)
        
        # Extract layout info
        layout_id = layout.get('layoutId', 'unknown')
        layout_name = layout.get('apartment', {}).get('name', 'Unknown Layout')
        
        results.append({
            "boundary_id": layout_id,
            "name": layout_name,
            "category": "residential",
            "composite_score": round(composite_score, 3),
            "area_score": round(area_score, 3),
            "iou_score": round(iou_score, 3),
            "topology_score": round(topology_score, 3),
            "coordinates": candidate_coords,
            "stats": candidate_stats
        })
    
    results.sort(key=lambda x: x['composite_score'], reverse=True)
    top_matches = results[:top_n_results]
    
    if top_matches:
        best_match = top_matches[0]
        svg_output = generate_boundary_comparison_svg(
            input_boundary,
            best_match['coordinates'],
            input_stats,
            best_match['stats'],
            {
                'composite': best_match['composite_score'],
                'area': best_match['area_score'],
                'iou': best_match['iou_score'],
                'topology': best_match['topology_score']
            },
            {
                'id': best_match['boundary_id'],
                'name': best_match['name']
            }
        )
        
        output_dir = Path(__file__).parent.parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"boundary_analysis_{timestamp}.svg"
        
        with open(output_file, 'w') as f:
            f.write(svg_output)
        
        return {
            "status": "success",
            "input_boundary_stats": input_stats,
            "top_matches": [
                {
                    "rank": i + 1,
                    "boundary_id": m['boundary_id'],
                    "name": m['name'],
                    "category": m['category'],
                    "composite_score": m['composite_score'],
                    "area_score": m['area_score'],
                    "iou_score": m['iou_score'],
                    "topology_score": m['topology_score']
                }
                for i, m in enumerate(top_matches)
            ],
            "visualization_svg": svg_output,
            "output_file": str(output_file)
        }
    else:
        return {
            "status": "error",
            "message": "No matches found in dataset"
        }
