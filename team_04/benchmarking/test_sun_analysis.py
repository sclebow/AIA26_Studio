"""Deterministic regressions for Phase 1 (sun analysis fitness).

No LLM and no MCP. These exercise the geometry of the sun-exposure model: the
worst-case preset vectors, facade exposure ordering (a facade that faces the sun
scores higher than one that turns away), full shadowing zeroing exposure, the
worst-site-side identification, and the optimizer's sun-avoidance objective.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.tools.site_model import build_site_model
from agent.tools.sun_analysis import (
    WORST_CASE_PRESETS,
    compute_sun_vectors,
    evaluate_sun_exposure,
    evaluate_sun_exposure_3d,
    identify_worst_sun_side,
    worst_case_sun_vector,
)

# A 10 m square building centred near the origin.
SQUARE_BUILDING = [
    [0.0, 0.0, 0.0],
    [10.0, 0.0, 0.0],
    [10.0, 10.0, 0.0],
    [0.0, 10.0, 0.0],
    [0.0, 0.0, 0.0],
]

SQUARE_SITE = [
    [0.0, 0.0, 0.0],
    [100.0, 0.0, 0.0],
    [100.0, 100.0, 0.0],
    [0.0, 100.0, 0.0],
    [0.0, 0.0, 0.0],
]

# Sun straight from the south (azimuth 180), 30° above the horizon.
SOUTH_SUN = [{"azimuth": 180.0, "altitude": 30.0, "weight": 1.0}]


class SunVectorTests(unittest.TestCase):
    def test_preset_returns_single_diagonal_vector(self) -> None:
        vectors = compute_sun_vectors(worst_case_preset="summer_west")
        self.assertEqual(len(vectors), 1)
        self.assertEqual(vectors[0]["azimuth"], WORST_CASE_PRESETS["summer_west"]["azimuth"])
        # Worst-case western sun sits low on the horizon.
        self.assertLess(vectors[0]["altitude"], 45.0)
        self.assertGreater(vectors[0]["azimuth"], 180.0)  # westerly

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(ValueError):
            worst_case_sun_vector("midnight_sun")

    def test_multi_hour_afternoon_sun_is_westerly(self) -> None:
        vectors = compute_sun_vectors(
            latitude=40.0, date="06-21", hours=[9.0, 12.0, 15.0], worst_case_preset=None
        )
        by_hour = {v["hour"]: v for v in vectors}
        # All daylight; noon highest; afternoon swings west, morning east.
        self.assertGreater(by_hour[12.0]["altitude"], by_hour[9.0]["altitude"])
        self.assertGreater(by_hour[15.0]["azimuth"], 180.0)   # afternoon → west of south
        self.assertLess(by_hour[9.0]["azimuth"], 180.0)       # morning → east of south

    def test_multi_hour_requires_astronomy_args(self) -> None:
        with self.assertRaises(ValueError):
            compute_sun_vectors(worst_case_preset=None)


class FacadeExposureTests(unittest.TestCase):
    def test_south_facade_more_exposed_than_north_for_south_sun(self) -> None:
        result = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN, piece_length=2.0)
        # Bucket each test point's normalized exposure by its facade normal.
        south = [p for p in result["per_test_point"] if p["outward_normal"][1] < -0.5]
        north = [p for p in result["per_test_point"] if p["outward_normal"][1] > 0.5]
        self.assertTrue(south and north)
        south_mean = sum(p["normalized_exposure"] for p in south) / len(south)
        north_mean = sum(p["normalized_exposure"] for p in north) / len(north)
        self.assertGreater(south_mean, north_mean)
        # The north facade turns fully away from a southern sun → no exposure.
        self.assertAlmostEqual(north_mean, 0.0, places=6)

    def test_score_is_unit_range_and_lower_is_better(self) -> None:
        result = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN)
        self.assertGreaterEqual(result["sun_exposure_score"], 0.0)
        self.assertLessEqual(result["sun_exposure_score"], 1.0)

    def test_no_sun_vectors_scores_zero(self) -> None:
        result = evaluate_sun_exposure(SQUARE_BUILDING, [])
        self.assertEqual(result["sun_exposure_score"], 0.0)
        self.assertEqual(result["test_point_count"], 0)

    def test_obstacle_shadows_the_south_facade(self) -> None:
        clear = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN)
        # A tall wide wall just south of the building blocks the southern sun.
        wall = {
            "boundary": [[-10.0, -8.0], [20.0, -8.0], [20.0, -4.0], [-10.0, -4.0]],
            "height": 40.0,
        }
        shaded = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN, [wall])
        self.assertLess(shaded["sun_exposure_score"], clear["sun_exposure_score"])
        # The most-exposed south point should now read (near) zero.
        south = [p for p in shaded["per_test_point"] if p["outward_normal"][1] < -0.5]
        self.assertTrue(all(p["normalized_exposure"] == 0.0 for p in south))

    def test_fast_path_matches_detail_path_score(self) -> None:
        detail = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN, return_ray_detail=True)
        fast = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN, return_ray_detail=False)
        self.assertAlmostEqual(detail["sun_exposure_score"], fast["sun_exposure_score"], places=6)
        self.assertEqual(fast["per_test_point"], [])


class WorstSideTests(unittest.TestCase):
    def test_south_sun_makes_south_side_worst(self) -> None:
        model = build_site_model(SQUARE_SITE, {})
        result = identify_worst_sun_side(model, SOUTH_SUN)
        self.assertTrue(result["available"])
        self.assertEqual(result["worst_side"]["compass_sector"], "S")
        # Sides turned away from a pure southern sun receive no exposure (the
        # north/east/west sides tie at 0); the best side is one of them.
        self.assertAlmostEqual(result["best_side"]["sun_exposure_score"], 0.0, places=6)
        self.assertGreater(
            result["worst_side"]["sun_exposure_score"],
            result["best_side"]["sun_exposure_score"],
        )
        # The north side specifically reads zero under a southern sun.
        north = next(s for s in result["per_side"] if s["compass_sector"] == "N")
        self.assertAlmostEqual(north["sun_exposure_score"], 0.0, places=6)

    def test_west_preset_makes_west_side_worst(self) -> None:
        model = build_site_model(SQUARE_SITE, {})
        result = identify_worst_sun_side(model, compute_sun_vectors())
        self.assertTrue(result["available"])
        self.assertIn(result["worst_compass_sector"], {"W", "SW"})

    def test_unavailable_site_model_is_handled(self) -> None:
        result = identify_worst_sun_side({"available": False}, SOUTH_SUN)
        self.assertFalse(result["available"])


class Sun3DTests(unittest.TestCase):
    """Height-aware facade exposure with per-floor mutual shading."""

    TOWER = [  # an 8-storey building (24 m) — the south facade faces the sun
        [0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 0.0],
    ]

    def test_uniform_exposure_without_obstacles(self) -> None:
        r = evaluate_sun_exposure_3d(self.TOWER, 24.0, SOUTH_SUN, [])
        self.assertEqual(r["n_floors"], 8)
        scores = [f["sun_exposure_score"] for f in r["per_floor"]]
        # With nothing shading, every floor sees the same facade geometry.
        self.assertAlmostEqual(min(scores), max(scores), places=6)
        self.assertGreater(scores[0], 0.0)
        self.assertGreaterEqual(r["sun_exposure_score_3d"], 0.0)
        self.assertLessEqual(r["sun_exposure_score_3d"], 1.0)

    def test_tall_neighbour_shades_only_lower_floors(self) -> None:
        # A 12 m wall right against the south facade shades floors below 12 m;
        # floors that rise above it keep their sun. This is the mutual-shading
        # behaviour a flat 2D projection cannot represent.
        wall = {"boundary": [[-5.0, -3.0], [15.0, -3.0], [15.0, -1.0], [-5.0, -1.0]], "height": 12.0}
        r = evaluate_sun_exposure_3d(self.TOWER, 24.0, SOUTH_SUN, [wall])
        per = {f["floor_number"]: f["sun_exposure_score"] for f in r["per_floor"]}
        # Floor 1 (z≈1.5 m) sits in shadow; the top floor (z≈22.5 m) is above the wall.
        self.assertLess(per[1], per[8])
        self.assertAlmostEqual(per[1], 0.0, places=6)
        self.assertGreater(per[8], 0.0)

    def test_cells_carry_normalized_exposure(self) -> None:
        r = evaluate_sun_exposure_3d(self.TOWER, 12.0, SOUTH_SUN, [])
        self.assertTrue(r["cells"])
        for c in r["cells"]:
            self.assertIn("sun_exposure", c)
            self.assertGreaterEqual(c["sun_exposure"], 0.0)
            self.assertLessEqual(c["sun_exposure"], 1.0)

    def test_fast_path_omits_cells(self) -> None:
        r = evaluate_sun_exposure_3d(self.TOWER, 12.0, SOUTH_SUN, [], return_ray_detail=False)
        self.assertNotIn("cells", r)
        self.assertIn("sun_exposure_score_3d", r)


class OptimizerObjectiveTests(unittest.TestCase):
    def test_registry_exposes_sun_avoidance(self) -> None:
        from agent.tools.view_optimizer import OBJECTIVE_REGISTRY, list_objectives

        self.assertIn("sun_avoidance", OBJECTIVE_REGISTRY)
        self.assertIn("sun_avoidance", list_objectives())

    def test_sun_avoidance_objective_inverts_exposure(self) -> None:
        from agent.tools.view_optimizer import _obj_sun_avoidance

        avoidance = _obj_sun_avoidance(SQUARE_BUILDING, obstacles=[], piece_length=2.0,
                                       sun_vectors=SOUTH_SUN)
        exposure = evaluate_sun_exposure(SQUARE_BUILDING, SOUTH_SUN)["sun_exposure_score"]
        self.assertAlmostEqual(avoidance, 1.0 - exposure, places=6)

    def test_sun_avoidance_is_one_without_vectors(self) -> None:
        from agent.tools.view_optimizer import _obj_sun_avoidance

        self.assertEqual(_obj_sun_avoidance(SQUARE_BUILDING, obstacles=[], piece_length=2.0), 1.0)

    def test_optimizer_runs_with_sun_objective(self) -> None:
        try:
            from agent.tools.view_optimizer import optimize_view_placement
        except Exception:  # pragma: no cover
            self.skipTest("view_optimizer import failed")
        try:
            result = optimize_view_placement(
                boundary=SQUARE_BUILDING,
                site_boundary=SQUARE_SITE,
                obstacles=[],
                sun_vectors=compute_sun_vectors(),
                sun_weight=0.5,
                population_size=12,
                generation_count=8,
                rotation_step_degrees=30,
            )
        except RuntimeError as exc:  # pymoo not installed in this kernel
            self.skipTest(f"pymoo unavailable: {exc}")
        self.assertTrue(result["optimized"])
        self.assertTrue(result["pareto_solutions"])
        top = result["pareto_solutions"][0]
        self.assertIsNotNone(top["sun_exposure_score"])
        self.assertGreaterEqual(top["sun_exposure_score"], 0.0)
        self.assertLessEqual(top["sun_exposure_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
