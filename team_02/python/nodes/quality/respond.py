"""
RESPOND node — generates the final user-facing response.
Format adapts to action (analyze/detect/full/edit/etc.) and user_type register.
Incorporates specialist interpretations and any evaluator revision feedback.
"""

from __future__ import annotations
import json as _json
from _runtime.llm import call_llm_simple
from nodes._shared.utils import grounded_facts, grounded_extremes
from nodes._shared.register import register_tone

# The unified edit action (one OR MORE edits applied in a single turn).
_EDIT_ACTIONS = ("edit",)


def _format_change(layout_diff):
    """One readable line describing a single edit, from the structured layout_diff."""
    if not layout_diff:
        return ""
    room = layout_diff.get("room_name", "the room")
    attr = layout_diff.get("attribute", "")
    old  = layout_diff.get("old_value", "")
    new  = layout_diff.get("new_value", "")
    sense = layout_diff.get("sense_affected", "")
    if attr == "furniture":
        line = f"{new} in the {room}"            # e.g. "added plant (natural) in the Kitchen"
    else:
        line = f"{room}: {attr} {old} -> {new}"
    if sense:
        line += f" (primarily affects {sense})"
    return line


def _format_changes(layout_diffs):
    """One line per edit when several were applied in the same turn."""
    diffs = [d for d in (layout_diffs or []) if d]
    if not diffs:
        return ""
    return "\n".join(f"- {_format_change(d)}" for d in diffs) if len(diffs) > 1 \
        else _format_change(diffs[0])


def _deterministic_summary(persona_label, layout_id, action, scores_json, conflicts_json,
                           layout_diffs=None, compare_versions=""):
    """A correct, data-grounded summary used when the LLM returns nothing.

    The reasoning model (qwen3) occasionally emits only a <think> block, leaving an
    empty answer. Rather than a generic 'see the panel' line, build a real summary
    from the computed extremes so the user always gets accurate information.
    """
    head = f"For {persona_label}, Layout {layout_id}: "

    # Edit: lead with the change(s) and whether scores moved.
    if action in _EDIT_ACTIONS:
        diffs = [d for d in (layout_diffs or []) if d]
        change = _format_changes(diffs).replace("\n", "; ") or "an edit was applied to the layout"
        # any meaningful delta line in the comparison (skip the header line)?
        has_delta = any(
            ":" in ln and "no change" not in ln.lower()
            for ln in (compare_versions or "").splitlines()[1:]
        )
        if has_delta:
            return head + f"applied {change}. Scores updated - see the panel for the before-to-after delta."
        return head + f"applied {change}. Scores were updated - see the panel."

    e = grounded_extremes(scores_json)
    if not e:
        return head + "the analysis is ready - see the panel for the full breakdown."
    parts = [
        f"the weakest spot is {e['lo_sense']} in the {e['lo_room']} ({e['lo_val']:.2f}), "
        f"and the lowest-scoring room overall is {e['worst_room']} ({e['worst_overall']:.2f})."
    ]
    if action in ("detect", "full") and conflicts_json:
        try:
            n = len(_json.loads(conflicts_json).get("flaggedRooms", []))
            if n:
                parts.append(f" {n} room(s) have comfort conflicts.")
        except Exception:
            pass
    parts.append(" See the panel for the full breakdown.")
    return head + "".join(parts)


_SYSTEM_PROMPT = (
    "You are Sensi, an architectural comfort analyst specialising in "
    "multi-sensory wellbeing: thermal, visual, acoustic, spatial, olfactory, tactile.\n\n"
    "Write a plain-language response shaped around what the user asked for.\n"
    "Use ONLY the data provided. Never invent scores, conflicts, or suggestions.\n\n"
    "ALWAYS start with exactly one line using the name and role from Persona:\n"
    "  For <name> (<role>), Layout <id>:\n\n"
    "Then follow the FORMAT INSTRUCTIONS in the user message exactly.\n\n"
    "Hard rules for ALL formats:\n"
    "- Use ONLY scores from PRE-PROCESSED ROOM DATA. Copy numbers exactly.\n"
    "- Best and Worst are pre-computed -- copy them, do not recalculate.\n"
    "- NEVER claim a room or sense is the 'lowest/highest/worst/best of all rooms',\n"
    "  'across all rooms', or 'across the layout' unless that exact statement appears\n"
    "  in GROUNDED FACTS. This includes per-sense claims like 'worst spatial of all\n"
    "  rooms' - those are NOT in GROUNDED FACTS, so do not make them.\n"
    "- The single worst sense+room for the WHOLE layout is the 'Lowest single sense'\n"
    "  line in GROUNDED FACTS - if you name an overall worst, use that one verbatim.\n"
    "- A room's own best/worst sense is in its PRE-PROCESSED ROOM DATA line (best=/worst=).\n"
    "  Use those for a single room - do not eyeball the per-sense numbers yourself.\n"
    "- Persona name appears ONCE at the top only.\n"
    "- No markdown tables. No JSON. No tool names. Plain ASCII only.\n"
    "- Use a hyphen (-) not an em dash. No special characters.\n"
    "- The full data breakdown is shown in the analysis panel. Your job is a SHORT SUMMARY only.\n"
    "- Name rooms by their EXACT name and senses by their exact word (thermal/visual/acoustic/\n"
    "  spatial/olfactory/tactile) - the live canvas highlights whatever you name, so don't paraphrase.\n"
    "- If SCORE INTERPRETATION context is provided, use it to enrich your language.\n"
    "- If REVISION INSTRUCTION is provided, apply it exactly before generating.\n"
    "- For an edit, WHAT CHANGED may list SEVERAL edits - summarise them together,\n"
    "  and report the combined before-to-after effect from VERSION COMPARISON.\n\n"
    "STATED PREFERENCES vs COMFORT RESEARCH:\n"
    "The persona carries comfort_weights derived from their stated preferences.\n"
    "When a finding or suggestion contradicts what the user rated as low priority\n"
    "but is supported by comfort research, add one brief note inline:\n"
    "  'Note: research flags this even though you rated <sense> as lower priority.'\n"
    "Only flag genuine contradictions. Do not add this note for aligned findings.\n"
)

_FORMAT_ANALYZE = (
    "FORMAT: 2-3 sentence chat summary (scores only)\n"
    "The full score breakdown is shown in the analysis panel — do NOT repeat it here.\n\n"
    "Write exactly 2-3 sentences:\n"
    "  1. What was analysed (layout ID, all rooms or a specific room).\n"
    "  2. The headline finding: the layout's worst spot — use the 'Lowest single sense'\n"
    "     line from GROUNDED FACTS verbatim (that room + sense + value). Do not pick a\n"
    "     different room/sense or invent a per-sense ranking.\n"
    "  3. Optionally: one sentence noting what stands out positively, if relevant.\n\n"
    "No room-by-room breakdown. No score lists. No markdown. Plain sentences only.\n"
    "Do NOT mention conflicts or suggestions.\n"
)

_FORMAT_DETECT = (
    "FORMAT: 2-3 sentence chat summary (scores + conflicts)\n"
    "The full score breakdown and conflict details are shown in the analysis panel — do NOT repeat them here.\n\n"
    "Write exactly 2-3 sentences:\n"
    "  1. How many rooms have comfort conflicts and which sense is most affected.\n"
    "  2. The single most critical conflict for this persona, in plain language.\n"
    "  3. One sentence: what the panel shows and what to ask next.\n\n"
    "No room-by-room breakdown. No score lists. No markdown. Plain sentences only.\n"
    "Do NOT mention suggestions.\n"
)

_FORMAT_FULL = (
    "FORMAT: 2-3 sentence chat summary (full analysis with suggestions)\n"
    "The full scores, conflicts, and suggestions are shown in the analysis panel — do NOT repeat them here.\n\n"
    "Write exactly 2-3 sentences:\n"
    "  1. The single most important intervention for this persona, stated plainly.\n"
    "  2. Which room benefits most and what sense is addressed.\n"
    "  3. One sentence: invite the user to explore the suggestions in the panel or ask a follow-up.\n\n"
    "No room-by-room breakdown. No score lists. No markdown. Plain sentences only.\n"
)

_FORMAT_EDIT = (
    "FORMAT: 2-3 sentence chat summary for a LAYOUT EDIT.\n"
    "You just applied ONE OR MORE changes to the layout and re-scored it once.\n"
    "Report the change(s) and the combined effect.\n\n"
    "Write exactly 2-3 sentences:\n"
    "  1. State the edit(s) plainly: the room(s) and what changed (see WHAT CHANGED).\n"
    "     If several edits were made, summarise them together in one natural sentence.\n"
    "  2. The effect: report ONLY the senses listed in VERSION COMPARISON, and copy their\n"
    "     'before->after' numbers EXACTLY as shown there. Do NOT mention a sense that isn't\n"
    "     listed, and NEVER invent, round, or alter a number (no values above 1.00). If a\n"
    "     room shows 'no change', say the change had no meaningful effect - do not invent one.\n"
    "  3. One short next step (e.g. detect conflicts, or try another change).\n\n"
    "Lead with the change(s) and their impact - do NOT write a generic full-layout analysis.\n"
    "No score lists. No markdown. Plain sentences only.\n"
)


def _preprocess_scores(scores_json):
    if not scores_json:
        return "(no scores available)"
    try:
        data = _json.loads(scores_json)
    except Exception:
        return scores_json

    lines = []
    for room in data.get("rooms", []):
        name    = room.get("roomName", "unknown")
        sc      = room.get("comfortScores", {})
        overall = room.get("overallScore", 0.0)
        if not sc:
            continue
        best_sense  = max(sc, key=lambda k: sc[k])
        worst_sense = min(sc, key=lambda k: sc[k])
        if best_sense == worst_sense:
            srt = sorted(sc, key=lambda k: sc[k], reverse=True)
            best_sense, worst_sense = srt[0], srt[-1]
        lines.append(
            "Room: {} | overall={:.2f} | best={}({:.2f}) worst={}({:.2f}) | "
            "thermal={:.2f} visual={:.2f} acoustic={:.2f} spatial={:.2f} olfactory={:.2f} tactile={:.2f}".format(
                name, overall,
                best_sense, sc[best_sense], worst_sense, sc[worst_sense],
                sc.get("thermal", 0), sc.get("visual", 0), sc.get("acoustic", 0),
                sc.get("spatial", 0), sc.get("olfactory", 0), sc.get("tactile", 0),
            )
        )
    return "\n".join(lines) if lines else "(no rooms found)"


def _preprocess_conflicts(conflicts_json):
    if not conflicts_json:
        return "not run"
    try:
        data = _json.loads(conflicts_json)
    except Exception:
        return conflicts_json
    flagged = data.get("flaggedRooms", [])
    if not flagged:
        return "no conflicts detected"
    lines = []
    for room in flagged:
        name   = room.get("roomName", "unknown")
        senses = []
        for c in room.get("conflicts", []):
            for s in ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]:
                if s in c and s not in senses:
                    senses.append(s)
        lines.append("{}: {}".format(name, ", ".join(senses)))
    return "\n".join(lines)


def _preprocess_suggestions(suggestions_json):
    if not suggestions_json:
        return "not run"
    try:
        data = _json.loads(suggestions_json)
    except Exception:
        return suggestions_json
    improvements = data.get("improvements", [])
    if not improvements:
        return "no suggestions generated"
    lines = []
    for room in improvements:
        name = room.get("roomName", "unknown")
        for s in room.get("suggestions", []):
            lines.append("{} / {}: {}".format(name, s.get("sense", "?"), s.get("suggestion", "")))
    return "\n".join(lines)


def build_respond_node(llm):
    """Return the respond node function, capturing the LLM instance."""

    def respond_node(state):
        # Persona: flat schema (persona_compiler v2) with legacy fallback
        persona_profile  = state.get("persona_profile") or {}
        persona_detected = state.get("persona_detected", "")
        user_name_state  = state.get("user_name", "")

        if persona_profile:
            # Flat persona_compiler v2 schema (always has name/role).
            p_name = persona_profile.get("name") or user_name_state or "User"
            p_role = persona_profile.get("role", "client")
            p_desc = persona_profile.get("description", "")
            p_prio = persona_profile.get("sensory_priorities", [])
            p_sens = persona_profile.get("sensory_sensitivities", [])
            p_wts  = persona_profile.get("comfort_weights", {})
            parts  = [f"{p_name} ({p_role})"]
            if p_desc:
                parts.append(p_desc)
            if p_prio:
                parts.append(f"sensory priorities: {', '.join(p_prio)}")
            if p_sens:
                parts.append(f"sensitivities: {', '.join(p_sens)}")
            if p_wts:
                wt_str = " | ".join(f"{k}={v:.2f}" for k, v in p_wts.items())
                parts.append(f"comfort weights: {wt_str}")
            persona = "; ".join(parts)
        else:
            persona  = persona_detected or "Neutral"
            p_name   = user_name_state or "User"
            p_role   = state.get("user_type", "client")

        layout_id   = state.get("layout_id", "?")
        # action is the unified v4 field (replaces dead comfort_depth)
        depth       = state.get("action", "") or "analyze"
        scores      = state.get("last_scores_json", "")
        conflicts   = state.get("last_conflicts_json", "")
        suggestions = state.get("last_suggestions_json", "")
        raw_prompt  = state.get("raw_prompt", "")
        user_type   = state.get("user_type", "architect")

        # Specialist interpretations from new pipeline
        score_interpretation    = state.get("score_interpretation", "")
        conflict_reasoning      = state.get("conflict_reasoning", "")
        suggestion_critique     = state.get("suggestion_critique", "")
        compare_versions        = state.get("compare_versions_summary", "")
        biophilic_summary       = state.get("biophilic_summary", "")
        persona_comparison      = state.get("persona_comparison_summary", "")
        evaluator_feedback      = state.get("evaluator_feedback", "")

        processed_scores      = _preprocess_scores(scores)
        processed_conflicts   = _preprocess_conflicts(conflicts) if conflicts else "not run"
        processed_suggestions = _preprocess_suggestions(suggestions) if suggestions else "not run"

        layout_diffs = state.get("layout_diffs") or (
            [state.get("layout_diff")] if state.get("layout_diff") else []
        )
        is_edit = depth in _EDIT_ACTIONS

        if is_edit:
            fmt = _FORMAT_EDIT
        elif depth == "full":
            fmt = _FORMAT_FULL
        elif depth == "detect":
            fmt = _FORMAT_DETECT
        else:
            fmt = _FORMAT_ANALYZE

        register_note = register_tone(user_type)

        sections = [
            "User request: " + raw_prompt,
            "Persona: " + persona,
            "Layout ID: " + str(layout_id),
            "Register: " + register_note,
            "",
            "--- FORMAT INSTRUCTIONS (follow exactly) ---",
            fmt,
            "",
            "--- PRE-PROCESSED ROOM DATA (copy scores exactly as shown) ---",
            processed_scores,
            "",
            grounded_facts(scores) or "GROUNDED FACTS: (no scores yet - do not make ranking claims)",
            "",
            "--- CONFLICTS ---",
            processed_conflicts,
            "",
            "--- SUGGESTIONS ---",
            processed_suggestions,
        ]

        # score_interpretation, conflict_reasoning, suggestion_critique are now
        # shown directly in the analysis panel — not fed into this prompt.
        # Respond writes a 2-3 sentence summary from the raw MCP data only.
        if is_edit:
            change_line = _format_changes(layout_diffs)
            sections += ["", "--- WHAT CHANGED (lead with this; may be several edits) ---",
                         change_line or "(an edit was applied to the layout)"]
        if compare_versions:
            sections += ["", "--- VERSION COMPARISON (use for the before-to-after delta) ---", compare_versions]
        if biophilic_summary:
            sections += ["", "--- BIOPHILIC AUDIT ---", biophilic_summary]
        if persona_comparison:
            sections += ["", "--- PERSONA COMPARISON ---", persona_comparison]
        if evaluator_feedback:
            sections += ["", "--- REVISION INSTRUCTION (apply this) ---", evaluator_feedback]

        user_message = "\n".join(sections)

        print("[respond] Generating natural language report...")
        response = call_llm_simple(llm, _SYSTEM_PROMPT, user_message)

        # Resilience: the reasoning model occasionally returns an empty answer
        # (only a <think> block) — both on first pass and during the REVISE loop.
        # Keep a previously-good summary if we have one; otherwise synthesise a
        # correct, data-grounded summary rather than a generic placeholder.
        if not (response or "").strip():
            prior = (state.get("final_response") or "").strip()
            if prior:
                print("[respond] Empty response from LLM — keeping prior summary.")
                response = prior
            else:
                print("[respond] Empty response — using deterministic grounded summary.")
                pp = state.get("persona_profile") or {}
                short_label = (
                    f"{pp.get('name')} ({pp.get('role')})" if pp.get("name") and pp.get("role")
                    else pp.get("name") or user_name_state or "you"
                )
                response = _deterministic_summary(short_label, layout_id, depth, scores, conflicts,
                                                   layout_diffs=layout_diffs, compare_versions=compare_versions)

        return {**state, "final_response": response}

    return respond_node
