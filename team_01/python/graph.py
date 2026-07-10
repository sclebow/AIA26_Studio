from __future__ import annotations
import json
import math
import sys
from pathlib import Path
from typing import Any, TypedDict


def _safe_input(prompt: str, default: str = "") -> str:
    """Return `default` silently when stdin is not a terminal (orchestrator / headless mode)."""
    if not sys.stdin.isatty():
        print(f"{prompt}{default}  [auto]")
        return default
    return input(prompt)
from langgraph.graph import END, START, StateGraph
from nodes.reason import build_reason_node
from nodes.modify import build_modify_node, DEFAULT_SECTIONS, BEAM_SECTION_UPGRADE, COL_SECTION_UPGRADE
from nodes.evaluate import build_evaluate_node, evaluate_structure, SETTINGS_PATH, _get_user_request
from nodes.comparison import build_comparison_node
from nodes.cost_flexibility import build_cost_flexibility_node
from nodes.tag_and_audit import generate_structure as _generate_structure

EXAMPLE_LAYOUTS_DIR = Path(__file__).parent / "example_layouts"
OTHER_LAYOUTS_DIR   = Path(__file__).parent.parent / "gh" / "other layouts"


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
    cost_flexibility: dict | None
    cost_history: list | None          # one entry per modify→cost_flex cycle
    # ### V4 START — context inputs for three-pillar cost/flexibility model
    # All five keys are loaded from team_01_settings.json at session start.
    # Absent settings keys fall back to the listed defaults.
    building_occupancy_class: str | None   # "VACANT"|"LOW"|"HIGH"|"CRITICAL"; default HIGH
    building_context: str | None           # "NEW"|"EXISTING_KNOWN"|"EXISTING_UNKNOWN"; default EXISTING_KNOWN
    floor_level: int | None                # positive = above grade, negative = basement; default 1
    heritage_status: bool                  # pre-existing heritage designation; immutable after init
    heritage_ratchet: bool                 # persistent building flag; seeded from heritage_status;
                                           # set True by cost_flexibility node when P4 triggers;
                                           # never reset to False within a session
    # ### V4 END


_EVAL_KEYWORDS = frozenset({
    "evaluat", "check loads", "check structure", "check if",
    "find minimum", "minimum section", "minimum sufficient",
    "optimiz", "upgrade section", "structurally feasible",
    "structure hold", "assess struct", "run structural",
    "is this safe", "is it safe", "is the structure",
    "will it hold", "can it support", "safe to",
    "remove column", "remove beam", "delete column", "delete beam",
    "what if", "what would happen", "if i remove", "if we remove",
})


def _looks_like_eval(state: AgentState) -> bool:
    """Return True when the user's original prompt is an evaluation/computation request."""
    text = _get_user_request(state.get("messages", []))
    return any(kw in text for kw in _EVAL_KEYWORDS)


def _route_from_reason(state: AgentState) -> str:
    if state.get("pending_tool_calls") and state.get("cycle", 0) < 2:
        calls = [tc.get("name") for tc in (state.get("pending_tool_calls") or [])]
        if "tag_and_audit" in calls:
            return "generate_grid"
        if _looks_like_eval(state):
            state["pending_tool_calls"] = None
            return "evaluate"
        return "modify"
    if state.get("cycle", 0) >= 2:
        return END
    if state.get("evaluation_result") is not None:
        return END
    if state.get("final_response"):
        if _looks_like_eval(state):
            return "evaluate"
        return END
    return "evaluate"


def _route_from_evaluate(state: AgentState) -> str:
    if state.get("pending_structural_change"):
        return "modify"
    if state.get("evaluation_result") is not None:
        return "cost_flexibility"
    return "reason"


def _route_from_cost_flexibility(state: AgentState) -> str:
    if state.get("came_from") in ("modify", "structural_change", "generate_grid"):
        return "comparison"
    return END


def build_generate_grid_node(edited_layout_path):
    from _runtime.llm import write_tool_result

    def generate_grid_node(state: dict) -> dict:
        print(f"\n{'='*50}")
        print(f"  NODE: GENERATE GRID")
        print(f"{'='*50}")

        if not state.get("original_layout_json_string"):
            state["original_layout_json_string"] = state["layout_json_string"]

        # Save original snapshot (layout without structure) — never overwritten by modify
        original_path = edited_layout_path.with_stem(edited_layout_path.stem + "_original")
        original_path.write_text(state["layout_json_string"], encoding="utf-8")
        # Also initialise before to the same state so first comparison has a valid baseline
        before_path = edited_layout_path.with_stem(edited_layout_path.stem + "_before")
        before_path.write_text(state["layout_json_string"], encoding="utf-8")

        layout_data = json.loads(state["layout_json_string"])
        options = _generate_structure(layout_data)

        if not options:
            print("[generate_grid] No options returned — layout unchanged.")
            state["came_from"] = "generate_grid"
            state["pending_tool_calls"] = None
            return state

        if len(options) == 1:
            chosen = options[0]
        else:
            from nodes._layout import get_structure as _gs_grid
            print(f"\n{len(options)} layout options generated:")
            for i, opt in enumerate(options):
                struct  = _gs_grid(opt)
                n_cols  = sum(1 for s in struct if len(s["geometry"]) == 1)
                n_beams = sum(1 for s in struct if len(s["geometry"]) == 2)
                max_span = max(
                    (s["attributes"]["length"] for s in struct
                     if len(s["geometry"]) == 2 and s["attributes"].get("length")),
                    default=0,
                )
                print(f"  {i+1}. {n_cols} columns · {n_beams} beams · max span {round(max_span, 2)}m")
            while True:
                raw = _safe_input(f"Choose option [1-{len(options)}, Enter=1]: ", "").strip()
                if not raw:
                    chosen = options[0]
                    print("[generate_grid] Using option 1")
                    break
                if raw.isdigit() and 1 <= int(raw) <= len(options):
                    chosen = options[int(raw) - 1]
                    print(f"[generate_grid] Using option {raw}")
                    break

        from nodes._layout import get_structure as _gs_grid
        n = len(_gs_grid(chosen))
        print(f"Structural grid ready — {n} elements placed.")

        state["layout_json_string"] = json.dumps(chosen)
        state["came_from"] = "generate_grid"
        state["pending_tool_calls"] = None
        write_tool_result(json.dumps(chosen), edited_layout_path)
        return state

    return generate_grid_node


def build_graph(ctx: Any) -> Any:
    reason       = build_reason_node(ctx.llm)
    generate_grid = build_generate_grid_node(ctx.edited_layout_path)
    modify       = build_modify_node(ctx.mcp_client, ctx.tools, ctx.edited_layout_path, evaluate_fn=evaluate_structure)
    evaluate     = build_evaluate_node(ctx.llm)
    cost_flex    = build_cost_flexibility_node()
    comparison   = build_comparison_node(ctx.llm)

    graph = StateGraph(AgentState)
    graph.add_node("reason",        reason)
    graph.add_node("generate_grid", generate_grid)
    graph.add_node("modify",        modify)
    graph.add_node("evaluate",      evaluate)
    graph.add_node("cost_flexibility", cost_flex)
    graph.add_node("comparison",    comparison)

    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", _route_from_reason,
        {"generate_grid": "generate_grid", "modify": "modify", "evaluate": "evaluate", END: END})
    graph.add_edge("generate_grid", "evaluate")
    graph.add_edge("modify",        "evaluate")
    graph.add_conditional_edges("evaluate", _route_from_evaluate,
        {"modify": "modify", "cost_flexibility": "cost_flexibility", "reason": "reason"})
    graph.add_conditional_edges("cost_flexibility", _route_from_cost_flexibility,
        {"comparison": "comparison", END: END})
    graph.add_edge("comparison", END)

    return graph.compile()


def run_agent(prompt: str, ctx: Any, layout_data: dict | None = None) -> tuple[str, str | None]:
    app = build_graph(ctx)
    initial_state = _build_initial_state(prompt, ctx, layout_data=layout_data)
    final_state = app.invoke(initial_state)

    # Persist material override to JSON after graph completes (survives multiple modify cycles)
    material = final_state.get("material_override")
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
                from nodes._layout import iter_all_structure as _ias
                is_steel = "STEEL" in material.upper()
                global_beam_sec = sec.get("beam_section", "") if is_steel else ""
                global_col_sec  = sec.get("col_section",  "") if is_steel else ""
                count = 0
                for _lk, el in _ias(data):
                    attrs = el.setdefault("attributes", {})
                    attrs["material"] = material
                    is_beam = len(el.get("geometry", [])) == 2
                    cur_sec = attrs.get("section", "")
                    # Preserve individually upgraded sections.
                    # STEEL: compare section codes (e.g. "IPE300").
                    # TIMBER/RCC: compare depth×width for beams, dimensions string for columns.
                    if is_beam:
                        if is_steel and global_beam_sec and cur_sec and cur_sec != global_beam_sec:
                            count += 1
                            continue
                        elif not is_steel:
                            cur_d = str(attrs.get("depth", ""))
                            cur_w = str(attrs.get("width", ""))
                            if cur_d and cur_w and (
                                cur_d != str(sec["beam_depth_mm"]) or
                                cur_w != str(sec["beam_width_mm"])
                            ):
                                count += 1
                                continue
                    else:
                        if is_steel and global_col_sec and cur_sec and cur_sec != global_col_sec:
                            count += 1
                            continue
                        elif not is_steel:
                            cur_dims = attrs.get("dimensions", "")
                            if cur_dims and cur_dims != sec["col_dims"]:
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
                print(f"Layout saved — {material} applied to {count} elements.")



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
        cost_flexibility=final_state.get("cost_flexibility"),
        cost_history=final_state.get("cost_history") or [],
        material=final_state.get("material_override"),
        sdl_kNm2=final_state.get("sdl_kNm2"),
        live_load_kNm2=final_state.get("live_load_kNm2"),
    )

    edited_layout_json = final_state.get("layout_json_string") or None
    # Inject cost/flexibility data into the returned layout JSON
    if edited_layout_json and final_state.get("cost_flexibility"):
        try:
            _layout_data = json.loads(edited_layout_json)
            _layout_data.setdefault("analysis", {})["structure_cost"] = final_state["cost_flexibility"]
            edited_layout_json = json.dumps(_layout_data, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return final_response, edited_layout_json, app


def _write_evaluation_report(
    prompt: str,
    eval_json: str | None,
    comparison: str | None,
    report_path: Path,
    cost_flexibility: dict | None = None,
    cost_history: list | None = None,
    material: str | None = None,
    sdl_kNm2: float | None = None,
    live_load_kNm2: float | None = None,
) -> None:
    import datetime
    lines = [
        f"# Structural Evaluation Report",
        f"",
        f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Prompt:** {prompt}",
        f"",
    ]
    # Analysis parameters summary
    if material or sdl_kNm2 or live_load_kNm2:
        lines.append("## Analysis Parameters")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        if material:
            lines.append(f"| Material | {material} |")
        if sdl_kNm2 is not None:
            lines.append(f"| Floor build-up (SDL) | {sdl_kNm2} kN/m² |")
        if live_load_kNm2 is not None:
            lines.append(f"| Live load | {live_load_kNm2} kN/m² |")
        if sdl_kNm2 is not None and live_load_kNm2 is not None:
            lines.append(f"| Total applied load | {round(sdl_kNm2 + live_load_kNm2, 2)} kN/m² |")
        lines.append("")
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
    # ### V4 MODIFIED — dual-path: reads V4 field names when present, falls back to V3 field
    # names for sessions still running the old cost_flexibility.py. V3 path is removed once
    # cost_flexibility.py is migrated; also hardened all V3 field accesses to .get() to
    # prevent KeyError if the dict is partially populated.
    if cost_flexibility:
        cf = cost_flexibility
        lines.append("## Cost & Flexibility Analysis")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        if cf.get("financial_cost_label") is not None or cf.get("total_build_cost"):
            # V4 path
            tbc = cf.get("total_build_cost", {})
            if tbc and tbc.get("total_build_mid_eur"):
                vol_str = "  ·  ".join(
                    f"{v:.3f} m³ {k}" for k, v in tbc.get("total_build_vol_m3", {}).items()
                )
                lines.append(
                    f"| **Total Structure Build Cost** | "
                    f"**{tbc['total_build_label']} "
                    f"(EUR {tbc['total_build_mid_eur']:,.0f} / "
                    f"{tbc['total_build_low_eur']:,.0f}–{tbc['total_build_high_eur']:,.0f})** |"
                )
                lines.append(f"| ↳ Volume | {vol_str} |")
                lines.append(f"| ↳ PEM (works budget) | EUR {tbc['total_build_pem_eur']:,.0f} |")
            ds = cf.get("design_savings_eur", 0)
            if ds:
                lines.append(f"| Design-Phase Saving | EUR {ds:,.0f} (avoided new-build cost of removed elements) |")
            if cf.get("financial_cost_label") is None:
                # only total build cost, no modification diff — stop here
                lines.append("")
            else:
                fc_range = cf.get("financial_cost_range", {})
                curr = fc_range.get("currency", "EUR")
                mid  = fc_range.get("mid",  0)
                intervention_eur = cf.get("intervention_mid_eur", 0)
                overhead_eur     = cf.get("overhead_mid_eur", 0)
                lines.append(f"| Last Modification Cost | {cf['financial_cost_label']} ({curr} {mid:,.0f}) |")
                lines.append(f"| ↳ Intervention | {curr} {intervention_eur:,.0f} (labour, demolition, material) |")
                lines.append(f"| ↳ Overhead | {curr} {overhead_eur:,.0f} (mobilisation, temp works, fees) |")
                lines.append(f"| Cost Driver | {cf.get('dominant_cost_driver', '—')} |")
                lines.append(f"| Admin Burden | {cf.get('admin_burden_label', '—')} |")
                crit = cf.get("admin_critical_path_weeks", {})
                lines.append(f"| Admin Critical Path | {crit.get('mid', '—')} wks (mid) |")
                lines.append(f"| Dominant Process | {cf.get('dominant_admin_process', '—')} |")
                lines.append(f"| Adaptability | {cf.get('adaptability_label', '—')} ({cf.get('adaptability_confidence', '—')} confidence) |")
                lines.append(f"| Adaptability Constraint | {cf.get('adaptability_constraint', '—')} |")
                lines.append(f"| Decision Signal | {cf.get('decision_signal', '—')} |")
                if cf.get("heritage_ratchet_triggered_this_intervention"):
                    lines.append("| Heritage Ratchet | Triggered this intervention — permanent |")
        else:
            # V3 fallback path — active until cost_flexibility.py is updated to V4
            if cf.get("cost_added_usd") is not None:
                lines.append(f"| Material added | +${cf['cost_added_usd']:,.0f} |")
                lines.append(f"| Material saved | -${abs(cf.get('cost_saved_usd', 0)):,.0f} |")
                lines.append(f"| Net cost change | ${cf.get('net_cost_usd', 0):+,.0f} |")
            else:
                lines.append(f"| Net cost change | ${cf.get('material_cost_usd', 0):+,.0f} |")
            lines.append(f"| Disruption | {cf.get('disruption_label', '—')} ({cf.get('disruption_score', 0)}/10) |")
            lines.append(f"| Spatial Penalty | {cf.get('spatial_penalty', 0):.2f} |")
            lines.append(f"| Flexibility | {cf.get('flexibility_score', 0):.1f}/10 — {cf.get('flexibility_label', '—')} |")
        lines.append("")
        if cf.get("summary"):
            lines.append(f"> {cf['summary']}")
            lines.append("")
    # Cumulative cost across all upgrade cycles
    if cost_history and len(cost_history) > 1:
        lines.append("## Cumulative Modification Cost")
        lines.append("")
        lines.append("| Cycle | Changes | Intervention Cost | Total Build Cost |")
        lines.append("|-------|---------|-------------------|-----------------|")
        total_intervention_eur = 0
        for entry in cost_history:
            mid = entry.get("total_mid_eur", 0)
            total_intervention_eur += mid
            tbc_eur = entry.get("total_build_cost_eur", {})
            tbc_mid = tbc_eur.get("total_build_mid_eur", 0) if isinstance(tbc_eur, dict) else 0
            tbc_str = f"EUR {tbc_mid:,.0f}" if tbc_mid else "—"
            lines.append(
                f"| {entry['cycle']} | {entry.get('changes', '—')} "
                f"| {entry.get('label', '—')} (EUR {mid:,.0f}) | {tbc_str} |"
            )
        lines.append(f"| **Total** | | **EUR {total_intervention_eur:,.0f}** | |")
        # Cost delta: first vs last total build cost
        first_tbc = cost_history[0].get("total_build_cost_eur", {})
        last_tbc  = cost_history[-1].get("total_build_cost_eur", {})
        if isinstance(first_tbc, dict) and isinstance(last_tbc, dict):
            first_mid = first_tbc.get("total_build_mid_eur", 0)
            last_mid  = last_tbc.get("total_build_mid_eur", 0)
            if first_mid and last_mid:
                delta = last_mid - first_mid
                sign = "+" if delta >= 0 else ""
                lines.append(f"| **Cost delta** | first to last | | **{sign}EUR {delta:,.0f}** |")
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
    """Load all layouts from example_layouts/ and gh/other layouts/."""
    all_layouts = []
    for layouts_dir in (EXAMPLE_LAYOUTS_DIR, OTHER_LAYOUTS_DIR):
        if not layouts_dir.exists():
            continue
        for json_file in sorted(layouts_dir.glob("*.json")):
            try:
                content = json.loads(json_file.read_text(encoding="utf-8"))
                entries = content if isinstance(content, list) else [content]
                for entry in entries:
                    if isinstance(entry, dict) and (
                        ("rooms" in entry and "outline" in entry)
                        or "levels" in entry
                    ):
                        all_layouts.append(entry)
            except Exception:
                pass
    return all_layouts


def _build_initial_state(prompt: str, ctx: Any, layout_data: dict | None = None) -> AgentState:
    # Orchestrator-provided layout wins over everything — no menu shown
    if layout_data is not None:
        layouts = [layout_data]
        print(f"[layout] Using orchestrator-provided layout: {layout_data.get('layoutId', '?')}")
    # Prefer the edited layout (current working state with structure) if it exists
    elif ctx.edited_layout_path.exists():
        edited = json.loads(ctx.edited_layout_path.read_text(encoding="utf-8"))
        layouts = [edited]
    else:
        layouts = _load_all_layouts()
        if len(layouts) > 1:
            print(f"\n{len(layouts)} layouts available:")
            from nodes._layout import get_structure as _gs_menu, get_all_rooms as _gar_menu
            for i, l in enumerate(layouts):
                lid     = l.get("layoutId", f"layout-{i+1}")
                n_rooms = len(_gar_menu(l))
                has_structure = len(_gs_menu(l)) > 0
                tag = " [has structure]" if has_structure else ""
                print(f"  {i+1}. {lid}  ({n_rooms} rooms){tag}")
            while True:
                raw = _safe_input(f"Choose layout [1-{len(layouts)}, Enter=1]: ", "").strip()
                if not raw:
                    layouts = [layouts[0]]
                    print(f"[layout] Using {layouts[0].get('layoutId', 'layout-1')}")
                    break
                if raw.isdigit() and 1 <= int(raw) <= len(layouts):
                    layouts = [layouts[int(raw) - 1]]
                    print(f"[layout] Using {layouts[0].get('layoutId', '?')}")
                    break

    layout_ids = [l.get("layoutId", "?") for l in layouts]

    # Send slim summary to LLM to stay within token limit
    from nodes._layout import get_structure as _gs_slim, get_all_rooms as _gar_slim, get_outline as _go_slim
    slim = []
    for l in layouts:
        structure = _gs_slim(l)
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
        all_rooms = _gar_slim(l)
        slim.append({
            "layoutId": l.get("layoutId"),
            "outline": _go_slim(l),
            "rooms": [{"id": r["id"], "name": r["name"]} for r in all_rooms],
            "structure_count": len(structure),
            "beams":   beam_lines,
            "columns": col_lines,
            "structure_conflicts": conflicts,
        })

    user_message = (
        f"Context: {len(layouts)} layouts loaded from team_01/python/example_layouts/ "
        f"and team_01/gh/other layouts/: {layout_ids}.\n"
        f"Valid room names are rooms[].name.\n\n"
        f"User request:\n{prompt}\n\n"
        f"Layout summaries:\n{json.dumps(slim, indent=2)}"
    )

    # Detect material set by set_material.py — preserve through modify/tag_and_audit
    from nodes._layout import get_structure as _gs_mat
    structure = _gs_mat(layouts[0]) if layouts else []
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
        "cost_flexibility": None,
        "cost_history": [],
        # ### V4 START — initialize context inputs; absent settings keys fall back to defaults
        "building_occupancy_class": _settings_load(SETTINGS_PATH, "building_occupancy_class") or "HIGH",
        "building_context":         _settings_load(SETTINGS_PATH, "building_context") or "EXISTING_KNOWN",
        "floor_level":              int(_settings_load(SETTINGS_PATH, "floor_level") or 1),
        "heritage_status":          bool(_settings_load(SETTINGS_PATH, "heritage_status") or False),
        "heritage_ratchet":         bool(_settings_load(SETTINGS_PATH, "heritage_status") or False),
        # ### V4 END
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