"""Ad-hoc smoke test for the validate->debug->retry loop (no LLM required)."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.decision_engine import RuleBasedPlanner, _repair_generate_shape_decision
from agent.graph import run_agent
from agent.mcp_client import build_default_local_tool_client
from agent.models import RoutingDecision, ToolCall
from agent.tool_catalog import ToolCatalog
from agent.tools.validate_design import validate_design


class StubEngine:
    """Deterministic stand-in: no network, exercises the real graph paths."""

    def decide(self, state, catalog, active_step):
        decision = RoutingDecision(
            action=active_step.action,
            reasoning="stub: generate a candidate footprint",
            tool_calls=(ToolCall(name="generate_building_boundary", arguments={}),),
        )
        return _repair_generate_shape_decision(decision, state, catalog, active_step)

    def build_report(self, state):
        return "stub report: " + (state.get("validation_result", {}) or {}).get("summary", "n/a")


# --- 1. unit-check the validator directly --------------------------------------
site = [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]]
inside = [[40, 40, 0], [60, 40, 0], [60, 60, 0], [40, 60, 0]]
outside = [[90, 90, 0], [130, 90, 0], [130, 130, 0], [90, 130, 0]]
print("valid inside ->", validate_design(inside, site)["data"]["passed"])
res_out = validate_design(outside, site)["data"]
print("spilling outside ->", res_out["passed"], res_out["failures"])
self_int = [[0, 0, 0], [10, 10, 0], [10, 0, 0], [0, 10, 0]]
print("self-intersecting ->", validate_design(self_int, site)["data"]["failures"])

# --- 2. run the whole graph end to end -----------------------------------------
client = build_default_local_tool_client()
catalog = ToolCatalog.from_discovered_tools(client.list_tools())
print("validate in catalog ->", catalog.names_for_action("validate"))

layout = {"site_boundary": site}
final = run_agent(
    user_prompt="Design one I-shaped building on the site.",
    decision_engine=StubEngine(),
    tool_client=client,
    catalog=catalog,
    initial_layout=layout,
    max_optimization_cycles=2,
)
print("\n--- final ---")
print("placed:", len(final.get("placed_buildings", [])))
print("validation_passed:", final.get("validation_passed"))
print("debug_attempts:", final.get("debug_attempts"))
print("final_response:", final.get("final_response"))
print("\n--- message tail ---")
for m in final.get("messages", [])[-12:]:
    print(" •", m)
tools_used = [r.get("tool") for r in final.get("tool_history", [])]
from collections import Counter
print("\ntool counts:", dict(Counter(tools_used)))

# --- 3. force validation failure -> debug -> retry -> bounded dead-end ----------
print("\n=== forced-failure scenario ===")
from agent.tools.validate_design import VALIDATE_DESIGN_TOOL_DEFINITION

def always_fail(**kwargs):
    return {
        "success": True,
        "data": {"passed": False, "failures": ["area"], "checks": [], "metrics": {}, "summary": "forced fail"},
        "metadata": {"tool_name": "validate_design", "source": "python"},
    }

client2 = build_default_local_tool_client()
client2._tools["validate_design"] = (VALIDATE_DESIGN_TOOL_DEFINITION, always_fail)
catalog2 = ToolCatalog.from_discovered_tools(client2.list_tools())

final2 = run_agent(
    user_prompt="Design one I-shaped building on the site.",
    decision_engine=StubEngine(),
    tool_client=client2,
    catalog=catalog2,
    initial_layout={"site_boundary": site, "max_debug_attempts": 2},
    max_optimization_cycles=2,
)
print("placed:", len(final2.get("placed_buildings", [])))
print("validation_passed:", final2.get("validation_passed"))
print("debug_attempts:", final2.get("debug_attempts"), "(expect 2)")
print("debug directives:", [h.get("directive") for h in final2.get("debug_history", [])])
c2 = Counter(r.get("tool") for r in final2.get("tool_history", []))
print("generate calls:", c2.get("generate_building_boundary"), "validate calls:", c2.get("validate_design"))
print("final_response:", final2.get("final_response"))
