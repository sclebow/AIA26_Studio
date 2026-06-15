from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# Footprint families the local generator already understands, plus "auto" for
# "let the agent decide". Kept in one place so the brief, the planner, and the
# shape generator all agree on the allowed vocabulary.
ALLOWED_SHAPES: frozenset[str] = frozenset(
    {"I", "L", "T", "U", "H", "Y", "X", "O", "auto"}
)


def _clamp_unit(value: Any, default: float) -> float:
    """Coerce ``value`` into a [0, 1] weight, falling back to ``default``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_shape(value: Any) -> str:
    text = str(value or "auto").strip()
    if not text:
        return "auto"
    if text.lower() == "auto":
        return "auto"
    upper = text.upper()
    return upper if upper in ALLOWED_SHAPES else "auto"


@dataclass(frozen=True)
class BuildingSpec:
    """One building's intent inside a DesignBrief.

    Every field is optional so the extractor can leave unknowns null instead of
    inventing values; downstream code falls back to defaults when a field is None.
    """

    shape_preference: str = "auto"
    footprint_area_sqm: float | None = None
    storeys: int | None = None
    use: str = "residential"
    intent_text: str = ""

    def to_state(self) -> dict[str, Any]:
        return {
            "shape_preference": self.shape_preference,
            "footprint_area_sqm": self.footprint_area_sqm,
            "storeys": self.storeys,
            "use": self.use,
            "intent_text": self.intent_text,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BuildingSpec":
        if not isinstance(payload, dict):
            return cls()
        use = str(payload.get("use", "residential") or "residential").strip() or "residential"
        return cls(
            shape_preference=_normalize_shape(payload.get("shape_preference")),
            footprint_area_sqm=_coerce_optional_float(payload.get("footprint_area_sqm")),
            storeys=_coerce_optional_int(payload.get("storeys")),
            use=use,
            intent_text=str(payload.get("intent_text", "") or "").strip(),
        )


@dataclass(frozen=True)
class DesignBrief:
    """Typed comprehension of the user's free-text request.

    This is the structure the agent reasons over instead of re-parsing the raw
    prompt at every step. The extractor fills what it can infer and records
    everything it could not in ``ambiguities`` rather than guessing.
    """

    building_count: int = 1
    buildings: tuple[BuildingSpec, ...] = ()
    courtyard_requested: bool = False
    courtyard_qualities: tuple[str, ...] = ()
    parking_requested: bool = False
    requested_rotation_deg: float | None = None
    view_weight: float = 0.5
    sun_weight: float = 0.5
    alignment_weight: float = 0.5
    ambiguities: tuple[str, ...] = ()
    source: str = "fallback"

    def to_state(self) -> dict[str, Any]:
        return {
            "building_count": self.building_count,
            "buildings": [building.to_state() for building in self.buildings],
            "courtyard_requested": self.courtyard_requested,
            "courtyard_qualities": list(self.courtyard_qualities),
            "parking_requested": self.parking_requested,
            "requested_rotation_deg": self.requested_rotation_deg,
            "view_weight": self.view_weight,
            "sun_weight": self.sun_weight,
            "alignment_weight": self.alignment_weight,
            "ambiguities": list(self.ambiguities),
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DesignBrief":
        if not isinstance(payload, dict):
            payload = {}

        raw_buildings = payload.get("buildings", [])
        if not isinstance(raw_buildings, (list, tuple)):
            raw_buildings = []
        buildings = tuple(
            BuildingSpec.from_payload(item)
            for item in raw_buildings
            if isinstance(item, dict)
        )

        count = _coerce_optional_int(payload.get("building_count"))
        if count is None:
            count = len(buildings) or 1
        # The count can never be smaller than the number of explicit specs, and
        # is always at least one.
        building_count = max(1, len(buildings), count)

        source = str(payload.get("source", "fallback") or "fallback").strip() or "fallback"

        return cls(
            building_count=building_count,
            buildings=buildings,
            courtyard_requested=bool(payload.get("courtyard_requested", False)),
            courtyard_qualities=_coerce_str_tuple(payload.get("courtyard_qualities")),
            parking_requested=bool(payload.get("parking_requested", False)),
            requested_rotation_deg=_coerce_optional_float(payload.get("requested_rotation_deg")),
            view_weight=_clamp_unit(payload.get("view_weight"), 0.5),
            sun_weight=_clamp_unit(payload.get("sun_weight"), 0.5),
            alignment_weight=_clamp_unit(payload.get("alignment_weight"), 0.5),
            ambiguities=_coerce_str_tuple(payload.get("ambiguities")),
            source=source,
        )

    def spec_for_index(self, index: int) -> BuildingSpec:
        """Return the spec for building ``index`` (0-based), or a default spec."""
        if 0 <= index < len(self.buildings):
            return self.buildings[index]
        return BuildingSpec()


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