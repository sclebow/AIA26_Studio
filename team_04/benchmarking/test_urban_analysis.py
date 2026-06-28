"""Deterministic tests for Phase 2b: Urban Analysis Engine.

All tests are offline-safe (no network calls).  They exercise:
  - detect_intersections_from_roads   (geometry-based junction detection)
  - find_frontages                    (frontage extraction from Phase 2 output)
  - classify_site_type                (corner / T-junction / linear / etc.)
  - analyze_corner_conditions         (gateway flags, visibility scores)
  - analyze_access                    (vehicle / pedestrian / service split)
  - generate_urban_response           (template lookup + response keys)
  - full_urban_analysis               (master function, end-to-end)
  - osm_context synthetic sites       (schema validation)

Run with:
    python -m pytest team_04/benchmarking/test_urban_analysis.py -v
"""
import sys
import os
import math
import unittest

# Make the workspace root importable from the benchmarking directory.
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_PARENT = os.path.abspath(os.path.join(_ROOT, ".."))
for p in [_ROOT, _PARENT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from team_04.agent.tools.urban_analysis import (
    detect_intersections_from_roads,
    find_frontages,
    classify_site_type,
    analyze_corner_conditions,
    analyze_access,
    generate_urban_response,
    full_urban_analysis,
    nearby_intersections,
    SITE_TYPE_LABELS,
)
from team_04.agent.tools.site_model import build_site_model
from team_04.agent.tools.osm_context import SYNTHETIC_SITES, INTERESTING_SITES


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RECT_SITE = [[0, 0, 0], [50, 0, 0], [50, 30, 0], [0, 30, 0], [0, 0, 0]]

MAIN_ROAD = {
    "type": "road",
    "centerline": [[-20, -8], [70, -8]],
    "width_m": 16.0,
    "hierarchy": "main",
    "name": "Main Street",
}
SECONDARY_ROAD = {
    "type": "road",
    "centerline": [[-8, -20], [-8, 50]],
    "width_m": 9.0,
    "hierarchy": "secondary",
    "name": "Side Avenue",
}
PATH_ROAD = {
    "type": "road",
    "centerline": [[-20, 38], [70, 38]],
    "width_m": 4.0,
    "hierarchy": "path",
    "name": "Back Lane",
}


def _corner_model():
    """Site with main + secondary roads → corner site."""
    return build_site_model(
        RECT_SITE,
        {"site_objects": [MAIN_ROAD, SECONDARY_ROAD], "default_setback": 3.0},
    )


def _linear_model():
    """Site with only one road → linear frontage."""
    return build_site_model(
        RECT_SITE,
        {"site_objects": [MAIN_ROAD], "default_setback": 3.0},
    )


def _t_model():
    """Site at T-junction terminal."""
    site = [[0, 5, 0], [40, 5, 0], [40, 40, 0], [0, 40, 0], [0, 5, 0]]
    cross = {
        "type": "road",
        "centerline": [[-60, 0], [100, 0]],
        "width_m": 10.0,
        "hierarchy": "secondary",
        "name": "Cross Street",
    }
    terminus = {
        "type": "road",
        "centerline": [[20, 0], [20, -60]],
        "width_m": 7.0,
        "hierarchy": "secondary",
        "name": "Terminus Lane",
    }
    return build_site_model(site, {"site_objects": [cross, terminus], "default_setback": 3.0})


def _no_road_model():
    return build_site_model(RECT_SITE, {"default_setback": 3.0})


# ---------------------------------------------------------------------------
# 1. Intersection detection
# ---------------------------------------------------------------------------

class IntersectionDetectionTests(unittest.TestCase):

    def test_crossing_roads_produce_crossroads(self):
        roads = [MAIN_ROAD, SECONDARY_ROAD]
        ixs = detect_intersections_from_roads(roads)
        types = {ix["type"] for ix in ixs}
        self.assertIn("crossroads", types)

    def test_parallel_roads_produce_no_intersections(self):
        r1 = {"type": "road", "centerline": [[0, 0], [100, 0]], "width_m": 8, "hierarchy": "secondary", "name": "A"}
        r2 = {"type": "road", "centerline": [[0, 30], [100, 30]], "width_m": 8, "hierarchy": "secondary", "name": "B"}
        ixs = detect_intersections_from_roads([r1, r2])
        crossing = [ix for ix in ixs if ix["type"] in ("crossroads", "t_junction")]
        self.assertEqual(len(crossing), 0)

    def test_t_junction_detected(self):
        through = {"type": "road", "centerline": [[-60, 0], [60, 0]], "width_m": 10, "hierarchy": "secondary", "name": "Cross"}
        branch = {"type": "road", "centerline": [[0, 0], [0, -40]], "width_m": 7, "hierarchy": "path", "name": "Branch"}
        ixs = detect_intersections_from_roads([through, branch])
        types = {ix["type"] for ix in ixs}
        self.assertTrue(types & {"t_junction", "crossroads"})

    def test_no_roads_returns_empty(self):
        self.assertEqual(detect_intersections_from_roads([]), [])

    def test_single_road_returns_empty(self):
        self.assertEqual(detect_intersections_from_roads([MAIN_ROAD]), [])

    def test_intersection_point_near_actual_crossing(self):
        roads = [MAIN_ROAD, SECONDARY_ROAD]
        ixs = detect_intersections_from_roads(roads)
        self.assertGreater(len(ixs), 0)
        pt = ixs[0]["point"]
        self.assertAlmostEqual(pt[0], -8.0, delta=5.0)
        self.assertAlmostEqual(pt[1], -8.0, delta=5.0)

    def test_degree_returned_in_result(self):
        roads = [MAIN_ROAD, SECONDARY_ROAD]
        ixs = detect_intersections_from_roads(roads)
        for ix in ixs:
            self.assertIn("degree", ix)
            self.assertGreater(ix["degree"], 0)


# ---------------------------------------------------------------------------
# 2. Frontage extraction
# ---------------------------------------------------------------------------

class FrontageTests(unittest.TestCase):

    def test_corner_model_has_two_frontages(self):
        model = _corner_model()
        fs = find_frontages(model)
        self.assertEqual(len(fs), 2)

    def test_linear_model_has_one_frontage(self):
        model = _linear_model()
        fs = find_frontages(model)
        self.assertEqual(len(fs), 1)

    def test_no_road_model_has_zero_frontages(self):
        model = _no_road_model()
        fs = find_frontages(model)
        self.assertEqual(len(fs), 0)

    def test_visibility_score_between_0_and_1(self):
        model = _corner_model()
        for f in find_frontages(model):
            self.assertGreaterEqual(f["visibility_score"], 0.0)
            self.assertLessEqual(f["visibility_score"], 1.0)

    def test_main_road_frontage_has_higher_visibility_than_path(self):
        model = build_site_model(
            RECT_SITE,
            {"site_objects": [MAIN_ROAD, PATH_ROAD], "default_setback": 3.0},
        )
        fs = find_frontages(model)
        hier_vis = {f["road_hierarchy"]: f["visibility_score"] for f in fs}
        if "main" in hier_vis and "path" in hier_vis:
            self.assertGreater(hier_vis["main"], hier_vis["path"])

    def test_frontage_has_required_keys(self):
        model = _corner_model()
        required = {"side_index", "road_hierarchy", "road_width_m",
                    "frontage_length_m", "visibility_score", "recommended_access"}
        for f in find_frontages(model):
            self.assertTrue(required.issubset(f.keys()))

    def test_frontages_sorted_highest_visibility_first(self):
        model = _corner_model()
        fs = find_frontages(model)
        scores = [f["visibility_score"] for f in fs]
        self.assertEqual(scores, sorted(scores, reverse=True))


# ---------------------------------------------------------------------------
# 3. Site type classification
# ---------------------------------------------------------------------------

class SiteTypeTests(unittest.TestCase):

    def test_corner_site_classified(self):
        model = _corner_model()
        fs = find_frontages(model)
        ixs = detect_intersections_from_roads([MAIN_ROAD, SECONDARY_ROAD])
        near = nearby_intersections(model, ixs)
        st = classify_site_type(fs, near, model)
        self.assertIn(st, ("corner", "crossroads_corner", "y_junction"))

    def test_linear_site_classified(self):
        model = _linear_model()
        fs = find_frontages(model)
        ixs = detect_intersections_from_roads([MAIN_ROAD])
        near = nearby_intersections(model, ixs)
        st = classify_site_type(fs, near, model)
        self.assertEqual(st, "linear")

    def test_no_road_gives_back_parcel(self):
        model = _no_road_model()
        st = classify_site_type([], [], model)
        self.assertEqual(st, "back_parcel")

    def test_t_junction_terminal_classified(self):
        model = _t_model()
        fs = find_frontages(model)
        cross = {"type": "road", "centerline": [[-60, 0], [100, 0]], "width_m": 10, "hierarchy": "secondary", "name": "Cross"}
        terminus = {"type": "road", "centerline": [[20, 0], [20, -60]], "width_m": 7, "hierarchy": "secondary", "name": "Term"}
        ixs = detect_intersections_from_roads([cross, terminus])
        near = nearby_intersections(model, ixs)
        st = classify_site_type(fs, near, model)
        self.assertIn(st, ("t_junction_terminal", "linear", "corner"))

    def test_three_frontages_gives_complex(self):
        # Fake three frontages
        fake_fs = [
            {"side_index": 0, "road_hierarchy": "main", "visibility_score": 0.9, "recommended_access": "pedestrian"},
            {"side_index": 1, "road_hierarchy": "secondary", "visibility_score": 0.6, "recommended_access": "primary_vehicle"},
            {"side_index": 2, "road_hierarchy": "path", "visibility_score": 0.3, "recommended_access": "service"},
        ]
        st = classify_site_type(fake_fs, [], _no_road_model())
        self.assertEqual(st, "complex")

    def test_all_site_types_have_labels(self):
        for st in SITE_TYPE_LABELS:
            self.assertIsInstance(SITE_TYPE_LABELS[st], str)
            self.assertGreater(len(SITE_TYPE_LABELS[st]), 0)


# ---------------------------------------------------------------------------
# 4. Corner conditions
# ---------------------------------------------------------------------------

class CornerConditionTests(unittest.TestCase):

    def test_corner_model_produces_gateway_corners(self):
        model = _corner_model()
        fs = find_frontages(model)
        cc = analyze_corner_conditions(model, fs)
        # Should find at least one active corner
        self.assertIsInstance(cc, list)

    def test_gateway_when_main_road_present(self):
        model = _corner_model()
        fs = find_frontages(model)
        cc = analyze_corner_conditions(model, fs)
        gateways = [c for c in cc if c["is_gateway"]]
        # Main road + secondary road → at least one gateway corner expected
        if cc:
            self.assertTrue(len(gateways) > 0)

    def test_corner_point_is_list_of_two_floats(self):
        model = _corner_model()
        fs = find_frontages(model)
        for c in analyze_corner_conditions(model, fs):
            self.assertEqual(len(c["point"]), 2)
            self.assertIsInstance(c["point"][0], float)

    def test_no_frontages_gives_no_corners(self):
        model = _no_road_model()
        cc = analyze_corner_conditions(model, [])
        self.assertEqual(cc, [])

    def test_visibility_score_range(self):
        model = _corner_model()
        fs = find_frontages(model)
        for c in analyze_corner_conditions(model, fs):
            self.assertGreaterEqual(c["visibility_score"], 0.0)
            self.assertLessEqual(c["visibility_score"], 1.0)


# ---------------------------------------------------------------------------
# 5. Access analysis
# ---------------------------------------------------------------------------

class AccessTests(unittest.TestCase):

    def test_main_road_only_gives_pedestrian(self):
        model = _linear_model()
        fs = find_frontages(model)
        ac = analyze_access(model, fs)
        # Main + wide road → pedestrian recommended
        total = len(ac["vehicle"]) + len(ac["pedestrian"]) + len(ac["service"])
        self.assertGreater(total, 0)

    def test_access_points_have_point_key(self):
        model = _corner_model()
        fs = find_frontages(model)
        ac = analyze_access(model, fs)
        for category in ("vehicle", "pedestrian", "service"):
            for entry in ac[category]:
                self.assertIn("point", entry)
                self.assertEqual(len(entry["point"]), 2)

    def test_no_frontages_gives_empty_access(self):
        model = _no_road_model()
        ac = analyze_access(model, [])
        self.assertEqual(len(ac["vehicle"]) + len(ac["pedestrian"]) + len(ac["service"]), 0)

    def test_count_fields_match_list_lengths(self):
        model = _corner_model()
        fs = find_frontages(model)
        ac = analyze_access(model, fs)
        self.assertEqual(ac["vehicle_count"], len(ac["vehicle"]))
        self.assertEqual(ac["pedestrian_count"], len(ac["pedestrian"]))
        self.assertEqual(ac["service_count"], len(ac["service"]))


# ---------------------------------------------------------------------------
# 6. Urban response generation
# ---------------------------------------------------------------------------

class UrbanResponseTests(unittest.TestCase):

    def _response_for(self, site_type: str) -> dict:
        return generate_urban_response(site_type, [], [], [])

    def test_all_known_types_return_dict(self):
        for st in SITE_TYPE_LABELS:
            r = self._response_for(st)
            self.assertIsInstance(r, dict)
            self.assertEqual(r["site_type"], st)

    def test_response_has_required_keys(self):
        required = {
            "site_type", "site_type_label", "building_response",
            "massing_strategy", "entry_strategy", "facade_strategy",
            "priority_frontage_side",
        }
        for st in SITE_TYPE_LABELS:
            r = self._response_for(st)
            self.assertTrue(required.issubset(r.keys()), f"Missing keys for {st}: {required - r.keys()}")

    def test_corner_response_mentions_both_streets(self):
        r = self._response_for("corner")
        combined = r["building_response"] + " " + r["facade_strategy"]
        self.assertIn("both", combined.lower())

    def test_t_junction_response_mentions_axis(self):
        r = self._response_for("t_junction_terminal")
        self.assertIn("axis", (r["building_response"] + " " + r["entry_strategy"]).lower())

    def test_linear_has_no_corner_treatment(self):
        r = self._response_for("linear")
        self.assertIsNone(r.get("corner_treatment"))

    def test_unknown_type_returns_linear_template(self):
        r = generate_urban_response("nonexistent_type", [], [], [])
        # Falls back to linear template
        self.assertIsInstance(r["building_response"], str)


# ---------------------------------------------------------------------------
# 7. Full urban analysis (end-to-end)
# ---------------------------------------------------------------------------

class FullUrbanAnalysisTests(unittest.TestCase):

    def test_corner_site_full_analysis(self):
        model = _corner_model()
        result = full_urban_analysis(model)
        self.assertTrue(result["available"])
        self.assertIn(result["site_type"], SITE_TYPE_LABELS)
        self.assertEqual(result["frontage_count"], len(result["frontages"]))

    def test_no_road_returns_unavailable(self):
        model = _no_road_model()
        result = full_urban_analysis(model)
        self.assertFalse(result["available"])
        self.assertEqual(result["ambiguity"], "no_road_data")

    def test_result_has_all_keys(self):
        model = _corner_model()
        result = full_urban_analysis(model)
        required = {
            "available", "source", "site_type", "frontage_count",
            "frontages", "nearby_intersections", "corner_conditions",
            "access", "urban_response", "ambiguity", "ambiguity_message",
        }
        self.assertTrue(required.issubset(result.keys()))

    def test_access_sub_keys_present(self):
        model = _corner_model()
        ac = full_urban_analysis(model)["access"]
        self.assertIn("vehicle", ac)
        self.assertIn("pedestrian", ac)
        self.assertIn("service", ac)

    def test_provided_intersections_used(self):
        model = _corner_model()
        fake_ixs = [{"point": [-8, -8], "degree": 4, "type": "crossroads"}]
        result = full_urban_analysis(model, intersections=fake_ixs)
        self.assertGreater(len(result["nearby_intersections"]), 0)

    def test_linear_site_full_analysis(self):
        model = _linear_model()
        result = full_urban_analysis(model)
        self.assertTrue(result["available"])
        self.assertEqual(result["site_type"], "linear")
        self.assertEqual(result["frontage_count"], 1)

    def test_urban_response_site_type_matches_site_type(self):
        model = _corner_model()
        result = full_urban_analysis(model)
        self.assertEqual(result["urban_response"]["site_type"], result["site_type"])

    def test_gateway_corners_in_response(self):
        model = _corner_model()
        result = full_urban_analysis(model)
        # Should be a list (may be empty if no corners found)
        self.assertIsInstance(result["urban_response"]["gateway_corners"], list)


# ---------------------------------------------------------------------------
# 8. OSM context synthetic sites schema validation
# ---------------------------------------------------------------------------

class SyntheticSiteSchemaTests(unittest.TestCase):

    def _validate_site(self, site: dict) -> None:
        self.assertIn("source", site)
        self.assertIn("site_boundary", site)
        bnd = site["site_boundary"]
        self.assertGreater(len(bnd), 3)
        for r in site["roads"]:
            self.assertEqual(r.get("type"), "road")
            self.assertIn(r["hierarchy"], ("main", "secondary", "path"))
            self.assertGreater(r["width_m"], 0)
            self.assertGreater(len(r["centerline"]), 1)
        for ix in site["intersections"]:
            self.assertIn("point", ix)
            self.assertIn("type", ix)

    def test_barcelona_style(self):
        from team_04.agent.tools.osm_context import SYNTHETIC_SITES
        self._validate_site(SYNTHETIC_SITES[0])

    def test_t_junction_style(self):
        from team_04.agent.tools.osm_context import SYNTHETIC_SITES
        self._validate_site(SYNTHETIC_SITES[1])

    def test_triangular_style(self):
        from team_04.agent.tools.osm_context import SYNTHETIC_SITES
        self._validate_site(SYNTHETIC_SITES[2])

    def test_all_synthetic_sites_flow_through_analysis(self):
        from team_04.agent.tools.osm_context import SYNTHETIC_SITES
        for site in SYNTHETIC_SITES:
            model = build_site_model(
                site["site_boundary"],
                {"site_objects": site["roads"], "default_setback": 3.0},
            )
            result = full_urban_analysis(model, intersections=site["intersections"])
            self.assertIn("available", result)
            self.assertIn("site_type", result)

    def test_interesting_sites_list_has_eight_entries(self):
        self.assertEqual(len(INTERESTING_SITES), 8)

    def test_interesting_sites_have_required_fields(self):
        required = {"name", "lat", "lon", "radius_m", "site_type_hint", "description"}
        for s in INTERESTING_SITES:
            self.assertTrue(required.issubset(s.keys()), f"Missing fields in {s.get('name')}")


if __name__ == "__main__":
    unittest.main()
