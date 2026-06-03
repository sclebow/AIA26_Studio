from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.decision_engine import RuleBasedPlanner, _repair_generate_shape_decision
from agent.graph import run_agent
from agent.mcp_client import CompositeToolClient, LocalToolClient
from agent.models import PlanStep, RoutingDecision, ToolCall
from agent.tools import IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION
from agent.tools import REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION
from agent.tools import REQUESTED_POSITION_CHECKER_TOOL_DEFINITION
from agent.tools import TOOL_DEFINITION as GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION
from agent.tools import direction_to_site_centroid, modify_building_boundary
from agent.tools import DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION, MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION
from agent.tools import generate_building_boundary, mock_check_requested_position, mock_import_building_boundary, mock_remaining_buildable_positions
from agent.tool_catalog import ToolCatalog


class FakeToolClient:
    def __init__(self) -> None:
        self.constraint_checks = 0
        self.calls: list[str] = []
        self._tools = [
            {"name": "site_boundary_reader"},
            {"name": "context_reader"},
            {"name": "legal_constraints_reader"},
            {"name": "rotate_mirror_tool"},
            {"name": "site_fit_checker"},
            {"name": "setback_checker"},
            {"name": "area_requirement_checker"},
            {"name": "adjacency_access_checker"},
            {"name": "tree_constraint_checker"},
            {"name": "spatial_intention_evaluator"},
            {"name": "performance_evaluator"},
            {"name": "shape_integrity_evaluator"},
            {"name": "test_fit"},
        ]

    def list_tools(self) -> list[dict[str, object]]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, object]) -> str:
        self.calls.append(name)
        if name == "site_boundary_reader":
            return json.dumps({"data": {"site": "loaded"}})
        if name == "context_reader":
            return json.dumps({"data": {"context": {"roads": 1, "trees": 2}}})
        if name == "legal_constraints_reader":
            return json.dumps({"data": {"constraints": {"setback": 5}}})
        if name == "rotate_mirror_tool":
            return json.dumps({"data": {"geometry_id": "shape-002", "operation": "rotate"}})
        if name == "site_fit_checker":
            return json.dumps({"data": {"fits": True}})
        if name == "setback_checker":
            self.constraint_checks += 1
            return json.dumps({"data": {"compliant": self.constraint_checks > 1}})
        if name == "area_requirement_checker":
            return json.dumps({"data": {"gfa_compliant": True}})
        if name == "adjacency_access_checker":
            return json.dumps({"data": {"road_access_ok": True}})
        if name == "tree_constraint_checker":
            return json.dumps({"data": {"no_conflicts": True}})
        if name == "spatial_intention_evaluator":
            return json.dumps({"data": {"score": 0.91}})
        if name == "performance_evaluator":
            return json.dumps({"data": {"score": 0.88}})
        if name == "shape_integrity_evaluator":
            return json.dumps({"data": {"score": 0.94}})
        if name == "test_fit":
            site_boundary = arguments.get("site_boundary") or []
            building_boundary = arguments.get("building_boundary") or []
            site_x = [point[0] for point in site_boundary[:-1]]
            site_y = [point[1] for point in site_boundary[:-1]]
            building_x = [point[0] for point in building_boundary[:-1]]
            building_y = [point[1] for point in building_boundary[:-1]]
            fits = (
                bool(site_x)
                and bool(site_y)
                and bool(building_x)
                and bool(building_y)
                and min(building_x) >= min(site_x)
                and max(building_x) <= max(site_x)
                and min(building_y) >= min(site_y)
                and max(building_y) <= max(site_y)
            )
            return json.dumps({"data": {"IsFit": fits}})
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
                tool_calls=(ToolCall(name="rotate_mirror_tool", arguments={"angle": 15}),),
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
                MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                    MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION,
                    modify_building_boundary,
                ),
                DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION["name"]: (
                    DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION,
                    direction_to_site_centroid,
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
        self.assertIn("rotate_mirror_tool", client.calls)
        self.assertGreaterEqual(client.calls.count("setback_checker"), 2)
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

    def test_place_building_node_fits_boundary_before_import(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        engine = ScriptedDecisionEngine()

        final_state = run_agent(
            user_prompt="Generate one building and place it inside the site.",
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout={
                "site_boundary": [
                    [0.0, 0.0, 0.0],
                    [100.0, 0.0, 0.0],
                    [100.0, 100.0, 0.0],
                    [0.0, 100.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
                "target_building_count": 1,
            },
            max_optimization_cycles=2,
            planner=RuleBasedPlanner(),
        )

        placed_building = final_state.get("placed_buildings", [])[0]
        placement_payload = placed_building["placement"]
        placement_fit_summary = final_state.get("placement_fit_summary", {})
        self.assertEqual(placement_payload.get("geometry_id"), placed_building.get("geometry_id"))
        self.assertEqual(placement_payload.get("boundary"), placed_building.get("boundary"))
        self.assertIn("fits_within_site_boundary", placement_fit_summary)
        self.assertIn("placement_suggested_move", placement_fit_summary)
        self.assertIn("test_fit_passed", placement_fit_summary)
        self.assertIn("test_fit", client.calls)
        xs = [point[0] for point in placed_building["boundary"][:-1]]
        ys = [point[1] for point in placed_building["boundary"][:-1]]
        self.assertGreaterEqual(min(xs), 0.0)
        self.assertGreaterEqual(min(ys), 0.0)
        self.assertLessEqual(max(xs), 100.0)
        self.assertLessEqual(max(ys), 100.0)

    def test_planner_adds_multi_building_steps(self) -> None:
        planner = RuleBasedPlanner()
        catalog = ToolCatalog.from_discovered_tools(self._build_tool_client().list_tools())

        plan = planner.build_plan(
            {
                "site_context": {"site_boundary_reader": {"data": {"site": "loaded"}}},
                "geometry_id": "shape-001",
                "checked_geometry_id": "shape-001",
                "constraint_results": {"setback_checker": {"data": {"compliant": True}}},
                "violations": [],
                "evaluation_results": {"performance_evaluator": {"data": {"score": 0.9}}},
                "placed_buildings": [],
                "requested_positions": [[90.0, 30.0], [110.0, 50.0]],
                "building_intents": [
                    "Keep a quiet western frontage.",
                    "Open toward the shared courtyard.",
                ],
                "requested_position_assessment": {},
                "target_building_count": 2,
            },
            catalog,
        )

        status_by_step = {step.step_id: step.status for step in plan}
        goal_by_step = {step.step_id: step.goal for step in plan}
        self.assertEqual(status_by_step["check_requested_position"], "pending")
        self.assertEqual(status_by_step["place_building"], "skipped")
        self.assertEqual(status_by_step["analyze_remaining_positions"], "skipped")
        self.assertIn("Keep a quiet western frontage.", goal_by_step["generate_shape"])

    def test_single_building_report_does_not_advance_label_past_target(self) -> None:
        planner = RuleBasedPlanner()
        catalog = ToolCatalog.from_discovered_tools(self._build_tool_client().list_tools())

        plan = planner.build_plan(
            {
                "site_context": {"site_boundary_reader": {"data": {"site": "loaded"}}},
                "geometry_id": "shape-001",
                "checked_geometry_id": "shape-001",
                "constraint_results": {"setback_checker": {"data": {"compliant": True}}},
                "violations": [],
                "evaluation_results": {"performance_evaluator": {"data": {"score": 0.9}}},
                "placed_buildings": [{"geometry_id": "shape-001"}],
                "target_building_count": 1,
            },
            catalog,
        )

        goal_by_step = {step.step_id: step.goal for step in plan}
        self.assertIn("building 1", goal_by_step["generate_shape"].lower())
        self.assertIn("building 1", goal_by_step["evaluate"].lower())
        self.assertIn("building 1", goal_by_step["place_building"].lower())

    def test_boundary_only_workflow_skips_non_generation_steps(self) -> None:
        planner = RuleBasedPlanner()
        catalog = ToolCatalog.from_discovered_tools(self._build_tool_client().list_tools())

        plan = planner.build_plan(
            {
                "workflow_mode": "boundary_only",
                "site_context": {"site_boundary_reader": {"data": {"site": "loaded"}}},
                "geometry_id": "shape-001",
            },
            catalog,
        )

        status_by_step = {step.step_id: step.status for step in plan}
        self.assertEqual(status_by_step["read_site"], "completed")
        self.assertEqual(status_by_step["generate_shape"], "completed")
        self.assertEqual(status_by_step["check_constraints"], "skipped")
        self.assertEqual(status_by_step["evaluate"], "skipped")
        self.assertEqual(status_by_step["place_building"], "skipped")
        self.assertEqual(status_by_step["report"], "pending")

    def test_generate_shape_repair_adds_boundary_tool_arguments(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        active_step = PlanStep(
            step_id="generate_shape",
            action="generate_shape",
            goal="Create the next geometry candidate for building 1.",
            status="pending",
        )

        repaired = _repair_generate_shape_decision(
            RoutingDecision(action="generate_shape", reasoning="Generate the requested shape."),
            {
                "user_prompt": "Generate an L-shaped building boundary for a site area of 5000 square meters.",
                "site_context": {"site_boundary_reader": {"data": {"site_area_sqm": 5000.0}}},
            },
            catalog,
            active_step,
        )

        self.assertEqual(repaired.tool_calls[0].name, "generate_building_boundary")
        self.assertEqual(repaired.tool_calls[0].arguments["building_type"], "L")
        self.assertEqual(repaired.tool_calls[0].arguments["area"], 1750.0)

    def test_generate_shape_repair_injects_site_boundary_for_placement(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        active_step = PlanStep(
            step_id="generate_shape",
            action="generate_shape",
            goal="Create the next geometry candidate for building 1.",
            status="pending",
        )

        repaired = _repair_generate_shape_decision(
            RoutingDecision(action="generate_shape", reasoning="Generate the requested shape."),
            {
                "user_prompt": "Generate an H-shaped building for this site.",
                "site_boundary": [
                    [0.0, 0.0, 0.0],
                    [100.0, 0.0, 0.0],
                    [100.0, 100.0, 0.0],
                    [0.0, 100.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
            },
            catalog,
            active_step,
        )

        self.assertIn("site_boundary", repaired.tool_calls[0].arguments)
        self.assertTrue(repaired.tool_calls[0].arguments["optimize_placement"])

    def test_generate_shape_repair_prefers_explicit_building_area(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        active_step = PlanStep(
            step_id="generate_shape",
            action="generate_shape",
            goal="Create the next geometry candidate for building 1.",
            status="pending",
        )

        repaired = _repair_generate_shape_decision(
            RoutingDecision(action="generate_shape", reasoning="Generate the requested shape."),
            {
                "user_prompt": "Generate an L-shaped building boundary with a building area of 3000 square meters.",
                "site_context": {"site_boundary_reader": {"data": {"site_area_sqm": 5000.0}}},
            },
            catalog,
            active_step,
        )

        self.assertEqual(repaired.tool_calls[0].name, "generate_building_boundary")
        self.assertEqual(repaired.tool_calls[0].arguments["building_type"], "L")
        self.assertEqual(repaired.tool_calls[0].arguments["area"], 3000.0)

    def test_generate_shape_repair_maps_requested_rotation_to_single_step(self) -> None:
        client = self._build_tool_client()
        catalog = ToolCatalog.from_discovered_tools(client.list_tools())
        active_step = PlanStep(
            step_id="generate_shape",
            action="generate_shape",
            goal="Create the next geometry candidate for building 1.",
            status="pending",
        )

        repaired = _repair_generate_shape_decision(
            RoutingDecision(action="generate_shape", reasoning="Generate the requested shape."),
            {
                "user_prompt": "Generate an L-shaped building boundary with a building area of 3000 square meters and rotate the building by 45 degrees.",
                "site_context": {"site_boundary_reader": {"data": {"site_area_sqm": 5000.0}}},
            },
            catalog,
            active_step,
        )

        self.assertEqual(repaired.tool_calls[0].arguments["max_rotation_angle"], 45.0)
        self.assertEqual(repaired.tool_calls[0].arguments["max_rotation_step"], 1)
        self.assertEqual(repaired.tool_calls[0].arguments["rotation_step"], 1)

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
                "building_intents": [
                    "Keep the first building calm on the west edge.",
                    "Place the second building to reinforce the shared courtyard edge.",
                ],
            },
            max_optimization_cycles=1,
            planner=RuleBasedPlanner(),
        )

        self.assertEqual(len(final_state.get("placed_buildings", [])), 2)
        self.assertIsNotNone(final_state.get("final_response"))
        self.assertEqual(final_state.get("active_step_id"), "report")
        self.assertIn("remaining_buildable_positions", client.calls)
        self.assertEqual(len(final_state.get("building_intents", [])), 2)


if __name__ == "__main__":
    unittest.main()