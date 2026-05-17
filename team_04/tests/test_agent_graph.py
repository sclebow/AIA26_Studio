from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.decision_engine import RuleBasedPlanner
from agent.graph import run_agent
from agent.mcp_client import CompositeToolClient, LocalToolClient
from agent.models import PlanStep, RoutingDecision, ToolCall
from agent.tools import IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION
from agent.tools import REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION
from agent.tools import REQUESTED_POSITION_CHECKER_TOOL_DEFINITION
from agent.tools import TOOL_DEFINITION as GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION
from agent.tools import generate_building_boundary, mock_check_requested_position, mock_import_building_boundary, mock_remaining_buildable_positions
from agent.tool_catalog import ToolCatalog


class FakeToolClient:
    def __init__(self) -> None:
        self.constraint_checks = 0
        self.calls: list[str] = []
        self._tools = [
            {"name": "site_boundary_reader_04"},
            {"name": "context_reader_04"},
            {"name": "legal_constraints_reader_04"},
            {"name": "rotate_mirror_tool_04"},
            {"name": "site_fit_checker_04"},
            {"name": "setback_checker_04"},
            {"name": "area_requirement_checker_04"},
            {"name": "adjacency_access_checker_04"},
            {"name": "tree_constraint_checker_04"},
            {"name": "spatial_intention_evaluator_04"},
            {"name": "performance_evaluator_04"},
            {"name": "shape_integrity_evaluator_04"},
        ]

    def list_tools(self) -> list[dict[str, object]]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, object]) -> str:
        self.calls.append(name)
        if name == "site_boundary_reader_04":
            return json.dumps({"data": {"site": "loaded"}})
        if name == "context_reader_04":
            return json.dumps({"data": {"context": {"roads": 1, "trees": 2}}})
        if name == "legal_constraints_reader_04":
            return json.dumps({"data": {"constraints": {"setback": 5}}})
        if name == "rotate_mirror_tool_04":
            return json.dumps({"data": {"geometry_id": "shape-002", "operation": "rotate"}})
        if name == "site_fit_checker_04":
            return json.dumps({"data": {"fits": True}})
        if name == "setback_checker_04":
            self.constraint_checks += 1
            return json.dumps({"data": {"compliant": self.constraint_checks > 1}})
        if name == "area_requirement_checker_04":
            return json.dumps({"data": {"gfa_compliant": True}})
        if name == "adjacency_access_checker_04":
            return json.dumps({"data": {"road_access_ok": True}})
        if name == "tree_constraint_checker_04":
            return json.dumps({"data": {"no_conflicts": True}})
        if name == "spatial_intention_evaluator_04":
            return json.dumps({"data": {"score": 0.91}})
        if name == "performance_evaluator_04":
            return json.dumps({"data": {"score": 0.88}})
        if name == "shape_integrity_evaluator_04":
            return json.dumps({"data": {"score": 0.94}})
        raise AssertionError(f"Unexpected tool call: {name}")

    def close(self) -> None:
        return None


class ScriptedDecisionEngine:
    def decide(self, state: dict[str, object], catalog: ToolCatalog, active_step: PlanStep) -> RoutingDecision:
        del catalog

        if active_step.action == "generate_shape":
            return RoutingDecision(
                action="generate_shape",
                reasoning="Create the initial massing.",
                tool_calls=(ToolCall(name="generate_building_boundary", arguments={"area": 900.0, "building_type": "I", "building_depth": 15.0}),),
            )
        if active_step.action == "optimize":
            return RoutingDecision(
                action="optimize",
                reasoning="Fix the setback violation.",
                tool_calls=(ToolCall(name="rotate_mirror_tool_04", arguments={"angle": 15}),),
            )
        return RoutingDecision(action=active_step.action, reasoning=active_step.goal)

    def build_report(self, state: dict[str, object]) -> str:
        geometry_id = state.get("geometry_id")
        violations = state.get("violations") or []
        evaluation_results = state.get("evaluation_results") or {}
        return (
            f"Final geometry: {geometry_id}. "
            f"Violations: {violations or ['none']}. "
            f"Evaluation tools: {sorted(evaluation_results.keys())}."
        )


class AgentGraphTests(unittest.TestCase):
    @staticmethod
    def _build_tool_client() -> CompositeToolClient:
        local_client = LocalToolClient(
            {
                GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                    GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION,
                    generate_building_boundary,
                ),
                IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                    IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION,
                    mock_import_building_boundary,
                ),
                REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION["name"]: (
                    REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION,
                    mock_remaining_buildable_positions,
                ),
                REQUESTED_POSITION_CHECKER_TOOL_DEFINITION["name"]: (
                    REQUESTED_POSITION_CHECKER_TOOL_DEFINITION,
                    mock_check_requested_position,
                ),
            }
        )
        return CompositeToolClient([local_client, FakeToolClient()])

    def test_hub_and_spoke_flow_completes(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        engine = ScriptedDecisionEngine()

        final_state = run_agent(
            user_prompt="Place a bar building and resolve any constraint issues.",
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout={"site": "placeholder"},
            max_optimization_cycles=2,
            planner=RuleBasedPlanner(),
        )

        self.assertEqual(final_state.get("geometry_id"), "shape-002")
        self.assertEqual(final_state.get("violations"), [])
        self.assertIn("Final geometry: shape-002.", final_state.get("final_response", ""))
        self.assertIn("rotate_mirror_tool_04", client.calls)
        self.assertGreaterEqual(client.calls.count("setback_checker_04"), 2)
        self.assertEqual(final_state.get("active_step_id"), "report")

    def test_await_human_finishes_without_blocking(self) -> None:
        class AwaitHumanEngine:
            def decide(self, state: dict[str, object], catalog: ToolCatalog, active_step: PlanStep) -> RoutingDecision:
                del state
                del catalog
                del active_step
                return RoutingDecision(
                    action="await_human",
                    reasoning="Need a clarification.",
                    user_question="Which frontage should the building prioritize?",
                )

            def build_report(self, state: dict[str, object]) -> str:
                return "unused"

        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        final_state = run_agent(
            user_prompt="Need clarification.",
            decision_engine=AwaitHumanEngine(),
            tool_client=client,
            catalog=catalog,
            initial_layout={"site": "placeholder"},
            max_optimization_cycles=1,
            planner=RuleBasedPlanner(),
        )

        self.assertEqual(
            final_state.get("final_response"),
            "Which frontage should the building prioritize?",
        )

    def test_planner_replans_after_each_major_step(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        engine = ScriptedDecisionEngine()

        final_state = run_agent(
            user_prompt="Plan and execute sequentially.",
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout={"site": "placeholder"},
            max_optimization_cycles=2,
            planner=RuleBasedPlanner(),
        )

        plan = final_state.get("plan", [])
        self.assertTrue(any(step.get("step_id") == "read_site" for step in plan))
        self.assertTrue(any(step.get("step_id") == "report" for step in plan))
        planner_messages = [message for message in final_state.get("messages", []) if message.startswith("Planner updated")]
        self.assertGreaterEqual(len(planner_messages), 3)

    def test_local_python_tool_is_discoverable(self) -> None:
        client = self._build_tool_client()
        tool_names = {tool["name"] for tool in client.list_tools()}
        self.assertIn("generate_building_boundary", tool_names)

    def test_planner_adds_multi_building_steps(self) -> None:
        planner = RuleBasedPlanner()
        catalog = ToolCatalog.from_discovered_tools(self._build_tool_client().list_tools())

        plan = planner.build_plan(
            {
                "site_context": {"site_boundary_reader_04": {"data": {"site": "loaded"}}},
                "geometry_id": "shape-001",
                "checked_geometry_id": "shape-001",
                "constraint_results": {"setback_checker_04": {"data": {"compliant": True}}},
                "violations": [],
                "evaluation_results": {"performance_evaluator_04": {"data": {"score": 0.9}}},
                "placed_buildings": [],
                "requested_positions": [[90.0, 30.0], [110.0, 50.0]],
                "requested_position_assessment": {},
                "target_building_count": 2,
            },
            catalog,
        )

        status_by_step = {step.step_id: step.status for step in plan}
        self.assertEqual(status_by_step["check_requested_position"], "pending")
        self.assertEqual(status_by_step["place_building"], "skipped")
        self.assertEqual(status_by_step["analyze_remaining_positions"], "skipped")

    def test_multi_building_runtime_places_first_building_and_analyzes_remaining_positions(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        engine = ScriptedDecisionEngine()

        final_state = run_agent(
            user_prompt="Place two buildings on the site and check the user's preferred locations.",
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout={
                "site_boundary": [
                    [0.0, 0.0, 0.0],
                    [140.0, 0.0, 0.0],
                    [140.0, 90.0, 0.0],
                    [0.0, 90.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
                "target_building_count": 2,
                "requested_positions": [[35.0, 45.0], [95.0, 45.0]],
            },
            max_optimization_cycles=1,
            planner=RuleBasedPlanner(),
        )

        self.assertEqual(len(final_state.get("placed_buildings", [])), 2)
        self.assertIsNotNone(final_state.get("final_response"))
        self.assertEqual(final_state.get("active_step_id"), "report")
        self.assertIn("remaining_buildable_positions_04", client.calls)


if __name__ == "__main__":
    unittest.main()