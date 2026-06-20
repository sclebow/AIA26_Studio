"""Deterministic regressions for Phase 0 (design brief + site model).

No LLM and no MCP are required — these exercise the dataclass validation, the
fallback extractor, the graph node's brief consumption, and the site model.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.brief import extract_brief_fallback, resolve_brief
from agent.decision_engine import RuleBasedPlanner, _active_brief_signals, _repair_generate_shape_decision
from agent.graph import run_agent
from agent.models import BuildingSpec, DesignBrief, PlanStep, RoutingDecision
from agent.tool_catalog import ToolCatalog
from agent.tools.site_model import build_site_model

# Reuse the existing in-memory tool harness from the agent graph tests.
from benchmarking.test_agent_graph import AgentGraphTests, ScriptedDecisionEngine


SQUARE_SITE = [
    [0.0, 0.0, 0.0],
    [100.0, 0.0, 0.0],
    [100.0, 100.0, 0.0],
    [0.0, 100.0, 0.0],
    [0.0, 0.0, 0.0],
]


class DesignBriefModelTests(unittest.TestCase):
    def test_round_trips_through_state(self) -> None:
        brief = DesignBrief(
            building_count=2,
            buildings=(
                BuildingSpec(shape_preference="U", footprint_area_sqm=800.0, storeys=4),
                BuildingSpec(shape_preference="L", intent_text="open to courtyard"),
            ),
            courtyard_requested=True,
            courtyard_qualities=("quiet", "sunny"),
            parking_requested=True,
            source="llm",
        )
        restored = DesignBrief.from_payload(brief.to_state())
        self.assertEqual(restored.building_count, 2)
        self.assertEqual(restored.buildings[0].shape_preference, "U")
        self.assertEqual(restored.buildings[0].footprint_area_sqm, 800.0)
        self.assertEqual(restored.buildings[1].intent_text, "open to courtyard")
        self.assertEqual(restored.courtyard_qualities, ("quiet", "sunny"))
        self.assertTrue(restored.parking_requested)
        self.assertEqual(restored.source, "llm")

    def test_clamps_and_defaults_junk_input(self) -> None:
        brief = DesignBrief.from_payload(
            {
                "building_count": -3,
                "buildings": [{"shape_preference": "banana"}, "not-a-dict"],
                "view_weight": 5.0,
                "sun_weight": -1.0,
                "alignment_weight": "abc",
                "requested_rotation_deg": "nope",
                "courtyard_qualities": "quiet",
            }
        )
        # building_count floored to at least the number of valid specs (1 here).
        self.assertGreaterEqual(brief.building_count, 1)
        self.assertEqual(brief.buildings[0].shape_preference, "auto")  # invalid -> auto
        self.assertEqual(brief.view_weight, 1.0)   # clamped down
        self.assertEqual(brief.sun_weight, 0.0)    # clamped up
        self.assertEqual(brief.alignment_weight, 0.5)  # junk -> default
        self.assertIsNone(brief.requested_rotation_deg)
        self.assertEqual(brief.courtyard_qualities, ("quiet",))

    def test_count_never_below_explicit_specs(self) -> None:
        brief = DesignBrief.from_payload(
            {"building_count": 1, "buildings": [{}, {}, {}]}
        )
        self.assertEqual(brief.building_count, 3)

    def test_empty_payload_is_single_auto_building(self) -> None:
        brief = DesignBrief.from_payload({})
        self.assertEqual(brief.building_count, 1)
        self.assertEqual(brief.spec_for_index(0).shape_preference, "auto")
        self.assertEqual(brief.source, "fallback")


class FallbackExtractorTests(unittest.TestCase):
    def test_extracts_count_shape_and_area(self) -> None:
        brief = extract_brief_fallback(
            "Place two U-shaped buildings with a building area of 800 square meters.",
            {},
        )
        self.assertEqual(brief.building_count, 2)
        self.assertEqual(brief.buildings[0].shape_preference, "U")
        self.assertEqual(brief.buildings[0].footprint_area_sqm, 800.0)
        self.assertTrue(brief.courtyard_requested)  # U shape implies courtyard
        self.assertEqual(brief.source, "fallback")

    def test_respects_explicit_layout_count_and_intents(self) -> None:
        brief = extract_brief_fallback(
            "Design an L-shaped office building.",
            {"target_building_count": 2, "building_intents": ["calm west edge", "face the street"]},
        )
        self.assertEqual(brief.building_count, 2)
        self.assertEqual(brief.buildings[0].use, "office")
        self.assertEqual(brief.buildings[0].intent_text, "calm west edge")
        self.assertEqual(brief.buildings[1].intent_text, "face the street")

    def test_detects_parking_rotation_and_weights(self) -> None:
        brief = extract_brief_fallback(
            "One building, provide parking, rotate the building by 30 degrees, daylight matters most.",
            {},
        )
        self.assertTrue(brief.parking_requested)
        self.assertEqual(brief.requested_rotation_deg, 30.0)
        self.assertGreater(brief.sun_weight, 0.5)

    def test_vague_prompt_does_not_invent_values(self) -> None:
        brief = extract_brief_fallback("Make something nice on the site.", {})
        self.assertEqual(brief.building_count, 1)
        self.assertEqual(brief.buildings[0].shape_preference, "auto")
        self.assertIsNone(brief.buildings[0].footprint_area_sqm)
        self.assertIsNone(brief.requested_rotation_deg)

    def test_resolve_brief_uses_llm_engine_when_present(self) -> None:
        class StubEngine:
            def extract_brief(self, user_prompt, layout_payload=None):
                return DesignBrief(building_count=3, source="llm")

        brief = resolve_brief(StubEngine(), "whatever", {})
        self.assertEqual(brief.building_count, 3)
        self.assertEqual(brief.source, "llm")

    def test_resolve_brief_falls_back_when_engine_raises(self) -> None:
        class BrokenEngine:
            def extract_brief(self, user_prompt, layout_payload=None):
                raise RuntimeError("no network")

        brief = resolve_brief(BrokenEngine(), "two buildings", {})
        self.assertEqual(brief.source, "fallback")
        self.assertEqual(brief.building_count, 2)


class BriefConsumptionTests(unittest.TestCase):
    def test_active_brief_signals_selects_current_building(self) -> None:
        state = {
            "design_brief": DesignBrief(
                building_count=2,
                buildings=(
                    BuildingSpec(shape_preference="L"),
                    BuildingSpec(shape_preference="U"),
                ),
                requested_rotation_deg=15.0,
            ).to_state(),
            "placed_buildings": [{"geometry_id": "shape-001"}],
        }
        spec, rotation = _active_brief_signals(state)
        self.assertEqual(spec["shape_preference"], "U")  # second building is active
        self.assertEqual(rotation, 15.0)

    def test_repair_prefers_brief_shape_over_prompt(self) -> None:
        catalog = ToolCatalog.from_discovered_tools(AgentGraphTests._build_tool_client().list_tools())
        active_step = PlanStep(
            step_id="generate_shape",
            action="generate_shape",
            goal="Create the next geometry candidate for building 1.",
            status="pending",
        )
        repaired = _repair_generate_shape_decision(
            RoutingDecision(action="generate_shape", reasoning="Generate."),
            {
                # Prompt says nothing about shape; the brief carries U + area.
                "user_prompt": "Design a building on this site.",
                "design_brief": DesignBrief(
                    building_count=1,
                    buildings=(BuildingSpec(shape_preference="U", footprint_area_sqm=1200.0),),
                ).to_state(),
            },
            catalog,
            active_step,
        )
        self.assertEqual(repaired.tool_calls[0].arguments["building_type"], "U")
        self.assertEqual(repaired.tool_calls[0].arguments["area"], 1200.0)

    def test_full_run_extracts_brief_into_state(self) -> None:
        client = AgentGraphTests._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        final_state = run_agent(
            user_prompt="Place a U-shaped building on the site.",
            decision_engine=ScriptedDecisionEngine(),
            tool_client=client,
            catalog=catalog,
            initial_layout={"site_boundary": SQUARE_SITE, "target_building_count": 1},
            max_optimization_cycles=2,
            planner=RuleBasedPlanner(),
        )
        brief = final_state.get("design_brief", {})
        self.assertTrue(brief)
        self.assertEqual(brief["source"], "fallback")  # ScriptedDecisionEngine has no extract_brief
        self.assertTrue(brief["courtyard_requested"])
        # Site model should be built during read_site.
        site_model = final_state.get("site_model", {})
        self.assertTrue(site_model.get("available"))
        self.assertEqual(len(site_model.get("sides", [])), 4)


class SiteModelTests(unittest.TestCase):
    def test_builds_sides_corners_and_setbacks(self) -> None:
        model = build_site_model(SQUARE_SITE, {})
        self.assertTrue(model["available"])
        self.assertEqual(len(model["sides"]), 4)
        self.assertEqual(len(model["corners"]), 4)
        self.assertIsNotNone(model["setbacks"])
        self.assertAlmostEqual(model["setbacks"]["site_area_sqm"], 10000.0, places=1)
        # Phase 2 landed: model["roads"] is an analyze_roads result dict now.
        # When no roads are supplied it records the ambiguity instead of None.
        self.assertIsNotNone(model["roads"])
        self.assertFalse(model["roads"].get("available"))
        self.assertEqual(model["roads"].get("ambiguity"), "no_road_data")
        # Remaining phase placeholders still None (Phases 3 grid and 1 sun filled
        # directly by their respective tools, not by build_site_model).
        self.assertIsNone(model["grid"])
        self.assertIsNone(model["sun"])
        # Each side has an explicit slot for a future road tag.
        self.assertIn("adjacent_road", model["sides"][0])

    def test_degenerate_boundary_is_marked_unavailable(self) -> None:
        model = build_site_model([[0.0, 0.0]], {})
        self.assertFalse(model["available"])


if __name__ == "__main__":
    unittest.main()
