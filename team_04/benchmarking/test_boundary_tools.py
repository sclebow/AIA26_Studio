from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.decision_engine import _infer_requested_building_type
from agent.mcp_client import build_default_local_tool_client
from agent.tools.measure_boundary_proximity import measure_boundary_proximity
from agent.tools.site_boundary_graph import analyze_site_boundary
from agent.tools.direction_to_site_centroid import direction_to_site_centroid
from agent.tools.generate_building_boundary import generate_building_boundary
from agent.tools.modify_building_boundary import modify_building_boundary
from agent.tools.modify_building_wings import modify_building_wings


class BoundaryToolTests(unittest.TestCase):
    def test_generate_building_boundary_supports_requested_shape_family(self) -> None:
        supported_shapes = ["I", "L", "T", "U", "Y", "H", "X", "O"]

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

    def test_generate_building_boundary_returns_indexed_wings_for_u_shape(self) -> None:
        result = generate_building_boundary(area=1200.0, building_type="U")

        self.assertTrue(result["success"])
        self.assertEqual([wing["wing_index"] for wing in result["data"]["wings"]], [0, 1, 2])
        self.assertEqual(result["data"]["building_graph"]["adjacency_list"], [[1, 2], [0], [0]])
        self.assertEqual(result["data"]["wings"][1]["role"], "left_wing")
        centerline_graph = result["data"]["building_graph"]["centerline_graph"]
        self.assertEqual(centerline_graph["node_count"], 4)
        self.assertEqual(centerline_graph["edge_count"], 3)
        self.assertEqual(sorted(edge["wing_index"] for edge in centerline_graph["edges"]), [0, 1, 2])

    def test_generate_building_boundary_can_optimize_placement_inside_site(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [120.0, 0.0, 0.0],
            [120.0, 120.0, 0.0],
            [0.0, 120.0, 0.0],
            [0.0, 0.0, 0.0],
        ]

        result = generate_building_boundary(
            area=900.0,
            building_type="L",
            site_boundary=site_boundary,
            population_size=24,
            generation_count=20,
            random_seed=11,
        )

        self.assertTrue(result["data"]["site_fit_summary"]["fits_within_site_boundary"])
        self.assertTrue(result["data"]["placement_optimization"]["optimized"])
        self.assertGreaterEqual(result["data"]["placement_optimization"]["saved_option_count"], 1)
        self.assertEqual(result["data"]["option_catalog"]["selected_option_id"], result["data"]["placement_optimization"]["selected_option_id"])
        self.assertEqual(result["data"]["object_hierarchy"]["node_type"], "building")
        xs = [point[0] for point in result["data"]["boundary"][:-1]]
        ys = [point[1] for point in result["data"]["boundary"][:-1]]
        self.assertGreaterEqual(min(xs), 0.0)
        self.assertGreaterEqual(min(ys), 0.0)
        self.assertLessEqual(max(xs), 120.0)
        self.assertLessEqual(max(ys), 120.0)

    def test_generate_building_boundary_exposes_sidebar_ready_hierarchy(self) -> None:
        result = generate_building_boundary(area=900.0, building_type="U")

        self.assertTrue(result["success"])
        hierarchy = result["data"]["object_hierarchy"]
        self.assertEqual(hierarchy["node_type"], "building")
        child_types = [child["node_type"] for child in hierarchy["children"]]
        self.assertIn("option_collection", child_types)
        self.assertIn("wing_collection", child_types)
        self.assertIn("graph", child_types)
        option_catalog = result["data"]["option_catalog"]
        self.assertEqual(len(option_catalog["options"]), 1)
        self.assertEqual(option_catalog["options"][0]["status"], "selected")

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

    def test_analyze_site_boundary_returns_corner_and_side_graph(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 80.0, 0.0],
            [0.0, 80.0, 0.0],
            [0.0, 0.0, 0.0],
        ]

        result = analyze_site_boundary(site_boundary)

        self.assertTrue(result["success"])
        graph = result["data"]["site_boundary_graph"]
        self.assertEqual(graph["node_count"], 4)
        self.assertEqual(graph["edge_count"], 4)
        self.assertEqual(graph["edges"][0]["label"], "side_0")
        self.assertEqual(graph["nodes"][0]["label"], "corner_0")

    def test_measure_boundary_proximity_reports_nearest_side_and_corner(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 100.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        building_boundary = [
            [40.0, 15.0, 0.0],
            [60.0, 15.0, 0.0],
            [60.0, 35.0, 0.0],
            [40.0, 35.0, 0.0],
            [40.0, 15.0, 0.0],
        ]

        result = measure_boundary_proximity(
            building_boundary=building_boundary,
            site_boundary=site_boundary,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["nearest_site_edge"]["label"], "side_0")
        self.assertAlmostEqual(result["data"]["minimum_distance_m"], 15.0, places=5)
        self.assertIn("nearest_site_corner", result["data"])

    def test_modify_building_boundary_can_move_toward_named_site_side(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 100.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        building_boundary = [
            [40.0, 20.0, 0.0],
            [60.0, 20.0, 0.0],
            [60.0, 40.0, 0.0],
            [40.0, 40.0, 0.0],
            [40.0, 20.0, 0.0],
        ]

        result = modify_building_boundary(
            geometry_id="shape-001",
            boundary=building_boundary,
            site_boundary=site_boundary,
            move_toward_site_edge_label="side_0",
            target_edge_clearance=8.0,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["transform_parameters"]["selected_site_edge"]["label"], "side_0")
        self.assertAlmostEqual(
            result["data"]["boundary_proximity_before_move"]["selected_site_edge"]["minimum_distance_m"],
            20.0,
            places=5,
        )
        self.assertAlmostEqual(
            result["data"]["boundary_proximity"]["selected_site_edge"]["minimum_distance_m"],
            8.0,
            places=5,
        )

    def test_modify_building_boundary_can_align_largest_edge_to_diagonal_site_side(self) -> None:
        site_boundary = [
            [0.0, 0.0, 0.0],
            [90.0, 0.0, 0.0],
            [110.0, 35.0, 0.0],
            [76.0, 68.0, 0.0],
            [8.0, 58.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        building_boundary = [
            [20.0, 18.0, 0.0],
            [56.0, 18.0, 0.0],
            [56.0, 34.0, 0.0],
            [20.0, 34.0, 0.0],
            [20.0, 18.0, 0.0],
        ]

        result = modify_building_boundary(
            geometry_id="shape-001",
            boundary=building_boundary,
            site_boundary=site_boundary,
            move_toward_site_edge_label="side_1",
            align_largest_edge_to_site_edge=True,
            target_edge_clearance=6.0,
        )

        self.assertTrue(result["success"])
        transform = result["data"]["transform_parameters"]
        self.assertEqual(transform["selected_site_edge"]["label"], "side_1")
        self.assertGreater(abs(transform["alignment_rotation_degrees"]), 1.0)
        building_edge = transform["aligned_building_edge"]
        site_edge = transform["selected_site_edge"]
        building_angle = math.atan2(
            building_edge["end_point"][1] - building_edge["start_point"][1],
            building_edge["end_point"][0] - building_edge["start_point"][0],
        )
        site_graph = result["data"]["site_boundary_graph"]
        site_start = site_graph["nodes"][site_edge["from_node_index"]]["point"]
        site_end = site_graph["nodes"][site_edge["to_node_index"]]["point"]
        site_angle = math.atan2(site_end[1] - site_start[1], site_end[0] - site_start[0])
        angle_delta = abs(((building_angle - site_angle + math.pi / 2.0) % math.pi) - (math.pi / 2.0))
        self.assertLess(angle_delta, 1e-4)

    def test_modify_building_wings_can_thicken_one_wing_and_flip_the_other(self) -> None:
        prototype = generate_building_boundary(area=900.0, building_type="U")

        result = modify_building_wings(
            geometry_id=prototype["data"]["geometry_id"],
            shape_type=prototype["data"]["shape_type"],
            wings=prototype["data"]["wings"],
            building_graph=prototype["data"]["building_graph"],
            edits=[
                {"wing_index": 1, "thickness_scale": 1.3},
                {"wing_index": 2, "rotation_degrees": 180.0},
            ],
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["building_graph"]["adjacency_list"], [[1, 2], [0], [0]])
        self.assertGreater(
            result["data"]["wings"][1]["nominal_width_m"],
            prototype["data"]["wings"][1]["nominal_width_m"],
        )
        self.assertEqual(
            result["data"]["applied_edits"][1]["rotation_pivot"],
            prototype["data"]["building_graph"]["centerline_graph"]["nodes"][1]["point"],
        )
        self.assertLess(
            result["data"]["wings"][2]["centroid"][1],
            prototype["data"]["wings"][2]["centroid"][1],
        )
        self.assertEqual(result["data"]["building_graph"]["centerline_graph"]["edge_count"], 3)

    def test_local_tool_client_exposes_modify_building_boundary(self) -> None:
        tool_names = {tool["name"] for tool in build_default_local_tool_client().list_tools()}
        self.assertIn("modify_building_boundary", tool_names)

    def test_local_tool_client_exposes_modify_building_wings(self) -> None:
        tool_names = {tool["name"] for tool in build_default_local_tool_client().list_tools()}
        self.assertIn("modify_building_wings", tool_names)

    def test_local_tool_client_exposes_site_boundary_tools(self) -> None:
        tool_names = {tool["name"] for tool in build_default_local_tool_client().list_tools()}
        self.assertIn("analyze_site_boundary", tool_names)
        self.assertIn("measure_boundary_proximity", tool_names)

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
        self.assertEqual(_infer_requested_building_type("Create a U-shaped building around a courtyard."), "U")
        self.assertEqual(_infer_requested_building_type("Use an X-shaped building form."), "X")
        self.assertEqual(_infer_requested_building_type("Create an O-shaped ring building."), "O")


if __name__ == "__main__":
    unittest.main()