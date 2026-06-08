from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.tools.generate_building_boundary import generate_building_boundary
from agent.tools.multi_building_mock import (
    mock_check_requested_position,
    mock_import_building_boundary,
    mock_remaining_buildable_positions,
)


class MultiBuildingMockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = [
            [0.0, 0.0, 0.0],
            [120.0, 0.0, 0.0],
            [120.0, 80.0, 0.0],
            [0.0, 80.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        self.first_building = generate_building_boundary(
            area=600.0,
            building_type="I",
            building_depth=15.0,
            location_xy=(30.0, 40.0),
        )

    def test_remaining_positions_return_candidates_for_second_building(self) -> None:
        second_building = generate_building_boundary(
            area=450.0,
            building_type="L",
            building_depth=15.0,
        )
        result = mock_remaining_buildable_positions(
            site_boundary=self.site,
            placed_buildings=[self.first_building["data"]],
            candidate_building_boundary=second_building["data"]["boundary"],
            grid_size=10.0,
            max_positions=8,
        )

        self.assertTrue(result["success"])
        self.assertGreater(result["data"]["candidate_count"], 0)
        self.assertLessEqual(result["data"]["candidate_count"], 8)
        self.assertTrue(all(len(point) == 3 for point in result["data"]["candidate_positions"]))

    def test_requested_position_checker_rejects_overlap_and_suggests_alternatives(self) -> None:
        second_building = generate_building_boundary(
            area=450.0,
            building_type="L",
            building_depth=15.0,
        )
        candidate_result = mock_remaining_buildable_positions(
            site_boundary=self.site,
            placed_buildings=[self.first_building["data"]],
            candidate_building_boundary=second_building["data"]["boundary"],
            grid_size=10.0,
            max_positions=12,
        )
        result = mock_check_requested_position(
            site_boundary=self.site,
            placed_buildings=[self.first_building["data"]],
            proposed_boundary=second_building["data"]["boundary"],
            requested_point=[30.0, 40.0],
            candidate_positions=candidate_result["data"]["candidate_positions"],
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["is_feasible"])
        self.assertTrue(any("overlaps" in reason.lower() for reason in result["data"]["geometric_reasons"]))
        self.assertGreater(len(result["data"]["suggested_positions"]), 0)

    def test_requested_position_checker_accepts_clear_point(self) -> None:
        second_building = generate_building_boundary(
            area=300.0,
            building_type="I",
            building_depth=10.0,
        )
        result = mock_check_requested_position(
            site_boundary=self.site,
            placed_buildings=[self.first_building["data"]],
            proposed_boundary=second_building["data"]["boundary"],
            requested_point=[90.0, 20.0],
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["is_feasible"])
        self.assertIn("geometrically feasible", result["data"]["geometric_reasons"][0].lower())

    def test_import_mock_returns_rhino_style_payload(self) -> None:
        result = mock_import_building_boundary(
            geometry_id=self.first_building["data"]["geometry_id"],
            boundary=self.first_building["data"]["boundary"],
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["is_closed"])
        self.assertIn("mock_rhino_curve_", result["data"]["footprint_guid"])


if __name__ == "__main__":
    unittest.main()
