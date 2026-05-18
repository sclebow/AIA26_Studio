"""
SVG Utilities - Reusable SVG generation functions for visualization
"""

from typing import List, Dict, Tuple


def generate_boundary_comparison_svg(
    input_coords: List[List[float]], 
    match_coords: List[List[float]],
    input_stats: Dict, 
    match_stats: Dict, 
    scores: Dict, 
    match_info: Dict,
    svg_width: int = 800,
    svg_height: int = 500
) -> str:
    """
    Generate SVG visualization comparing two boundaries with analysis panel.
    
    Args:
        input_coords: Input boundary coordinates
        match_coords: Best match boundary coordinates
        input_stats: Statistics of input boundary (area, perimeter, vertex_count, compactness)
        match_stats: Statistics of matched boundary
        scores: Dictionary with composite, area, iou, topology scores
        match_info: Dictionary with id and name of matched boundary
        svg_width: Width of SVG canvas (default: 800)
        svg_height: Height of SVG canvas (default: 500)
    
    Returns:
        SVG string with visualization
    """
    # Get combined bounding box for scaling
    all_coords = input_coords + match_coords
    all_x = [p[0] for p in all_coords]
    all_y = [p[1] for p in all_coords]
    
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    # Calculate scaling and transformation
    margin = 20
    width_geom = max_x - min_x
    height_geom = max_y - min_y
    scale = min(400 / max(width_geom, 1), 400 / max(height_geom, 1))
    
    def transform(coords):
        return [(margin + (x - min_x) * scale, margin + (y - min_y) * scale) for x, y in coords]
    
    input_transformed = transform(input_coords)
    match_transformed = transform(match_coords)
    
    # Create SVG paths
    input_path = "M " + " L ".join([f"{x},{y}" for x, y in input_transformed]) + " Z"
    match_path = "M " + " L ".join([f"{x},{y}" for x, y in match_transformed]) + " Z"
    
    # Generate SVG
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


def create_polygon_path(coords: List[Tuple[float, float]]) -> str:
    """
    Create SVG path string from polygon coordinates.
    
    Args:
        coords: List of (x, y) coordinate tuples
    
    Returns:
        SVG path string (e.g., "M 0,0 L 10,0 L 10,10 Z")
    """
    if not coords:
        return ""
    
    path = "M " + " L ".join([f"{x},{y}" for x, y in coords]) + " Z"
    return path


def transform_coords_to_viewport(
    coords: List[List[float]], 
    viewport_width: float, 
    viewport_height: float,
    margin: float = 20
) -> List[Tuple[float, float]]:
    """
    Transform polygon coordinates to fit within SVG viewport.
    
    Args:
        coords: Original polygon coordinates
        viewport_width: Width of viewport area
        viewport_height: Height of viewport area
        margin: Margin around the geometry (default: 20)
    
    Returns:
        Transformed coordinates as list of (x, y) tuples
    """
    if not coords:
        return []
    
    # Get bounding box
    all_x = [p[0] for p in coords]
    all_y = [p[1] for p in coords]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    # Calculate scale
    width_geom = max_x - min_x
    height_geom = max_y - min_y
    available_width = viewport_width - 2 * margin
    available_height = viewport_height - 2 * margin
    
    scale = min(
        available_width / max(width_geom, 1),
        available_height / max(height_geom, 1)
    )
    
    # Transform coordinates
    transformed = [
        (margin + (x - min_x) * scale, margin + (y - min_y) * scale) 
        for x, y in coords
    ]
    
    return transformed