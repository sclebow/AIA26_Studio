from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node
from nodes.modify import build_modify_node, DEFAULT_SECTIONS, BEAM_SECTION_UPGRADE, COL_SECTION_UPGRADE
from nodes.evaluate import build_evaluate_node, evaluate_structure, SETTINGS_PATH, _get_user_request
from nodes.comparison import build_comparison_node

EXAMPLE_LAYOUTS_DIR = Path(__file__).parent / "example_layouts"


def _dist(a: list, b: list) -> float:
    return math.dist(a, b)


def _settings_load(path: Any, key: str) -> float | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(key)
    except Exception:
        return None


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]] | None
    final_response: str | None
    iteration: int
    max_iterations: int
    tool_catalog: str
    layout_json_string: str
    evaluation_result: str | None
    comparison_result: str | None
    came_from: str | None
    original_layout_json_string: str | None
    cycle: int
    material_override: str | None
    pending_structural_change: dict | None
    layout_before_change: str | None
    live_load_kNm2: float | None
    sdl_kNm2: float | None
    find_minimum_done: bool | None


_EVAL_KEYWORDS = frozenset({
    "evaluat", "check loads", "check structure", "check if",
    "find minimum", "minimum section", "minimum sufficient",
    "optimiz", "upgrade section", "structurally feasible",
    "structure hold", "assess struct", "run structural",
    "is this safe", "is it safe", "is the structure",
    "will it hold", "can it support", "safe to",
})


def _looks_like_eval(state: AgentState) -> bool:
    """Return True when the user's original prompt is an evaluation/computation request."""
    text = _get_user_request(state.get("messages", []))
    return any(kw in text for kw in _EVAL_KEYWORDS)


def _route_from_reason(state: AgentState) -> str:
    if state.get("pending_tool_calls") and state.get("cycle", 0) < 2:
        return "modify"
    if state.get("cycle", 0) >= 2:
        return END
    if state.get("evaluation_result") is not None:
        return END  # evaluate already ran — done
    if state.get("final_response"):
        # If the user asked for evaluation/computation, force it even if LLM answered directly
        if _looks_like_eval(state):
            return "evaluate"
        return END  # genuine Q&A — use LLM's direct answer
    return "evaluate"


def _route_from_evaluate(state: AgentState) -> str:
    if state.get("came_from") == "tag_and_audit":
        return END
    if state.get("pending_structural_change"):
        return "modify"
    if state.get("came_from") in ("modify", "structural_change"):
        return "comparison"
    if state.get("evaluation_result") is not None:
        return END  # plain evaluation done — skip the redundant reason call
    return "reason"


def build_graph(ctx: Any) -> Any:
    reason = build_reason_node(ctx.llm)
    modify = build_modify_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path, evaluate_fn=evaluate_structure)
    evaluate = build_evaluate_node(ctx.llm)
    comparison = build_comparison_node(ctx.llm)

    graph = StateGraph(AgentState)
    graph.add_node("reason", reason)
    graph.add_node("modify", modify)
    graph.add_node("evaluate", evaluate)
    graph.add_node("comparison", comparison)

    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", _route_from_reason, {"modify": "modify", "evaluate": "evaluate", END: END})
    graph.add_edge("modify", "evaluate")
    graph.add_conditional_edges("evaluate", _route_from_evaluate, {"reason": "reason", "comparison": "comparison", "modify": "modify", END: END})
    graph.add_edge("comparison", "reason")

    return graph.compile()


def run_agent(prompt: str, ctx: Any) -> str:
    app = build_graph(ctx)
    # Snapshot the layout before this run so before/after comparison is always available
    if ctx.edited_layout_path.exists():
        before_path = ctx.edited_layout_path.with_stem(ctx.edited_layout_path.stem + "_before")
        before_path.write_text(ctx.edited_layout_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[snapshot] saved {before_path.name}")
    initial_state = _build_initial_state(prompt, ctx)
    final_state = app.invoke(initial_state)

    # Persist material override to JSON after graph completes (survives multiple modify cycles)
    material = final_state.get("material_override")
    print(f"[material] final material_override = {material!r}")
    if material:
        from nodes.modify import DEFAULT_SECTIONS, BEAM_SECTION_UPGRADE, COL_SECTION_UPGRADE
        sec = DEFAULT_SECTIONS.get(material)
        if sec:
            # Use the in-state layout (which carries per-element upgrades) as the source
            state_layout = final_state.get("layout_json_string")
            if state_layout:
                data = json.loads(state_layout)
            elif ctx.edited_layout_path.exists():
                data = json.loads(ctx.edited_layout_path.read_text(encoding="utf-8"))
            else:
                data = None
            if data:
                is_steel = "STEEL" in material.upper()
                global_beam_sec = sec.get("beam_section", "") if is_steel else ""
                global_col_sec  = sec.get("col_section",  "") if is_steel else ""
                count = 0
                for el in data.get("structure", []):
                    attrs = el.setdefault("attributes", {})
                    attrs["material"] = material
                    is_beam = len(el.get("geometry", [])) == 2
                    cur_sec = attrs.get("section", "")
                    # Preserve individually upgraded sections
                    if is_beam and global_beam_sec and cur_sec and cur_sec != global_beam_sec:
                        count += 1
                        continue
                    if not is_beam and global_col_sec and cur_sec and cur_sec != global_col_sec:
                        count += 1
                        continue
                    if is_beam:
                        attrs["depth"] = str(sec["beam_depth_mm"])
                        attrs["width"] = str(sec["beam_width_mm"])
                        if is_steel and "beam_section" in sec:
                            attrs["section"] = sec["beam_section"]
                        else:
                            attrs.pop("section", None)
                    else:
                        attrs["dimensions"] = sec["col_dims"]
                        if is_steel and "col_section" in sec:
                            attrs["section"] = sec["col_section"]
                        else:
                            attrs.pop("section", None)
                    count += 1
                ctx.edited_layout_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"JSON updated: {material} applied to {count} elements → {ctx.edited_layout_path.name}")

    print("\nWorkflow graph:")
    app.get_graph().print_ascii()

    llm_response = (
        final_state.get("final_response")
        or final_state.get("comparison_result")
        or ""
    )
    eval_table = _format_evaluation(final_state.get("evaluation_result"))

    if eval_table and llm_response:
        final_response = llm_response + "\n\n" + eval_table
    elif eval_table:
        final_response = eval_table
    else:
        final_response = llm_response

    if not final_response and ctx.edited_layout_path.exists():
        final_response = f"Done. Layout saved to {ctx.edited_layout_path.name}"

    # Write evaluation report to file
    _write_evaluation_report(
        prompt=prompt,
        eval_json=final_state.get("evaluation_result"),
        comparison=final_state.get("comparison_result"),
        report_path=ctx.edited_layout_path.parent / "team_01_evaluation_report.md",
    )

    return final_response


def _write_evaluation_report(
    prompt: str,
    eval_json: str | None,
    comparison: str | None,
    report_path: Path,
) -> None:
    import datetime
    lines = [
        f"# Structural Evaluation Report",
        f"",
        f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Prompt:** {prompt}",
        f"",
    ]
    eval_table = _format_evaluation(eval_json)
    if eval_table:
        lines.append("## Structural Checks")
        lines.append("")
        lines.append("```")
        lines.append(eval_table)
        lines.append("```")
        lines.append("")
    if comparison:
        lines.append("## Change Summary")
        lines.append("")
        lines.append(comparison)
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] saved {report_path.name}")


def _format_evaluation(eval_json: str | None) -> str:
    if not eval_json:
        return ""
    try:
        data = json.loads(eval_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    lines = []
    summary = data.get("summary", {})
    status = "PASS" if summary.get("overall_PASS") else "FAIL"
    lines.append(f"Structural evaluation: {status}")
    lines.append("")

    lines.append("BEAMS:")
    for b in data.get("beams", []):
        checks = []
        if not b["bend_PASS"]:   checks.append(f"BEND FAIL S={b['sigma_bend_MPa']}>{b['allow_bend_MPa']}MPa")
        if not b["shear_PASS"]:  checks.append(f"SHEAR FAIL T={b['tau_MPa']}>{b['allow_shear_MPa']}MPa")
        if not b["defl_TL_PASS"]: checks.append(f"DEFL_TL FAIL {b['delta_total_mm']}>{b['limit_TL_mm']}mm")
        if not b["defl_LL_PASS"]: checks.append(f"DEFL_LL FAIL {b['delta_LL_mm']}>{b['limit_LL_mm']}mm")
        flag = "  FAIL: " + " | ".join(checks) if checks else "  ok"
        lines.append(
            f"  {b['id']:8s} {b['section_mm']:9s} L={b['span_m']}m  "
            f"M={b['M_max_kNm']}kNm  S={b['sigma_bend_MPa']}MPa  "
            f"d_LL={b['delta_LL_mm']}mm/{b['limit_LL_mm']}mm{flag}"
        )

    lines.append("")
    lines.append("COLUMNS:")
    for c in data.get("columns", []):
        checks = []
        if not c["stress_PASS"]:   checks.append(f"STRESS FAIL S={c['sigma_comp_MPa']}>{c['allow_comp_MPa']}MPa")
        if not c["buckling_PASS"]: checks.append(f"BUCKLE FAIL SF={c['SF_buckling']}<3")
        flag = "  FAIL: " + " | ".join(checks) if checks else "  ok"
        lines.append(
            f"  {c['id']:8s} {c['section_mm']:9s} H={c['height_m']}m  "
            f"P={c['P_total_kN']}kN  S={c['sigma_comp_MPa']}MPa  "
            f"SF={c['SF_buckling']}{flag}"
        )

    whatif = data.get("what_if")
    if whatif:
        lines.append("")
        ws = whatif.get("summary", {})
        lines.append(f"WHAT-IF — remove {', '.join(whatif.get('removed_ids', []))}: "
                     f"{'PASS' if ws.get('overall_PASS') else 'FAIL'}")
        for r in whatif.get("affected_beams", []):
            span = (f"{r['original_span_m']}m→{r['effective_span_m']}m"
                    if r.get("effective_span_m") else "unsupported")
            checks = []
            if not r.get("bend_PASS",    True): checks.append(f"BEND S={r.get('sigma_bend_MPa')}>{r.get('allow_bend_MPa')}MPa")
            if not r.get("defl_LL_PASS", True): checks.append(f"DEFL_LL {r.get('delta_LL_mm')}>{r.get('limit_LL_mm')}mm")
            if not r.get("defl_TL_PASS", True): checks.append(f"DEFL_TL {r.get('delta_total_mm')}>{r.get('limit_TL_mm')}mm")
            flag = "  FAIL: " + " | ".join(checks) if checks else "  ok"
            lines.append(f"  {r['id']:8s} {span:14s}  M={r.get('M_max_kNm','?')}kNm  S={r.get('sigma_bend_MPa','?')}MPa{flag}")

    return "\n".join(lines)


def _load_all_layouts() -> list[dict[str, Any]]:
    """Load all layouts from example_layouts folder."""
    all_layouts = []
    for json_file in sorted(EXAMPLE_LAYOUTS_DIR.glob("*.json")):
        content = json.loads(json_file.read_text(encoding="utf-8"))
        if isinstance(content, list):
            all_layouts.extend(content)
        else:
            all_layouts.append(content)
    return all_layouts


def _build_initial_state(prompt: str, ctx: Any) -> AgentState:
    # Prefer the edited layout (current working state with structure) if it exists
    if ctx.edited_layout_path.exists():
        edited = json.loads(ctx.edited_layout_path.read_text(encoding="utf-8"))
        layouts = [edited]
    else:
        layouts = _load_all_layouts()

    layout_ids = [l.get("layoutId", "?") for l in layouts]

    # Send slim summary to LLM to stay within token limit
    slim = []
    for l in layouts:
        structure = l.get("structure", [])
        conflicts = [
            {"id": s["id"], "conflict": s["attributes"].get("conflict")}
            for s in structure
            if s.get("attributes", {}).get("conflict") not in (None, "None", "none", "")
        ]
        # Compact per-element lines: "id type material section span_m"
        # Format is intentionally terse (~25 chars/element) to stay within LLM context
        beam_lines = []
        col_lines  = []
        for s in structure:
            attrs   = s.get("attributes", {})
            geo     = s.get("geometry", [])
            is_beam = len(geo) == 2
            sec = (attrs.get("section")
                   or attrs.get("dimensions")
                   or (f"{attrs['width']}x{attrs['depth']}" if attrs.get("depth") and attrs.get("width") else "?"))
            mat = attrs.get("material", "RCC")
            if is_beam:
                span = round(_dist(geo[0], geo[1]), 2)
                beam_lines.append(f"{s['id']} {mat} {sec} {span}m")
            else:
                col_lines.append(f"{s['id']} {mat} {sec}")
        slim.append({
            "layoutId": l.get("layoutId"),
            "outline": l.get("outline"),
            "rooms": [{"id": r["id"], "name": r["name"]} for r in l.get("rooms", [])],
            "structure_count": len(structure),
            "beams":   beam_lines,
            "columns": col_lines,
            "structure_conflicts": conflicts,
        })

    user_message = (
        f"Context: {len(layouts)} layouts loaded from team_01/python/example_layouts/: {layout_ids}.\n"
        f"Valid room names are rooms[].name.\n\n"
        f"User request:\n{prompt}\n\n"
        f"Layout summaries:\n{json.dumps(slim, indent=2)}"
    )

    # Detect material set by set_material.py — preserve through modify/tag_and_audit
    structure = layouts[0].get("structure", []) if layouts else []
    mats = {el.get("attributes", {}).get("material", "RCC") for el in structure if el.get("attributes")}
    detected_material = next(iter(mats)) if len(mats) == 1 else None

    return {
        "messages": [{"role": "user", "content": user_message}],
        "pending_tool_calls": None,
        "final_response": None,
        "iteration": 0,
        "max_iterations": ctx.max_iterations,
        "tool_catalog": _format_tool_catalog(ctx.tools),
        "layout_json_string": json.dumps(layouts[0] if layouts else {}),
        "evaluation_result": None,
        "comparison_result": None,
        "came_from": None,
        "original_layout_json_string": None,
        "cycle": 0,
        "material_override": detected_material,
        "pending_structural_change": None,
        "layout_before_change": None,
        "live_load_kNm2": _settings_load(SETTINGS_PATH, "live_load_kNm2"),
        "sdl_kNm2": _settings_load(SETTINGS_PATH, "sdl_kNm2"),
        "find_minimum_done": False,
    }


def _format_tool_catalog(tools: list[dict[str, Any]]) -> str:
    skip = {"compute_volume_of_sphere", "compute_area_of_sphere",
            "compute_volume_of_cone", "compute_volume_of_box"}
    lines = []
    for tool in tools:
        name = tool.get("name", "<unknown>")
        if name in skip:
            continue
        description = tool.get("description", "")
        schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={schema}")
    return "\n".join(lines)