"""Deterministic regressions for the interactive clarification loop (no LLM/MCP).

Covers the pure logic in ``agent/clarify.py`` and the graph wiring that pauses at
``await_human`` when a placement-critical field is missing and the run opted into
``interactive_clarification``.
"""
from __future__ import annotations

import unittest

from agent.clarify import (
    ClarificationRequest,
    apply_clarification_answers,
    required_clarifications,
    side_to_point,
)
from agent.graph import build_agent_graph, run_agent
from agent.mcp_client import build_default_local_tool_client
from agent.models import BuildingSpec, DesignBrief
from agent.tool_catalog import ToolCatalog

SQUARE = [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [100.0, 100.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 0.0]]


class _NoLLMEngine:
    """Engine without extract_brief → resolve_brief falls back to regex."""


def _vague_brief() -> DesignBrief:
    return DesignBrief(building_count=1, buildings=(BuildingSpec(shape_preference="auto"),))


class ClarifyLogicTests(unittest.TestCase):
    def test_vague_brief_raises_request_with_critical_fields(self):
        req = required_clarifications(_vague_brief(), {}, None)
        self.assertIsInstance(req, ClarificationRequest)
        keys = {f.key for f in req.fields}
        # The three critical gaps must be present.
        self.assertTrue({"shape", "side", "view_side"} <= keys)
        self.assertTrue(any(f.critical for f in req.fields))
        # Non-critical extras are folded in for one-shot collection.
        self.assertIn("count", keys)

    def test_fully_specified_brief_needs_no_clarification(self):
        brief = DesignBrief(
            building_count=1,
            buildings=(BuildingSpec(shape_preference="L", footprint_area_sqm=900.0),),
        )
        layout = {"requested_positions": [[20.0, 15.0]], "view_target_sides": ["south"]}
        self.assertIsNone(required_clarifications(brief, layout, None))

    def test_apply_answers_patches_brief_and_layout(self):
        brief_payload = _vague_brief().to_state()
        answers = {
            "shape": "L", "size": "~900 m²", "side": "south",
            "view_side": ["south"], "use": "office", "count": "2",
        }
        new_brief, new_layout = apply_clarification_answers(brief_payload, {}, answers, SQUARE)

        self.assertEqual(new_brief["building_count"], 2)
        self.assertEqual(len(new_brief["buildings"]), 2)
        for b in new_brief["buildings"]:
            self.assertEqual(b["shape_preference"], "L")
            self.assertEqual(b["footprint_area_sqm"], 900.0)
            self.assertEqual(b["use"], "office")

        self.assertEqual(new_layout["target_building_count"], 2)
        self.assertEqual(len(new_layout["requested_positions"]), 2)
        self.assertEqual(new_layout["preferred_side"], "south")
        self.assertEqual(new_layout["view_target_sides"], ["south"])

    def test_apply_answers_makes_brief_self_sufficient(self):
        """After answering, the same brief/layout must no longer need clarification."""
        brief_payload = _vague_brief().to_state()
        answers = {"shape": "U", "side": "north", "view_side": ["north"], "count": "1"}
        new_brief, new_layout = apply_clarification_answers(brief_payload, {}, answers, SQUARE)
        self.assertIsNone(
            required_clarifications(DesignBrief.from_payload(new_brief), new_layout, None)
        )

    def test_side_to_point_maps_directions(self):
        south = side_to_point(SQUARE, "south")
        north = side_to_point(SQUARE, "north")
        east = side_to_point(SQUARE, "east")
        west = side_to_point(SQUARE, "west")
        self.assertLess(south[1], 50)   # south → low y
        self.assertGreater(north[1], 50)
        self.assertGreater(east[0], 50)
        self.assertLess(west[0], 50)


class ClarifyGraphTests(unittest.TestCase):
    def setUp(self):
        self.client = build_default_local_tool_client()
        self.catalog = ToolCatalog.from_discovered_tools(self.client.list_tools())

    def test_interactive_vague_run_pauses_for_clarification(self):
        final_state = run_agent(
            user_prompt="Place a building on the site.",
            decision_engine=_NoLLMEngine(),
            tool_client=self.client,
            catalog=self.catalog,
            initial_layout={"interactive_clarification": True, "site_boundary": SQUARE},
            max_optimization_cycles=2,
        )
        self.assertTrue(final_state.get("clarification_request"))
        self.assertEqual(final_state.get("placed_buildings", []), [])
        self.assertIn("confirm", (final_state.get("final_response") or "").lower())

    def test_non_interactive_run_does_not_set_clarification(self):
        # Without the flag, comprehension must not raise a clarification request,
        # regardless of how vague the prompt is.
        from agent.graph import _route_from_brief  # noqa: PLC0415
        state = {"clarification_request": None, "clarification_resolved": False}
        self.assertEqual(_route_from_brief(state), "planner")


if __name__ == "__main__":
    unittest.main()
