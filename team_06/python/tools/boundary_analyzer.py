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
                    "description": "Closed loop coordinates [[x1,y1], [x2,y2], ..., [xn,yn]]",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2
                    }
                },
                "dataset_path": {
                    "type": "string",
                    "description": "Path to boundary dataset JSON file (optional)",
                    "default": "team_06/assets/boundary_dataset.json"
                },
                "top_n_results": {
                    "type": "integer",
                    "description": "Number of top matches to return",
                    "default": 5
                }
            },
            "required": ["input_boundary"]
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


def clip_polygon_component(polygon: List[List[float]], edge_start: List[float], edge_end: List[float]) -> List[List[float]]:
    """Sutherland-Hodgman: Clip polygon against a single edge."""
    def inside(point: List[float]) -> bool:
        """Check if point is on the left side of the edge."""
        return (edge_end[0] - edge_start[0]) * (point[1] - edge_start[1]) - \
               (edge_end[1] - edge_start[1]) * (point[0] - edge_start[0]) >= 0
    
    def intersection(p1: List[float], p2: List[float]) -> List[float]:
        """Find intersection point of line segment with edge."""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = edge_start
        x4, y4 = edge_end
        
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return p1
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)]
    
    if not polygon:
        return []
    
    output = []
    prev_point = polygon[-1]
    prev_inside = inside(prev_point)
    
    for curr_point in polygon:
        curr_inside = inside(curr_point)
        
        if curr_inside:
            if not prev_inside:
                output.append(intersection(prev_point, curr_point))
            output.append(curr_point)
        elif prev_inside:
            output.append(intersection(prev_point, curr_point))
        
        prev_point = curr_point
        prev_inside = curr_inside
    
    return output


def polygon_intersection(poly1: List[List[float]], poly2: List[List[float]]) -> List[List[float]]:
    """Calculate polygon intersection using Sutherland-Hodgman algorithm."""
    output = list(poly1)
    
    for i in range(len(poly2)):
        if not output:
            break
        edge_start = poly2[i]
        edge_end = poly2[(i + 1) % len(poly2)]
        output = clip_polygon_component(output, edge_start, edge_end)
    
    return output


def calculate_iou(coords1: List[List[float]], coords2: List[List[float]]) -> float:
    """Calculate Intersection over Union (IoU) for two polygons."""
    area1 = polygon_area(coords1)
    area2 = polygon_area(coords2)
    
    if area1 == 0 or area2 == 0:
        return 0.0
    
    intersection_poly = polygon_intersection(coords1, coords2)
    
    if not intersection_poly or len(intersection_poly) < 3:
        return 0.0
    
    intersection_area = polygon_area(intersection_poly)
    union_area = area1 + area2 - intersection_area
    
    if union_area == 0:
        return 0.0
    
    return intersection_area / union_area


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


def calculate_composite_score(area_score: float, iou_score: float, topology_score: float,
                              w1: float = 0.2, w2: float = 0.5, w3: float = 0.3) -> float:
    """Calculate weighted composite score."""
    return w1 * area_score + w2 * iou_score + w3 * topology_score


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


# ============================================================================
# SVG GENERATION
# ============================================================================

def generate_svg(input_coords: List[List[float]], match_coords: List[List[float]],
                input_stats: Dict, match_stats: Dict, scores: Dict, match_info: Dict) -> str:
    """Generate SVG visualization with overlay and analysis panel."""
    
    all_coords = input_coords + match_coords
    all_x = [p[0] for p in all_coords]
    all_y = [p[1] for p in all_coords]
    
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    margin = 20
    width_geom = max_x - min_x
    height_geom = max_y - min_y
    scale = min(400 / max(width_geom, 1), 400 / max(height_geom, 1))
    
    def transform(coords):
        return [(margin + (x - min_x) * scale, margin + (y - min_y) * scale) for x, y in coords]
    
    input_transformed = transform(input_coords)
    match_transformed = transform(match_coords)
    
    input_path = "M " + " L ".join([f"{x},{y}" for x, y in input_transformed]) + " Z"
    match_path = "M " + " L ".join([f"{x},{y}" for x, y in match_transformed]) + " Z"
    
    svg_width = 800
    svg_height = 500
    
    svg = f'''<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="{svg_width}" height="{svg_height}" fill="#f8f9fa"/>
    
    <!-- Geometry Panel -->
    <rect x="10" y="10" width="450" height="480" fill="white" stroke="#dee2e6" stroke-width="2"/>
    
    <!-- Match boundary (red) -->
    <path d="{match_path}" fill="rgba(220, 53, 69, 0.1)" stroke="#dc3545" stroke-width="2"/>
    
    <!-- Input boundary (blue) -->
    <path d="{input_path}" fill="rgba(13, 110, 253, 0.1)" stroke="#0d6efd" stroke-width="2"/>
    
    <!-- Analysis Panel -->
    <rect x="470" y="10" width="320" height="480" fill="white" stroke="#dee2e6" stroke-width="2"/>
    
    <text x="490" y="40" font-family="Arial" font-size="18" font-weight="bold" fill="#212529">ANALYSIS RESULTS</text>
    
    <text x="490" y="75" font-family="Arial" font-size="14" font-weight="bold" fill="#495057">Best Match: {match_info['name']}</text>
    <text x="490" y="95" font-family="Arial" font-size="12" fill="#6c757d">ID: {match_info['id']}</text>
    
    <text x="490" y="130" font-family="Arial" font-size="14" font-weight="bold" fill="#198754">Composite Score: {scores['composite']:.3f}</text>
    
    <text x="490" y="160" font-family="Arial" font-size="12" fill="#495057">Area Score:</text>
    <text x="650" y="160" font-family="Arial" font-size="12" fill="#495057">{scores['area']:.3f}</text>
    
    <text x="490" y="180" font-family="Arial" font-size="12" fill="#495057">IoU Score:</text>
    <text x="650" y="180" font-family="Arial" font-size="12" fill="#495057">{scores['iou']:.3f}</text>
    
    <text x="490" y="200" font-family="Arial" font-size="12" fill="#495057">Topology Score:</text>
    <text x="650" y="200" font-family="Arial" font-size="12" fill="#495057">{scores['topology']:.3f}</text>
    
    <line x1="490" y1="220" x2="770" y2="220" stroke="#dee2e6" stroke-width="1"/>
    
    <text x="490" y="245" font-family="Arial" font-size="13" font-weight="bold" fill="#495057">Input Boundary Stats:</text>
    <text x="490" y="265" font-family="Arial" font-size="11" fill="#6c757d">Area: {input_stats['area']}</text>
    <text x="490" y="280" font-family="Arial" font-size="11" fill="#6c757d">Perimeter: {input_stats['perimeter']}</text>
    <text x="490" y="295" font-family="Arial" font-size="11" fill="#6c757d">Vertices: {input_stats['vertex_count']}</text>
    <text x="490" y="310" font-family="Arial" font-size="11" fill="#6c757d">Compactness: {input_stats['compactness']}</text>
    
    <line x1="490" y1="325" x2="770" y2="325" stroke="#dee2e6" stroke-width="1"/>
    
    <text x="490" y="350" font-family="Arial" font-size="13" font-weight="bold" fill="#495057">Match Boundary Stats:</text>
    <text x="490" y="370" font-family="Arial" font-size="11" fill="#6c757d">Area: {match_stats['area']}</text>
    <text x="490" y="385" font-family="Arial" font-size="11" fill="#6c757d">Perimeter: {match_stats['perimeter']}</text>
    <text x="490" y="400" font-family="Arial" font-size="11" fill="#6c757d">Vertices: {match_stats['vertex_count']}</text>
    <text x="490" y="415" font-family="Arial" font-size="11" fill="#6c757d">Compactness: {match_stats['compactness']}</text>
    
    <!-- Legend -->
    <line x1="30" y1="460" x2="60" y2="460" stroke="#0d6efd" stroke-width="2"/>
    <text x="70" y="465" font-family="Arial" font-size="11" fill="#495057">Input Boundary</text>
    
    <line x1="200" y1="460" x2="230" y2="460" stroke="#dc3545" stroke-width="2"/>
    <text x="240" y="465" font-family="Arial" font-size="11" fill="#495057">Match Boundary</text>
</svg>'''
    
    return svg


# ============================================================================
# MAIN TOOL FUNCTION
# ============================================================================

def boundary_analyzer(input_boundary: List[List[float]], 
                     dataset_path: str = None,
                     top_n_results: int = 5) -> Dict[str, Any]:
    """
    Analyze input boundary against dataset and return top matches with visualization.
    
    Args:
        input_boundary: Closed loop coordinates [[x1,y1], [x2,y2], ..., [xn,yn]]
        dataset_path: Path to boundary dataset JSON (optional)
        top_n_results: Number of top matches to return
    
    Returns:
        Dictionary with analysis results, scores, and SVG visualization
    """
    
    if dataset_path is None:
        dataset_path = Path(__file__).parent.parent.parent / "assets" / "boundary_dataset.json"
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
    
    for boundary in dataset['boundaries']:
        candidate_coords = boundary['coordinates']
        candidate_stats = compute_boundary_stats(candidate_coords)
        
        area_score = calculate_area_score(input_stats['area'], candidate_stats['area'])
        iou_score = calculate_iou(input_boundary, candidate_coords)
        topology_score = calculate_topology_score(input_stats, candidate_stats)
        composite_score = calculate_composite_score(area_score, iou_score, topology_score)
        
        results.append({
            "boundary_id": boundary['id'],
            "name": boundary['name'],
            "category": boundary.get('category', 'unknown'),
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
        svg_output = generate_svg(
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
