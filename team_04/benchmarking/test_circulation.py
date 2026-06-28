"""Regression tests for Phase 5 — Circulation, Access, Fire Safety.

Covers agent/tools/circulation.py:
  - propose_site_entries        (entry-on-main-road invariant)
  - route_internal_circulation  (corridors reach every target, stay in site)
  - building_entrance_orientation (entrance faces access, private faces away)
  - check_fire_access           (distance math, constraint sign convention)

Deterministic, no LLM, no MCP, no network calls.
Run with:  python -m pytest team_04/benchmarking/test_circulation.py -v
       or: python -m unittest team_04.benchmarking.test_circulation
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

# Allow import without installing the package
_TEAM_ROOT = Path(__file__).resolve().parent.parent
if str(_TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEAM_ROOT))

from agent.tools.circulation import (
    DEFAULT_PATH_WIDTH_M,
    MAX_FIRE_DISTANCE_M,
    MIN_PATH_WIDTH_M,
    building_entrance_orientation,
    check_fire_access,
    propose_site_entries,
    route_internal_circulation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RECT_SITE = [           # 90 m × 60 m rectangle
    [0.0,  0.0, 0.0],
    [90.0, 0.0, 0.0],
    [90.0, 60.0, 0.0],
    [0.0,  60.0, 0.0],
    [0.0,  0.0, 0.0],
]

# South side (index 0) = main road; north side (index 2) = secondary road.
_SITE_MODEL = {
    "boundary": _RECT_SITE,
    "sides": [
        {"side_index": 0, "start": [0.0, 0.0],  "end": [90.0, 0.0],
         "adjacent_road": {"name": "Main St", "hierarchy": "main", "width_m": 20.0}},
        {"side_index": 1, "start": [90.0, 0.0], "end": [90.0, 60.0],
         "adjacent_road": None},
        {"side_index": 2, "start": [90.0, 60.0], "end": [0.0, 60.0],
         "adjacent_road": {"name": "Back Ln", "hierarchy": "secondary", "width_m": 8.0}},
        {"side_index": 3, "start": [0.0, 60.0], "end": [0.0, 0.0],
         "adjacent_road": None},
    ],
    "roads": {"main_road_side_index": 0, "main_road": {"name": "Main St", "width_m": 20.0}},
}

# A site with no road information at all.
_SITE_MODEL_NO_ROAD = {"boundary": _RECT_SITE}

_BUILDING_A = {
    "building_id": "A",
    "boundary": [[10.0, 25.0, 0.0], [35.0, 25.0, 0.0], [35.0, 45.0, 0.0], [10.0, 45.0, 0.0]],
    "storeys": 5,
}
_BUILDING_B = {
    "building_id": "B",
    "boundary": [[55.0, 25.0, 0.0], [80.0, 25.0, 0.0], [80.0, 45.0, 0.0], [55.0, 45.0, 0.0]],
    "storeys": 4,
}

# A parking zone hugging the main-road (south) frontage.
_PARKING = {
    "zones": [
        {"zone_id": "parking_zone_0",
         "boundary": [[0.3, 0.3, 0.0], [89.7, 0.3, 0.0], [89.7, 11.0, 0.0], [0.3, 11.0, 0.0]],
         "stalls_allocated": 18, "side_index": 0, "is_main_road_side": True},
    ],
}


def _poly(boundary) -> Polygon:
    return Polygon([(p[0], p[1]) for p in boundary])


# ---------------------------------------------------------------------------
# Class 1 — propose_site_entries
# ---------------------------------------------------------------------------

class TestProposeSiteEntries(unittest.TestCase):

    def test_public_entry_on_main_road_side(self):
        result = propose_site_entries(_SITE_MODEL)
        public = [e for e in result["entries"] if e["type"] == "public"]
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["side_index"], 0)
        self.assertEqual(public[0]["road_name"], "Main St")

    def test_public_entry_lies_on_boundary(self):
        result = propose_site_entries(_SITE_MODEL)
        pub = next(e for e in result["entries"] if e["type"] == "public")
        pt = Point(pub["point"][0], pub["point"][1])
        # Within a hair of the site boundary
        self.assertLess(_poly(_RECT_SITE).exterior.distance(pt), 1e-6)

    def test_public_entry_midpoint_of_main_road(self):
        result = propose_site_entries(_SITE_MODEL)
        pub = next(e for e in result["entries"] if e["type"] == "public")
        self.assertAlmostEqual(pub["point"][0], 45.0, places=3)
        self.assertAlmostEqual(pub["point"][1], 0.0, places=3)

    def test_inward_normal_points_into_site(self):
        result = propose_site_entries(_SITE_MODEL)
        pub = next(e for e in result["entries"] if e["type"] == "public")
        nx, ny = pub["inward_normal"]
        px, py = pub["point"][0], pub["point"][1]
        probe = Point(px + nx * 1.0, py + ny * 1.0)
        self.assertTrue(_poly(_RECT_SITE).contains(probe))

    def test_private_entry_on_secondary_side(self):
        result = propose_site_entries(_SITE_MODEL)
        private = [e for e in result["entries"] if e["type"] == "private"]
        self.assertEqual(len(private), 1)
        self.assertEqual(private[0]["side_index"], 2)

    def test_no_road_falls_back_to_longest_side_with_ambiguity(self):
        result = propose_site_entries(_SITE_MODEL_NO_ROAD)
        self.assertEqual(result["ambiguity"], "no_road_data")
        pub = next(e for e in result["entries"] if e["type"] == "public")
        # Longest side of a 90×60 rect is a 90 m side (index 0 or 2)
        self.assertIn(pub["side_index"], (0, 2))

    def test_no_road_has_no_private_entry(self):
        result = propose_site_entries(_SITE_MODEL_NO_ROAD)
        self.assertEqual(result["private_count"], 0)

    def test_empty_boundary_returns_no_entries(self):
        result = propose_site_entries({"boundary": []})
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["ambiguity"], "no_site_boundary")


# ---------------------------------------------------------------------------
# Class 2 — route_internal_circulation
# ---------------------------------------------------------------------------

class TestRouteInternalCirculation(unittest.TestCase):

    def setUp(self):
        self.entries = propose_site_entries(_SITE_MODEL)

    def test_one_path_per_target(self):
        circ = route_internal_circulation(
            _SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING
        )
        # 2 buildings + 1 parking zone = 3 corridors
        self.assertEqual(len(circ["paths"]), 3)
        serves = {p["serves"] for p in circ["paths"]}
        self.assertIn("A", serves)
        self.assertIn("B", serves)
        self.assertIn("parking_zone_0", serves)

    def test_paths_reach_their_buildings(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], None)
        for p in circ["paths"]:
            if p["target_type"] != "building":
                continue
            bld = _BUILDING_A if p["serves"] == "A" else _BUILDING_B
            line = LineString([(pt[0], pt[1]) for pt in p["polyline"]])
            self.assertLess(line.distance(_poly(bld["boundary"])), 1e-6)

    def test_corridors_have_positive_length(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], None)
        for p in circ["paths"]:
            self.assertGreater(p["length_m"], 0.0)

    def test_total_length_is_sum_of_paths(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING)
        self.assertAlmostEqual(
            circ["total_length_m"], sum(p["length_m"] for p in circ["paths"]), places=1
        )

    def test_corridor_polygons_inside_site(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING)
        site = _poly(_RECT_SITE)
        for p in circ["paths"]:
            if not p["buffered_boundary"]:
                continue
            poly = _poly(p["buffered_boundary"])
            outside = poly.difference(site).area
            self.assertLess(outside, 0.5, f"{p['path_id']} extends {outside:.2f} m² outside site")

    def test_default_width_used(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A], None)
        self.assertAlmostEqual(circ["path_width_m"], DEFAULT_PATH_WIDTH_M)

    def test_custom_width(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A], None, path_width_m=8.0)
        self.assertAlmostEqual(circ["path_width_m"], 8.0)
        self.assertAlmostEqual(circ["paths"][0]["width_m"], 8.0)

    def test_no_entries_skips(self):
        circ = route_internal_circulation(_SITE_MODEL, [], [_BUILDING_A], None)
        self.assertEqual(circ["paths"], [])

    def test_no_targets_skips(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [], None)
        self.assertEqual(circ["paths"], [])

    def test_occupied_polygons_match_paths(self):
        circ = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING)
        with_poly = [p for p in circ["paths"] if p["buffered_boundary"]]
        self.assertEqual(len(circ["occupied_polygons"]), len(with_poly))

    def test_accepts_raw_zone_list(self):
        circ = route_internal_circulation(
            _SITE_MODEL, self.entries, [_BUILDING_A], _PARKING["zones"]
        )
        serves = {p["serves"] for p in circ["paths"]}
        self.assertIn("parking_zone_0", serves)


# ---------------------------------------------------------------------------
# Class 3 — building_entrance_orientation
# ---------------------------------------------------------------------------

class TestBuildingEntranceOrientation(unittest.TestCase):

    def setUp(self):
        self.entries = propose_site_entries(_SITE_MODEL)
        self.circ = route_internal_circulation(
            _SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING
        )

    def test_one_result_per_building(self):
        orient = building_entrance_orientation([_BUILDING_A, _BUILDING_B], self.entries, self.circ)
        self.assertEqual(len(orient["buildings"]), 2)

    def test_entrance_point_on_building_boundary(self):
        orient = building_entrance_orientation([_BUILDING_A], self.entries, self.circ)
        b = orient["buildings"][0]
        pt = Point(b["entrance_point"][0], b["entrance_point"][1])
        self.assertLess(_poly(_BUILDING_A["boundary"]).exterior.distance(pt), 1e-6)

    def test_entrance_and_private_are_opposite(self):
        orient = building_entrance_orientation([_BUILDING_A], self.entries, self.circ)
        b = orient["buildings"][0]
        ed = b["entrance_direction"]
        pd = b["private_direction"]
        self.assertAlmostEqual(ed[0], -pd[0], places=5)
        self.assertAlmostEqual(ed[1], -pd[1], places=5)

    def test_direction_is_unit_vector(self):
        orient = building_entrance_orientation([_BUILDING_A], self.entries, self.circ)
        ed = orient["buildings"][0]["entrance_direction"]
        self.assertAlmostEqual(math.hypot(ed[0], ed[1]), 1.0, places=4)

    def test_faces_circulation_when_paths_present(self):
        orient = building_entrance_orientation([_BUILDING_A], self.entries, self.circ)
        self.assertEqual(orient["buildings"][0]["faces"], "circulation")

    def test_faces_public_entry_without_circulation(self):
        orient = building_entrance_orientation([_BUILDING_A], self.entries, None)
        self.assertEqual(orient["buildings"][0]["faces"], "public_entry")


# ---------------------------------------------------------------------------
# Class 4 — check_fire_access
# ---------------------------------------------------------------------------

class TestCheckFireAccess(unittest.TestCase):

    def setUp(self):
        self.entries = propose_site_entries(_SITE_MODEL)
        self.circ = route_internal_circulation(
            _SITE_MODEL, self.entries, [_BUILDING_A, _BUILDING_B], _PARKING
        )

    def test_served_buildings_pass(self):
        fire = check_fire_access([_BUILDING_A, _BUILDING_B], self.circ)
        self.assertTrue(fire["all_pass"])
        self.assertEqual(fire["n_fail"], 0)

    def test_no_circulation_fails(self):
        fire = check_fire_access([_BUILDING_A], None)
        self.assertFalse(fire["all_pass"])
        self.assertEqual(fire["n_fail"], 1)
        self.assertFalse(fire["buildings"][0]["within_reach"])

    def test_constraint_sign_convention_pass(self):
        # A building right on the network has distance ~0 → constraint ≈ -max_distance ≤ 0
        fire = check_fire_access([_BUILDING_A], self.circ, max_distance=50.0)
        b = fire["buildings"][0]
        self.assertLessEqual(b["constraint_value"], 0.0)
        self.assertTrue(b["pass"])

    def test_constraint_sign_convention_fail(self):
        # Big site, building far from the only path → distance > max → constraint > 0
        big_site = {"boundary": [[0, 0, 0], [200, 0, 0], [200, 200, 0], [0, 200, 0], [0, 0, 0]],
                    "roads": {"main_road_side_index": 0}}
        ent = propose_site_entries(big_site)
        near = {"building_id": "near", "boundary": [[10, 10, 0], [30, 10, 0], [30, 30, 0], [10, 30, 0]]}
        far = {"building_id": "far", "boundary": [[160, 160, 0], [190, 160, 0], [190, 190, 0], [160, 190, 0]]}
        circ = route_internal_circulation(big_site, ent, [near], None)  # only serves 'near'
        fire = check_fire_access([near, far], circ, max_distance=50.0)
        far_b = next(b for b in fire["buildings"] if b["building_id"] == "far")
        self.assertGreater(far_b["constraint_value"], 0.0)
        self.assertFalse(far_b["pass"])
        # constraint_value == distance - max_distance
        self.assertAlmostEqual(far_b["constraint_value"], far_b["distance_m"] - 50.0, places=2)

    def test_narrow_path_does_not_qualify(self):
        # A 3 m path is below the 4 m fire-access minimum → no qualifying network
        circ_narrow = route_internal_circulation(_SITE_MODEL, self.entries, [_BUILDING_A], None, path_width_m=3.0)
        fire = check_fire_access([_BUILDING_A], circ_narrow, min_path_width=4.0)
        self.assertFalse(fire["all_pass"])

    def test_max_constraint_value_is_worst(self):
        fire = check_fire_access([_BUILDING_A, _BUILDING_B], self.circ)
        worst = max(b["constraint_value"] for b in fire["buildings"])
        self.assertAlmostEqual(fire["max_constraint_value"], worst, places=3)

    def test_reachable_ratio_bounds(self):
        fire = check_fire_access([_BUILDING_A], self.circ)
        ratio = fire["buildings"][0]["reachable_perimeter_ratio"]
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)

    def test_empty_buildings(self):
        fire = check_fire_access([], self.circ)
        self.assertFalse(fire["all_pass"])  # nothing to pass
        self.assertEqual(fire["buildings"], [])

    def test_accepts_raw_path_list(self):
        fire = check_fire_access([_BUILDING_A], self.circ["paths"])
        self.assertTrue(fire["all_pass"])

    def test_default_constants(self):
        self.assertEqual(MAX_FIRE_DISTANCE_M, 50.0)
        self.assertEqual(MIN_PATH_WIDTH_M, 4.0)


# ---------------------------------------------------------------------------
# Class 5 — end-to-end pipeline integration
# ---------------------------------------------------------------------------

class TestPipelineIntegration(unittest.TestCase):

    def test_full_pipeline_runs(self):
        entries = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, entries, [_BUILDING_A, _BUILDING_B], _PARKING)
        orient = building_entrance_orientation([_BUILDING_A, _BUILDING_B], entries, circ)
        fire = check_fire_access([_BUILDING_A, _BUILDING_B], circ)
        self.assertGreater(len(entries["entries"]), 0)
        self.assertGreater(len(circ["paths"]), 0)
        self.assertEqual(len(orient["buildings"]), 2)
        self.assertTrue(fire["all_pass"])

    def test_circulation_polygons_usable_as_obstacles(self):
        # occupied_polygons should be valid closed rings (≥ 4 pts incl. closure)
        entries = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, entries, [_BUILDING_A], _PARKING)
        for poly_pts in circ["occupied_polygons"]:
            self.assertGreaterEqual(len(poly_pts), 4)
            self.assertTrue(_poly(poly_pts).area > 0)


# ---------------------------------------------------------------------------
# Complex fixtures — non-rectangular sites and courtyard footprints
# ---------------------------------------------------------------------------

# An L-shaped (concave) site — the bottom-right quadrant is cut out.
_L_SITE = [
    [0.0,   0.0,  0.0],
    [60.0,  0.0,  0.0],
    [60.0,  40.0, 0.0],
    [100.0, 40.0, 0.0],
    [100.0, 100.0, 0.0],
    [0.0,   100.0, 0.0],
    [0.0,   0.0,  0.0],
]
_L_SITE_MODEL = {"boundary": _L_SITE, "roads": {"main_road_side_index": 0}}

# U-shaped footprint (open courtyard facing +y, the mouth at the top).
_U_BUILDING = {
    "building_id": "U1",
    "boundary": [
        [0.0, 0.0, 0.0], [40.0, 0.0, 0.0], [40.0, 30.0, 0.0], [28.0, 30.0, 0.0],
        [28.0, 12.0, 0.0], [12.0, 12.0, 0.0], [12.0, 30.0, 0.0], [0.0, 30.0, 0.0],
    ],
    "storeys": 6,
}

# O-shaped footprint (true enclosed courtyard via an explicit hole).
_O_BUILDING = {
    "building_id": "O1",
    "boundary": [[0.0, 0.0, 0.0], [40.0, 0.0, 0.0], [40.0, 40.0, 0.0], [0.0, 40.0, 0.0]],
    "holes": [[[12.0, 12.0], [28.0, 12.0], [28.0, 28.0], [12.0, 28.0]]],
    "storeys": 6,
}

# A site model with a main road (south) and a secondary/service road (north).
_SITE_TWO_ROADS = {
    "boundary": [[-10.0, -10.0, 0.0], [60.0, -10.0, 0.0], [60.0, 50.0, 0.0], [-10.0, 50.0, 0.0]],
    "sides": [
        {"side_index": 0, "start": [-10.0, -10.0], "end": [60.0, -10.0],
         "adjacent_road": {"name": "Main St", "hierarchy": "main", "width_m": 20.0}},
        {"side_index": 1, "start": [60.0, -10.0], "end": [60.0, 50.0], "adjacent_road": None},
        {"side_index": 2, "start": [60.0, 50.0], "end": [-10.0, 50.0],
         "adjacent_road": {"name": "Service Ln", "hierarchy": "secondary", "width_m": 6.0}},
        {"side_index": 3, "start": [-10.0, 50.0], "end": [-10.0, -10.0], "adjacent_road": None},
    ],
    "roads": {"main_road_side_index": 0},
}


# ---------------------------------------------------------------------------
# Class 6 — courtyard detection
# ---------------------------------------------------------------------------

class TestDetectCourtyards(unittest.TestCase):

    def test_open_courtyard_from_u_shape(self):
        from agent.tools.circulation import detect_courtyards
        courts = detect_courtyards(_U_BUILDING["boundary"])
        self.assertEqual(len(courts), 1)
        self.assertEqual(courts[0]["type"], "open")
        self.assertGreater(courts[0]["area_sqm"], 100.0)
        # An open court advertises a drivable mouth.
        self.assertIsNotNone(courts[0]["opening_point"])

    def test_enclosed_courtyard_from_hole(self):
        from agent.tools.circulation import detect_courtyards
        courts = detect_courtyards(_O_BUILDING["boundary"], _O_BUILDING["holes"])
        self.assertEqual(len(courts), 1)
        self.assertEqual(courts[0]["type"], "enclosed")
        self.assertIsNone(courts[0]["opening_point"])
        self.assertAlmostEqual(courts[0]["area_sqm"], 256.0, places=1)

    def test_solid_rectangle_has_no_courtyard(self):
        from agent.tools.circulation import detect_courtyards
        self.assertEqual(detect_courtyards(_BUILDING_A["boundary"]), [])

    def test_courtyard_centroid_inside_void(self):
        from agent.tools.circulation import detect_courtyards
        courts = detect_courtyards(_U_BUILDING["boundary"])
        cx, cy, _ = courts[0]["centroid"]
        # Void centre should NOT be inside the (solid) footprint.
        self.assertFalse(_poly(_U_BUILDING["boundary"]).contains(Point(cx, cy)))


# ---------------------------------------------------------------------------
# Class 7 — obstacle-aware routing on complex sites
# ---------------------------------------------------------------------------

class TestObstacleAwareRouting(unittest.TestCase):

    def _block_far_site(self):
        site = {"boundary": [[0, 0, 0], [100, 0, 0], [100, 60, 0], [0, 60, 0]],
                "roads": {"main_road_side_index": 0}}
        block = {"building_id": "block", "boundary": [[40, 10, 0], [60, 10, 0], [60, 50, 0], [40, 50, 0]]}
        far = {"building_id": "far", "boundary": [[80, 20, 0], [95, 20, 0], [95, 40, 0], [80, 40, 0]]}
        return site, block, far

    def test_corridor_does_not_cut_through_other_buildings(self):
        site, block, far = self._block_far_site()
        ent = propose_site_entries(site)
        circ = route_internal_circulation(site, ent, [block, far], None)
        block_poly = _poly(block["boundary"]).buffer(-0.05)  # shrink to ignore grazing
        for p in circ["paths"]:
            if p["serves"] == "block":
                continue
            line = LineString([(pt[0], pt[1]) for pt in p["polyline"]])
            self.assertLess(
                line.intersection(block_poly).length, 0.1,
                f"{p['path_id']} cuts through the blocking building",
            )

    def test_route_bends_around_obstacle(self):
        site, block, far = self._block_far_site()
        ent = propose_site_entries(site)
        circ = route_internal_circulation(site, ent, [block, far], None)
        far_path = next(p for p in circ["paths"] if p["serves"] == "far")
        # A straight shot would be 2 points; bending introduces a waypoint.
        self.assertGreaterEqual(len(far_path["polyline"]), 3)
        self.assertGreaterEqual(far_path["routed_around"], 1)

    def test_corridor_stays_inside_concave_site(self):
        # The L-site has a notched-out region; corridors must not enter it.
        ent = propose_site_entries(_L_SITE_MODEL)
        b1 = {"building_id": "b1", "boundary": [[10, 10, 0], [40, 10, 0], [40, 30, 0], [10, 30, 0]]}
        b2 = {"building_id": "b2", "boundary": [[20, 60, 0], [50, 60, 0], [50, 90, 0], [20, 90, 0]]}
        circ = route_internal_circulation(_L_SITE_MODEL, ent, [b1, b2], None)
        site = _poly(_L_SITE)
        for p in circ["paths"]:
            line = LineString([(pt[0], pt[1]) for pt in p["polyline"]])
            self.assertLess(
                line.difference(site).length, 0.5,
                f"{p['path_id']} leaves the concave site",
            )

    def test_entrances_aim_circulation_when_provided(self):
        site, block, far = self._block_far_site()
        ent = propose_site_entries(site)
        circ0 = route_internal_circulation(site, ent, [block, far], None)
        orient = building_entrance_orientation([block, far], ent, circ0)
        # Re-route aiming at the resolved entrances — still one path per target.
        circ1 = route_internal_circulation(site, ent, [block, far], None, entrances_by_building=orient)
        self.assertEqual(len({p["serves"] for p in circ1["paths"]}), 2)


# ---------------------------------------------------------------------------
# Class 8 — multiple typed entrances
# ---------------------------------------------------------------------------

class TestTypedEntrances(unittest.TestCase):

    def test_public_service_and_residential_roles(self):
        ent = propose_site_entries(_SITE_TWO_ROADS)
        circ = route_internal_circulation(_SITE_TWO_ROADS, ent, [_U_BUILDING], None)
        orient = building_entrance_orientation([_U_BUILDING], ent, circ)
        roles = {e["role"] for e in orient["buildings"][0]["entrances"]}
        self.assertIn("public", roles)
        self.assertIn("service", roles)       # secondary road present
        self.assertIn("residential", roles)

    def test_residential_faces_courtyard_when_present(self):
        ent = propose_site_entries(_SITE_TWO_ROADS)
        circ = route_internal_circulation(_SITE_TWO_ROADS, ent, [_U_BUILDING], None)
        orient = building_entrance_orientation([_U_BUILDING], ent, circ)
        res = next(e for e in orient["buildings"][0]["entrances"] if e["role"] == "residential")
        self.assertEqual(res["faces"], "courtyard")

    def test_courtyard_building_reports_courtyards(self):
        ent = propose_site_entries(_SITE_TWO_ROADS)
        orient = building_entrance_orientation([_O_BUILDING], ent, None)
        self.assertEqual(len(orient["buildings"][0]["courtyards"]), 1)

    def test_legacy_single_entrance_fields_present(self):
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], None)
        orient = building_entrance_orientation([_BUILDING_A], ent, circ)
        b = orient["buildings"][0]
        # Old contract still satisfied.
        self.assertIsNotNone(b["entrance_point"])
        self.assertIsNotNone(b["entrance_direction"])
        self.assertEqual(len(b["entrance_direction"]), 2)
        self.assertAlmostEqual(b["entrance_direction"][0], -b["private_direction"][0], places=5)

    def test_multiple_public_entries_on_long_frontage(self):
        # A long main-road frontage with a small frontage budget → several gates.
        result = propose_site_entries(_SITE_MODEL, frontage_per_public_entry_m=30.0)
        self.assertGreater(result["public_count"], 1)
        for e in result["entries"]:
            if e["type"] == "public":
                self.assertEqual(e["side_index"], 0)


# ---------------------------------------------------------------------------
# Class 9 — interior- and courtyard-aware fire access
# ---------------------------------------------------------------------------

class TestFireAccessAdvanced(unittest.TestCase):

    def test_deepest_point_distance_reported(self):
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], _PARKING)
        fire = check_fire_access([_BUILDING_A], circ)
        d = fire["buildings"][0]["deepest_point_distance_m"]
        self.assertIsNotNone(d)
        # The deepest interior point is at least as far as the nearest facade.
        self.assertGreaterEqual(d, fire["buildings"][0]["distance_m"])

    def test_courtyard_reported_in_fire_check(self):
        ent = propose_site_entries(_SITE_TWO_ROADS)
        circ = route_internal_circulation(_SITE_TWO_ROADS, ent, [_O_BUILDING], None)
        fire = check_fire_access([_O_BUILDING], circ)
        self.assertEqual(len(fire["buildings"][0]["courtyards"]), 1)

    def test_strict_flag_recorded(self):
        ent = propose_site_entries(_SITE_TWO_ROADS)
        circ = route_internal_circulation(_SITE_TWO_ROADS, ent, [_U_BUILDING], None)
        fire = check_fire_access([_U_BUILDING], circ, strict=True)
        self.assertTrue(fire["strict"])

    def test_enclosed_courtyard_unreachable_fails_strict(self):
        # A big O-building: the enclosed court centre is far from any external road,
        # so strict mode must reject it even though the outer wall is reachable.
        big_o = {
            "building_id": "bigO",
            "boundary": [[0, 0, 0], [120, 0, 0], [120, 120, 0], [0, 120, 0]],
            "holes": [[[40, 40], [80, 40], [80, 80], [40, 80]]],
        }
        site = {"boundary": [[-5, -5, 0], [125, -5, 0], [125, 125, 0], [-5, 125, 0]],
                "roads": {"main_road_side_index": 0}}
        ent = propose_site_entries(site)
        circ = route_internal_circulation(site, ent, [big_o], None)
        loose = check_fire_access([big_o], circ, strict=False)
        strict = check_fire_access([big_o], circ, strict=True)
        # Outer wall is reachable → passes the loose distance test…
        self.assertTrue(loose["buildings"][0]["within_reach"])
        # …but the enclosed courtyard core is not serviceable → strict fails.
        self.assertFalse(strict["buildings"][0]["courtyards_reachable"])
        self.assertFalse(strict["all_pass"])

    def test_constraint_convention_unchanged_in_strict(self):
        # strict tightens pass/fail but must NOT change the G = d - max constraint.
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], _PARKING)
        loose = check_fire_access([_BUILDING_A], circ, max_distance=50.0)
        strict = check_fire_access([_BUILDING_A], circ, max_distance=50.0, strict=True)
        self.assertAlmostEqual(
            loose["buildings"][0]["constraint_value"],
            strict["buildings"][0]["constraint_value"],
            places=3,
        )


# ---------------------------------------------------------------------------
# Class 10 — facade segmentation (typology-aware primitive)
# ---------------------------------------------------------------------------

class TestSegmentFacades(unittest.TestCase):

    def test_rectangle_has_four_open_facades(self):
        from agent.tools.circulation import segment_facades
        facades = segment_facades(_BUILDING_A)
        self.assertEqual(len(facades), 4)
        self.assertTrue(all(f["faces"] == "open" for f in facades))
        self.assertTrue(all(f["is_exterior"] for f in facades))

    def test_u_shape_has_courtyard_facades(self):
        from agent.tools.circulation import segment_facades
        facades = segment_facades(_U_BUILDING)
        kinds = {f["faces"] for f in facades}
        self.assertIn("open", kinds)
        self.assertIn("courtyard", kinds)  # inner faces of the U pocket

    def test_o_shape_has_enclosed_facades(self):
        from agent.tools.circulation import segment_facades
        facades = segment_facades(_O_BUILDING)
        self.assertTrue(any(f["faces"] == "enclosed_courtyard" for f in facades))
        # The hole ring contributes 4 enclosed facades.
        self.assertEqual(sum(1 for f in facades if f["faces"] == "enclosed_courtyard"), 4)

    def test_outward_normal_points_out_of_solid(self):
        from agent.tools.circulation import segment_facades
        poly = _poly(_BUILDING_A["boundary"])
        for f in segment_facades(_BUILDING_A):
            mx, my, _ = f["midpoint"]
            nx, ny = f["outward_normal"]
            probe = Point(mx + nx * 0.5, my + ny * 0.5)
            self.assertFalse(poly.contains(probe))
            self.assertAlmostEqual(math.hypot(nx, ny), 1.0, places=4)


# ---------------------------------------------------------------------------
# Class 11 — emergency exits
# ---------------------------------------------------------------------------

class TestEmergencyExits(unittest.TestCase):

    def test_box_gets_multiple_independent_exits(self):
        from agent.tools.circulation import generate_emergency_exits
        ee = generate_emergency_exits(_BUILDING_A)
        self.assertGreaterEqual(ee["n_exits"], 2)
        self.assertGreaterEqual(ee["independent_directions"], 2)
        self.assertTrue(ee["multiple_directions"])
        self.assertFalse(ee["single_point_failure"])

    def test_exits_are_on_open_facades_not_courtyard(self):
        from agent.tools.circulation import generate_emergency_exits
        ee = generate_emergency_exits(_O_BUILDING)
        self.assertTrue(all(e["faces"] == "open" for e in ee["exits"]))
        self.assertFalse(ee["courtyard_only_egress_risk"])

    def test_exits_lie_on_building_boundary(self):
        from agent.tools.circulation import generate_emergency_exits
        poly = _poly(_U_BUILDING["boundary"])
        ee = generate_emergency_exits(_U_BUILDING)
        for e in ee["exits"]:
            pt = Point(e["point"][0], e["point"][1])
            self.assertLess(poly.exterior.distance(pt), 1e-6)

    def test_exit_distance_reported_with_circulation(self):
        from agent.tools.circulation import generate_emergency_exits
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], None)
        ee = generate_emergency_exits(_BUILDING_A, circ)
        self.assertIsNotNone(ee["exits"][0]["distance_to_access_m"])


# ---------------------------------------------------------------------------
# Class 12 — arrival, pedestrian network, parking, egress, conflicts, audit
# ---------------------------------------------------------------------------

class TestFunctionalAccessLayer(unittest.TestCase):

    def setUp(self):
        self.entries = propose_site_entries(_SITE_TWO_ROADS)
        self.circ = route_internal_circulation(_SITE_TWO_ROADS, self.entries, [_U_BUILDING], None)
        self.orient = building_entrance_orientation([_U_BUILDING], self.entries, self.circ)

    def test_arrival_classifies_modes(self):
        from agent.tools.circulation import analyze_site_arrival
        arr = analyze_site_arrival(_SITE_TWO_ROADS, self.entries, self.orient)
        modes = {a["mode"] for a in arr["arrivals"]}
        self.assertTrue(modes & {"both", "vehicular", "pedestrian"})
        self.assertGreaterEqual(len(arr["frontages"]), 1)

    def test_pedestrian_network_one_path_per_building(self):
        from agent.tools.circulation import route_pedestrian_network
        ped = route_pedestrian_network(_SITE_TWO_ROADS, self.entries, [_U_BUILDING], None, self.orient)
        self.assertTrue(all(p["mode"] == "pedestrian" for p in ped["paths"]))
        self.assertGreaterEqual(len(ped["paths"]), 1)

    def test_pedestrian_avoids_parking_interior(self):
        from agent.tools.circulation import route_pedestrian_network
        # A *partial* parking strip on the right of the frontage, leaving a gap on
        # the left so the walk to building A (x 10–35) can route around it.
        partial = {"zones": [{"zone_id": "parking_zone_0",
                              "boundary": [[55.0, 0.3, 0.0], [89.7, 0.3, 0.0],
                                           [89.7, 11.0, 0.0], [55.0, 11.0, 0.0]],
                              "is_main_road_side": True}]}
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], partial)
        orient = building_entrance_orientation([_BUILDING_A], ent, circ)
        ped = route_pedestrian_network(_SITE_MODEL, ent, [_BUILDING_A], partial, orient)
        park = _poly(partial["zones"][0]["boundary"]).buffer(-0.5)
        for p in ped["paths"]:
            if p.get("source") == "parking_zone_0":
                continue  # a walk FROM parking legitimately starts at its edge
            line = LineString([(pt[0], pt[1]) for pt in p["polyline"]])
            self.assertLess(line.intersection(park).length, 2.0)

    def test_parking_access_reports_distance_and_dropoff(self):
        from agent.tools.circulation import analyze_parking_access
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], _PARKING)
        orient = building_entrance_orientation([_BUILDING_A], ent, circ)
        pa = analyze_parking_access([_BUILDING_A], _PARKING, orient)
        z = pa["zones"][0]
        self.assertEqual(z["nearest_entrance_building"], "A")
        self.assertIsNotNone(z["drop_off_point"])
        self.assertIsInstance(z["within_comfort_walk"], bool)

    def test_egress_reports_compliance(self):
        from agent.tools.circulation import analyze_egress
        eg = analyze_egress([_U_BUILDING], self.circ)
        row = eg["buildings"][0]
        self.assertIn("compliant", row)
        self.assertEqual(eg["min_clear_width_m"], MIN_PATH_WIDTH_M)

    def test_conflicts_detects_crossings(self):
        from agent.tools.circulation import (
            route_pedestrian_network, detect_circulation_conflicts,
        )
        ent = propose_site_entries(_SITE_MODEL)
        circ = route_internal_circulation(_SITE_MODEL, ent, [_BUILDING_A], _PARKING)
        orient = building_entrance_orientation([_BUILDING_A], ent, circ)
        ped = route_pedestrian_network(_SITE_MODEL, ent, [_BUILDING_A], _PARKING, orient)
        conf = detect_circulation_conflicts(circ, ped, _PARKING)
        self.assertIn("conflicts", conf)
        self.assertIsInstance(conf["conflicts"], list)

    def test_audit_runs_and_reports_checks(self):
        from agent.tools.circulation import (
            route_pedestrian_network, analyze_parking_access, analyze_egress,
            detect_circulation_conflicts, audit_circulation,
        )
        ped = route_pedestrian_network(_SITE_TWO_ROADS, self.entries, [_U_BUILDING], None, self.orient)
        pa = analyze_parking_access([_U_BUILDING], None, self.orient, ped)
        eg = analyze_egress([_U_BUILDING], self.circ)
        fire = check_fire_access([_U_BUILDING], self.circ)
        conf = detect_circulation_conflicts(self.circ, ped, None, fire)
        audit = audit_circulation(self.entries, self.orient, self.circ, ped, pa, eg, fire, conf)
        names = {c["check"] for c in audit["checks"]}
        self.assertIn("every_building_has_public_entrance", names)
        self.assertIn("fire_vehicle_access_available", names)


# ---------------------------------------------------------------------------
# Class 13 — end-to-end orchestrator on a complex layout
# ---------------------------------------------------------------------------

class TestEvaluateSiteCirculation(unittest.TestCase):

    def test_orchestrator_returns_all_sections(self):
        from agent.tools.circulation import evaluate_site_circulation
        rep = evaluate_site_circulation(_SITE_MODEL, [_BUILDING_A, _BUILDING_B], _PARKING)
        for key in ("entrances", "site_access", "vehicular_circulation",
                    "pedestrian_circulation", "movement_hierarchy",
                    "parking_integration", "fire_safety_egress", "conflicts", "audit"):
            self.assertIn(key, rep)

    def test_orchestrator_aims_corridors_at_entrances(self):
        from agent.tools.circulation import evaluate_site_circulation
        rep = evaluate_site_circulation(_SITE_MODEL, [_BUILDING_A, _BUILDING_B], _PARKING)
        veh = rep["vehicular_circulation"]
        self.assertTrue(all(p.get("mode") == "vehicular" for p in veh["paths"]))
        serves = {p["serves"] for p in veh["paths"]}
        self.assertIn("A", serves)
        self.assertIn("B", serves)

    def test_orchestrator_handles_courtyard_building(self):
        from agent.tools.circulation import evaluate_site_circulation
        rep = evaluate_site_circulation(_SITE_TWO_ROADS, [_O_BUILDING], None)
        # The enclosed-court building still gets ≥2 open-facade exits.
        eg = rep["fire_safety_egress"]["egress"]["buildings"][0]
        self.assertGreaterEqual(eg["n_exits"], 2)
        self.assertFalse(eg["courtyard_only_egress_risk"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
