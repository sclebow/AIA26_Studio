from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.decision_engine import _infer_requested_building_type
from agent.mcp_client import build_default_local_tool_client
from agent.tools.direction_to_site_centroid import direction_to_site_centroid
from agent.tools.generate_building_boundary import generate_building_boundary
from agent.tools.modify_building_boundary import modify_building_boundary


class BoundaryToolTests(unittest.TestCase):
    def test_generate_building_boundary_supports_requested_shape_family(self) -> None:
        supported_shapes = ["I", "L", "T", "Y", "H", "X", "O"]

        for building_type in supported_shapes:
            with self.subTest(building_type=building_type):
                result = generate_building_boundary(
                    area=900.0,
                    building_type=building_type,
                    rotation_degrees=20.0,
                    is_mirrored=True,
                    mirror_axis="x",
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["data"]["shape_type"], building_type)
                self.assertAlmostEqual(result["data"]["boundary_area_sqm"], 900.0, places=5)
                self.assertGreater(len(result["data"]["boundary"]), 4)

    def test_modify_building_boundary_flags_site_intersection(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [120.0, 0.0, 0.0],
            [120.0, 120.0, 0.0],
            [0.0, 120.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        prototype = generate_building_boundary(area=1200.0, building_type="Y")

        inside = modify_building_boundary(
            geometry_id=prototype["data"]["geometry_id"],
            boundary=prototype["data"]["boundary"],
            target_centroid_xy=[60.0, 60.0],
            site_boundary=site_boundary,
        )
        outside = modify_building_boundary(
            geometry_id=prototype["data"]["geometry_id"],
            boundary=prototype["data"]["boundary"],
            target_centroid_xy=[116.0, 116.0],
            orientation_degrees=30.0,
            site_boundary=site_boundary,
        )

        self.assertTrue(inside["data"]["fits_within_site_boundary"])
        self.assertFalse(outside["data"]["fits_within_site_boundary"])
        self.assertIn("transformed_building_leaves_site", outside["data"]["violations"])

    def test_local_tool_client_exposes_modify_building_boundary(self) -> None:
        tool_names = {tool["name"] for tool in build_default_local_tool_client().list_tools()}
        self.assertIn("modify_building_boundary", tool_names)

    def test_local_tool_client_exposes_direction_to_site_centroid(self) -> None:
        tool_names = {tool["name"] for tool in build_default_local_tool_client().list_tools()}
        self.assertIn("direction_to_site_centroid", tool_names)

    def test_direction_to_site_centroid_points_toward_site(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 100.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        building_boundary = [
            [120.0, 40.0, 0.0],
            [140.0, 40.0, 0.0],
            [140.0, 60.0, 0.0],
            [120.0, 60.0, 0.0],
            [120.0, 40.0, 0.0],
        ]

        result = direction_to_site_centroid(
            building_boundary=building_boundary,
            site_boundary=site_boundary,
            step_distance=10.0,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["site_centroid"], [50.0, 50.0, 0.0])
        self.assertEqual(result["data"]["building_centroid"], [130.0, 50.0, 0.0])
        self.assertEqual(result["data"]["unit_direction"], [-1.0, 0.0])
        self.assertEqual(result["data"]["suggested_translate_by_xy"], [-10.0, 0.0])

    def test_requested_shape_inference_supports_new_shapes(self) -> None:
        self.assertEqual(_infer_requested_building_type("Generate a Y-shaped building."), "Y")
        self.assertEqual(_infer_requested_building_type("Create an H shaped building."), "H")
        self.assertEqual(_infer_requested_building_type("Use an X-shaped building form."), "X")
        self.assertEqual(_infer_requested_building_type("Create an O-shaped ring building."), "O")


if __name__ == "__main__":
    unittest.main()