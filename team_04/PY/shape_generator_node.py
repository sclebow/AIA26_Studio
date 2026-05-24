"""
3D Shape Generator Node for Building Design

This module creates parametric 3D building shapes (L, I, H, T, U, rectangular, etc.)
and sends them to Grasshopper as BREP or curves.

Shape Types Supported:
- rectangle: Simple rectangular footprint
- L_shape: L-shaped building with two perpendicular wings
- I_shape: I-shaped building (two offset wings)
- H_shape: H-shaped building (three parallel sections)
- T_shape: T-shaped building
- U_shape: U-shaped building (courtyard on one side)
- Plus_shape: Plus/cross-shaped building
- Custom: User-defined polygon

Usage:
    from shape_generator_node import ShapeGenerator, create_shape_generator_node
    
    generator = ShapeGenerator()
    shape_data = generator.generate_l_shape(
        arm_a_length=30,
        arm_b_length=24,
        building_width=10,
        height=15,
        base_point=[0, 0, 0]
    )
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from typing import Any, Callable, Optional
from enum import Enum
import numpy as np
import random


class ShapeType(Enum):
    """Enumeration of supported shape types."""
    RECTANGLE = "rectangle"
    L_SHAPE = "l_shape"
    I_SHAPE = "i_shape"
    H_SHAPE = "h_shape"
    T_SHAPE = "t_shape"
    U_SHAPE = "u_shape"
    PLUS_SHAPE = "plus_shape"
    CUSTOM = "custom"


@dataclass
class Point3D:
    """3D point representation."""
    x: float
    y: float
    z: float

    def to_list(self) -> list[float]:
        """Convert to list format."""
        return [self.x, self.y, self.z]

    @staticmethod
    def from_list(lst: list[float]) -> Point3D:
        """Create Point3D from list."""
        return Point3D(lst[0], lst[1], lst[2])


@dataclass
class ShapeParameters:
    """Parameters for shape generation."""
    shape_type: str
    units: str = "meters"
    length: float = 30.0
    width: float = 10.0
    height: float = 15.0
    base_point: Optional[list[float]] = None
    rotation_angle: float = 0.0
    
    # L-shape specific
    arm_a_length: Optional[float] = None
    arm_b_length: Optional[float] = None
    wing_depth: Optional[float] = None
    courtyard_size: Optional[float] = None
    
    # I-shape specific
    segment_count: int = 2
    segment_spacing: float = 5.0
    
    # H-shape specific
    connector_width: float = 8.0
    
    # Custom shape
    vertices: Optional[list[list[float]]] = None

    def __post_init__(self):
        """Validate and set defaults."""
        if self.base_point is None:
            self.base_point = [0.0, 0.0, 0.0]


@dataclass
class ShapeGenes:
    """Normalized genes payload for shape generation."""

    shape_type: str
    length: float = 30.0
    width: float = 10.0
    height: float = 15.0
    rotation: float = 0.0
    base_point: Optional[list[float]] = None
    units: str = "meters"

    # Optional shape-specific genes
    arm_a_length: Optional[float] = None
    arm_b_length: Optional[float] = None
    wing_depth: Optional[float] = None
    courtyard_size: Optional[float] = None
    connector_width: Optional[float] = None
    segment_spacing: Optional[float] = None
    cap_width: Optional[float] = None
    cap_height: Optional[float] = None
    core_size: Optional[float] = None
    vertices: Optional[list[list[float]]] = None

    def __post_init__(self):
        if self.base_point is None:
            self.base_point = [0.0, 0.0, 0.0]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShapeGenes:
        """Create a ShapeGenes object from a raw dictionary."""
        payload = dict(data or {})

        raw_shape_type = payload.get("shape_type")
        if raw_shape_type is None:
            normalized_shape_type = "rectangle"
        else:
            normalized_shape_type = str(raw_shape_type).lower().strip().replace(" ", "_")
            if normalized_shape_type in {"", "none", "null", "nan", "undefined"}:
                normalized_shape_type = "rectangle"

        payload["shape_type"] = normalized_shape_type
        payload.setdefault("length", 30.0)
        payload.setdefault("width", 10.0)
        payload.setdefault("height", 15.0)
        payload.setdefault("rotation", payload.get("rotation_angle", 0.0))
        payload.setdefault("base_point", [0.0, 0.0, 0.0])
        payload.setdefault("units", "meters")
        return cls(
            shape_type=payload["shape_type"],
            length=payload.get("length", 30.0),
            width=payload.get("width", 10.0),
            height=payload.get("height", 15.0),
            rotation=payload.get("rotation", payload.get("rotation_angle", 0.0)),
            base_point=payload.get("base_point", [0.0, 0.0, 0.0]),
            units=payload.get("units", "meters"),
            arm_a_length=payload.get("arm_a_length"),
            arm_b_length=payload.get("arm_b_length"),
            wing_depth=payload.get("wing_depth"),
            courtyard_size=payload.get("courtyard_size"),
            connector_width=payload.get("connector_width"),
            segment_spacing=payload.get("segment_spacing"),
            cap_width=payload.get("cap_width"),
            cap_height=payload.get("cap_height"),
            core_size=payload.get("core_size"),
            vertices=payload.get("vertices"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert genes to a JSON-ready dictionary."""
        return {
            "shape_type": self.shape_type,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "rotation_angle": self.rotation,
            "base_point": self.base_point,
            "units": self.units,
            "arm_a_length": self.arm_a_length,
            "arm_b_length": self.arm_b_length,
            "wing_depth": self.wing_depth,
            "courtyard_size": self.courtyard_size,
            "connector_width": self.connector_width,
            "segment_spacing": self.segment_spacing,
            "cap_width": self.cap_width,
            "cap_height": self.cap_height,
            "core_size": self.core_size,
            "vertices": self.vertices,
        }


@dataclass
class ShapeOutput:
    """Output data for generated shape."""
    shape_id: str
    shape_type: str
    vertices_2d: list[list[float]]  # 2D footprint vertices
    vertices_3d: list[list[float]]  # 3D vertices for extrusion
    faces: list[list[int]]  # Face indices for BREP
    metadata: dict[str, Any]
    editable_parameters: dict[str, bool]
    grasshopper_ready: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "shape_id": self.shape_id,
            "shape_type": self.shape_type,
            "vertices_2d": self.vertices_2d,
            "vertices_3d": self.vertices_3d,
            "faces": self.faces,
            "metadata": self.metadata,
            "editable_parameters": self.editable_parameters,
            "grasshopper_ready": self.grasshopper_ready,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class ShapeGenerator:
    """
    Generator for parametric 3D building shapes.
    
    Handles creation of various building footprints and extrusion to 3D.
    Provides output compatible with Grasshopper/Rhino.
    """

    def __init__(self, shape_id_prefix: str = "BLDG"):
        """
        Initialize the shape generator.
        
        Args:
            shape_id_prefix: Prefix for generated shape IDs (default: "BLDG")
        """
        self.shape_id_prefix = shape_id_prefix
        self.shape_counter = 0

    def _normalize_shape_type(self, shape_type: Any) -> str:
        """Normalize a shape label into the internal naming convention."""
        if shape_type is None:
            return "rectangle"
        normalized = str(shape_type).lower().strip().replace(" ", "_")
        if normalized in {"", "none", "null", "nan", "undefined"}:
            return "rectangle"
        return normalized

    def build_gene_template(self, shape_type: Any, overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Build a default genes payload for a given shape type."""
        normalized_shape = self._normalize_shape_type(shape_type)

        template_map = {
            ShapeType.RECTANGLE.value: {
                "shape_type": ShapeType.RECTANGLE.value,
                "length": 30.0,
                "width": 10.0,
                "height": 15.0,
                "rotation": 0.0,
            },
            ShapeType.L_SHAPE.value: {
                "shape_type": ShapeType.L_SHAPE.value,
                "length": 32.0,
                "width": 24.0,
                "height": 15.0,
                "rotation": 0.0,
                "arm_a_length": 32.0,
                "arm_b_length": 24.0,
                "wing_depth": 10.0,
            },
            ShapeType.I_SHAPE.value: {
                "shape_type": ShapeType.I_SHAPE.value,
                "length": 45.0,
                "width": 10.0,
                "height": 15.0,
                "rotation": 0.0,
                "segment_spacing": 8.0,
            },
            ShapeType.H_SHAPE.value: {
                "shape_type": ShapeType.H_SHAPE.value,
                "length": 40.0,
                "width": 30.0,
                "height": 15.0,
                "rotation": 0.0,
                "wing_depth": 10.0,
                "connector_width": 8.0,
            },
            ShapeType.T_SHAPE.value: {
                "shape_type": ShapeType.T_SHAPE.value,
                "length": 24.0,
                "width": 10.0,
                "height": 15.0,
                "rotation": 0.0,
                "cap_width": 30.0,
                "cap_height": 12.0,
            },
            ShapeType.U_SHAPE.value: {
                "shape_type": ShapeType.U_SHAPE.value,
                "length": 40.0,
                "width": 30.0,
                "height": 15.0,
                "rotation": 0.0,
                "wing_depth": 10.0,
                "courtyard_size": 12.0,
            },
            ShapeType.PLUS_SHAPE.value: {
                "shape_type": ShapeType.PLUS_SHAPE.value,
                "length": 30.0,
                "width": 10.0,
                "height": 15.0,
                "rotation": 0.0,
                "core_size": 10.0,
            },
            ShapeType.CUSTOM.value: {
                "shape_type": ShapeType.CUSTOM.value,
                "height": 15.0,
                "rotation": 0.0,
            },
        }

        template = dict(template_map.get(normalized_shape, template_map[ShapeType.RECTANGLE.value]))
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    template[key] = value

        template["shape_type"] = normalized_shape
        template.setdefault("rotation_angle", template.get("rotation", 0.0))
        template.setdefault("base_point", [0.0, 0.0, 0.0])
        template.setdefault("units", "meters")
        return template

    def genes_to_parameters(self, genes: dict[str, Any] | ShapeGenes) -> ShapeParameters:
        """Map genes into ShapeParameters for the existing generator path."""
        genes_obj = genes if isinstance(genes, ShapeGenes) else ShapeGenes.from_dict(genes)
        template = self.build_gene_template(genes_obj.shape_type, genes_obj.to_dict())

        return ShapeParameters(
            shape_type=template.get("shape_type", "rectangle"),
            units=template.get("units", "meters"),
            length=template.get("length", 30.0),
            width=template.get("width", 10.0),
            height=template.get("height", 15.0),
            base_point=template.get("base_point", [0.0, 0.0, 0.0]),
            rotation_angle=template.get("rotation", template.get("rotation_angle", 0.0)),
            arm_a_length=template.get("arm_a_length"),
            arm_b_length=template.get("arm_b_length"),
            wing_depth=template.get("wing_depth"),
            courtyard_size=template.get("courtyard_size"),
            connector_width=template.get("connector_width", 8.0),
            vertices=template.get("vertices"),
        )

    def generate_from_genes(self, genes: dict[str, Any] | ShapeGenes) -> ShapeOutput:
        """Generate a shape from a genes payload."""
        return self.generate_shape(self.genes_to_parameters(genes))

    def generate_random_genes(
        self,
        shape_type: Optional[str] = None,
        locked_shape_type: Optional[str] = None,
        overrides: Optional[dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
    ) -> dict[str, Any]:
        """Generate a randomized genes payload, optionally locked to one typology."""
        rng = rng or random.Random()
        selected_shape = self._normalize_shape_type(locked_shape_type or shape_type or rng.choice([
            ShapeType.RECTANGLE.value,
            ShapeType.L_SHAPE.value,
            ShapeType.I_SHAPE.value,
            ShapeType.H_SHAPE.value,
            ShapeType.T_SHAPE.value,
            ShapeType.U_SHAPE.value,
            ShapeType.PLUS_SHAPE.value,
        ]))

        genes = self.build_gene_template(selected_shape, overrides)
        genes["shape_type"] = selected_shape

        genes["length"] = round(rng.uniform(24.0, 80.0), 2)
        genes["width"] = round(rng.uniform(8.0, 30.0), 2)
        genes["height"] = round(rng.uniform(9.0, 30.0), 2)
        genes["rotation"] = round(rng.uniform(0.0, 360.0), 2)
        genes["rotation_angle"] = genes["rotation"]
        genes["base_point"] = [round(rng.uniform(-10.0, 10.0), 2), round(rng.uniform(-10.0, 10.0), 2), 0.0]

        if selected_shape == ShapeType.RECTANGLE.value:
            pass
        elif selected_shape == ShapeType.L_SHAPE.value:
            genes["arm_a_length"] = genes["length"]
            genes["arm_b_length"] = max(genes["width"], round(rng.uniform(12.0, genes["length"]), 2))
            genes["wing_depth"] = round(rng.uniform(4.0, max(6.0, min(genes["length"], genes["width"]))), 2)
        elif selected_shape == ShapeType.I_SHAPE.value:
            genes["segment_spacing"] = round(rng.uniform(4.0, 14.0), 2)
        elif selected_shape == ShapeType.H_SHAPE.value:
            genes["wing_depth"] = round(rng.uniform(4.0, max(6.0, genes["width"])), 2)
            genes["connector_width"] = round(rng.uniform(4.0, max(6.0, genes["width"])), 2)
        elif selected_shape == ShapeType.T_SHAPE.value:
            genes["cap_width"] = round(rng.uniform(18.0, 60.0), 2)
            genes["cap_height"] = round(rng.uniform(6.0, 20.0), 2)
        elif selected_shape == ShapeType.U_SHAPE.value:
            genes["wing_depth"] = round(rng.uniform(4.0, max(6.0, genes["width"])), 2)
            genes["courtyard_size"] = round(rng.uniform(8.0, max(10.0, genes["length"] - 2 * genes["wing_depth"])), 2)
        elif selected_shape == ShapeType.PLUS_SHAPE.value:
            genes["core_size"] = round(rng.uniform(6.0, max(8.0, genes["width"])), 2)

        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    if key == "shape_type" and locked_shape_type:
                        continue
                    genes[key] = value

        return genes

    def mutate_genes(
        self,
        genes: dict[str, Any],
        locked_shape_type: Optional[str] = None,
        mutation_rate: float = 0.25,
        rng: Optional[random.Random] = None,
    ) -> dict[str, Any]:
        """Mutate an existing genes payload without changing the locked typology."""
        rng = rng or random.Random()
        candidate = dict(genes or {})
        shape_type = self._normalize_shape_type(locked_shape_type or candidate.get("shape_type", "rectangle"))
        candidate["shape_type"] = shape_type

        def maybe_mutate(key: str, spread: float, lower: float, upper: float) -> None:
            if rng.random() <= mutation_rate and key in candidate:
                base_value = float(candidate.get(key, lower))
                delta = base_value * spread * rng.uniform(-1.0, 1.0)
                candidate[key] = round(max(lower, min(upper, base_value + delta)), 2)

        maybe_mutate("length", 0.25, 12.0, 120.0)
        maybe_mutate("width", 0.25, 6.0, 60.0)
        maybe_mutate("height", 0.20, 3.0, 60.0)
        maybe_mutate("rotation", 0.5, 0.0, 360.0)
        candidate["rotation_angle"] = candidate.get("rotation", 0.0)

        if shape_type == ShapeType.L_SHAPE.value:
            maybe_mutate("arm_a_length", 0.25, 12.0, 120.0)
            maybe_mutate("arm_b_length", 0.25, 12.0, 120.0)
            maybe_mutate("wing_depth", 0.25, 4.0, 40.0)
        elif shape_type == ShapeType.I_SHAPE.value:
            maybe_mutate("segment_spacing", 0.30, 4.0, 20.0)
        elif shape_type == ShapeType.H_SHAPE.value:
            maybe_mutate("wing_depth", 0.25, 4.0, 40.0)
            maybe_mutate("connector_width", 0.25, 3.0, 30.0)
        elif shape_type == ShapeType.T_SHAPE.value:
            maybe_mutate("cap_width", 0.25, 12.0, 120.0)
            maybe_mutate("cap_height", 0.25, 4.0, 60.0)
        elif shape_type == ShapeType.U_SHAPE.value:
            maybe_mutate("wing_depth", 0.25, 4.0, 40.0)
            maybe_mutate("courtyard_size", 0.25, 8.0, 90.0)
        elif shape_type == ShapeType.PLUS_SHAPE.value:
            maybe_mutate("core_size", 0.25, 4.0, 40.0)

        return candidate

    def _next_shape_id(self) -> str:
        """Generate next unique shape ID."""
        self.shape_counter += 1
        return f"{self.shape_id_prefix}_{self.shape_counter:04d}"

    def _clamp_dimension(self, value: float, minimum: float, maximum: float | None = None) -> float:
        """Clamp a dimension to a safe minimum (and optional maximum)."""
        try:
            result = float(value)
        except Exception:
            result = float(minimum)
        result = max(result, float(minimum))
        if maximum is not None:
            result = min(result, float(maximum))
        return result

    def _rotate_point(
        self,
        point: list[float],
        center: list[float],
        angle_degrees: float,
    ) -> list[float]:
        """
        Rotate a 2D point around a center by angle (in degrees).
        
        Args:
            point: [x, y] point to rotate
            center: [cx, cy] rotation center
            angle_degrees: Rotation angle in degrees
            
        Returns:
            Rotated [x, y] point
        """
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Translate to origin
        x = point[0] - center[0]
        y = point[1] - center[1]

        # Rotate
        x_rot = x * cos_a - y * sin_a
        y_rot = x * sin_a + y * cos_a

        # Translate back
        return [x_rot + center[0], y_rot + center[1]]

    def _extrude_to_3d(
        self,
        vertices_2d: list[list[float]],
        height: float,
        base_z: float = 0.0,
    ) -> tuple[list[list[float]], list[list[int]]]:
        """
        Extrude 2D vertices to 3D shape (create bottom and top faces).
        
        Args:
            vertices_2d: List of 2D [x, y] vertices
            height: Extrusion height
            base_z: Z coordinate for base
            
        Returns:
            Tuple of (vertices_3d, faces)
        """
        def _signed_area(points_2d):
            area = 0.0
            count = len(points_2d)
            for i in range(count):
                x1, y1 = points_2d[i][0], points_2d[i][1]
                x2, y2 = points_2d[(i + 1) % count][0], points_2d[(i + 1) % count][1]
                area += (x1 * y2) - (x2 * y1)
            return area / 2.0

        def _cross(ax, ay, bx, by, cx, cy):
            return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

        def _point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
            c1 = _cross(ax, ay, bx, by, px, py)
            c2 = _cross(bx, by, cx, cy, px, py)
            c3 = _cross(cx, cy, ax, ay, px, py)
            has_neg = (c1 < 0) or (c2 < 0) or (c3 < 0)
            has_pos = (c1 > 0) or (c2 > 0) or (c3 > 0)
            return not (has_neg and has_pos)

        def _triangulate_polygon(points_2d):
            count = len(points_2d)
            if count < 3:
                return []

            signed_area = _signed_area(points_2d)
            working = list(points_2d)
            if signed_area < 0:
                working.reverse()

            remaining = list(range(len(working)))
            triangles = []

            guard = 0
            while len(remaining) > 3 and guard < 1000:
                guard += 1
                ear_found = False

                for index in range(len(remaining)):
                    prev_index = remaining[(index - 1) % len(remaining)]
                    curr_index = remaining[index]
                    next_index = remaining[(index + 1) % len(remaining)]

                    ax, ay = working[prev_index][0], working[prev_index][1]
                    bx, by = working[curr_index][0], working[curr_index][1]
                    cx, cy = working[next_index][0], working[next_index][1]

                    if _cross(ax, ay, bx, by, cx, cy) <= 0:
                        continue

                    is_ear = True
                    for other_index in remaining:
                        if other_index in (prev_index, curr_index, next_index):
                            continue
                        px, py = working[other_index][0], working[other_index][1]
                        if _point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
                            is_ear = False
                            break

                    if is_ear:
                        triangles.append([prev_index, curr_index, next_index])
                        del remaining[index]
                        ear_found = True
                        break

                if not ear_found:
                    triangles = []
                    break

            if len(remaining) == 3:
                triangles.append([remaining[0], remaining[1], remaining[2]])

            if not triangles:
                for index in range(1, len(working) - 1):
                    triangles.append([0, index, index + 1])

            return working, triangles

        working_vertices_2d, bottom_triangles = _triangulate_polygon(vertices_2d)
        n = len(working_vertices_2d)
        vertices_3d = []

        for vertex in working_vertices_2d:
            vertices_3d.append([vertex[0], vertex[1], base_z])
        for vertex in working_vertices_2d:
            vertices_3d.append([vertex[0], vertex[1], base_z + height])

        faces = []
        # Bottom cap triangles (use triangle order)
        for triangle in bottom_triangles:
            faces.append([triangle[0], triangle[1], triangle[2]])

        for i in range(n):
            next_i = (i + 1) % n
            faces.append([i, next_i, next_i + n, i + n])

        # Top cap triangles (reverse winding to point outward/up)
        for triangle in bottom_triangles:
            faces.append([triangle[0] + n, triangle[2] + n, triangle[1] + n])

        return vertices_3d, faces

    def _extrude_rectangles_to_3d(
        self,
        rectangles_2d: list[list[list[float]]],
        height: float,
        base_z: float = 0.0,
    ) -> tuple[list[list[float]], list[list[int]]]:
        vertices_3d: list[list[float]] = []
        faces: list[list[int]] = []

        for footprint in rectangles_2d:
            box_vertices, box_faces = self._extrude_to_3d(footprint, height, base_z)
            offset = len(vertices_3d)
            vertices_3d.extend(box_vertices)
            for face in box_faces:
                faces.append([index + offset for index in face])

        return vertices_3d, faces

    def generate_rectangle(
        self,
        length: float = 30.0,
        width: float = 10.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate a simple rectangular building footprint.
        
        Args:
            length: Length of rectangle (X direction)
            width: Width of rectangle (Y direction)
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with geometry data
        """
        length = self._clamp_dimension(length, 10.0)
        width = self._clamp_dimension(width, 10.0)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        base_xy = [base_point[0], base_point[1]]
        center = [base_point[0] + length / 2, base_point[1] + width / 2]

        # Create rectangle vertices (counterclockwise)
        vertices_2d = [
            [base_point[0], base_point[1]],
            [base_point[0] + length, base_point[1]],
            [base_point[0] + length, base_point[1] + width],
            [base_point[0], base_point[1] + width],
        ]

        # Apply rotation if needed
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        # Extrude to 3D
        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, base_point[2])

        # Calculate metadata
        area = length * width
        perimeter = 2 * (length + width)

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.RECTANGLE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "length": length,
                "width": width,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), base_point[2]],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), base_point[2] + height],
                },
            },
            editable_parameters={
                "length": True,
                "width": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_l_shape(
        self,
        arm_a_length: float = 32.0,
        arm_b_length: float = 24.0,
        building_width: float = 10.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate an L-shaped building footprint.
        
        Args:
            arm_a_length: Length of first arm
            arm_b_length: Length of second arm
            building_width: Width of both arms
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with L-shaped geometry
        """
        arm_a_length = self._clamp_dimension(arm_a_length, 12.0)
        arm_b_length = self._clamp_dimension(arm_b_length, 12.0)
        building_width = self._clamp_dimension(building_width, 4.0, min(arm_a_length, arm_b_length) - 0.5)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        # Build a single L-shaped footprint and extrude it once
        vertices_2d = [
            [x, y],
            [x + arm_a_length, y],
            [x + arm_a_length, y + building_width],
            [x + building_width, y + building_width],
            [x + building_width, y + arm_b_length],
            [x, y + arm_b_length],
        ]
        center = [x + arm_a_length / 2, y + arm_b_length / 2]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, z)

        # Calculate metadata
        area = (arm_a_length * building_width) + (
            arm_b_length * building_width - building_width * building_width
        )
        perimeter = 2 * (
            arm_a_length + arm_b_length - building_width
        ) + 2 * building_width

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.L_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "arm_a_length": arm_a_length,
                "arm_b_length": arm_b_length,
                "building_width": building_width,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "arm_a_length": True,
                "arm_b_length": True,
                "building_width": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_i_shape(
        self,
        total_length: float = 45.0,
        segment_width: float = 10.0,
        segment_spacing: float = 8.0,
        height: float = 15.0,
        connector: bool = True,
        connector_width: Optional[float] = None,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate an I-shaped building footprint (two parallel segments).
        
        Args:
            total_length: Total length of the I-shape
            segment_width: Width of each segment
            segment_spacing: Space between segments
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with I-shaped geometry
        """
        total_length = self._clamp_dimension(total_length, 20.0)
        segment_width = self._clamp_dimension(segment_width, 4.0)
        segment_spacing = self._clamp_dimension(segment_spacing, 4.0)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        total_width = 2 * segment_width + segment_spacing
        center = [x + total_length / 2, y + total_width / 2]

        y2 = y + segment_width + segment_spacing
        lower_rect = [
            [x, y],
            [x + total_length, y],
            [x + total_length, y + segment_width],
            [x, y + segment_width],
        ]
        upper_rect = [
            [x, y2],
            [x + total_length, y2],
            [x + total_length, y2 + segment_width],
            [x, y2 + segment_width],
        ]

        rectangles = [lower_rect, upper_rect]

        cw = 0.0

        # Optionally add a central connector (vertical bar) between the two segments
        if connector:
            if connector_width is None:
                cw = max(1.0, segment_width / 2.0)
            else:
                cw = float(connector_width)
            cw = min(cw, total_length * 0.8)
            cx = x + total_length / 2.0
            conn_bottom = y + segment_width
            conn_top = y + segment_width + segment_spacing
            connector_rect = [
                [cx - cw / 2.0, conn_bottom],
                [cx + cw / 2.0, conn_bottom],
                [cx + cw / 2.0, conn_top],
                [cx - cw / 2.0, conn_top],
            ]
            rectangles.insert(1, connector_rect)

        if rotation_angle != 0:
            rectangles = [[self._rotate_point(v, center, rotation_angle) for v in rect] for rect in rectangles]

        vertices_3d, faces = self._extrude_rectangles_to_3d(rectangles, height, z)

        area = 2 * total_length * segment_width + (cw * segment_spacing if connector else 0)
        perimeter = 4 * total_length + 4 * segment_width + 2 * segment_spacing + (2 * cw if connector else 0)

        # Extract 2D vertices for reference (bounding outline)
        vertices_2d = [
            [x, y],
            [x + total_length, y],
            [x + total_length, y + segment_width],
            [x, y + segment_width],
            [x, y + segment_width + segment_spacing],
            [x + total_length, y + segment_width + segment_spacing],
            [x + total_length, y + total_width],
            [x, y + total_width],
        ]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.I_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "total_length": total_length,
                "segment_width": segment_width,
                "segment_spacing": segment_spacing,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "total_length": True,
                "segment_width": True,
                "segment_spacing": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_h_shape(
        self,
        vertical_length: float = 40.0,
        horizontal_width: float = 30.0,
        wing_depth: float = 10.0,
        connector_width: float = 8.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate an H-shaped building footprint.
        
        Args:
            vertical_length: Height of vertical sections
            horizontal_width: Width of horizontal span
            wing_depth: Depth of each wing
            connector_width: Width of central connector
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with H-shaped geometry
        """
        vertical_length = self._clamp_dimension(vertical_length, 20.0)
        wing_depth = self._clamp_dimension(wing_depth, 4.0)
        connector_width = self._clamp_dimension(connector_width, 4.0, vertical_length - 0.5)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        # Coordinates for H-shape rectangles
        left_x = x
        middle_x = x + wing_depth
        right_x = x + wing_depth + connector_width
        far_right_x = x + 2 * wing_depth + connector_width

        connector_top = y + (vertical_length - connector_width) / 2
        connector_bottom = connector_top + connector_width

        vertices_2d = [
            [x, y],
            [x + wing_depth, y],
            [x + wing_depth, connector_top],
            [right_x, connector_top],
            [right_x, y],
            [far_right_x, y],
            [far_right_x, y + vertical_length],
            [right_x, y + vertical_length],
            [right_x, connector_bottom],
            [x + wing_depth, connector_bottom],
            [x + wing_depth, y + vertical_length],
            [x, y + vertical_length],
        ]

        center = [x + (2 * wing_depth + connector_width) / 2, y + vertical_length / 2]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, z)

        area = 2 * wing_depth * vertical_length + connector_width * connector_width
        perimeter = 4 * vertical_length + 4 * wing_depth + 2 * connector_width

        # Extract 2D vertices for reference
        vertices_2d = [
            [left_x, y],
            [middle_x, y],
            [middle_x, y + vertical_length],
            [left_x, y + vertical_length],
            [middle_x, connector_top],
            [right_x, connector_top],
            [right_x, connector_bottom],
            [middle_x, connector_bottom],
            [right_x, y],
            [far_right_x, y],
            [far_right_x, y + vertical_length],
            [right_x, y + vertical_length],
        ]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.H_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "vertical_length": vertical_length,
                "wing_depth": wing_depth,
                "connector_width": connector_width,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "vertical_length": True,
                "wing_depth": True,
                "connector_width": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_t_shape(
        self,
        stem_length: float = 24.0,
        stem_width: float = 10.0,
        cap_width: float = 30.0,
        cap_height: float = 12.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate a T-shaped building footprint.
        
        Args:
            stem_length: Length of the stem
            stem_width: Width of the stem
            cap_width: Width of the top cap
            cap_height: Height of the top cap
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with T-shaped geometry
        """
        stem_length = self._clamp_dimension(stem_length, 20.0)
        stem_width = self._clamp_dimension(stem_width, 6.0)
        cap_width = self._clamp_dimension(cap_width, 20.0)
        cap_height = self._clamp_dimension(cap_height, 6.0)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        stem_start_x = x + (cap_width - stem_width) / 2
        cap_start_y = y + stem_length
        vertices_2d = [
            [stem_start_x, y],
            [stem_start_x + stem_width, y],
            [stem_start_x + stem_width, cap_start_y],
            [x + cap_width, cap_start_y],
            [x + cap_width, cap_start_y + cap_height],
            [x, cap_start_y + cap_height],
            [x, cap_start_y],
            [stem_start_x, cap_start_y],
        ]

        center = [x + cap_width / 2, y + stem_length / 2]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, z)

        area = stem_length * stem_width + cap_width * cap_height
        perimeter = 2 * (stem_length + stem_width + cap_width + cap_height) - 2 * min(
            stem_width, cap_width
        )

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.T_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "stem_length": stem_length,
                "stem_width": stem_width,
                "cap_width": cap_width,
                "cap_height": cap_height,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "stem_length": True,
                "stem_width": True,
                "cap_width": True,
                "cap_height": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_u_shape(
        self,
        outer_length: float = 40.0,
        outer_width: float = 30.0,
        wing_depth: float = 10.0,
        courtyard_width: float = 12.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate a U-shaped building footprint (with courtyard).
        
        Args:
            outer_length: Outer length
            outer_width: Outer width
            wing_depth: Depth of each wing
            courtyard_width: Width of central courtyard opening
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with U-shaped geometry
        """
        outer_length = self._clamp_dimension(outer_length, 20.0)
        outer_width = self._clamp_dimension(outer_width, 20.0)
        wing_depth = self._clamp_dimension(wing_depth, 4.0, outer_width - 0.5)
        courtyard_width = self._clamp_dimension(
            courtyard_width,
            8.0,
            max(8.0, outer_length - 2.0 * wing_depth),
        )
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        leg_width = (outer_length - courtyard_width) / 2.0
        opening_depth = wing_depth

        vertices_2d = [
            [x, y],
            [x + outer_length, y],
            [x + outer_length, y + outer_width],
            [x + outer_length - leg_width, y + outer_width],
            [x + outer_length - leg_width, y + opening_depth],
            [x + leg_width, y + opening_depth],
            [x + leg_width, y + outer_width],
            [x, y + outer_width],
        ]

        center = [x + outer_length / 2, y + outer_width / 2]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, z)

        area = outer_length * outer_width - courtyard_width * wing_depth
        perimeter = (
            2 * outer_length
            + 4 * outer_width
            - 2 * wing_depth
        )

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.U_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "outer_length": outer_length,
                "outer_width": outer_width,
                "wing_depth": wing_depth,
                "courtyard_width": courtyard_width,
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "outer_length": True,
                "outer_width": True,
                "wing_depth": True,
                "courtyard_width": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_plus_shape(
        self,
        arm_length: float = 30.0,
        arm_width: float = 10.0,
        core_size: float = 10.0,
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate a Plus/Cross-shaped building footprint.
        
        Args:
            arm_length: Length of each arm from center
            arm_width: Width of each arm
            core_size: Size of central square
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with Plus-shaped geometry
        """
        arm_length = self._clamp_dimension(arm_length, 12.0)
        arm_width = self._clamp_dimension(arm_width, 6.0)
        core_size = self._clamp_dimension(core_size, 6.0, arm_width)
        height = self._clamp_dimension(height, 3.0)

        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        x, y, z = base_point[0], base_point[1], base_point[2]

        # Center of the plus
        center_x = x + arm_length + arm_width / 2
        center_y = y + arm_length + arm_width / 2

        hw = arm_width / 2  # Half width
        cw = core_size / 2  # Half core

        # Build a single Plus-shaped footprint and extrude it once
        vertices_2d = [
            [x, center_y - hw],
            [center_x - cw, center_y - hw],
            [center_x - cw, y],
            [center_x + cw, y],
            [center_x + cw, center_y - hw],
            [x + 2 * arm_length + arm_width, center_y - hw],
            [x + 2 * arm_length + arm_width, center_y + hw],
            [center_x + cw, center_y + hw],
            [center_x + cw, y + 2 * arm_length + arm_width],
            [center_x - cw, y + 2 * arm_length + arm_width],
            [center_x - cw, center_y + hw],
            [x, center_y + hw],
        ]

        rotation_center = [center_x, center_y]
        if rotation_angle != 0:
            vertices_2d = [
                self._rotate_point(v, rotation_center, rotation_angle)
                for v in vertices_2d
            ]

        vertices_3d, faces = self._extrude_to_3d(vertices_2d, height, z)

        # Calculate area (4 arms + core)
        area = 4 * arm_length * arm_width + core_size * core_size

        # Extract 2D vertices for reference
        vertices_2d = [
            [x, center_y - hw],
            [center_x - cw, center_y - hw],
            [center_x - cw, center_y + hw],
            [x, center_y + hw],
            [center_x - hw, y],
            [center_x + hw, y],
            [center_x + hw, center_y - cw],
            [center_x - cw, center_y - cw],
            [center_x + cw, center_y - hw],
            [x + 2 * arm_length + arm_width, center_y - hw],
            [x + 2 * arm_length + arm_width, center_y + hw],
            [center_x + cw, center_y + hw],
            [center_x + cw, center_y + cw],
            [center_x + hw, center_y + cw],
            [center_x + hw, y + 2 * arm_length + arm_width],
            [center_x - hw, y + 2 * arm_length + arm_width],
            [center_x - hw, center_y + cw],
            [center_x - cw, center_y + cw],
            [center_x - cw, center_y + hw],
            [x, center_y + hw],
        ]
        if rotation_angle != 0:
            rotation_center = [center_x, center_y]
            vertices_2d = [
                self._rotate_point(v, rotation_center, rotation_angle)
                for v in vertices_2d
            ]

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.PLUS_SHAPE.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "arm_length": arm_length,
                "arm_width": arm_width,
                "core_size": core_size,
                "height": height,
                "area": area,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), z],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), z + height],
                },
            },
            editable_parameters={
                "arm_length": True,
                "arm_width": True,
                "core_size": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_custom_polygon(
        self,
        vertices_2d: list[list[float]],
        height: float = 15.0,
        base_point: Optional[list[float]] = None,
        rotation_angle: float = 0.0,
    ) -> ShapeOutput:
        """
        Generate a custom polygon-shaped building footprint.
        
        Args:
            vertices_2d: List of 2D [x, y] vertices defining the polygon
            height: Height for 3D extrusion
            base_point: [x, y, z] base point
            rotation_angle: Rotation in degrees
            
        Returns:
            ShapeOutput with custom geometry
        """
        if base_point is None:
            base_point = [0.0, 0.0, 0.0]

        if rotation_angle != 0:
            # Calculate centroid for rotation center
            center_x = sum(v[0] for v in vertices_2d) / len(vertices_2d)
            center_y = sum(v[1] for v in vertices_2d) / len(vertices_2d)
            center = [center_x, center_y]

            vertices_2d = [
                self._rotate_point(v, center, rotation_angle)
                for v in vertices_2d
            ]

        # Extrude to 3D
        vertices_3d, faces = self._extrude_to_3d(
            vertices_2d, height, base_point[2]
        )

        # Calculate area using shoelace formula
        area = 0.0
        n = len(vertices_2d)
        for i in range(n):
            j = (i + 1) % n
            area += vertices_2d[i][0] * vertices_2d[j][1]
            area -= vertices_2d[j][0] * vertices_2d[i][1]
        area = abs(area) / 2.0

        # Calculate perimeter
        perimeter = 0.0
        for i in range(n):
            j = (i + 1) % n
            dx = vertices_2d[j][0] - vertices_2d[i][0]
            dy = vertices_2d[j][1] - vertices_2d[i][1]
            perimeter += math.sqrt(dx * dx + dy * dy)

        output = ShapeOutput(
            shape_id=self._next_shape_id(),
            shape_type=ShapeType.CUSTOM.value,
            vertices_2d=vertices_2d,
            vertices_3d=vertices_3d,
            faces=faces,
            metadata={
                "num_vertices": len(vertices_2d),
                "height": height,
                "area": area,
                "perimeter": perimeter,
                "volume": area * height,
                "base_point": base_point,
                "rotation_angle": rotation_angle,
                "bounding_box": {
                    "min": [min(v[0] for v in vertices_2d), min(v[1] for v in vertices_2d), base_point[2]],
                    "max": [max(v[0] for v in vertices_2d), max(v[1] for v in vertices_2d), base_point[2] + height],
                },
            },
            editable_parameters={
                "vertices": True,
                "height": True,
                "rotation_angle": True,
                "base_point": True,
            },
        )

        return output

    def generate_shape(self, params: ShapeParameters) -> ShapeOutput:
        """
        Generate shape based on parameters.
        
        Args:
            params: ShapeParameters object with shape specifications
            
        Returns:
            ShapeOutput with generated geometry
            
        Raises:
            ValueError: If shape_type is not supported
        """
        shape_type = params.shape_type.lower().replace(" ", "_")

        if shape_type in [ShapeType.RECTANGLE.value.lower(), "rectangular"]:
            return self.generate_rectangle(
                length=params.length,
                width=params.width,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.L_SHAPE.value.lower():
            return self.generate_l_shape(
                arm_a_length=params.arm_a_length or params.length,
                arm_b_length=params.arm_b_length or params.width,
                building_width=params.wing_depth or 10.0,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.I_SHAPE.value.lower():
            return self.generate_i_shape(
                total_length=params.length,
                segment_width=params.width,
                segment_spacing=params.wing_depth or 5.0,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.H_SHAPE.value.lower():
            return self.generate_h_shape(
                vertical_length=params.length,
                wing_depth=params.wing_depth or params.width,
                connector_width=params.connector_width,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.T_SHAPE.value.lower():
            return self.generate_t_shape(
                stem_length=params.length or 24.0,
                stem_width=params.width or 10.0,
                cap_width=params.wing_depth or 30.0,
                cap_height=params.height or 12.0,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.U_SHAPE.value.lower():
            return self.generate_u_shape(
                outer_length=params.length,
                outer_width=params.width,
                wing_depth=params.wing_depth or 10.0,
                courtyard_width=params.courtyard_size or 12.0,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.PLUS_SHAPE.value.lower():
            return self.generate_plus_shape(
                arm_length=params.length or 30.0,
                arm_width=params.wing_depth or params.width,
                core_size=params.width or 10.0,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        elif shape_type == ShapeType.CUSTOM.value.lower():
            if params.vertices is None:
                raise ValueError("Custom shape requires 'vertices' parameter")
            return self.generate_custom_polygon(
                vertices_2d=params.vertices,
                height=params.height,
                base_point=params.base_point,
                rotation_angle=params.rotation_angle,
            )
        else:
            raise ValueError(f"Unsupported shape type: {params.shape_type}")


def create_shape_generator_node(
    dbg: Callable[[str], None],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """
    Create a shape generator node for LangGraph workflow.
    
    This node generates 3D building shapes based on user specifications
    and adds them to the design state.
    
    Args:
        dbg: Debug logging callback function
        
    Returns:
        Node function that processes shape generation
    """
    generator = ShapeGenerator()

    def shape_generator_node(state: dict[str, Any], /) -> dict[str, Any]:
        """
        Process shape generation in the workflow.
        
        Expects state to contain:
        - shape_request: Dict with shape specifications
        
        Updates state with:
        - generated_shape: ShapeOutput with geometry
        - shape_json: JSON representation of shape
        """
        dbg("[workflow][shape_gen] Enter node")

        shape_request = state.get("shape_request", {})
        if not shape_request:
            dbg("[workflow][shape_gen] No shape request found")
            return state

        try:
            # Parse shape request into parameters
            params = ShapeParameters(
                shape_type=shape_request.get("shape_type", "rectangle"),
                units=shape_request.get("units", "meters"),
                length=shape_request.get("length", 30.0),
                width=shape_request.get("width", 10.0),
                height=shape_request.get("height", 15.0),
                base_point=shape_request.get("base_point", [0.0, 0.0, 0.0]),
                rotation_angle=shape_request.get("rotation_angle", 0.0),
                arm_a_length=shape_request.get("arm_a_length"),
                arm_b_length=shape_request.get("arm_b_length"),
                wing_depth=shape_request.get("wing_depth"),
                courtyard_size=shape_request.get("courtyard_size"),
                connector_width=shape_request.get("connector_width", 8.0),
                vertices=shape_request.get("vertices"),
            )

            # Generate shape
            shape_output = generator.generate_shape(params)

            dbg(
                f"[workflow][shape_gen] Generated {shape_output.shape_type} "
                f"(ID: {shape_output.shape_id}) | Area: {shape_output.metadata['area']:.2f}m²"
            )

            # Update state
            state["generated_shape"] = shape_output
            state["shape_json"] = shape_output.to_json()

            # Add to design state
            if "design_state" not in state:
                state["design_state"] = {}

            if "generated_shapes" not in state["design_state"]:
                state["design_state"]["generated_shapes"] = []

            state["design_state"]["generated_shapes"].append(shape_output.to_dict())

        except Exception as e:
            dbg(f"[workflow][shape_gen] Error: {str(e)}")
            state["shape_generation_error"] = str(e)

        return state

    return shape_generator_node
