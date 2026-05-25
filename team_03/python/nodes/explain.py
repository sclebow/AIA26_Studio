from __future__ import annotations
from typing import TYPE_CHECKING, Any
from _runtime.llm import call_llm, call_llm_simple

if TYPE_CHECKING:
    from graph import AgentState


def explain_node(state: AgentState) -> dict:
    # Called only once, immediately after the user approves at the checkpoint.
    # The LLM receives a compact summary of every tool's results so it can
    # give grounded feedback without re-reading the full layout JSON.

    scoring    = state.get("scoring_results") or {}
    collision  = state.get("collision_results") or {}
    path       = state.get("path_results") or {}

    score     = scoring.get("total_score", 0)
    grade     = scoring.get("grade", "?")
    breakdown = scoring.get("breakdown", {})

    # Build a concise text summary the LLM can reason over quickly.
    analysis_summary = (
        f"Layout score: {score:.1f}/100  Grade: {grade}\n\n"
        f"Tool breakdown:\n"
        f"- Collision:    {breakdown.get('collision',    {}).get('score', 0):.0f}/100\n"
        f"- Visibility:   {breakdown.get('visibility',   {}).get('score', 0):.0f}/100\n"
        f"- Path:         {breakdown.get('path',         {}).get('score', 0):.0f}/100\n"
        f"- Reachability: {breakdown.get('reachability', {}).get('score', 0):.0f}/100\n"
        f"- Orientation:  {breakdown.get('orientation',  {}).get('score', 0):.0f}/100\n\n"
    )

    # Include the top collision violations so the LLM can name specific issues.
    violations = collision.get("violations", [])
    if violations:
        analysis_summary += "Collision issues:\n"
        for v in violations[:3]:
            analysis_summary += f"  - {v}\n"

    # Worst-case path distance gives the LLM a concrete distance to cite.
    wc = path.get("worst_case", {})
    if wc.get("from"):
        analysis_summary += (
            f"\nLongest path: {wc['from']} -> {wc['to']} ({wc['distance']}m)\n"
        )

    # Placement summary grouped by room.
    placement_history = state.get("placement_history") or []
    if placement_history:
        from collections import defaultdict
        by_room: dict = defaultdict(list)
        for p in placement_history:
            by_room[p.get("room", "Unknown")].append(p.get("name", "?"))
        placement_summary = "Equipment placed by room:\n"
        for room, items in by_room.items():
            placement_summary += f"  {room}: {', '.join(items)}\n"
        analysis_summary += "\n" + placement_summary

    # Inject spatial graph text for grounded object-level explanation.
    graph_text = state.get("spatial_graph_text") or ""
    spatial_section = (
        f"\nSpatial relationships and findings:\n{graph_text}\n"
        if graph_text else ""
    )

    prompt = (
        "You are an industrial spatial design expert.\n"
        "The user has approved a layout.\n\n"
        "Analysis results:\n" + analysis_summary +
        spatial_section +
        "\n\nWrite a clear 3-5 sentence explanation covering:\n"
        "0. In one sentence describe the complete material flow across "
        "all zones — which zone feeds into which from entry to exit.\n"
        "1. Overall score and grade with specific reasons\n"
        "2. Name the 1-2 objects with the best placement and why\n"
        "3. Name the 1-2 objects with the worst clearance or path issues "
        "and give the actual distance (from SPATIAL RELATIONSHIPS above)\n"
        "4. One concrete recommendation referencing a specific object, "
        "direction, and distance in metres\n\n"
        "Reference actual object names, distances, and OSHA/ISO standards. "
        "Do not use generic phrases like 'adequate clearance on all sides'.\n\n"
        "Respond with action final and put your explanation in final_response."
    )

    try:
        result = call_llm(
            state.get("_llm"),
            prompt,
            state["messages"],
            state["tool_catalog"],
        )
        explanation = result.get("final_response", "Layout approved and saved.")
    except Exception:
        # LLM may return markdown/text instead of JSON — use call_llm_simple
        # as a fallback to get the raw text response.
        try:
            raw = call_llm_simple(state.get("_llm"), prompt, "Generate the explanation.")
            if raw and isinstance(raw, dict):
                explanation = raw.get("final_response", str(raw))
            else:
                explanation = "Layout approved and saved."
        except Exception as exc2:
            print(f"[explain] Fallback also failed: {exc2}")
            explanation = "Layout approved and saved."
    print(f"\nLayout Explanation:\n{explanation}")
    return {"final_response": explanation}
