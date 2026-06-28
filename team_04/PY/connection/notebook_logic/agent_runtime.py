"""Agent workflow runtime — the single entry point for prompt-to-design.

Wraps the EXISTING compiled LangGraph agent (built by connection.agent_runtime,
which wires agent.graph / agent.decision_engine / agent.tools exactly like
agent/main.py). Nothing here reimplements the planner, supervisor, or any tool.

Used by:
  * connection/routes/agent_routes.py  (POST /api/agent/run)  -> frontend Copilot
  * test_notebooks/end_to_end_api_agent.ipynb                 -> validation

Both call run_prompt_to_design(...) and get the same final state + traces.
"""
from __future__ import annotations

import re
from typing import Any

from . import site_state

# The cached, compiled real agent graph (same construction as agent/main.py).
from ..agent_runtime import get_graph
from agent.graph import _extract_current_shape_payload  # noqa: PLC2701 (reuse, don't duplicate)
from agent.state import build_initial_state

DEFAULT_FLOOR_HEIGHT_M = 3.0

# Building-use keywords → a normalized program tag. Used to tag the design and to
# pick sensible per-floor area defaults so "commercial" vs "residential" differ.
_USE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("commercial", "commercial"),
    ("retail", "commercial"),
    ("shop", "commercial"),
    ("mall", "commercial"),
    ("office", "office"),
    ("workplace", "office"),
    ("residential", "residential"),
    ("apartment", "residential"),
    ("housing", "residential"),
    ("flats", "residential"),
    ("hotel", "hospitality"),
    ("hospitality", "hospitality"),
    ("mixed use", "mixed_use"),
    ("mixed-use", "mixed_use"),
    ("institutional", "institutional"),
    ("school", "institutional"),
    ("hospital", "institutional"),
)


# --------------------------------------------------------------------------- #
# Prompt program parsing — floors → height, and building use. Small regex
# extractors in the same spirit as agent.decision_engine's prompt parsers.
# --------------------------------------------------------------------------- #
def extract_floor_count(prompt: str) -> int | None:
    """Pull a storey/floor count out of the prompt, e.g. '5 floors', 'G+4',
    'five-storey'. Returns None if no count is mentioned."""
    if not prompt:
        return None
    low = prompt.lower()

    # "G+4" (ground + 4) → 5 floors
    m = re.search(r"\bg\s*\+\s*(\d+)\b", low)
    if m:
        return int(m.group(1)) + 1

    m = re.search(r"(\d+)\s*(?:-|\s)?\s*(?:floors?|storey?s?|stories|levels?)\b", low)
    if m:
        n = int(m.group(1))
        return n if n > 0 else None

    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    }
    m = re.search(r"\b(" + "|".join(words) + r")\s*(?:-|\s)?\s*(?:floors?|storey?s?|stories|levels?)\b", low)
    if m:
        return words[m.group(1)]
    return None


def infer_building_use(prompt: str) -> str | None:
    """Normalize the building use/program mentioned in the prompt, or None."""
    if not prompt:
        return None
    low = prompt.lower()
    for keyword, tag in _USE_KEYWORDS:
        if keyword in low:
            return tag
    return None


def parse_program(prompt: str, *, floor_height_m: float = DEFAULT_FLOOR_HEIGHT_M) -> dict[str, Any]:
    """Extract the building 'program' from the prompt: floor count, derived height,
    and use. height_m = floors × floor_height when floors are given."""
    floors = extract_floor_count(prompt)
    use = infer_building_use(prompt)
    height_m = round(floors * floor_height_m, 2) if floors else None
    return {
        "floors": floors,
        "floor_height_m": floor_height_m,
        "height_m": height_m,
        "building_use": use,
    }


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def run_prompt_to_design(
    prompt: str,
    *,
    layout: dict[str, Any] | None = None,
    max_optimization_cycles: int = 3,
    use_confirmed_site: bool = True,
    recursion_limit: int = 150,
) -> dict[str, Any]:
    """Run the full agent workflow for a natural-language prompt.

    layout: optional layout_payload (site_boundary, building_intents,
            requested_positions, target_building_count, workflow_mode). When it
            omits site_boundary and use_confirmed_site is True, the confirmed
            site (site_state) is injected so geometry lands inside it.
    Returns the final AgentState dict.
    """
    layout = dict(layout or {})
    if use_confirmed_site and not layout.get("site_boundary"):
        confirmed = site_state.load_confirmed_boundary()
        if confirmed:
            layout["site_boundary"] = confirmed

    initial_state = build_initial_state(
        user_prompt=prompt,
        layout_payload=layout,
        max_optimization_cycles=max_optimization_cycles,
    )
    graph = get_graph()
    return graph.invoke(initial_state, config={"recursion_limit": recursion_limit})


# --------------------------------------------------------------------------- #
# Extraction — pure read helpers over the final state (no algorithm logic)
# --------------------------------------------------------------------------- #
def extract_final_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """A condensed, JSON-friendly view of the final design state."""
    placed = final_state.get("placed_buildings", []) or []
    return {
        "final_response": final_state.get("final_response"),
        "workflow_mode": final_state.get("workflow_mode"),
        "site_boundary": final_state.get("site_boundary", []),
        "placed_building_count": len(placed),
        "placed_building_geometry_ids": [
            item.get("geometry_id") for item in placed if isinstance(item, dict)
        ],
        "violations": final_state.get("violations", []),
        "placement_fit_summary": final_state.get("placement_fit_summary", {}),
        "optimization_cycles": final_state.get("optimization_cycles", 0),
        "error": final_state.get("error"),
    }


def extract_latest_shape(final_state: dict[str, Any]) -> dict[str, Any] | None:
    """The most recent generated/modified shape payload (boundary, wings,
    building_graph, …). Reuses agent.graph's own traversal so it matches what the
    agent sees internally."""
    return _extract_current_shape_payload(final_state)


def extract_geometry_payload(final_state: dict[str, Any]) -> dict[str, Any]:
    """Frontend-ready geometry: every placed building plus the latest candidate."""
    placed = final_state.get("placed_buildings", []) or []
    buildings = []
    for i, item in enumerate(placed):
        if not isinstance(item, dict):
            continue
        buildings.append(
            {
                "index": i,
                "geometry_id": item.get("geometry_id"),
                "boundary": item.get("boundary"),
                "shape_type": item.get("shape_type"),
                "wings": item.get("wings"),
                "building_graph": item.get("building_graph"),
                "height_m": item.get("height_m"),
                "building_use": item.get("building_use"),
            }
        )
    return {
        "site_boundary": final_state.get("site_boundary", []),
        "buildings": buildings,
        "latest_candidate": extract_latest_shape(final_state),
    }


def _trace_with_prefixes(final_state: dict[str, Any], prefixes: tuple[str, ...]) -> list[str]:
    return [
        msg
        for msg in final_state.get("messages", []) or []
        if isinstance(msg, str) and msg.startswith(prefixes)
    ]


def extract_planner_trace(final_state: dict[str, Any]) -> list[str]:
    return _trace_with_prefixes(final_state, ("Planner updated",))


def extract_supervisor_trace(final_state: dict[str, Any]) -> list[str]:
    return _trace_with_prefixes(final_state, ("Supervisor decision",))


def extract_decision_trace(final_state: dict[str, Any]) -> list[str]:
    """The combined narrative the notebook builds: planner + supervisor + tools +
    final report, in message order."""
    return _trace_with_prefixes(
        final_state,
        ("Planner updated", "Supervisor decision", "Tool ", "Final report"),
    )


def extract_tool_sequence(final_state: dict[str, Any]) -> list[str]:
    return [
        record.get("tool")
        for record in final_state.get("tool_history", []) or []
        if isinstance(record, dict) and record.get("tool")
    ]


# --------------------------------------------------------------------------- #
# Post-generation checks — run the generated shape through the same constraint /
# view-analysis tools the notebooks use. Reuses agent.tools.* + the view
# optimization runtime; no scoring math is reimplemented here.
# --------------------------------------------------------------------------- #
def run_design_checks(
    final_state: dict[str, Any],
    *,
    program: dict[str, Any] | None = None,
    site_boundary: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Validate each placed building: site-fit + setback summary + (height-aware)
    view score. Returns one entry per building plus a top-level `passed` flag."""
    from agent.tools.site_setback import setback_summary
    from agent.tools.view_3d import evaluate_building_views_3d

    program = program or {}
    site = site_boundary or final_state.get("site_boundary") or site_state.load_confirmed_boundary() or []
    placed = final_state.get("placed_buildings", []) or []
    floor_height = float(program.get("floor_height_m") or DEFAULT_FLOOR_HEIGHT_M)
    height_m = program.get("height_m")

    # Site setback summary (once per site).
    setbacks: list[dict[str, Any]] = []
    if site and len(site) >= 3:
        try:
            setbacks = setback_summary(site)
        except Exception:  # noqa: BLE001 — checks are best-effort, never fatal
            setbacks = []

    building_checks: list[dict[str, Any]] = []
    all_passed = True
    for i, item in enumerate(placed):
        if not isinstance(item, dict):
            continue
        boundary = item.get("boundary")
        fit = item.get("site_fit_summary") or {}
        fits = fit.get("fits_within_site_boundary")
        if fits is False:
            all_passed = False

        # Height-aware view score: other placed buildings act as obstacles.
        view = None
        if boundary and len(boundary) >= 3:
            others = [
                b.get("boundary")
                for j, b in enumerate(placed)
                if j != i and isinstance(b, dict) and b.get("boundary")
            ]
            obstacles = [{"boundary": ob, "height": float("inf")} for ob in others if ob]
            bld_height = float(height_m) if height_m else 12.0
            try:
                view = evaluate_building_views_3d(
                    boundary, bld_height, obstacles, floor_height=floor_height, return_ray_detail=False
                )
            except Exception:  # noqa: BLE001
                view = None

        building_checks.append(
            {
                "index": i,
                "geometry_id": item.get("geometry_id"),
                "fits_within_site": fits,
                "site_fit_summary": fit,
                "view_score_3d": (view or {}).get("view_score_3d") if view else None,
                "view_floors": (view or {}).get("n_floors") if view else None,
            }
        )

    return {
        "passed": all_passed and not final_state.get("violations"),
        "violations": final_state.get("violations", []),
        "setback_summary": setbacks,
        "buildings": building_checks,
    }


def run_and_summarize(prompt: str, *, run_checks: bool = True, **kwargs: Any) -> dict[str, Any]:
    """Convenience for routes/notebooks: parse the program (floors→height, use),
    run the agent, then run the generated shape through the constraint/view checks
    — all via the shared runtime so notebooks and the frontend agree."""
    program = parse_program(prompt)

    # Pass the program into the agent via building_intents so the supervisor sees
    # the requested use/floors, and tag the layout for downstream consumers.
    layout = dict(kwargs.pop("layout", None) or {})
    layout.setdefault("program", program)
    if program.get("building_use") and not layout.get("building_intents"):
        floors_txt = f"{program['floors']}-floor " if program.get("floors") else ""
        layout["building_intents"] = [f"{floors_txt}{program['building_use']} building"]

    final_state = run_prompt_to_design(prompt, layout=layout, **kwargs)

    # Stamp the parsed height/use onto each placed building so the viewer/explorer
    # can render the correct number of storeys.
    if program.get("height_m"):
        for b in final_state.get("placed_buildings", []) or []:
            if isinstance(b, dict):
                b.setdefault("height_m", program["height_m"])
                b.setdefault("building_use", program.get("building_use"))

    result = {
        "program": program,
        "state": extract_final_state(final_state),
        "geometry": extract_geometry_payload(final_state),
        "planner_trace": extract_planner_trace(final_state),
        "supervisor_trace": extract_supervisor_trace(final_state),
        "decision_trace": extract_decision_trace(final_state),
        "tool_sequence": extract_tool_sequence(final_state),
    }
    if run_checks:
        result["checks"] = run_design_checks(final_state, program=program)
    return result
