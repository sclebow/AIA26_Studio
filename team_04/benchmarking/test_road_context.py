"""Deterministic regressions for Phase 2 (road / transportation context).

No LLM and no MCP.  These exercise:
  - Main-road selection (hierarchy > width > frontage).
  - Nearest-side identification for each road.
  - Side tagging (adjacent_road populated on the right side).
  - edge_road_widths derivation for the setback tool.
  - Ambiguity recording when no roads are supplied.
  - Integration with site_grid: main-road side drives the default alignment.
  - Integration with build_site_model: site_objects roads flow through.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.tools.road_context import (
    HIERARCHY_RANK,
    analyze_roads,
    validate_road,
)
from agent.tools.site_model import build_site_model
from agent.tools.site_grid import derive_site_grid

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# A 100 × 100 m square site.
SQUARE_SITE = [
    [0.0, 0.0, 0.0],
    [100.0, 0.0, 0.0],
    [100.0, 100.0, 0.0],
    [0.0, 100.0, 0.0],
    [0.0, 0.0, 0.0],
]

# Non-orthogonal "splayed" pentagon (same as grid/sun tests).
COMPLEX_SITE = [[0, 0, 0], [130, 18, 0], [150, 92, 0], [62, 128, 0], [-14, 74, 0], [0, 0, 0]]

# Road running along the south side (y ≈ -5, x 0..100) — a wide main road.
MAIN_ROAD = {
    "type": "road",
    "centerline": [[-10.0, -8.0], [110.0, -8.0]],
    "width_m": 20.0,
    "hierarchy": "main",
    "name": "Main Street",
}

# Road running along the east side (x ≈ 105, y 0..100) — narrow secondary.
SECONDARY_ROAD = {
    "type": "road",
    "centerline": [[105.0, -5.0], [105.0, 105.0]],
    "width_m": 8.0,
    "hierarchy": "secondary",
    "name": "East Lane",
}

# Road running along the north side (y ≈ 105) — a path.
PATH_ROAD = {
    "type": "road",
    "centerline": [[-5.0, 107.0], [105.0, 107.0]],
    "width_m": 4.0,
    "hierarchy": "path",
    "name": "North Path",
}


def _make_model(site=None, roads=None):
    site = site or SQUARE_SITE
    payload = {}
    if roads:
        payload["site_objects"] = roads
    return build_site_model(site, payload)


# ---------------------------------------------------------------------------
# validate_road
# ---------------------------------------------------------------------------

class ValidateRoadTests(unittest.TestCase):
    def test_valid_road_normalised(self):
        r = validate_road(MAIN_ROAD)
        self.assertEqual(r["hierarchy"], "main")
        self.assertEqual(r["width_m"], 20.0)
        self.assertEqual(len(r["centerline"]), 2)

    def test_unknown_hierarchy_defaults_to_secondary(self):
        r = validate_road({"centerline": [[0, 0], [10, 0]], "hierarchy": "boulevard"})
        self.assertEqual(r["hierarchy"], "secondary")

    def test_missing_width_defaults(self):
        from agent.tools.road_context import DEFAULT_ROAD_WIDTH_M
        r = validate_road({"centerline": [[0, 0], [10, 0]]})
        self.assertEqual(r["width_m"], DEFAULT_ROAD_WIDTH_M)

    def test_negative_width_defaults(self):
        from agent.tools.road_context import DEFAULT_ROAD_WIDTH_M
        r = validate_road({"centerline": [[0, 0], [10, 0]], "width_m": -5.0})
        self.assertEqual(r["width_m"], DEFAULT_ROAD_WIDTH_M)

    def test_missing_centerline_raises(self):
        with self.assertRaises(ValueError):
            validate_road({"width_m": 10})

    def test_single_point_raises(self):
        with self.assertRaises(ValueError):
            validate_road({"centerline": [[0, 0]]})

    def test_non_dict_raises(self):
        with self.assertRaises(ValueError):
            validate_road("not a dict")


# ---------------------------------------------------------------------------
# Main-road selection
# ---------------------------------------------------------------------------

class MainRoadSelectionTests(unittest.TestCase):
    def _analyse(self, roads):
        model = build_site_model(SQUARE_SITE, {})
        return analyze_roads(model, roads)

    def test_main_road_wins_by_hierarchy(self):
        result = self._analyse([MAIN_ROAD, SECONDARY_ROAD, PATH_ROAD])
        self.assertTrue(result["available"])
        self.assertEqual(result["main_road"]["hierarchy"], "main")
        self.assertEqual(result["main_road"]["name"], "Main Street")

    def test_wider_wins_when_hierarchy_tied(self):
        wide = {**SECONDARY_ROAD, "width_m": 15.0, "name": "Wide Secondary"}
        narrow = {**SECONDARY_ROAD, "width_m": 6.0, "name": "Narrow Secondary",
                  "centerline": [[-5.0, -8.0], [110.0, -8.0]]}
        result = self._analyse([narrow, wide])
        self.assertEqual(result["main_road"]["name"], "Wide Secondary")

    def test_more_frontage_wins_when_hierarchy_and_width_tied(self):
        long_road = {
            "type": "road",
            "centerline": [[-10.0, -8.0], [110.0, -8.0]],
            "width_m": 10.0, "hierarchy": "secondary", "name": "Long",
        }
        short_road = {
            "type": "road",
            "centerline": [[20.0, -8.0], [80.0, -8.0]],
            "width_m": 10.0, "hierarchy": "secondary", "name": "Short",
        }
        result = self._analyse([short_road, long_road])
        self.assertEqual(result["main_road"]["name"], "Long")

    def test_single_road_is_always_main(self):
        result = self._analyse([PATH_ROAD])
        self.assertIsNotNone(result["main_road"])
        self.assertEqual(result["main_road"]["hierarchy"], "path")


# ---------------------------------------------------------------------------
# Nearest-side identification
# ---------------------------------------------------------------------------

class NearestSideTests(unittest.TestCase):
    """On the 100×100 square (side 0=south, 1=east, 2=north, 3=west)."""

    def _side_for(self, road):
        model = build_site_model(SQUARE_SITE, {})
        result = analyze_roads(model, [road])
        return result["roads"][0]["nearest_side_index"]

    def test_main_road_south_maps_to_side_0(self):
        # MAIN_ROAD runs along y ≈ -8, parallel to the south edge (side 0)
        si = self._side_for(MAIN_ROAD)
        self.assertEqual(si, 0)

    def test_east_road_maps_to_side_1(self):
        si = self._side_for(SECONDARY_ROAD)
        self.assertEqual(si, 1)

    def test_north_road_maps_to_side_2(self):
        si = self._side_for(PATH_ROAD)
        self.assertEqual(si, 2)

    def test_west_road_maps_to_side_3(self):
        west_road = {
            "type": "road",
            "centerline": [[-8.0, -5.0], [-8.0, 105.0]],
            "width_m": 6.0,
            "hierarchy": "secondary",
        }
        si = self._side_for(west_road)
        self.assertEqual(si, 3)


# ---------------------------------------------------------------------------
# Side tagging
# ---------------------------------------------------------------------------

class SideTaggingTests(unittest.TestCase):

    def test_main_road_side_tagged(self):
        model = build_site_model(SQUARE_SITE, {"site_objects": [MAIN_ROAD]})
        roads = model["roads"]
        self.assertTrue(roads["available"])
        main_si = roads["main_road_side_index"]
        tagged_side = model["sides"][main_si]
        adj = tagged_side.get("adjacent_road")
        self.assertIsNotNone(adj)
        self.assertEqual(adj["hierarchy"], "main")

    def test_unrelated_sides_not_tagged(self):
        # Only the south road is provided — north side (side 2) should be None
        model = build_site_model(SQUARE_SITE, {"site_objects": [MAIN_ROAD]})
        # side 2 = north (opposite of south main road)
        north_side = model["sides"][2]
        self.assertIsNone(north_side.get("adjacent_road"))

    def test_multiple_roads_tag_their_sides(self):
        model = build_site_model(
            SQUARE_SITE,
            {"site_objects": [MAIN_ROAD, SECONDARY_ROAD, PATH_ROAD]},
        )
        roads = model["roads"]
        # Three different sides should be tagged (south, east, north)
        tagged = [s for s in model["sides"] if s.get("adjacent_road") is not None]
        self.assertGreaterEqual(len(tagged), 2)


# ---------------------------------------------------------------------------
# edge_road_widths / setback derivation
# ---------------------------------------------------------------------------

class SetbackDerivationTests(unittest.TestCase):

    def test_edge_road_widths_populated_for_main_road(self):
        model = build_site_model(SQUARE_SITE, {})
        result = analyze_roads(model, [MAIN_ROAD])
        erw = result["edge_road_widths"]
        main_si = result["main_road_side_index"]
        self.assertIn(main_si, erw)
        self.assertAlmostEqual(erw[main_si], 20.0, places=1)

    def test_road_derived_setback_larger_than_default(self):
        # With a 20 m main road, setback = max(3, 20×0.4) = 8 m > default 5 m.
        model_with_road = build_site_model(SQUARE_SITE, {"site_objects": [MAIN_ROAD]})
        model_no_road = build_site_model(SQUARE_SITE, {})
        sb_with = model_with_road.get("setbacks", {})
        sb_no = model_no_road.get("setbacks", {})
        # The road-adjacent edge should have a larger setback
        if sb_with and sb_no:
            erw_si = model_with_road["roads"]["main_road_side_index"]
            edge_with = next(
                (e for e in (sb_with.get("edges") or []) if e["edge_index"] == erw_si), None
            )
            edge_no = next(
                (e for e in (sb_no.get("edges") or []) if e["edge_index"] == erw_si), None
            )
            if edge_with and edge_no:
                self.assertGreater(edge_with["setback_m"], edge_no["setback_m"])

    def test_explicit_edge_road_widths_override_road_derived(self):
        # An explicit payload override beats the road-derived value.
        model = build_site_model(
            SQUARE_SITE,
            {"site_objects": [MAIN_ROAD], "edge_road_widths": {0: 30.0}},
        )
        sb = model.get("setbacks", {})
        if sb:
            edge0 = next((e for e in (sb.get("edges") or []) if e["edge_index"] == 0), None)
            if edge0:
                # 30 m road → setback = 30 × 0.4 = 12 m
                self.assertAlmostEqual(edge0["setback_m"], 12.0, places=1)

    def test_no_road_edge_road_widths_empty(self):
        model = build_site_model(SQUARE_SITE, {})
        result = analyze_roads(model, None)
        self.assertEqual(result["edge_road_widths"], {})


# ---------------------------------------------------------------------------
# Ambiguity recording
# ---------------------------------------------------------------------------

class AmbiguityTests(unittest.TestCase):

    def test_no_roads_returns_ambiguity(self):
        model = build_site_model(SQUARE_SITE, {})
        result = analyze_roads(model, None)
        self.assertFalse(result["available"])
        self.assertEqual(result["ambiguity"], "no_road_data")
        self.assertIsNotNone(result["ambiguity_message"])

    def test_empty_list_returns_ambiguity(self):
        model = build_site_model(SQUARE_SITE, {})
        result = analyze_roads(model, [])
        self.assertFalse(result["available"])
        self.assertEqual(result["ambiguity"], "no_road_data")

    def test_all_invalid_roads_returns_ambiguity(self):
        model = build_site_model(SQUARE_SITE, {})
        bad = [{"type": "road", "centerline": [[0, 0]]}, {"not": "a road"}]
        result = analyze_roads(model, bad)
        self.assertFalse(result["available"])

    def test_no_road_site_model_roads_is_not_available(self):
        model = build_site_model(SQUARE_SITE, {})
        roads = model.get("roads", {})
        self.assertFalse(roads.get("available", True))


# ---------------------------------------------------------------------------
# Grid integration — main road side drives alignment_side default
# ---------------------------------------------------------------------------

class GridRoadIntegrationTests(unittest.TestCase):

    def test_grid_aligns_to_main_road_side(self):
        # MAIN_ROAD is along the south side (side 0).  Without an explicit
        # alignment_side, derive_site_grid should pick side 0 as the reference.
        model = build_site_model(
            SQUARE_SITE,
            {"site_objects": [MAIN_ROAD], "default_setback": 5.0},
        )
        grid = derive_site_grid(model, spacing=10.0)
        self.assertTrue(grid["available"])
        self.assertEqual(grid["alignment_side_index"], 0)

    def test_explicit_alignment_side_overrides_main_road(self):
        model = build_site_model(
            SQUARE_SITE,
            {"site_objects": [MAIN_ROAD], "default_setback": 5.0},
        )
        # Force side 2 (north) explicitly — should beat the main-road default.
        grid = derive_site_grid(model, spacing=10.0, alignment_side=2)
        self.assertEqual(grid["alignment_side_index"], 2)

    def test_longest_side_fallback_when_no_roads(self):
        # A 120×80 rotated rectangle — longest side is the 120 m edge.
        import math
        rot = 30.0
        a = math.radians(rot)
        ca, sa = math.cos(a), math.sin(a)
        W, H = 120.0, 80.0
        pts = [(-W/2, -H/2), (W/2, -H/2), (W/2, H/2), (-W/2, H/2)]
        cx, cy = 60.0, 40.0
        rot_site = [[cx + x*ca - y*sa, cy + x*sa + y*ca, 0.0] for x, y in pts]
        rot_site.append(rot_site[0])
        model = build_site_model(rot_site, {})
        grid = derive_site_grid(model, spacing=10.0)
        self.assertTrue(grid["available"])
        # Without roads the grid must fall back to the longest side (120 m, ~30°).
        self.assertAlmostEqual(grid["angle_deg"] % 180.0, 30.0, delta=1.0)


# ---------------------------------------------------------------------------
# build_site_model integration
# ---------------------------------------------------------------------------

class SiteModelIntegrationTests(unittest.TestCase):

    def test_site_objects_roads_flow_through(self):
        model = build_site_model(
            SQUARE_SITE,
            {"site_objects": [MAIN_ROAD, SECONDARY_ROAD]},
        )
        roads = model.get("roads", {})
        self.assertTrue(roads.get("available"))
        self.assertEqual(len(roads["roads"]), 2)

    def test_main_road_side_index_in_model(self):
        model = build_site_model(SQUARE_SITE, {"site_objects": [MAIN_ROAD]})
        roads = model["roads"]
        self.assertIsNotNone(roads["main_road_side_index"])

    def test_no_site_objects_yields_ambiguity_in_roads(self):
        model = build_site_model(SQUARE_SITE, {})
        roads = model.get("roads", {})
        self.assertFalse(roads.get("available", True))
        self.assertEqual(roads.get("ambiguity"), "no_road_data")

    def test_non_road_site_objects_ignored(self):
        objects = [
            {"type": "attractor", "geometry": [[50, 50]]},
            MAIN_ROAD,
        ]
        model = build_site_model(SQUARE_SITE, {"site_objects": objects})
        roads = model["roads"]
        self.assertTrue(roads["available"])
        self.assertEqual(len(roads["roads"]), 1)

    def test_complex_site_with_roads(self):
        # Phase-2 tool should work on a non-orthogonal site without error.
        road = {
            "type": "road",
            "centerline": [[-20.0, -5.0], [160.0, 25.0]],
            "width_m": 15.0,
            "hierarchy": "main",
            "name": "Diagonal Road",
        }
        model = build_site_model(COMPLEX_SITE, {"site_objects": [road]})
        roads = model["roads"]
        self.assertTrue(roads["available"])
        self.assertIsNotNone(roads["main_road_side_index"])


if __name__ == "__main__":
    unittest.main()
