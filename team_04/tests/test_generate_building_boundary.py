from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.tools.generate_building_boundary import (
    DEFAULT_SITE_COVERAGE_RATIO,
    TOOL_DEFINITION,
    generate_building_boundary,
    get_boundary_planning_defaults,
    get_default_tool_arguments,
)
from agent.tool_catalog import ToolCatalog


class GenerateBuildingBoundaryTests(unittest.TestCase):
    def test_tool_definition_exposes_required_area(self) -> None:
        self.assertEqual(TOOL_DEFINITION["name"], "generate_building_boundary")
        self.assertIn("area", TOOL_DEFINITION["inputSchema"]["required"])

    def test_default_tool_arguments_match_schema_defaults(self) -> None:
        defaults = get_default_tool_arguments()
        self.assertEqual(defaults["building_type"], "I")
        self.assertEqual(defaults["building_depth"], 15.0)
        self.assertEqual(defaults["shape_ratio"], 0.66)
        self.assertEqual(defaults["location_xy"], [0, 0])
        self.assertFalse(defaults["is_mirrored"])
        self.assertEqual(defaults["max_rotation_angle"], 180)
        self.assertEqual(defaults["max_rotation_step"], 4)
        self.assertEqual(defaults["rotation_step"], 0)

    def test_boundary_planning_defaults_expose_site_coverage_ratio(self) -> None:
        planning_defaults = get_boundary_planning_defaults()
        self.assertEqual(planning_defaults["default_site_coverage_ratio"], DEFAULT_SITE_COVERAGE_RATIO)
        self.assertEqual(planning_defaults["tool_argument_defaults"]["building_type"], "I")

    def test_tool_catalog_renders_parameter_descriptions_and_defaults(self) -> None:
        catalog = ToolCatalog.from_discovered_tools([TOOL_DEFINITION])
        rendered = catalog.render_for_action("generate_shape")
        self.assertIn("parameters:", rendered)
        self.assertIn("area (required)", rendered)
        self.assertIn("building_type (default=\"I\")", rendered)
        self.assertIn("45 degree rotation in one step", rendered)

    def test_i_shape_preserves_requested_area(self) -> None:
        result = generate_building_boundary(area=1200.0, building_type="I", building_depth=20.0)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["data"]["boundary_area_sqm"], 1200.0, places=6)
        self.assertEqual(result["data"]["shape_type"], "I")

    def test_l_shape_is_translated_and_closed(self) -> None:
        result = generate_building_boundary(
            area=900.0,
            building_type="L",
            building_depth=15.0,
            shape_ratio=0.6,
            location_xy=(100.0, 50.0),
        )
        boundary = result["data"]["boundary"]
        self.assertEqual(boundary[0], boundary[-1])
        centroid = result["data"]["centroid"]
        self.assertGreater(centroid[0], 80.0)
        self.assertGreater(centroid[1], 50.0)

    def test_t_shape_rotation_changes_bounding_box(self) -> None:
        unrotated = generate_building_boundary(area=1000.0, building_type="T", building_depth=20.0)
        rotated = generate_building_boundary(
            area=1000.0,
            building_type="T",
            building_depth=20.0,
            max_rotation_angle=180,
            max_rotation_step=4,
            rotation_step=1,
        )
        self.assertAlmostEqual(rotated["data"]["boundary_area_sqm"], unrotated["data"]["boundary_area_sqm"], places=6)
        self.assertNotEqual(rotated["data"]["bounding_box"], unrotated["data"]["bounding_box"])
        self.assertTrue(math.isclose(rotated["data"]["parameters"]["applied_rotation_angle"], 45.0, rel_tol=0, abs_tol=1e-9))

    def test_single_step_rotation_applies_requested_angle(self) -> None:
        rotated = generate_building_boundary(
            area=1000.0,
            building_type="I",
            building_depth=20.0,
            max_rotation_angle=45.0,
            max_rotation_step=1,
            rotation_step=1,
        )

        self.assertTrue(math.isclose(rotated["data"]["parameters"]["applied_rotation_angle"], 45.0, rel_tol=0, abs_tol=1e-9))

    def test_invalid_area_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_building_boundary(area=0)


if __name__ == "__main__":
    unittest.main()