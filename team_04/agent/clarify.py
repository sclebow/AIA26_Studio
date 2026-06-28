"""Interactive clarification for Team 04.

When a prompt is too vague to place buildings accurately, the agent should ask
the user back instead of fabricating values (the brief's no-invention principle).
This module turns the Phase 0 ``DesignBrief`` + the layout payload into a typed,
structured *clarification request* — a list of fields, each with suggested chip
options — that the frontend renders and the user answers.

Policy (chosen 2026-06-16): **ask only on critical gaps.** A clarification is
raised only when a placement-critical field is missing — building **shape**, the
**side/position** the building should sit next to, or the **view-optimisation
side**. When we do ask, we also fold in the non-critical-but-useful fields the
user wanted (size, use, count) so everything is collected in one round. Minor
gaps alone never block; they fall back to documented defaults downstream.

Pure, deterministic, no LLM/MCP — so it is unit-testable and the agent graph can
call it inside the ``extract_brief`` node. Interactivity is opt-in via the layout
flag ``interactive_clarification`` so non-interactive (test/CLI) runs are
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import DesignBrief

# Suggested chip options ------------------------------------------------------
SHAPE_OPTIONS: tuple[str, ...] = ("auto", "I", "L", "T", "U", "H", "Y", "X", "O")
USE_OPTIONS: tuple[str, ...] = ("residential", "office", "mixed")
SIZE_OPTIONS: tuple[str, ...] = ("~600 m²", "~900 m²", "~1200 m²", "~1800 m²")
COUNT_OPTIONS: tuple[str, ...] = ("1", "2", "3", "4")
CARDINAL_SIDES: tuple[str, ...] = ("north", "south", "east", "west")

# Field keys that, when missing, are reason enough to pause and ask.
CRITICAL_KEYS: frozenset[str] = frozenset({"shape", "side", "view_side"})


@dataclass(frozen=True)
class ClarificationField:
    """One question in a clarification request, with suggested chip options."""

    key: str
    question: str
    options: tuple[str, ...] = ()
    multi: bool = False
    allow_custom: bool = True
    critical: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "question": self.question,
            "options": list(self.options),
            "multi": self.multi,
            "allow_custom": self.allow_custom,
            "critical": self.critical,
        }


@dataclass(frozen=True)
class ClarificationRequest:
    """A bundle of fields the agent needs answered before it can place accurately."""

    summary: str
    fields: tuple[ClarificationField, ...]

    @property
    def is_empty(self) -> bool:
        return not self.fields

    def question_text(self) -> str:
        """Flat prose version (used for ``final_response`` / await_human)."""
        lines = [self.summary]
        for f in self.fields:
            opts = f" (options: {', '.join(f.options)})" if f.options else ""
            lines.append(f"- {f.question}{opts}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "fields": [f.to_dict() for f in self.fields]}


# ---------------------------------------------------------------------------
# Site-side helpers
# ---------------------------------------------------------------------------

def _bbox(site_boundary: list[list[float]] | None) -> tuple[float, float, float, float] | None:
    if not site_boundary or len(site_boundary) < 3:
        return None
    xs = [float(p[0]) for p in site_boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    ys = [float(p[1]) for p in site_boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def side_options(site_model: dict[str, Any] | None, layout_payload: dict[str, Any] | None) -> tuple[str, ...]:
    """Prefer named site sides / site objects; fall back to cardinal directions."""
    names: list[str] = []
    if isinstance(site_model, dict):
        for side in site_model.get("sides", []) or []:
            label = side.get("label") if isinstance(side, dict) else None
            if label:
                names.append(str(label))
    if isinstance(layout_payload, dict):
        for obj in layout_payload.get("site_objects", []) or []:
            if isinstance(obj, dict) and obj.get("name"):
                names.append(str(obj["name"]))
    out = tuple(dict.fromkeys(names))  # de-dupe, keep order
    return out + CARDINAL_SIDES if out else CARDINAL_SIDES


def side_to_point(
    site_boundary: list[list[float]] | None,
    side: str,
    index: int = 0,
    count: int = 1,
) -> list[float] | None:
    """Map a side label to an interior representative point near that side.

    Buildings are spread along the chosen side by ``index`` so two buildings on
    the same side don't land on top of each other.
    """
    box = _bbox(site_boundary)
    if box is None:
        return None
    min_x, min_y, max_x, max_y = box
    w, h = max_x - min_x, max_y - min_y
    # Spread factor 0.25..0.75 across the side for up to `count` buildings.
    frac = 0.5 if count <= 1 else 0.25 + 0.5 * (index / max(1, count - 1))
    s = (side or "").lower()
    inset = 0.22
    if "south" in s or "main" in s:   # "main street" frontage usually south edge
        return [min_x + w * frac, min_y + h * inset]
    if "north" in s:
        return [min_x + w * frac, max_y - h * inset]
    if "east" in s:
        return [max_x - w * inset, min_y + h * frac]
    if "west" in s:
        return [min_x + w * inset, min_y + h * frac]
    # Unknown label → centre, offset by index.
    return [min_x + w * frac, min_y + h * 0.5]


# ---------------------------------------------------------------------------
# Build a request from the brief
# ---------------------------------------------------------------------------

def required_clarifications(
    brief: DesignBrief,
    layout_payload: dict[str, Any] | None,
    site_model: dict[str, Any] | None = None,
) -> ClarificationRequest | None:
    """Return a structured clarification request, or ``None`` when not needed.

    Only returns a request when at least one **critical** gap exists; otherwise
    the agent proceeds with defaults.
    """
    layout_payload = layout_payload or {}
    sides = side_options(site_model, layout_payload)

    fields: list[ClarificationField] = []

    # --- critical: shape ---
    shapes = [b.shape_preference for b in brief.buildings] or ["auto"]
    if any(s == "auto" for s in shapes):
        fields.append(ClarificationField(
            "shape", "Which building shape do you want?",
            SHAPE_OPTIONS, multi=False, critical=True,
        ))

    # --- critical: preferred side / position ---
    has_position = bool(layout_payload.get("requested_positions"))
    has_side = bool(layout_payload.get("preferred_side") or layout_payload.get("preferred_sides"))
    if not has_position and not has_side:
        fields.append(ClarificationField(
            "side", "Which site side should the building sit next to?",
            sides, multi=False, critical=True,
        ))

    # --- critical: view-optimisation side ---
    has_view = bool(
        layout_payload.get("view_target_side")
        or layout_payload.get("view_target_sides")
        or layout_payload.get("attractors")
    )
    if not has_view:
        fields.append(ClarificationField(
            "view_side", "Which side should the view be optimised toward?",
            sides, multi=True, critical=True,
        ))

    # --- non-critical (only offered because a critical gap already triggers the ask) ---
    if all(b.footprint_area_sqm is None for b in brief.buildings):
        fields.append(ClarificationField(
            "size", "Approximate footprint size per building?",
            SIZE_OPTIONS, multi=False, critical=False,
        ))
    fields.append(ClarificationField(
        "use", "What is the building use?", USE_OPTIONS, multi=False, critical=False,
    ))
    fields.append(ClarificationField(
        "count", "How many buildings?", COUNT_OPTIONS, multi=False, critical=False,
    ))

    if not any(f.critical for f in fields):
        return None

    summary = "The prompt is a bit vague to place this accurately — could you confirm a few things?"
    return ClarificationRequest(summary, tuple(fields))


# ---------------------------------------------------------------------------
# Apply answers back onto the brief + layout
# ---------------------------------------------------------------------------

def _parse_area(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value)
    # ASCII digits + dot only — note "²" in "m²" is .isdigit()==True, so avoid it.
    digits = "".join(ch for ch in text if ch in "0123456789.")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def apply_clarification_answers(
    brief_payload: dict[str, Any],
    layout_payload: dict[str, Any],
    answers: dict[str, Any],
    site_boundary: list[list[float]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge user answers onto the brief + layout so the run can proceed.

    Returns ``(new_brief_payload, new_layout_payload)``. Both are deep-ish copies
    (top-level dicts rebuilt) so the originals are not mutated. Unknown keys are
    ignored. ``site_boundary`` is used to turn a side answer into requested
    positions that actually drive placement.
    """
    brief_payload = dict(brief_payload or {})
    layout_payload = dict(layout_payload or {})
    answers = answers or {}

    # count → building_count + target_building_count
    if answers.get("count"):
        try:
            count = max(1, int(str(answers["count"]).strip()))
            brief_payload["building_count"] = count
            layout_payload["target_building_count"] = count
        except (TypeError, ValueError):
            pass

    count = max(1, int(brief_payload.get("building_count", 1) or 1))

    # Ensure the buildings list has `count` entries to patch.
    buildings = list(brief_payload.get("buildings") or [])
    while len(buildings) < count:
        buildings.append({
            "shape_preference": "auto", "footprint_area_sqm": None,
            "storeys": None, "use": "residential", "intent_text": "",
        })
    buildings = [dict(b) for b in buildings[:count]]

    shape = str(answers.get("shape", "")).strip()
    area = _parse_area(answers.get("size"))
    use = str(answers.get("use", "")).strip()
    for b in buildings:
        if shape and shape.lower() != "auto":
            b["shape_preference"] = shape.upper()
        if area is not None:
            b["footprint_area_sqm"] = area
        if use:
            b["use"] = use
    brief_payload["buildings"] = buildings

    # side → requested_positions (one per building, spread along that side)
    side = answers.get("side")
    if side and not layout_payload.get("requested_positions"):
        side_label = side[0] if isinstance(side, (list, tuple)) and side else side
        pts = [
            side_to_point(site_boundary, str(side_label), i, count)
            for i in range(count)
        ]
        pts = [p for p in pts if p is not None]
        if pts:
            layout_payload["requested_positions"] = pts
        layout_payload["preferred_side"] = str(side_label)

    # view_side → recorded for the optimizer / report (attractor wiring is Phase 2)
    view_side = answers.get("view_side")
    if view_side:
        layout_payload["view_target_sides"] = (
            list(view_side) if isinstance(view_side, (list, tuple)) else [view_side]
        )

    return brief_payload, layout_payload
