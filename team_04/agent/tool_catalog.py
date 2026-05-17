from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SITE_READ_GROUP = "site_read"
SHAPE_GROUP = "shape_generation"
CONSTRAINT_GROUP = "constraint_check"
MANIPULATION_GROUP = "manipulation"
EVALUATION_GROUP = "evaluation"
PLACEMENT_GROUP = "placement"
POSITION_ANALYSIS_GROUP = "position_analysis"


TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    SITE_READ_GROUP: (
        "site_boundary_reader_04",
        "context_reader_04",
        "legal_constraints_reader_04",
    ),
    SHAPE_GROUP: (
        "shape_library_loader_04",
        "generate_building_boundary",
        "parametric_shape_generator_04",
    ),
    CONSTRAINT_GROUP: (
        "site_fit_checker_04",
        "setback_checker_04",
        "area_requirement_checker_04",
        "adjacency_access_checker_04",
        "tree_constraint_checker_04",
    ),
    MANIPULATION_GROUP: (
        "scale_shape_tool_04",
        "stretch_arm_tool_04",
        "width_modifier_tool_04",
        "courtyard_modifier_tool_04",
        "rotate_mirror_tool_04",
        "bend_angle_tool_04",
        "terrace_step_tool_04",
    ),
    EVALUATION_GROUP: (
        "spatial_intention_evaluator_04",
        "performance_evaluator_04",
        "shape_integrity_evaluator_04",
    ),
    PLACEMENT_GROUP: (
        "import_building_boundary_04",
    ),
    POSITION_ANALYSIS_GROUP: (
        "remaining_buildable_positions_04",
        "requested_position_checker_04",
    ),
}


ACTION_TO_GROUP: dict[str, str] = {
    "read_site": SITE_READ_GROUP,
    "generate_shape": SHAPE_GROUP,
    "check_requested_position": POSITION_ANALYSIS_GROUP,
    "check_constraints": CONSTRAINT_GROUP,
    "optimize": MANIPULATION_GROUP,
    "evaluate": EVALUATION_GROUP,
    "place_building": PLACEMENT_GROUP,
    "analyze_remaining_positions": POSITION_ANALYSIS_GROUP,
}


@dataclass(frozen=True)
class ToolCatalog:
    tools: tuple[dict[str, Any], ...]

    @classmethod
    def from_discovered_tools(cls, tools: list[dict[str, Any]]) -> "ToolCatalog":
        normalized = tuple(tool for tool in tools if isinstance(tool, dict) and tool.get("name"))
        return cls(tools=normalized)

    def by_name(self) -> dict[str, dict[str, Any]]:
        return {str(tool["name"]): tool for tool in self.tools}

    def names_for_group(self, group_name: str) -> tuple[str, ...]:
        return tuple(name for name in TOOL_GROUPS.get(group_name, ()) if name in self.by_name())

    def names_for_action(self, action: str) -> tuple[str, ...]:
        group_name = ACTION_TO_GROUP.get(action)
        if group_name is None:
            return ()
        return self.names_for_group(group_name)

    def render(self) -> str:
        return self.render_for_actions(tuple(ACTION_TO_GROUP.keys()))

    def render_for_action(self, action: str) -> str:
        return self.render_for_actions((action,))

    def render_for_actions(self, actions: tuple[str, ...]) -> str:
        by_name = self.by_name()
        lines: list[str] = []
        allowed_groups = {
            ACTION_TO_GROUP[action]
            for action in actions
            if action in ACTION_TO_GROUP
        }
        for group_name, tool_names in TOOL_GROUPS.items():
            if allowed_groups and group_name not in allowed_groups:
                continue
            available_names = [name for name in tool_names if name in by_name]
            if not available_names:
                continue
            lines.append(f"[{group_name}]")
            for tool_name in available_names:
                description = str(by_name[tool_name].get("description", "")).strip()
                if description:
                    lines.append(f"- {tool_name}: {description}")
                else:
                    lines.append(f"- {tool_name}")
        if not lines:
            return "No MCP tools discovered."
        return "\n".join(lines)