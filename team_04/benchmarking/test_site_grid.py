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

from agent.tools.building_shape_graph import SUPPORTED_WINGED_BUILDING_TYPES, build_shape_model
from agent.tools.site_model import build_site_model
from agent.tools.site_grid import (
    aligned_orientations,
    alignment_score,
    align_building_to_grid,
    align_building_to_local_grid,
    corner_interior_angle,
    corner_wing_rotation,
    derive_adaptive_site_grid,
    derive_site_grid,
    local_grid_orientation,
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


def _longest_edge_deg(boundary):
    """Direction (deg, mod 180) of a footprint's longest edge."""
    pts = boundary[:-1] if boundary[0] == boundary[-1] else boundary
    best_ang, best_len = 0.0, -1.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L > best_len:
            best_len, best_ang = L, math.degrees(math.atan2(dy, dx))
    return best_ang % 180.0


class AdaptiveGridTests(unittest.TestCase):
    def test_rectangle_grid_does_not_warp(self) -> None:
        # Four straight, parallel chains -> Coons patch reduces to a uniform grid.
        grid = derive_adaptive_site_grid(build_site_model(ROT_SITE, {}), spacing=12.0)
        self.assertTrue(grid["available"])
        self.assertEqual(grid["corner_indices"], [0, 1, 2, 3])
        self.assertLess(grid["angle_range_deg"], 1.0)

    def test_splayed_site_grid_warps_to_match_complexity(self) -> None:
        # On a non-orthogonal pentagon the local axis angle must vary across the
        # field — this is "the angle changes to match the site's complexity".
        grid = derive_adaptive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0)
        self.assertTrue(grid["available"])
        self.assertGreater(grid["angle_range_deg"], 8.0)
        self.assertEqual(grid["node_count"], len(grid["node_orientations"]))

    def test_local_orientation_changes_across_the_site(self) -> None:
        grid = derive_adaptive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0)
        nodes = grid["grid_nodes"]
        left = min(nodes, key=lambda p: p[0])
        right = max(nodes, key=lambda p: p[0])
        a_left = local_grid_orientation(grid, left)
        a_right = local_grid_orientation(grid, right)
        diff = abs(((a_left - a_right + 180) % 360) - 180)
        self.assertGreater(diff, 5.0)

    def test_adaptive_nodes_lie_inside_the_site(self) -> None:
        from agent.tools.view_analysis import _coerce_polygon_2d
        from shapely.geometry import Point
        grid = derive_adaptive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0)
        site = _coerce_polygon_2d(PENTAGON)
        for node in grid["grid_nodes"]:
            self.assertLessEqual(site.distance(Point(node[0], node[1])), 1e-6)

    def test_building_orients_to_local_grid_direction(self) -> None:
        grid = derive_adaptive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0)
        node = grid["grid_nodes"][len(grid["grid_nodes"]) // 2]
        placed = align_building_to_local_grid(_ibuilding(), grid, node)
        local = local_grid_orientation(grid, node) % 180.0
        dev = abs(((_longest_edge_deg(placed) - local + 90) % 180) - 90)
        self.assertLess(dev, 1.0)  # long edge follows the local grid direction

    def test_adaptive_grid_unavailable_for_triangle(self) -> None:
        tri = [[0, 0, 0], [100, 0, 0], [50, 90, 0], [0, 0, 0]]
        self.assertFalse(derive_adaptive_site_grid(build_site_model(tri, {}))["available"])


#: The full footprint library: winged (I/L/T/U/H) + legacy templates (Y/X/O).
ALL_SHAPES = tuple(SUPPORTED_WINGED_BUILDING_TYPES) + ("Y", "X", "O")


def _shape_boundary(building_type, area=600.0, depth=13.0, ratio=0.5):
    poly = build_shape_model(area=area, building_type=building_type,
                             building_depth=depth, shape_ratio=ratio).polygon
    return [[round(float(x), 3), round(float(y), 3), 0.0] for x, y in poly.exterior.coords]


def _polygon_area(boundary):
    from agent.tools.view_analysis import _coerce_polygon_2d
    return _coerce_polygon_2d(boundary).area


class GridSideAnchorTests(unittest.TestCase):
    def test_grid_bottom_chain_is_always_the_chosen_side(self) -> None:
        # The B (bottom) chain must equal the chosen side for EVERY side, even when
        # that side's vertices are not the sharpest corners — so the grid (and any
        # building on it) follows the chosen side instead of drifting to a corner.
        model = build_site_model(PENTAGON, {})
        n = len(PENTAGON) - 1
        for side in range(n):
            grid = derive_adaptive_site_grid(model, spacing=12.0, alignment_side=side)
            c0, c1 = grid["corner_indices"][0], grid["corner_indices"][1]
            self.assertEqual((c0, c1), (side, (side + 1) % n),
                             f"side {side}: bottom chain {(c0, c1)} is not the chosen side")


class RigidLocalPlacementTests(unittest.TestCase):
    """Buildings stay RIGID and only rotate to the local grid direction.

    A real building has straight walls, so we rotate the whole footprint to the
    local grid direction rather than deforming it through the warped grid (which
    over-warped complex shapes like X/Y and blew up their area). These tests pin
    that the placement preserves each shape exactly while still following the grid.
    """

    def _grid(self, site=PENTAGON):
        return derive_adaptive_site_grid(build_site_model(site, {}), spacing=12.0)

    def test_library_covers_eight_shapes(self) -> None:
        self.assertEqual(set(ALL_SHAPES), {"I", "L", "T", "U", "H", "Y", "X", "O"})

    def test_every_shape_builds_closed(self) -> None:
        for s in ALL_SHAPES:
            b = _shape_boundary(s)
            self.assertGreaterEqual(len(b), 4, f"{s} failed to build")
            self.assertEqual(b[0], b[-1], f"{s} not a closed ring")

    def test_rigid_placement_preserves_every_shape_exactly(self) -> None:
        # area AND vertex count identical to the base — zero deformation.
        grid = self._grid()
        node = grid["grid_nodes"][len(grid["grid_nodes"]) // 2]
        for s in ALL_SHAPES:
            base = _shape_boundary(s)
            placed = align_building_to_local_grid(base, grid, node)
            self.assertEqual(len(placed), len(base), f"{s} changed vertex count")
            self.assertAlmostEqual(_polygon_area(placed), _polygon_area(base), places=3,
                                   msg=f"{s} area changed under placement")

    def test_long_edge_follows_local_grid_direction(self) -> None:
        grid = self._grid()
        node = grid["grid_nodes"][len(grid["grid_nodes"]) // 2]
        placed = align_building_to_local_grid(_ibuilding(), grid, node)
        local = local_grid_orientation(grid, node) % 180.0
        dev = abs(((_longest_edge_deg(placed) - local + 90) % 180) - 90)
        self.assertLess(dev, 1.0)

    def test_every_shape_places_rigidly_inside_the_site(self) -> None:
        from agent.tools.view_analysis import _coerce_polygon_2d
        grid = self._grid()
        site = _coerce_polygon_2d(PENTAGON)
        cx = sum(p[0] for p in PENTAGON[:-1]) / (len(PENTAGON) - 1)
        cy = sum(p[1] for p in PENTAGON[:-1]) / (len(PENTAGON) - 1)
        for s in ALL_SHAPES:
            base = _shape_boundary(s, area=400.0)
            placed = None
            for nd in sorted(grid["grid_nodes"], key=lambda n: math.dist(n, [cx, cy])):
                cand = align_building_to_local_grid(base, grid, nd)
                if site.contains(_coerce_polygon_2d(cand)):
                    placed = cand
                    break
            self.assertIsNotNone(placed, f"{s} could not be placed rigidly inside the site")
            self.assertEqual(len(placed), len(base), f"{s} deformed during placement")

    def test_building_reorients_to_follow_the_chosen_side(self) -> None:
        # Re-key the grid to each side; the SAME rigid building re-orients to that
        # side (shape preserved) and its orientation genuinely changes.
        base = _ibuilding()
        angles = []
        for side in range(len(PENTAGON) - 1):
            grid = derive_adaptive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0, alignment_side=side)
            node = grid["grid_nodes"][len(grid["grid_nodes"]) // 2]
            placed = align_building_to_local_grid(base, grid, node)
            self.assertAlmostEqual(_polygon_area(placed), _polygon_area(base), places=3)
            angles.append(_longest_edge_deg(placed))
        self.assertGreater(max(angles) - min(angles), 10.0)

    def test_every_shape_grid_aligns_via_optimizer_path(self) -> None:
        # The rigid grid-aligned candidate path (sample_valid_placements) is
        # shape-agnostic too and keeps shapes rigid.
        grid = derive_site_grid(build_site_model(PENTAGON, {}), spacing=12.0)
        for s in ALL_SHAPES:
            cands = sample_valid_placements(_shape_boundary(s, area=400.0), PENTAGON, grid=grid)
            self.assertTrue(cands, f"{s} produced no grid-aligned candidates")
            self.assertTrue(all(c["aligned"] for c in cands), f"{s} candidates not all aligned")


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
