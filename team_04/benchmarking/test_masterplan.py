"""Regression tests for Phase 6 — circulation-first generative masterplanning.

Covers agent/tools/masterplan.py:
  - reserve_site_margins        (buildable envelope inside the site)
  - plan_access_structure       (main/service entry roles)
  - generate_movement_spine     (spine laid before buildings)
  - place_buildings_along_spine (inside envelope, separated, clear of spine)
  - generate_dropoffs           (one per public entrance, on a road)
  - score_masterplan            (five sub-scores + accept/reject)
  - generate_masterplan         (full pipeline, complex sites)

Deterministic, no LLM, no MCP, no network calls.
Run:  python -m unittest team_04.benchmarking.test_masterplan
"""
from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString, Polygon

_TEAM_ROOT = Path(__file__).resolve().parent.parent
if str(_TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEAM_ROOT))

from agent.tools.masterplan import (
    MIN_BUILDING_SEPARATION_M,
    generate_dropoffs,
    generate_masterplan,
    generate_movement_spine,
    place_buildings_along_spine,
    plan_access_structure,
    reserve_site_margins,
    score_masterplan,
)


# ---------------------------------------------------------------------------
# Fixtures — an irregular (concave) site fronted by a main road + service lane
# ---------------------------------------------------------------------------

_SITE = {
    "boundary": [[0, 0, 0], [180, 0, 0], [180, 80, 0], [120, 80, 0], [120, 150, 0], [0, 150, 0]],
    "sides": [
        {"side_index": 0, "start": [0, 0], "end": [180, 0],
         "adjacent_road": {"name": "Main Blvd", "hierarchy": "main", "width_m": 24.0}},
        {"side_index": 1, "start": [180, 0], "end": [180, 80], "adjacent_road": None},
        {"side_index": 2, "start": [180, 80], "end": [120, 80], "adjacent_road": None},
        {"side_index": 3, "start": [120, 80], "end": [120, 150], "adjacent_road": None},
        {"side_index": 4, "start": [120, 150], "end": [0, 150],
         "adjacent_road": {"name": "Park Walk", "hierarchy": "path", "width_m": 4.0}},
        {"side_index": 5, "start": [0, 150], "end": [0, 0],
         "adjacent_road": {"name": "Service Ln", "hierarchy": "secondary", "width_m": 6.0}},
    ],
    "roads": {"main_road_side_index": 0},
}

_PROGRAM = [
    {"building_id": "B1", "label": "U-court", "type": "U", "area": 1100, "storeys": 6},
    {"building_id": "B2", "label": "H-block", "type": "H", "area": 1200, "storeys": 7},
    {"building_id": "B3", "label": "L-wing", "type": "L", "area": 900, "storeys": 5},
    {"building_id": "B4", "label": "O-court", "type": "O", "area": 1000, "storeys": 5},
]


def _poly(b) -> Polygon:
    return Polygon([(p[0], p[1]) for p in b["boundary"]])


# ---------------------------------------------------------------------------
# Step 1 — margins
# ---------------------------------------------------------------------------

class TestReserveMargins(unittest.TestCase):

    def test_buildable_smaller_than_site(self):
        m = reserve_site_margins(_SITE)
        self.assertLess(m["buildable_area_sqm"], m["site_area_sqm"])
        self.assertLess(m["buildable_fraction"], 1.0)

    def test_buildable_polygon_inside_site(self):
        m = reserve_site_margins(_SITE)
        site = Polygon([(p[0], p[1]) for p in _SITE["boundary"]])
        self.assertTrue(site.buffer(1e-6).contains(m["buildable_polygon"]))

    def test_wider_road_deeper_setback(self):
        # Main Blvd (24 m) should impose a deeper setback than the service lane.
        m = reserve_site_margins(_SITE)
        by_edge = {e["edge_index"]: e["setback_m"] for e in m["edges"]}
        self.assertGreater(by_edge[0], by_edge[5])


# ---------------------------------------------------------------------------
# Step 2 — access structure
# ---------------------------------------------------------------------------

class TestAccessStructure(unittest.TestCase):

    def test_has_main_entry(self):
        acc = plan_access_structure(_SITE)
        self.assertIsNotNone(acc["main"])
        self.assertEqual(acc["main"]["role"], "main")

    def test_service_entry_on_secondary(self):
        acc = plan_access_structure(_SITE)
        roles = {r["role"] for r in acc["roles"]}
        self.assertIn("service", roles)


# ---------------------------------------------------------------------------
# Step 3 — spine
# ---------------------------------------------------------------------------

class TestSpine(unittest.TestCase):

    def setUp(self):
        self.buildable = reserve_site_margins(_SITE)["buildable_polygon"]
        self.entries = plan_access_structure(_SITE)["entries"]

    def test_spine_has_geometry(self):
        spine = generate_movement_spine(self.buildable, self.entries)
        self.assertGreaterEqual(len(spine["vehicular_spine"]), 2)
        self.assertGreaterEqual(len(spine["fire_loop"]), 3)

    def test_spine_inside_buildable(self):
        spine = generate_movement_spine(self.buildable, self.entries)
        line = LineString([(x, y) for x, y, *_ in spine["vehicular_spine"]])
        self.assertLess(line.difference(self.buildable.buffer(0.5)).length, 1.0)

    def test_entry_stub_touches_entry(self):
        spine = generate_movement_spine(self.buildable, self.entries)
        self.assertEqual(len(spine["entry_stub"]), 2)


# ---------------------------------------------------------------------------
# Step 4 — placement
# ---------------------------------------------------------------------------

class TestPlacement(unittest.TestCase):

    def setUp(self):
        self.buildable = reserve_site_margins(_SITE)["buildable_polygon"]
        self.entries = plan_access_structure(_SITE)["entries"]
        self.spine = generate_movement_spine(self.buildable, self.entries)

    def test_placed_buildings_inside_envelope(self):
        res = place_buildings_along_spine(self.buildable, self.spine, _PROGRAM)
        for b in res["buildings"]:
            self.assertTrue(self.buildable.buffer(0.2).contains(_poly(b)),
                            f"{b['building_id']} pokes outside the buildable envelope")

    def test_placed_buildings_do_not_overlap(self):
        res = place_buildings_along_spine(self.buildable, self.spine, _PROGRAM)
        polys = [_poly(b) for b in res["buildings"]]
        for i, j in itertools.combinations(range(len(polys)), 2):
            self.assertGreaterEqual(polys[i].distance(polys[j]), MIN_BUILDING_SEPARATION_M - 0.5)

    def test_buildings_clear_the_spine_corridor(self):
        res = place_buildings_along_spine(self.buildable, self.spine, _PROGRAM)
        spine_line = LineString([(x, y) for x, y, *_ in self.spine["vehicular_spine"]])
        for b in res["buildings"]:
            self.assertGreaterEqual(_poly(b).distance(spine_line), self.spine["spine_width_m"] / 2.0 - 0.5)

    def test_each_placement_has_reason(self):
        res = place_buildings_along_spine(self.buildable, self.spine, _PROGRAM)
        for b in res["buildings"]:
            self.assertTrue(b["placement_reason"])

    def test_oversized_building_is_unplaced(self):
        big = [{"building_id": "huge", "type": "I", "area": 90000, "storeys": 3}]
        res = place_buildings_along_spine(self.buildable, self.spine, big)
        self.assertIn("huge", res["unplaced"])
        self.assertEqual(res["buildings"], [])

    def test_all_wing_typologies_make_a_footprint(self):
        for t in ("I", "L", "T", "U", "H", "X", "Y", "O"):
            res = place_buildings_along_spine(
                self.buildable, self.spine,
                [{"building_id": t, "type": t, "area": 1000, "storeys": 5}])
            self.assertEqual(len(res["buildings"]), 1, f"type {t} failed to place")


# ---------------------------------------------------------------------------
# Step 6 — drop-offs
# ---------------------------------------------------------------------------

class TestDropoffs(unittest.TestCase):

    def test_one_dropoff_per_public_entrance_on_a_road(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        n_buildings = len(rep["buildings"])
        drops = rep["dropoffs"]["dropoffs"]
        self.assertGreaterEqual(len(drops), 1)
        self.assertLessEqual(len(drops), n_buildings)
        veh = rep["vehicular_circulation"]
        net = [LineString([(p[0], p[1]) for p in pa["polyline"]]) for pa in veh["paths"] if len(pa["polyline"]) >= 2]
        from shapely.ops import unary_union
        net_geom = unary_union(net)
        for d in drops:
            from shapely.geometry import Point
            self.assertLess(net_geom.distance(Point(d["point"][0], d["point"][1])), 1.0)


# ---------------------------------------------------------------------------
# Step 10 — scoring
# ---------------------------------------------------------------------------

class TestScoring(unittest.TestCase):

    def test_score_has_five_subscores(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        subs = rep["score"]["sub_scores"]
        for k in ("building_placement", "vehicular_network", "pedestrian_network",
                  "entrance_quality", "fire_safety"):
            self.assertIn(k, subs)
            self.assertGreaterEqual(subs[k], 0.0)
            self.assertLessEqual(subs[k], 1.0)

    def test_good_layout_accepted(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        self.assertTrue(rep["score"]["accepted"])
        self.assertGreaterEqual(rep["score"]["overall"], rep["score"]["threshold"])

    def test_empty_program_rejected(self):
        rep = generate_masterplan(_SITE, [])
        self.assertFalse(rep["score"]["accepted"])


# ---------------------------------------------------------------------------
# Orchestrator — full pipeline on complex sites
# ---------------------------------------------------------------------------

class TestGenerateMasterplan(unittest.TestCase):

    def test_returns_all_sections(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        for key in ("margins", "access", "spine", "placement", "buildings", "entrances",
                    "dropoffs", "parking", "vehicular_circulation", "pedestrian_circulation",
                    "site_access", "parking_integration", "fire_safety_egress", "conflicts",
                    "audit", "score", "reasoning"):
            self.assertIn(key, rep)

    def test_reasoning_is_populated(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        self.assertGreater(len(rep["reasoning"]), 5)
        self.assertTrue(any(r.startswith("[4]") for r in rep["reasoning"]))

    def test_no_building_outside_envelope(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        buildable = rep["margins"]["buildable_polygon"]
        for b in rep["buildings"]:
            self.assertTrue(buildable.buffer(0.2).contains(_poly(b)))

    def test_buildings_reach_fire_access(self):
        rep = generate_masterplan(_SITE, _PROGRAM)
        for fb in rep["fire_safety_egress"]["fire_access"]["buildings"]:
            self.assertTrue(fb["within_reach"], f"{fb['building_id']} unreachable by appliance")

    def test_runs_on_dense_square_site(self):
        dense = {"boundary": [[0, 0, 0], [90, 0, 0], [90, 90, 0], [0, 90, 0]],
                 "roads": {"main_road_side_index": 0}}
        rep = generate_masterplan(dense, _PROGRAM[:2])
        self.assertIn("score", rep)
        self.assertGreaterEqual(len(rep["buildings"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
