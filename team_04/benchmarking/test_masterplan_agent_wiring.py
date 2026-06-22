"""Wiring tests: generate_masterplan is reachable by the reactive agent.

Covers everything except the LangGraph assembly itself (which needs langgraph
installed): the tool wrapper + envelope, the local tool client registration, the
tool catalog group/action, the planner's masterplan workflow, and the reactive
intent detection in build_initial_state.

Run:  python -m unittest team_04.benchmarking.test_masterplan_agent_wiring
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_TEAM_ROOT = Path(__file__).resolve().parent.parent
if str(_TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEAM_ROOT))

from agent.decision_engine import RuleBasedPlanner
from agent.mcp_client import build_default_local_tool_client
from agent.state import build_initial_state, _wants_masterplan
from agent.tool_catalog import ToolCatalog, MASTERPLAN_GROUP
from agent.tools.masterplan import (
    MASTERPLAN_TOOL_DEFINITION,
    program_from_brief,
    run_masterplan_tool,
)

_SITE = [[0, 0, 0], [180, 0, 0], [180, 80, 0], [120, 80, 0], [120, 150, 0], [0, 150, 0]]


# ---------------------------------------------------------------------------
# Tool wrapper + envelope
# ---------------------------------------------------------------------------

class TestRunMasterplanTool(unittest.TestCase):

    def test_runs_on_a_bare_boundary(self):
        out = run_masterplan_tool(site_boundary=_SITE, target_building_count=3)
        self.assertTrue(out["success"])
        self.assertIn("placed_buildings", out["data"])
        self.assertGreaterEqual(len(out["data"]["placed_buildings"]), 1)
        # Each placed building carries a geometry_id + boundary for the explorer.
        for b in out["data"]["placed_buildings"]:
            self.assertTrue(str(b["geometry_id"]).startswith("masterplan_"))
            self.assertGreaterEqual(len(b["boundary"]), 3)

    def test_missing_boundary_is_reported_not_raised(self):
        out = run_masterplan_tool(site_boundary=[[0, 0]])
        self.assertFalse(out["success"])
        self.assertIn("error", out)

    def test_envelope_has_score_and_summary(self):
        out = run_masterplan_tool(site_boundary=_SITE, target_building_count=4)
        data = out["data"]
        self.assertIn("overall_score", data)
        self.assertIn("accepted", data)
        self.assertIsInstance(data["summary"], str)
        self.assertEqual(data["placed_count"], len(data["placed_buildings"]))

    def test_program_from_brief_maps_shapes_and_area(self):
        brief = {"buildings": [
            {"shape_preference": "U", "footprint_area_sqm": 1500, "storeys": 7},
            {"shape_preference": "auto"},
        ]}
        prog = program_from_brief(brief, target_building_count=2)
        self.assertEqual(prog[0]["type"], "U")
        self.assertEqual(prog[0]["area"], 1500.0)
        self.assertEqual(prog[0]["storeys"], 7)
        self.assertIn(prog[1]["type"], ("I", "L", "T", "U", "H", "X", "Y", "O"))

    def test_program_from_empty_brief_uses_count(self):
        prog = program_from_brief(None, target_building_count=3)
        self.assertEqual(len(prog), 3)


# ---------------------------------------------------------------------------
# Local tool client registration
# ---------------------------------------------------------------------------

class TestLocalClientRegistration(unittest.TestCase):

    def setUp(self):
        self.client = build_default_local_tool_client()

    def test_masterplan_is_listed(self):
        names = {t["name"] for t in self.client.list_tools()}
        self.assertIn("generate_masterplan", names)

    def test_call_tool_returns_placed_buildings(self):
        raw = self.client.call_tool("generate_masterplan",
                                    {"site_boundary": _SITE, "target_building_count": 3})
        parsed = json.loads(raw)
        self.assertTrue(parsed["success"])
        self.assertGreaterEqual(len(parsed["data"]["placed_buildings"]), 1)

    def test_call_tool_ignores_unknown_kwargs(self):
        # LocalToolClient filters args to the handler signature; extra keys (e.g.
        # an injected geometry_id) must not break the call.
        raw = self.client.call_tool("generate_masterplan",
                                    {"site_boundary": _SITE, "geometry_id": "x", "foo": 1})
        self.assertTrue(json.loads(raw)["success"])


# ---------------------------------------------------------------------------
# Tool catalog group + action
# ---------------------------------------------------------------------------

class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.catalog = ToolCatalog.from_discovered_tools(
            build_default_local_tool_client().list_tools())

    def test_action_maps_to_tool(self):
        self.assertEqual(self.catalog.names_for_action("generate_masterplan"),
                         ("generate_masterplan",))

    def test_group_constant(self):
        self.assertEqual(MASTERPLAN_GROUP, "masterplan")

    def test_rendered_catalog_mentions_masterplan(self):
        rendered = self.catalog.render_for_action("generate_masterplan")
        self.assertIn("generate_masterplan", rendered)


# ---------------------------------------------------------------------------
# Planner masterplan workflow
# ---------------------------------------------------------------------------

class TestPlannerMasterplanWorkflow(unittest.TestCase):

    def setUp(self):
        self.planner = RuleBasedPlanner()
        self.catalog = ToolCatalog.from_discovered_tools(
            build_default_local_tool_client().list_tools())

    def _actions(self, state):
        return [s.action for s in self.planner.build_plan(state, self.catalog)]

    def test_masterplan_step_present(self):
        state = {"workflow_mode": "masterplan", "site_context": {}}
        self.assertIn("generate_masterplan", self._actions(state))

    def test_masterplan_pending_after_site_read(self):
        state = {"workflow_mode": "masterplan", "site_context": {"x": 1}}
        steps = self.planner.build_plan(state, self.catalog)
        mp = next(s for s in steps if s.action == "generate_masterplan")
        self.assertEqual(mp.status, "pending")

    def test_report_pending_after_masterplan(self):
        state = {"workflow_mode": "masterplan", "site_context": {"x": 1},
                 "masterplan_result": {"summary": "done"}}
        steps = self.planner.build_plan(state, self.catalog)
        mp = next(s for s in steps if s.action == "generate_masterplan")
        report = next(s for s in steps if s.action == "report")
        self.assertEqual(mp.status, "completed")
        self.assertEqual(report.status, "pending")

    def test_full_workflow_has_no_masterplan_step(self):
        state = {"workflow_mode": "full", "site_context": {"x": 1}}
        self.assertNotIn("generate_masterplan", self._actions(state))


# ---------------------------------------------------------------------------
# Reactive intent detection
# ---------------------------------------------------------------------------

class TestIntentDetection(unittest.TestCase):

    def test_masterplan_prompt_switches_mode(self):
        for prompt in ("Create a masterplan for this site",
                       "Lay out the whole site with circulation and fire access",
                       "Give me a site plan"):
            st = build_initial_state(prompt, {"site_boundary": _SITE}, 4)
            self.assertEqual(st["workflow_mode"], "masterplan", prompt)

    def test_single_building_prompt_stays_full(self):
        st = build_initial_state("Design one L-shaped building on the site", {"site_boundary": _SITE}, 4)
        self.assertEqual(st["workflow_mode"], "full")

    def test_explicit_layout_mode_wins(self):
        st = build_initial_state("Design one L-shaped building",
                                 {"site_boundary": _SITE, "workflow_mode": "masterplan"}, 4)
        self.assertEqual(st["workflow_mode"], "masterplan")

    def test_detector_is_narrow(self):
        self.assertTrue(_wants_masterplan("draw the masterplan"))
        self.assertFalse(_wants_masterplan("place a tall tower"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
