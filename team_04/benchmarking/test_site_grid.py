"""Deterministic regressions for Phase 3 (site grid + side alignment).

No LLM and no MCP. These exercise the grid derivation from a chosen side, the
discrete aligned-orientation set, alignment scoring, the obtuse-corner wing
rotation, and the exhaustive grid-aligned placement optimizer (including the
use-driven "commercial hugs the frontage" rule and multi-building placement).
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.tools.building_shape_graph import build_shape_model
from agent.tools.site_model import build_site_model
from agent.tools.site_grid import (
    aligned_orientations,
    alignment_score,
    align_building_to_grid,
    corner_interior_angle,
    corner_wing_rotation,
    derive_site_grid,
    snap_to_grid,
)
from agent.tools.view_optimizer import (
    OBJECTIVE_REGISTRY,
    optimize_aligned_placement,
    place_buildings_aligned,
    sample_valid_placements,
)


def _rect(width, height, angle_deg, cx, cy):
    """A rectangle of (width × height) rotated by angle_deg about its centre."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(-width / 2, -height / 2), (width / 2, -height / 2),
           (width / 2, height / 2), (-width / 2, height / 2)]
    out = [[cx + x * ca - y * sa, cy + x * sa + y * ca, 0.0] for x, y in pts]
    return out + [out[0]]


# A large rectangle rotated 30° — the grid should align to that 30° long edge.
ROT_SITE = _rect(120.0, 80.0, 30.0, 60.0, 40.0)
# A splayed (non-orthogonal) pentagon for the obtuse-corner tests.
PENTAGON = [[0, 0, 0], [120, 10, 0], [140, 80, 0], [60, 120, 0], [-10, 70, 0], [0, 0, 0]]


def _ibuilding(area=300.0, depth=12.0):
    poly = build_shape_model(area=area, building_type="I", building_depth=depth, shape_ratio=0.5).polygon
    return [[round(float(x), 3), round(float(y), 3), 0.0] for x, y in poly.exterior.coords]


class GridDerivationTests(unittest.TestCase):
    def test_grid_aligns_to_longest_side(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        self.assertTrue(grid["available"])
        # Longest side of the 120×80 rectangle is the 120 m edge at 30°.
        self.assertAlmostEqual(grid["angle_deg"] % 180.0, 30.0, delta=0.5)
        self.assertGreater(grid["node_count"], 10)
        self.assertTrue(grid["grid_lines"])

    def test_explicit_alignment_side_changes_axis(self) -> None:
        model = build_site_model(ROT_SITE, {})
        g0 = derive_site_grid(model, spacing=10.0, alignment_side=0)
        g1 = derive_site_grid(model, spacing=10.0, alignment_side=1)
        # Adjacent rectangle sides are perpendicular → axes differ by ~90°.
        self.assertAlmostEqual(abs((g0["angle_deg"] - g1["angle_deg"]) % 180.0), 90.0, delta=1.0)

    def test_grid_nodes_lie_inside_the_site(self) -> None:
        from agent.tools.view_analysis import _coerce_polygon_2d
        from shapely.geometry import Point
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        site = _coerce_polygon_2d(ROT_SITE)
        for node in grid["grid_nodes"]:
            self.assertTrue(site.distance(Point(node[0], node[1])) <= 1e-6)

    def test_unavailable_without_boundary(self) -> None:
        self.assertFalse(derive_site_grid({"available": False}, spacing=10.0)["available"])


class OrientationAndAlignmentTests(unittest.TestCase):
    def test_aligned_orientations_parallel_and_perpendicular(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        angles = aligned_orientations(grid)
        self.assertEqual(len(angles), 2)
        self.assertAlmostEqual(abs((angles[0] - angles[1]) % 180.0), 90.0, delta=0.5)

    def test_offsets_extend_the_orientation_set(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        self.assertEqual(len(aligned_orientations(grid, offsets_deg=(5.0,))), 6)

    def test_alignment_score_high_when_aligned_low_when_skew(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        node = snap_to_grid([60, 40], grid)
        on_axis = align_building_to_grid(_ibuilding(), grid, node, aligned_orientations(grid)[0])
        off_axis = align_building_to_grid(_ibuilding(), grid, node, aligned_orientations(grid)[0] + 30)
        self.assertGreater(alignment_score(on_axis, grid), 0.98)
        self.assertLess(alignment_score(off_axis, grid), 0.5)

    def test_snap_returns_a_grid_node(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        self.assertIn(snap_to_grid([61, 41], grid), grid["grid_nodes"])


class ObtuseCornerTests(unittest.TestCase):
    def test_pentagon_corners_are_obtuse(self) -> None:
        model = build_site_model(PENTAGON, {})
        angles = [corner_interior_angle(model, i) for i in range(5)]
        self.assertTrue(all(a is not None and a > 90.0 for a in angles))

    def test_wing_rotation_follows_adjacent_side(self) -> None:
        model = build_site_model(PENTAGON, {})
        # Aligning to side 0 makes the free wing follow side 1; their shared
        # corner is obtuse, so the wing rotates by (interior_angle - 90) > 0.
        rot = corner_wing_rotation(model, 0)
        corner_angle = corner_interior_angle(model, 1)
        self.assertAlmostEqual(rot, corner_angle - 90.0, places=2)
        self.assertGreater(rot, 0.0)


class AlignedPlacementTests(unittest.TestCase):
    def test_sample_valid_placements_grid_mode_is_all_aligned(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=12.0)
        cands = sample_valid_placements(_ibuilding(), ROT_SITE, grid=grid)
        self.assertTrue(cands)
        for c in cands:
            self.assertTrue(c["aligned"])
            self.assertGreater(alignment_score(c["boundary"], grid), 0.98)

    def test_registry_exposes_new_objectives(self) -> None:
        self.assertIn("grid_alignment", OBJECTIVE_REGISTRY)
        self.assertIn("boundary_proximity", OBJECTIVE_REGISTRY)

    def test_optimize_aligned_placement_returns_aligned_options(self) -> None:
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=12.0)
        res = optimize_aligned_placement(
            base_boundary=_ibuilding(), site_boundary=ROT_SITE, grid=grid, use="residential",
        )
        self.assertTrue(res["optimized"])
        self.assertTrue(res["options"])
        for opt in res["options"]:
            self.assertGreater(opt["alignment_score"], 0.98)
            self.assertTrue(opt["fits_within_site"])

    def test_commercial_hugs_the_frontage_more_than_residential(self) -> None:
        from agent.tools.view_analysis import _coerce_polygon_2d
        site_poly = _coerce_polygon_2d(ROT_SITE)
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)

        def best_distance(use):
            res = optimize_aligned_placement(
                base_boundary=_ibuilding(area=240, depth=10), site_boundary=ROT_SITE,
                grid=grid, use=use,
            )
            best = res["options"][0]
            return site_poly.boundary.distance(_coerce_polygon_2d(best["boundary"])), res

        d_comm, res_comm = best_distance("commercial")
        d_resi, _ = best_distance("residential")
        # Commercial picks up a boundary_proximity objective…
        names = [c["name"] for c in res_comm["objective_configs"]]
        self.assertIn("boundary_proximity", names)
        # …so its chosen footprint sits closer to the site edge than residential's.
        self.assertLessEqual(d_comm, d_resi)

    def test_place_two_buildings_aligned_without_overlap(self) -> None:
        from agent.tools.view_analysis import _coerce_polygon_2d
        grid = derive_site_grid(build_site_model(ROT_SITE, {}), spacing=10.0)
        result = place_buildings_aligned(
            [{"base_boundary": _ibuilding(area=240, depth=10), "use": "commercial"},
             {"base_boundary": _ibuilding(area=240, depth=10), "use": "residential"}],
            ROT_SITE, grid, min_separation=6.0,
        )
        self.assertEqual(result["placed_count"], 2)
        b1, b2 = (_coerce_polygon_2d(b["boundary"]) for b in result["buildings"])
        self.assertLess(b1.intersection(b2).area, 1e-6)
        self.assertGreaterEqual(b1.distance(b2), 6.0 - 1e-6)
        for b in result["buildings"]:
            self.assertGreater(b["alignment_score"], 0.98)


if __name__ == "__main__":
    unittest.main()
