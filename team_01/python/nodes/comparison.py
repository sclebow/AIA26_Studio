from __future__ import annotations
import json
import re
import time
from collections import Counter

# ### V4 MODIFIED — updated field language to match V4 three-pillar output
SYSTEM_PROMPT = """You summarise a structural change for an architect in 2-4 plain sentences, like a colleague.

Base everything on the change summary, cost/flexibility data, and cost delta provided. Rules, follow exactly:
- Mention only element IDs that appear in the summary. Never invent an ID, room, or number.
- Keep element types exactly as labelled in the summary — if it says "beams", call them beams; never call a beam a column.
- The cost/flexibility data uses three pillars: Financial Cost (label + EUR range), Administrative Burden (label + critical-path weeks), and Adaptability (label + confidence level). Quote these labels exactly as given. Do not substitute old terms such as "flexibility score", "disruption score", or decimal scores.
- The decision_signal field summarises the cross-pillar relationship (e.g. "balanced", "adaptability_premium", "cheap_and_locking"). Translate it into plain language only when it adds meaning; do not quote the raw key.
- If a "Cost delta" line is present in the context, state the before/after total cost and the net change (e.g. "This brings total build cost from X to Y, a saving of Z EUR"). If no cost delta is provided, do not mention costs.
- If heritage_ratchet_triggered_this_intervention is true, note that the building has been flagged for heritage review on all future modifications. Do not mention it if false.
- First, say what changed and what it means structurally.

TRADEOFFS — name at least one that applies:
- Structural safety vs adaptability: if the change brought elements close to their limit (high utilisation), note that headroom for future changes is reduced.
- Adaptability vs cost: if elements were removed, note that the layout is now less reversible, but material cost decreases.
- Safety vs cost: if sections were upgraded, note the improvement in safety margin and the increased cost.

You MAY then suggest ONE next step to explore — but ONLY from this list of moves the system can perform, and ONLY when the data motivates it:
- re-run the evaluation to confirm the change holds
- right-size sections to find the lighter minimum (suggest only if the change reduced or removed load)
- remove another element that looks over-provisioned (only name an element still present after this change)
- upgrade or add a section (only name an element still present after this change)

NEVER suggest an action on an element listed as Removed in the summary — it no longer exists. NEVER suggest adding bracing, trusses, transfer beams, or any move not in the list above. If nothing in the list is clearly motivated, do not force a suggestion — just describe the change and stop.

Reply with JSON: {"action":"final","final_response":"<summary>","tool_calls":[]}"""


def print_diff(before: str, after: str) -> None:
    """Print a human-readable before/after summary of structural attribute changes."""
    from nodes._layout import get_structure as _gs_diff
    def _struct_map(s: str) -> dict:
        return {el["id"]: el for el in _gs_diff(json.loads(s))}
    orig = _struct_map(before)
    mod  = _struct_map(after)
    added   = [v for k, v in mod.items()  if k not in orig]
    removed = [v for k, v in orig.items() if k not in mod]
    changed = [
        {"id": k, "before": orig[k].get("attributes", {}), "after": mod[k].get("attributes", {})}
        for k in orig if k in mod and orig[k].get("attributes") != mod[k].get("attributes")
    ]
    if added:
        print(f"  Added   : {', '.join(e['id'] for e in added)}")
    if removed:
        print(f"  Removed : {', '.join(e['id'] for e in removed)}")

    if changed:
        # Detect bulk tier upgrade: no adds/removes, all elements changed section uniformly
        def _sec(attrs):
            return attrs.get("section") or f"{attrs.get('width','')}x{attrs.get('depth','')}" or attrs.get("dimensions","")
        _beam_before = set(); _beam_after = set()
        _col_before  = set(); _col_after  = set()
        _beam_ids = []; _col_ids = []
        for c in changed:
            is_beam = len(orig.get(c["id"], {}).get("geometry", [])) == 2
            if is_beam:
                _beam_before.add(_sec(c["before"])); _beam_after.add(_sec(c["after"]))
                _beam_ids.append(c["id"])
            else:
                _col_before.add(_sec(c["before"])); _col_after.add(_sec(c["after"]))
                _col_ids.append(c["id"])
        _is_bulk = (
            not added and not removed
            and len(changed) >= 5
            and len(_beam_before) <= 1 and len(_beam_after) <= 1
            and len(_col_before)  <= 1 and len(_col_after)  <= 1
        )
        if _is_bulk:
            parts = []
            if _beam_ids:
                b_from = next(iter(_beam_before), "?"); b_to = next(iter(_beam_after), "?")
                parts.append(f"{len(_beam_ids)} beams: {b_from} -> {b_to}")
            if _col_ids:
                c_from = next(iter(_col_before), "?"); c_to = next(iter(_col_after), "?")
                parts.append(f"{len(_col_ids)} columns: {c_from} -> {c_to}")
            print(f"  Tier upgrade: {' | '.join(parts)}")
        else:
            for c in changed:
                b, a = c["before"], c["after"]
                diffs = [f"{k}: {b.get(k,'—')} -> {a.get(k,'—')}"
                         for k in set(list(b) + list(a)) if b.get(k) != a.get(k)]
                if diffs:
                    print(f"  {c['id']:12s} {' | '.join(diffs)}")

    if not added and not removed and not changed:
        print("  No structural changes.")


def _slim_diff_for_llm(original_json: str, modified_json: str) -> str:
    """Compact grouped text summary of structural changes — stays well under 400 tokens."""
    from nodes._layout import get_structure as _gs_slim
    def _struct_map(s: str) -> dict:
        return {el["id"]: el for el in _gs_slim(json.loads(s))}

    orig = _struct_map(original_json)
    mod  = _struct_map(modified_json)

    added   = [k for k in mod  if k not in orig]
    removed = [k for k in orig if k not in mod]
    changed = [k for k in orig if k in mod and orig[k].get("attributes") != mod[k].get("attributes")]

    def _kind(el: dict) -> str:
        return "column" if len(el.get("geometry", [])) == 1 else "beam"

    def _grouped(ids: list, src: dict, verb: str) -> list:
        out = []
        for label in ("columns", "beams"):
            kind = "column" if label == "columns" else "beam"
            group = [k for k in ids if _kind(src[k]) == kind]
            if group:
                sample = ", ".join(group[:5]) + (f" +{len(group)-5} more" if len(group) > 5 else "")
                out.append(f"{verb} {label} ({len(group)}): {sample}")
        return out

    lines = []
    lines += _grouped(added, mod, "Added")
    lines += _grouped(removed, orig, "Removed")

    if changed:
        patterns: Counter = Counter()
        def _size_token(el: dict) -> str:
            at = el.get("attributes", {})
            if at.get("section"):
                return at["section"]
            if _kind(el) == "beam" and at.get("width") and at.get("depth"):
                return f"{at['width']}x{at['depth']}"
            if at.get("dimensions"):
                return at["dimensions"]
            return at.get("material", "")
        for k in changed:
            sec_b = _size_token(orig[k])
            sec_a = _size_token(mod[k])
            if sec_b != sec_a:
                patterns[f"{sec_b}->{sec_a}"] += 1
            else:
                _attrs_b = orig[k].get("attributes", {})
                _attrs_a = mod[k].get("attributes", {})
                mat_b, mat_a = _attrs_b.get("material", ""), _attrs_a.get("material", "")
                if mat_b != mat_a:
                    patterns[f"material {mat_b}->{mat_a}"] += 1
                else:
                    patterns["other attribute change"] += 1

        lines.append(f"Changed {len(changed)} elements:")
        for pat, cnt in patterns.most_common(8):
            lines.append(f"  {cnt}x {pat}")

    if not added and not removed and not changed:
        lines.append("No structural changes.")

    return "\n".join(lines)


def _fallback_summary(original_json: str, modified_json: str) -> str:
    """Plain-text comparison used when the LLM is unavailable — reuses grouped diff."""
    diff = _slim_diff_for_llm(original_json, modified_json)
    return diff if diff else "No structural changes detected."


def build_comparison_node(llm):

    def comparison_node(state):
        print(f"\n{'='*50}")
        print(f"  NODE: COMPARISON  (cycle {state.get('cycle', 0) + 1})")
        print(f"{'='*50}")

        if state.get("came_from") == "structural_change" and state.get("layout_before_change"):
            original = state["layout_before_change"]
            print("\nChanges from last structural modification:")
            print_diff(original, state["layout_json_string"])
        else:
            original = state.get("original_layout_json_string") or state["layout_json_string"]

        diff_text = _slim_diff_for_llm(original, state["layout_json_string"])
        context_message = f"Structural change summary:\n{diff_text}"
        _cf = state.get("cost_flexibility")
        if _cf and _cf.get("summary"):
            context_message += f"\n\nCost & Flexibility: {_cf['summary']}"
        _cost_history = state.get("cost_history") or []
        if len(_cost_history) >= 2:
            _prev = _cost_history[-2]
            _curr = _cost_history[-1]
            _prev_total = _prev.get("total_build_cost_eur") or _prev.get("total_mid_eur")
            _curr_total = _curr.get("total_build_cost_eur") or _curr.get("total_mid_eur")
            if _prev_total is not None and _curr_total is not None:
                _delta = _curr_total - _prev_total
                _sign = "+" if _delta >= 0 else ""
                context_message += (
                    f"\n\nCost delta: previous total {_prev_total:,.0f} EUR -> current total {_curr_total:,.0f} EUR"
                    f" ({_sign}{_delta:,.0f} EUR)"
                )
        messages = [{"role": "user", "content": context_message}]

        result = None
        last_error = None
        for attempt in range(3):
            try:
                llm_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context_message},
                ]
                raw = llm.invoke(llm_messages)
                data = json.loads(raw.content)
                result = data.get("final_response", raw.content)
                # Strip any XML/HTML tags that small models sometimes echo back
                result = re.sub(r"<[^>]+>", "", result).strip()
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"Comparison LLM failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                    time.sleep(wait)

        if result is None:
            result = _fallback_summary(original, state["layout_json_string"])
            print(f"Comparison LLM unavailable — using built-in summary.")

        print(f"Comparison result: {result}")
        state["comparison_result"] = result
        state["cycle"] = state.get("cycle", 0) + 1
        state["messages"].append({
            "role": "user",
            "content": f"Comparison summary: {result}",
        })
        return state

    return comparison_node
