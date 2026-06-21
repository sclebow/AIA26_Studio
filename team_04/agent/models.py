from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ActionName = Literal[
    "read_site",
    "generate_shape",
    "check_requested_position",
    "check_constraints",
    "optimize",
    "evaluate",
    "place_building",
    "analyze_remaining_positions",
    "report",
    "await_human",
    "finish",
]

PlanStatus = Literal["pending", "completed", "skipped"]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolCall":
        name = str(payload.get("name", "")).strip()
        arguments = payload.get("arguments", {})
        if not name:
            raise ValueError("Tool call is missing a name")
        if not isinstance(arguments, dict):
            raise ValueError("Tool call arguments must be an object")
        return cls(name=name, arguments=arguments)


@dataclass(frozen=True)
class RoutingDecision:
    action: ActionName
    reasoning: str
    tool_calls: tuple[ToolCall, ...] = ()
    user_question: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RoutingDecision":
        action = str(payload.get("action", "")).strip()
        reasoning = str(payload.get("reasoning", "")).strip()
        user_question = str(payload.get("user_question", "")).strip()
        tool_calls_payload = payload.get("tool_calls", [])

        if action not in {
            "read_site",
            "generate_shape",
            "check_requested_position",
            "check_constraints",
            "optimize",
            "evaluate",
            "place_building",
            "analyze_remaining_positions",
            "report",
            "await_human",
            "finish",
        }:
            raise ValueError(f"Unsupported action: {action}")

        if not isinstance(tool_calls_payload, list):
            raise ValueError("tool_calls must be an array")

        tool_calls = tuple(ToolCall.from_payload(item) for item in tool_calls_payload)
        return cls(
            action=action,
            reasoning=reasoning,
            tool_calls=tool_calls,
            user_question=user_question,
        )


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    action: ActionName
    goal: str
    status: PlanStatus

    def to_state(self) -> dict[str, str]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "goal": self.goal,
            "status": self.status,
        }

    @classmethod
    def from_state(cls, payload: dict[str, Any]) -> "PlanStep":
        step_id = str(payload.get("step_id", "")).strip()
        action = str(payload.get("action", "")).strip()
        goal = str(payload.get("goal", "")).strip()
        status = str(payload.get("status", "")).strip()

        if not step_id:
            raise ValueError("Plan step is missing step_id")
        if action not in {
            "read_site",
            "generate_shape",
            "check_requested_position",
            "check_constraints",
            "optimize",
            "evaluate",
            "place_building",
            "analyze_remaining_positions",
            "report",
            "await_human",
            "finish",
        }:
            raise ValueError(f"Unsupported plan step action: {action}")
        if status not in {"pending", "completed", "skipped"}:
            raise ValueError(f"Unsupported plan step status: {status}")

        return cls(step_id=step_id, action=action, goal=goal, status=status)