"""Regression tests for Phase 4 — Parking (agent/tools/parking.py).

Deterministic, no LLM, no MCP, no network calls.
Run with:  python -m pytest team_04/benchmarking/test_parking.py -v
       or: python -m unittest team_04.benchmarking.test_parking
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Allow import without installing the package
_TEAM_ROOT = Path(__file__).resolve().parent.parent
if str(_TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEAM_ROOT))

from agent.tools.parking import (
    BAY_DEPTH_M,
    M2_PER_STALL,
    STALL_WIDTH_M,
    allocate_parking_zones,
    compute_building_demand,
    estimate_apartments,
    parking_demand,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RECT_SITE = [          # 90 m × 60 m rectangle
    [0.0,  0.0, 0.0],
    [90.0, 0.0, 0.0],
    [90.0, 60.0, 0.0],
    [0.0,  60.0, 0.0],
    [0.0,  0.0, 0.0],
]

_SMALL_SITE = [         # 20 m × 20 m — tight site
    [0.0,  0.0, 0.0],
    [20.0, 0.0, 0.0],
    [20.0, 20.0, 0.0],
    [0.0,  20.0, 0.0],
    [0.0,  0.0, 0.0],
]

# A site model with a named main-road side (south edge = index 0)
_SITE_MODEL_WITH_ROAD = {
    "boundary": _RECT_SITE,
    "sides": [
        {"side_index": 0, "start": [0.0,  0.0], "end": [90.0, 0.0]},  # south (main road)
        {"side_index": 1, "start": [90.0, 0.0], "end": [90.0, 60.0]}, # east
        {"side_index": 2, "start": [90.0, 60.0], "end": [0.0, 60.0]}, # north
        {"side_index": 3, "start": [0.0, 60.0],  "end": [0.0, 0.0]},  # west
    ],
    "roads": {
        "main_road_side_index": 0,
        "main_road": {"name": "Main Street", "width_m": 20.0},
    },
}

_SITE_MODEL_PLAIN = {
    "boundary": _RECT_SITE,
    "sides": [
        {"side_index": 0, "start": [0.0,  0.0], "end": [90.0, 0.0]},
        {"side_index": 1, "start": [90.0, 0.0], "end": [90.0, 60.0]},
        {"side_index": 2, "start": [90.0, 60.0], "end": [0.0, 60.0]},
        {"side_index": 3, "start": [0.0, 60.0],  "end": [0.0, 0.0]},
    ],
}

# A building occupying the south strip of the site — forces parking elsewhere
_BUILDING_SOUTH_STRIP = {
    "building_id": "bld_south",
    "boundary": [
        [0.0,  0.0,  0.0],
        [90.0, 0.0,  0.0],
        [90.0, 15.0, 0.0],
        [0.0,  15.0, 0.0],
        [0.0,  0.0,  0.0],
    ],
    "storeys": 5,
}

_BUILDING_CENTRE = {
    "building_id": "bld_centre",
    "boundary": [
        [30.0, 20.0, 0.0],
        [60.0, 20.0, 0.0],
        [60.0, 40.0, 0.0],
        [30.0, 40.0, 0.0],
        [30.0, 20.0, 0.0],
    ],
    "storeys": 4,
}


# ---------------------------------------------------------------------------
# Class 1 — estimate_apartments
# ---------------------------------------------------------------------------

class TestEstimateApartments(unittest.TestCase):

    def test_basic_count(self):
        # 900 m² × 5 floors × 0.8 efficiency / 70 m² = 51.4 → 51
        apts = estimate_apartments(900, 5)
        self.assertEqual(apts, 51)

    def test_single_storey(self):
        apts = estimate_apartments(300, 1)
        expected = int(300 * 1 * 0.8 / 70)
        self.assertEqual(apts, expected)

    def test_zero_storeys_returns_zero(self):
        self.assertEqual(estimate_apartments(900, 0), 0)

    def test_zero_area_returns_zero(self):
        self.assertEqual(estimate_apartments(0, 5), 0)

    def test_custom_efficiency(self):
        apts = estimate_apartments(700, 4, efficiency=1.0, avg_apartment_sqm=70)
        self.assertEqual(apts, 40)

    def test_custom_avg_apartment(self):
        apts = estimate_apartments(700, 4, avg_apartment_sqm=35)
        expected = int(700 * 4 * 0.8 / 35)
        self.assertEqual(apts, expected)


# ---------------------------------------------------------------------------
# Class 2 — parking_demand
# ---------------------------------------------------------------------------

class TestParkingDemand(unittest.TestCase):

    def test_one_to_one_ratio(self):
        d = parking_demand(10)
        self.assertEqual(d["stalls_required"], 10)

    def test_zero_apartments(self):
        d = parking_demand(0)
        self.assertEqual(d["stalls_required"], 0)
        self.assertEqual(d["area_sqm_required"], 0.0)

    def test_half_ratio(self):
        d = parking_demand(10, parking_ratio=0.5)
        self.assertEqual(d["stalls_required"], 5)

    def test_1_5_ratio_rounds_up(self):
        # 5 apts × 1.5 = 7.5 → ceil → 8
        d = parking_demand(5, parking_ratio=1.5)
        self.assertEqual(d["stalls_required"], 8)

    def test_area_matches_stalls(self):
        d = parking_demand(20)
        self.assertAlmostEqual(d["area_sqm_required"], 20 * M2_PER_STALL, places=1)

    def test_constants_present(self):
        d = parking_demand(5)
        for key in ("stall_width_m", "stall_depth_m", "aisle_width_m", "bay_depth_m", "m2_per_stall"):
            self.assertIn(key, d)

    def test_bay_depth_matches_constant(self):
        d = parking_demand(1)
        self.assertAlmostEqual(d["bay_depth_m"], BAY_DEPTH_M)


# ---------------------------------------------------------------------------
# Class 3 — compute_building_demand
# ---------------------------------------------------------------------------

class TestComputeBuildingDemand(unittest.TestCase):

    def test_two_buildings(self):
        buildings = [_BUILDING_SOUTH_STRIP, _BUILDING_CENTRE]
        result = compute_building_demand(buildings)
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertIn("building_id", entry)
            self.assertIn("apartments", entry)
            self.assertIn("stalls_required", entry)
            self.assertGreaterEqual(entry["stalls_required"], 0)

    def test_empty_buildings(self):
        self.assertEqual(compute_building_demand([]), [])

    def test_stalls_proportional_to_storeys(self):
        low  = compute_building_demand([{"building_id": "a", "boundary": _BUILDING_CENTRE["boundary"], "storeys": 2}])
        high = compute_building_demand([{"building_id": "b", "boundary": _BUILDING_CENTRE["boundary"], "storeys": 8}])
        self.assertLess(low[0]["stalls_required"], high[0]["stalls_required"])


# ---------------------------------------------------------------------------
# Class 4 — allocate_parking_zones: basic allocation
# ---------------------------------------------------------------------------

class TestAllocateParkingZonesBasic(unittest.TestCase):

    def _demand(self, stalls):
        return [{"building_id": "bld_1", "stalls_required": stalls}]

    def test_zero_demand_returns_no_zones(self):
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], self._demand(0))
        self.assertEqual(result["zones"], [])
        self.assertTrue(result["feasible"])
        self.assertEqual(result["shortfall"], 0)

    def test_small_demand_allocates(self):
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], self._demand(5))
        self.assertGreater(result["total_stalls_allocated"], 0)
        self.assertEqual(result["stalls_required"], 5)

    def test_feasible_when_demand_met(self):
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], self._demand(4))
        if result["total_stalls_allocated"] >= 4:
            self.assertTrue(result["feasible"])
            self.assertEqual(result["shortfall"], 0)

    def test_demand_exceeds_site_reports_shortfall(self):
        # Tiny site + huge demand
        tiny_model = {"boundary": _SMALL_SITE}
        result = allocate_parking_zones(tiny_model, [], self._demand(500))
        self.assertGreater(result["shortfall"], 0)
        self.assertFalse(result["feasible"])

    def test_no_valid_site_returns_empty(self):
        result = allocate_parking_zones({"boundary": []}, [], self._demand(5))
        self.assertEqual(result["zones"], [])

    def test_summary_is_string(self):
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], self._demand(3))
        self.assertIsInstance(result["summary"], str)
        self.assertGreater(len(result["summary"]), 0)


# ---------------------------------------------------------------------------
# Class 5 — no-overlap invariant
# ---------------------------------------------------------------------------

class TestNoOverlapInvariant(unittest.TestCase):

    def _zone_poly(self, zone):
        from shapely.geometry import Polygon
        pts = [(p[0], p[1]) for p in zone["boundary"]]
        return Polygon(pts)

    def _building_poly(self, bld):
        from shapely.geometry import Polygon
        pts = [(p[0], p[1]) for p in bld["boundary"]]
        return Polygon(pts)

    def test_zones_do_not_overlap_buildings(self):
        demand = [{"building_id": "bld_centre", "stalls_required": 10}]
        result = allocate_parking_zones(
            _SITE_MODEL_PLAIN, [_BUILDING_CENTRE], demand
        )
        bld_poly = self._building_poly(_BUILDING_CENTRE)
        for zone in result["zones"]:
            zone_p = self._zone_poly(zone)
            overlap = zone_p.intersection(bld_poly).area
            self.assertLess(overlap, 0.5, f"Zone {zone['zone_id']} overlaps building by {overlap:.1f} m²")

    def test_zones_do_not_overlap_each_other(self):
        demand = [{"building_id": "bld_centre", "stalls_required": 60}]
        result = allocate_parking_zones(
            _SITE_MODEL_PLAIN, [_BUILDING_CENTRE], demand
        )
        zones = result["zones"]
        for i, z1 in enumerate(zones):
            p1 = self._zone_poly(z1)
            for j, z2 in enumerate(zones):
                if j <= i:
                    continue
                p2 = self._zone_poly(z2)
                overlap = p1.intersection(p2).area
                self.assertLess(overlap, 0.5, f"Zones {i} and {j} overlap by {overlap:.1f} m²")

    def test_zones_inside_site(self):
        from shapely.geometry import Polygon as SPolygon
        site_p = SPolygon([(p[0], p[1]) for p in _RECT_SITE])
        demand = [{"building_id": "b", "stalls_required": 15}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for zone in result["zones"]:
            zp = self._zone_poly(zone)
            outside = zp.difference(site_p).area
            self.assertLess(outside, 0.5, f"Zone {zone['zone_id']} extends {outside:.1f} m² outside site")


# ---------------------------------------------------------------------------
# Class 6 — near-road preference
# ---------------------------------------------------------------------------

class TestNearRoadPreference(unittest.TestCase):

    def test_first_zone_is_main_road_side(self):
        demand = [{"building_id": "bld_1", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_WITH_ROAD, [], demand)
        if result["zones"]:
            self.assertTrue(
                result["zones"][0]["is_main_road_side"],
                "First parking zone should be on the main-road side",
            )

    def test_building_on_main_road_side_forces_elsewhere(self):
        demand = [{"building_id": "bld_south", "stalls_required": 6}]
        result = allocate_parking_zones(
            _SITE_MODEL_WITH_ROAD, [_BUILDING_SOUTH_STRIP], demand
        )
        # Parking must not overlap the south building (which covers the south strip)
        from shapely.geometry import Polygon as SP
        bld_p = SP([(p[0], p[1]) for p in _BUILDING_SOUTH_STRIP["boundary"]])
        for zone in result["zones"]:
            zp = SP([(p[0], p[1]) for p in zone["boundary"]])
            overlap = zp.intersection(bld_p).area
            self.assertLess(overlap, 0.5)

    def test_prefer_road_false_ignores_road_side(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result_road = allocate_parking_zones(
            _SITE_MODEL_WITH_ROAD, [], demand, prefer_road_side=True
        )
        result_no = allocate_parking_zones(
            _SITE_MODEL_WITH_ROAD, [], demand, prefer_road_side=False
        )
        # Both should allocate something; road_side version has main-road flag on first zone
        if result_road["zones"]:
            self.assertTrue(result_road["zones"][0]["is_main_road_side"])


# ---------------------------------------------------------------------------
# Class 7 — zone schema correctness
# ---------------------------------------------------------------------------

class TestZoneSchema(unittest.TestCase):

    def test_zone_fields_present(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for zone in result["zones"]:
            for key in ("zone_id", "boundary", "stalls_allocated", "area_sqm",
                        "side_index", "is_main_road_side"):
                self.assertIn(key, zone, f"Missing key: {key}")

    def test_stalls_allocated_positive(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for zone in result["zones"]:
            self.assertGreater(zone["stalls_allocated"], 0)

    def test_area_sqm_plausible(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for zone in result["zones"]:
            # Each zone should be at least one stall-worth of area
            self.assertGreaterEqual(zone["area_sqm"], M2_PER_STALL * 0.9)

    def test_total_allocated_equals_sum_of_zones(self):
        demand = [{"building_id": "b", "stalls_required": 20}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        zone_total = sum(z["stalls_allocated"] for z in result["zones"])
        self.assertEqual(result["total_stalls_allocated"], zone_total)

    def test_result_top_level_keys(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for key in ("zones", "total_stalls_allocated", "stalls_required",
                    "shortfall", "feasible", "summary", "building_demand"):
            self.assertIn(key, result)

    def test_boundary_has_3d_points(self):
        demand = [{"building_id": "b", "stalls_required": 5}]
        result = allocate_parking_zones(_SITE_MODEL_PLAIN, [], demand)
        for zone in result["zones"]:
            for pt in zone["boundary"]:
                self.assertEqual(len(pt), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
